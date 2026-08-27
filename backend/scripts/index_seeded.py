"""Index all existing patient versions into Qdrant so the chat demonstrates
true vector RAG (MedCPT + BGE-M3) during the demo, instead of the Postgres
fallback. Seed data is inserted directly (no indexing), so run this after
seed_demo.py.

    docker exec -e PYTHONPATH=/app soloprac-backend python /app/scripts/index_seeded.py
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import migration_engine
from app.models import Patient, PatientVersion
from app.services.indexer import index_version

MigSM = async_sessionmaker(migration_engine, expire_on_commit=False)


async def main():
    async with MigSM() as db:
        versions = (await db.execute(select(PatientVersion))).scalars().all()
        print(f"Found {len(versions)} versions to index")
        for v in versions:
            pat = (await db.execute(select(Patient).where(Patient.id == v.patient_id))).scalar_one()
            pid = await index_version(db, v, pat, v.doctor_id)
            print(f"  indexed v{v.version_number} {pat.id} -> {pid}")
        print("DONE — Qdrant now has the seeded patient records.")


if __name__ == "__main__":
    asyncio.run(main())
