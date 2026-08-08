# Database Setup

import contextvars

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Context variable to carry doctor_id from middleware into get_db()
_current_doctor_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_doctor_id", default=None)


class Base(DeclarativeBase):
    pass


# Create async engine with tuned pool settings
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


# RLS session variable is reset per-request via get_db() context manager.
# The connection pool "checkin" event is incompatible with asyncpg
# (which doesn't expose a synchronous cursor). Instead, each get_db()
# call sets app.current_doctor_id at the start and the session is closed
# at the end, so there is no cross-request leakage.
# Connection health is verified via pool_pre_ping.
# This is the correct approach for asyncpg connections.


# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency for database sessions.

    Sets the RLS session variable on the actual session the route handler uses,
    then commits on success / rolls back on exception.

    Callers should NOT call commit() themselves — use this dependency.
    """
    async with async_session_maker() as session:
        try:
            # Set RLS session variable on THIS session (not a separate one)
            doctor_id = _current_doctor_id.get()
            if doctor_id:
                await session.execute(
                    text("SELECT set_config('app.current_doctor_id', :did, true)"),
                    {"did": doctor_id},
                )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database - create all tables + enable RLS."""
    async with engine.begin() as conn:
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

        # ── Row-Level Security: Enforce doctor isolation ──
        # Every patient-bearing table has RLS enabled with the policy:
        #   USING (doctor_id = current_setting('app.current_doctor_id')::uuid)
        # This ensures even a buggy query cannot leak data across doctors.
        rls_tables = [
            "patients",
            "patient_versions",
            "prescription_boxes",
            "invoices",
            "certificates",
            "appointments",
            "risk_alerts",
            "patient_notifications",
            "image_comparisons",
            "report_verifications",
        ]
        for table_name in rls_tables:
            # Enable RLS on the table (idempotent)
            await conn.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
            # Create policy only if it doesn't exist (idempotent)
            await conn.execute(
                text(f"""
                DO $$ BEGIN
                    CREATE POLICY tenant_isolation ON {table_name}
                    FOR ALL
                    USING (doctor_id = current_setting('app.current_doctor_id')::uuid);
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """)
            )

        # Special case: audit_log has doctor_id as FK
        await conn.execute(text("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY"))
        await conn.execute(
            text("""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation ON audit_log
                FOR ALL
                USING (doctor_id = current_setting('app.current_doctor_id')::uuid);
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        )

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
