"""E2E: true vector RAG path. Index patient versions into Qdrant, then retrieve
from Qdrant (must NOT fall back to Postgres).

Run inside container:
    docker exec -e PYTHONPATH=/app soloprac-backend python /app/scripts/test_rag_e2e.py
"""

import asyncio
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.tools import retrieve_patient_context
from app.database import migration_engine
from app.models import Doctor, Patient, PatientVersion
from app.services.indexer import index_version


async def main():
    doc_id = uuid.uuid4()
    pat_id = uuid.uuid4()
    v1, v2 = uuid.uuid4(), uuid.uuid4()
    sm = async_sessionmaker(migration_engine, expire_on_commit=False)
    async with sm() as db:
        db.add(
            Doctor(
                id=doc_id,
                email=f"seed_{uuid.uuid4().hex[:8]}@soloprac.test",
                name="Seed Doctor",
                clinic_name="Seed Clinic",
                password_hash="x",
                verification_status="verified",
            )
        )
        db.add(Patient(id=pat_id, doctor_id=doc_id))
        db.add(
            PatientVersion(
                id=v1,
                patient_id=pat_id,
                doctor_id=doc_id,
                version_number=1,
                state_jsonb={"demographics": {"name": "Seed Patient"}},
                version_hash="deadbeef",
                author="doctor:seed",
                edit_type="manual",
                summary="Diagnosed with hypertension; started amlodipine 5mg OD",
                tags=["diagnosis", "medication"],
            )
        )
        db.add(
            PatientVersion(
                id=v2,
                patient_id=pat_id,
                doctor_id=doc_id,
                version_number=2,
                state_jsonb={"demographics": {"name": "Seed Patient"}},
                version_hash="cafebeef",
                author="doctor:seed",
                edit_type="manual",
                summary="BP improved to 130/82 on follow-up",
                tags=["vitals", "medication"],
            )
        )
        await db.commit()

    # Index both versions into Qdrant (the real arq-worker path, run sync here)
    async with sm() as db:
        from sqlalchemy import select

        patient = (await db.execute(select(Patient).where(Patient.id == pat_id))).scalar_one()
        for vid in (v1, v2):
            ver = (await db.execute(select(PatientVersion).where(PatientVersion.id == vid))).scalar_one()
            pid = await index_version(db, ver, patient, doc_id)
            print(f"indexed {vid} -> qdrant point {pid}")

    # Now retrieve — should hit Qdrant, NOT the Postgres fallback
    out = await retrieve_patient_context(
        patient_id=str(pat_id),
        query="summarize in short crisp points about patient",
        k=5,
        doctor_id=str(doc_id),
    )
    results = out.get("results", [])
    print(f"\nstatus={out.get('status')}  results={len(results)}  fallback={out.get('meta', {}).get('fallback')}")
    for r in results:
        print(f"  [v{r['version_number']} score={r.get('score'):.3f} mod={r['modality']}] {r['summary']}")

    assert out.get("status") == "ok"
    assert len(results) == 2, f"expected 2 Qdrant hits, got {len(results)}"
    assert out.get("meta", {}).get("fallback") is None, "retrieve fell back to Postgres — Qdrant path broken"
    print("\nPASS: true vector RAG works (retrieved from Qdrant, not fallback).")

    # Cleanup
    async with sm() as db:
        await db.execute(delete(PatientVersion).where(PatientVersion.patient_id == pat_id))
        await db.execute(delete(Patient).where(Patient.id == pat_id))
        await db.execute(delete(Doctor).where(Doctor.id == doc_id))
        await db.commit()
    print("Cleaned up.")


if __name__ == "__main__":
    asyncio.run(main())
