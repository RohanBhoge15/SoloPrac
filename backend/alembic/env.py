import os
import sys
from logging.config import fileConfig
from pathlib import Path

# Add the parent directory to sys.path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Import models
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Resolve the SQLAlchemy URL. Precedence:
#   1. $MIGRATION_DATABASE_URL env var
#   2. $DATABASE_URL env var (legacy)
#   3. The app's own settings.MIGRATION_DATABASE_URL — the OWNER/SUPERUSER URL.
#      Schema DDL must run as the table owner; the runtime URL now connects as
#      soloprac_app (a non-owner role subject to RLS) and would fail on ALTER
#      TABLE / CREATE TABLE. Never migrate through the runtime role.
#   4. The alembic.ini fallback (placeholder only).
database_url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not database_url:
    try:
        from app.config import get_settings

        database_url = get_settings().MIGRATION_DATABASE_URL
    except Exception:
        database_url = config.get_main_option("sqlalchemy.url")
# Belt-and-braces: if the resolved URL is still using the sync `postgresql://`
# scheme, upgrade it to the async driver so create_async_engine works.
if database_url and database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # The URL is already fully-formed by the resolver above (see the block near
    # the top of this file). Don't concatenate "+asyncpg" — that produced
    # nonsense like `postgresql://.../soloprac+asyncpg` and made SQLAlchemy
    # fall back to psycopg2 (which isn't installed).
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
