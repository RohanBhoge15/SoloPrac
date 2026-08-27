"""Hard-reset all demo data so seed_demo.py starts from a clean slate.

Uses migration_engine (owner role) so RLS does not block the TRUNCATE.
Truncates every table in the public schema except alembic_version.
Run inside container:

    docker exec -e PYTHONPATH=/app soloprac-backend python /app/scripts/clear_demo.py
"""

import asyncio

from sqlalchemy import text

from app.database import migration_engine


async def main():
    async with migration_engine.begin() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename != 'alembic_version' "
                "ORDER BY tablename"
            )
        )
        tables = [r[0] for r in rows]
        if not tables:
            print("No tables to truncate.")
            return
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    print(f"TRUNCATE OK — cleared {len(tables)} tables: {', '.join(tables)}")


if __name__ == "__main__":
    asyncio.run(main())
