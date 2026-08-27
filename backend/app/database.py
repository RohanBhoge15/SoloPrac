# Database Setup

import contextlib
import contextvars
import logging
import os

from sqlalchemy import text


def split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into top-level statements, honoring dollar-quoting
    ($$ … $$ / $tag$ … $tag$), single quotes, and line/block comments — so DO
    blocks containing internal semicolons are NOT cut apart.
    """
    stmts: list[str] = []
    cur: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        # Line comment
        if ch == "-" and nxt == "-":
            j = sql.find("\n", i)
            if j == -1:
                break
            i = j + 1
            continue
        # Block comment
        if ch == "/" and nxt == "*":
            j = sql.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue
        # Single-quoted string ('' escape)
        if ch == "'":
            cur.append(ch)
            i += 1
            while i < n:
                if sql[i] == "'" and (i + 1 >= n or sql[i + 1] != "'"):
                    cur.append(sql[i])
                    i += 1
                    break
                cur.append(sql[i])
                i += 1
            continue
        # Dollar-quoted string $$…$$ / $tag$…$tag$
        if ch == "$":
            m = i + 1
            while m < n and (sql[m].isalnum() or sql[m] == "_"):
                m += 1
            if m < n and sql[m] == "$":
                tag = sql[i : m + 1]
                j = sql.find(tag, m + 1)
                cur.append(sql[i : (j + len(tag)) if j != -1 else n])
                i = (j + len(tag)) if j != -1 else n
                continue
        # Statement terminator
        if ch == ";":
            stmts.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur and "".join(cur).strip():
        stmts.append("".join(cur).strip())
    return [s for s in stmts if s and not s.startswith("--")]


from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

# Context variables to carry identity from middleware into get_db():
#   doctor_id — set for doctor/patient portal sessions that resolved a doctor
#   user_id   — set for patient (portal) sessions
_current_doctor_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_doctor_id", default=None)
_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user_id", default=None)


class Base(DeclarativeBase):
    pass


# ── Two engines, two trust levels ──────────────────────────────────────────
# engine:          runtime sessions (soloprac_app) — RLS is ENFORCED here.
# migration_engine: schema work (init_db, Alembic) as the owner/superuser —
#                  RLS does not apply to this role, which is correct for DDL,
#                  but this engine must NEVER back a request handler session.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,  # Recycle connections every hour (prevents stale conns)
    pool_use_lifo=True,  # LIFO: reuse recent connections first (better perf)
    pool_timeout=30,  # Wait max 30s for a connection from pool
)

migration_engine = create_async_engine(
    settings.MIGRATION_DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=2,
    max_overflow=2,
    pool_pre_ping=True,
)


# RLS session variables are reset per-request via get_db() / rls_session().
# set_config(..., true) scopes the value to the current transaction, so it is
# cleared on commit/rollback — the connection pool never leaks identity across
# requests. Connection health is verified via pool_pre_ping.


# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
)


async def set_rls_context(session: AsyncSession, doctor_id=None, user_id=None, *, local: bool = True) -> None:
    """Set the RLS identity session variables on a session.

    Both variables use missing_ok=true in the policies, so an unset variable
    filters rows out instead of raising — anonymous sessions simply see
    nothing on RLS-protected tables.

    Args:
        local: transaction-scoped (True) or session/connection-scoped (False).
        Transaction-scoped vars are auto-cleared at commit/rollback — safe for
        one-shot ad-hoc sessions. Request sessions (get_db) use local=False so
        identity SURVIVES mid-request commits (the app commits then refreshes
        ORM objects); get_db clears the vars in its finally block.
    """
    if doctor_id is not None:
        await session.execute(
            text("SELECT set_config('app.current_doctor_id', :did, :is_local)"),
            {"did": str(doctor_id), "is_local": local},
        )
    if user_id is not None:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, :is_local)"),
            {"uid": str(user_id), "is_local": local},
        )


async def clear_rls_context(session: AsyncSession) -> None:
    """Clear persistent RLS identity so a pooled connection never leaks it to
    the next request. (NULL values are stored as '' — the policies wrap the
    vars in NULLIF, so this is safe.)"""
    try:
        await session.execute(text("SELECT set_config('app.current_doctor_id', NULL, false)"))
        await session.execute(text("SELECT set_config('app.current_user_id', NULL, false)"))
    except Exception:
        pass


async def resolve_doctor_id(session: AsyncSession, *, patient_id=None, version_id=None):
    """Resolve a patient/version id to its owning doctor via the SECURITY
    DEFINER helpers (the only sanctioned RLS bypass for id-only lookups in
    background jobs). Returns uuid string or None."""
    if patient_id is not None:
        row = await session.execute(text("SELECT public.patient_doctor_id(:pid)"), {"pid": patient_id})
    elif version_id is not None:
        row = await session.execute(text("SELECT public.version_doctor_id(:vid)"), {"vid": version_id})
    else:
        return None
    val = row.scalar()
    return str(val) if val is not None else None


async def get_db() -> AsyncSession:
    """FastAPI dependency for runtime database sessions.

    Sets the RLS session variables from the request's identity context, then
    commits on success / rolls back on exception.
    """
    async with async_session_maker() as session:
        try:
            await set_rls_context(
                session,
                doctor_id=_current_doctor_id.get(),
                user_id=_current_user_id.get(),
                local=False,
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Persistent vars survive commits; clear so the pooled connection
            # never carries identity into the next request.
            await clear_rls_context(session)
            await session.close()


@contextlib.asynccontextmanager
async def rls_session(doctor_id=None, user_id=None):
    """Ad-hoc session with RLS identity applied.

    Explicit ids win; otherwise falls back to the request contextvars (so
    code that runs inside a request can simply use rls_session()).
    """
    async with async_session_maker() as session:
        did = doctor_id if doctor_id is not None else _current_doctor_id.get()
        uid = user_id if user_id is not None else _current_user_id.get()
        await set_rls_context(session, doctor_id=did, user_id=uid)
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database - create all tables + enable RLS.

    Runs as the migration (owner/superuser) role so schema DDL and the RLS
    bootstrap (roles, policies, FORCE ROW LEVEL SECURITY) succeed.
    """
    async with migration_engine.begin() as conn:
        # Import models to register them
        from app import models  # noqa

        # Create extensions
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

        # Create pg_trgm index on patient version name for fast ILIKE search
        await conn.execute(
            text("""
            DO $$ BEGIN
                CREATE INDEX IF NOT EXISTS ix_patient_versions_name_trgm
                ON patient_versions
                USING GIN (LOWER(state_jsonb->'demographics'->>'name') gin_trgm_ops);
            EXCEPTION
                WHEN duplicate_table THEN null;
            END $$;
        """)
        )

        # ── Row-Level Security bootstrap ──
        # Roles, grants, FORCE ROW LEVEL SECURITY, policies and the sanctioned
        # SECURITY DEFINER helpers all live in rls_setup.sql (idempotent).
        rls_setup_path = os.path.join(os.path.dirname(__file__), "migrations", "rls_setup.sql")
        try:
            with open(rls_setup_path, "r", encoding="utf-8") as _f:
                rls_sql = _f.read()
            # Strip BEGIN/COMMIT if present (we're inside engine.begin()).
            rls_sql = rls_sql.replace("BEGIN;", "").replace("COMMIT;", "")
            _stmts = split_sql_statements(rls_sql)
            for _stmt in _stmts:
                try:
                    async with conn.begin_nested():
                        await conn.execute(text(_stmt))
                except Exception as _exc:
                    logger.warning(
                        "rls_setup: skipped statement (%s): %.100s...", type(_exc).__name__, _stmt.replace("\n", " ")
                    )
        except Exception as _exc:
            logger.warning("rls_setup.sql failed to load/apply: %s", _exc)

        # ── Schema drift: patients.link_rejected_by_user_ids ──
        # Users who explicitly said "not me" for this walk-in; skip them in
        # future pending-matches responses. Idempotent add.
        await conn.execute(
            text("""
            ALTER TABLE patients
            ADD COLUMN IF NOT EXISTS link_rejected_by_user_ids UUID[] DEFAULT '{}'::UUID[]
        """)
        )

        # ── P1.14 + P1.15 — run the index-hygiene migration ──
        # Idempotent CREATE INDEX IF NOT EXISTS statements. Safe to re-apply
        # every boot; Postgres skips existing indexes in <1ms each.
        #
        # IMPORTANT: In Postgres, a single failing statement inside an active
        # transaction poisons the ENTIRE transaction — every subsequent
        # command errors with `InFailedSQLTransactionError` until we rollback.
        # A plain per-statement try/except doesn't save us. We isolate each
        # statement in its own SAVEPOINT so one missing-table failure only
        # rolls back that statement and leaves the outer transaction usable.
        try:
            import os as _os

            _mig_path = _os.path.join(_os.path.dirname(__file__), "migrations", "p1_indexes.sql")
            if _os.path.isfile(_mig_path):
                with open(_mig_path, "r", encoding="utf-8") as _f:
                    _sql = _f.read()
                # We're already inside `engine.begin()`, so strip the BEGIN/COMMIT
                # from the file to avoid nested transactions.
                _sql = _sql.replace("BEGIN;", "").replace("COMMIT;", "")
                import logging as _logging

                _log_mig = _logging.getLogger(__name__)
                _stmts = [s.strip() for s in _sql.split(";") if s.strip() and not s.strip().startswith("--")]
                for _stmt in _stmts:
                    # Nested transaction = SAVEPOINT under asyncpg. If the
                    # statement fails, `async with` rolls back the SAVEPOINT
                    # only — the outer engine.begin() transaction stays valid.
                    try:
                        async with conn.begin_nested():
                            await conn.execute(text(_stmt))
                    except Exception as _exc:
                        _log_mig.info(
                            "p1_indexes: skipped (%s): %.100s...", type(_exc).__name__, _stmt.replace("\n", " ")
                        )
        except Exception as _exc:
            import logging as _logging

            _logging.getLogger(__name__).warning("p1_indexes migration failed: %s", _exc)

        # ── Schema drift: drop users.phone_hash UNIQUE constraint ──
        # Family members legitimately share a phone number (shared handset,
        # elderly parent). We keep the index for fast lookup but drop
        # uniqueness. Disambiguation is handled via /pending-matches.
        # SAVEPOINT-wrapped: same reason as the p1_indexes block above —
        # a failure here (e.g. constraint already gone) must not poison
        # the outer engine.begin() transaction.
        try:
            async with conn.begin_nested():
                await conn.execute(
                    text("""
                    DO $$
                    DECLARE
                        cname text;
                    BEGIN
                        FOR cname IN
                            SELECT conname FROM pg_constraint
                            WHERE conrelid = 'users'::regclass
                              AND contype = 'u'
                              AND (SELECT attname FROM pg_attribute
                                   WHERE attrelid = 'users'::regclass
                                     AND attnum = ANY(conkey)
                                   LIMIT 1) = 'phone_hash'
                        LOOP
                            EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || quote_ident(cname);
                        END LOOP;
                    END $$;
                """)
                )
        except Exception as _exc:
            import logging as _logging

            _logging.getLogger(__name__).info("users.phone_hash constraint cleanup skipped: %s", _exc)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    await migration_engine.dispose()
