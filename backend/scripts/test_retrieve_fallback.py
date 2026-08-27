"""Test: retrieve_patient_context must ground on real Postgres versions when
Qdrant has no vectors for the patient.

Run inside the backend container (code is bind-mounted):
    docker exec soloprac-backend python /app/scripts/test_retrieve_fallback.py
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.tools import retrieve_patient_context
from app.database import migration_engine
from app.models import Doctor, Patient, PatientVersion


async def main():
    doc_id = uuid.uuid4()
    pat_id = uuid.uuid4()
    v1_id = uuid.uuid4()
    v2_id = uuid.uuid4()

    # ── Seed via the OWNER role so RLS doesn't block inserts ──
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
                id=v1_id,
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
                id=v2_id,
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
    print(f"Seeded doctor={doc_id} patient={pat_id} with 2 versions")

    # ── Call the real tool — Qdrant has no vectors for this patient ──
    out = await retrieve_patient_context(
        patient_id=str(pat_id),
        query="summarize in short crisp points about patient",
        k=5,
        doctor_id=str(doc_id),
    )

    results = out.get("results", [])
    print(f"\nstatus={out.get('status')}  results={len(results)}  fallback={out.get('meta', {}).get('fallback')}")
    for r in results:
        print(f"  [v{r['version_number']} · {r['timestamp'][:10]}] ({r['modality']}) {r['summary']}")

    assert out.get("status") == "ok", f"unexpected status: {out}"
    assert len(results) == 2, f"expected 2 grounded versions, got {len(results)}"
    assert out.get("meta", {}).get("fallback") == "postgres_versions"
    # Citations must be present and reference real version numbers
    cites = out.get("citations", [])
    assert len(cites) == 2 and cites[0]["version_number"] in (1, 2)
    print("\nPASS: retrieval grounded on real Postgres versions with citations.")

    # ── Cleanup (owner role bypasses RLS) ──
    from sqlalchemy import delete

    async with sm() as db:
        await db.execute(delete(PatientVersion).where(PatientVersion.patient_id == pat_id))
        await db.execute(delete(Patient).where(Patient.id == pat_id))
        await db.execute(delete(Doctor).where(Doctor.id == doc_id))
        await db.commit()
    print("Cleaned up seed data.")


if __name__ == "__main__":
    asyncio.run(main())
