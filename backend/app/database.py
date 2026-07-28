# Database Setup

import contextvars
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Context variable to carry doctor_id from middleware into get_db()
_current_doctor_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_doctor_id", default=None
)


class Base(DeclarativeBase):
    pass


# Create async engine with tuned pool settings
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,           # Verify connections before use
    pool_recycle=3600,            # Recycle connections every hour (prevents stale conns)
    pool_use_lifo=True,           # LIFO: reuse recent connections first (better perf)
    pool_timeout=30,              # Wait max 30s for a connection from pool
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
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE INDEX IF NOT EXISTS ix_patient_versions_name_trgm
                ON patient_versions
                USING GIN (LOWER(state_jsonb->'demographics'->>'name') gin_trgm_ops);
            EXCEPTION
                WHEN duplicate_table THEN null;
            END $$;
        """))

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
            await conn.execute(text(f"""
                DO $$ BEGIN
                    CREATE POLICY tenant_isolation ON {table_name}
                    FOR ALL
                    USING (doctor_id = current_setting('app.current_doctor_id')::uuid);
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))

        # Special case: audit_log has doctor_id as FK
        await conn.execute(text("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation ON audit_log
                FOR ALL
                USING (doctor_id = current_setting('app.current_doctor_id')::uuid);
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()