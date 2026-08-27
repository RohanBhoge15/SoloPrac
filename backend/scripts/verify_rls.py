"""Verify RLS tenant isolation against the live database.

Runs as soloprac_app (the runtime role), so it only passes if PostgreSQL's
Row-Level Security policies are actually enforced — a superuser/owner
connection would report every cross-doctor row as visible and fail loudly.

Usage:
    docker compose exec backend python /app/scripts/verify_rls.py
"""

import asyncio
import json

from app.database import async_session_maker
from app.services.audit import verify_rls_isolation


async def main() -> None:
    async with async_session_maker() as db:
        report = await verify_rls_isolation(db)
    print(json.dumps(report, indent=2, default=str))
    if report.get("passed"):
        print("\n✅ RLS ISOLATION PASSED — policies are enforced.")
    else:
        print("\n❌ RLS ISOLATION FAILED — see results above.")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
