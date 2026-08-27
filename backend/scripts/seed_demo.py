"""Seed the database with demo doctors, users, patients, appointments,
prescriptions, and certificates so testing the UI doesn't require doing every
setup step manually every restart.

Idempotent: skip creating any row whose "logical key" (email for doctors/users,
`{doctor_email}:{patient_name}` for patients) already exists. Safe to re-run.

Run:
    docker compose exec backend python -m scripts.seed_demo

At the end it prints all logins so you can copy-paste into the UI.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Demo clinics are in India; treat seed/local wall-clock times as IST (UTC+5:30).
IST_OFFSET = timedelta(hours=5, minutes=30)
from pathlib import Path
from typing import Optional

# Allow running as either `python scripts/seed_demo.py` or `python -m scripts.seed_demo`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passlib.context import CryptContext
from sqlalchemy import func, select

from app.database import async_session_maker, set_rls_context
from app.models import (
    Appointment,
    Certificate,
    Doctor,
    Patient,
    PatientVersion,
    PrescriptionBox,
    User,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _phone_hash(phone: str) -> str:
    """Match app.services.patient_auth._phone_hash exactly."""
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────
# Data definitions — one flat structure keeps intent readable
# ────────────────────────────────────────────────────────────

DOCTORS = [
    {
        "email": "demo@soloprac.dev",
        "password": "Demo@1234",
        "name": "Dr. Rohan Bhoge",
        "speciality": "General Practice",
        "clinic_name": "Bhoge Family Clinic",
        "clinic_address": "12 MG Road, Pune 411001",
        "pincode": "411001",
        "phone": "+919000000001",
        "registration_number": "MH-12345-2015",
        "state_medical_council": "Maharashtra Medical Council",
        "year_of_registration": 2015,
        "qualification": "MBBS, MD (Internal Medicine)",
        "latitude": 18.5204,
        "longitude": 73.8567,
    },
    {
        "email": "priya@soloprac.dev",
        "password": "Demo@1234",
        "name": "Dr. Priya Menon",
        "speciality": "Pediatrics",
        "clinic_name": "Menon Child Care",
        "clinic_address": "45 Brigade Road, Bengaluru 560025",
        "pincode": "560025",
        "phone": "+919000000002",
        "registration_number": "KA-98765-2018",
        "state_medical_council": "Karnataka Medical Council",
        "year_of_registration": 2018,
        "qualification": "MBBS, DCH",
        "latitude": 12.9716,
        "longitude": 77.5946,
    },
]

USERS = [
    {
        "email": "arjun@demo.dev",
        "password": "Demo@1234",
        "name": "Arjun Patel",
        "phone": "+919812345601",
        "gender": "male",
        "dob_years_ago": 34,
        "blood_group": "O+",
        "allergies": "Penicillin",
        "known_conditions": "Hypertension (controlled with amlodipine)",
    },
    {
        "email": "sneha@demo.dev",
        "password": "Demo@1234",
        "name": "Sneha Iyer",
        "phone": "+919812345602",
        "gender": "female",
        "dob_years_ago": 29,
        "blood_group": "A+",
        "allergies": None,
        "known_conditions": "Migraine",
    },
    {
        "email": "raj@demo.dev",
        "password": "Demo@1234",
        "name": "Rajesh Kumar",
        "phone": "+919812345603",
        "gender": "male",
        "dob_years_ago": 58,
        "blood_group": "B+",
        "allergies": "Sulfa drugs",
        "known_conditions": "Type 2 Diabetes, Hyperlipidemia",
    },
]

# Each patient links to a doctor by index into DOCTORS and optionally a user
# by index into USERS (None = walk-in only, no linked account).
PATIENTS = [
    {
        "doctor_idx": 0,
        "user_idx": 0,
        "demographics": {
            "name": "Arjun Patel",
            "phone": "+919812345601",
            "age": 34,
            "gender": "male",
            "address": "Kothrud, Pune",
        },
        "vitals": {
            "bp": "132/86",
            "bp_systolic": 132,
            "bp_diastolic": 86,
            "pulse": 78,
            "temp_c": 36.9,
            "weight_kg": 78,
        },
        "diagnosis": "Uncontrolled hypertension — likely non-adherence to amlodipine.",
        "diagnoses": ["Hypertension"],
        "medications": [
            {
                "drug": "Amlodipine",
                "strength": "5 mg",
                "frequency": "OD",
                "instructions": "Restart; home BP diary for 2 weeks",
            },
        ],
        "plan": "Restart amlodipine 5 mg OD. Home BP diary for 2 weeks. Recheck in 3 weeks.",
        "followup": {
            "vitals": {"bp": "128/82", "bp_systolic": 128, "bp_diastolic": 82, "pulse": 76, "weight_kg": 77},
            "diagnosis": "Hypertension — adherence improved on amlodipine.",
            "diagnoses": ["Hypertension (improving)"],
            "medications": [
                {
                    "drug": "Amlodipine",
                    "strength": "5 mg",
                    "frequency": "OD",
                    "instructions": "Continue; adherence improved",
                },
            ],
            "plan": "Continue amlodipine 5 mg OD. Recheck in 4 weeks.",
            "summary": "Follow-up: BP improved to 128/82 on amlodipine; adherence better.",
            "tags": ["seed", "followup"],
        },
    },
    {
        "doctor_idx": 0,
        "user_idx": 1,
        "demographics": {
            "name": "Sneha Iyer",
            "phone": "+919812345602",
            "age": 29,
            "gender": "female",
            "address": "Baner, Pune",
        },
        "vitals": {"bp": "112/74", "bp_systolic": 112, "bp_diastolic": 74, "pulse": 82, "temp_c": 37.1},
        "diagnosis": "Recurrent migraine with aura — 3rd episode in 6 weeks.",
        "diagnoses": ["Migraine with aura"],
        "medications": [
            {
                "drug": "Sumatriptan",
                "strength": "50 mg",
                "frequency": "PRN",
                "instructions": "For acute migraine attacks",
            },
        ],
        "plan": "Trigger diary. Consider sumatriptan for acute attacks. Neurology referral if >2/month persists.",
    },
    {
        "doctor_idx": 0,
        "user_idx": 2,
        "demographics": {
            "name": "Rajesh Kumar",
            "phone": "+919812345603",
            "age": 58,
            "gender": "male",
            "address": "Aundh, Pune",
        },
        "vitals": {"bp": "144/92", "bp_systolic": 144, "bp_diastolic": 92, "pulse": 88, "hba1c": 8.4, "weight_kg": 84},
        "diagnosis": "Poorly controlled T2DM (HbA1c 8.4) + stage-1 hypertension.",
        "diagnoses": ["Type 2 Diabetes", "Hypertension"],
        "medications": [
            {"drug": "Metformin", "strength": "1 g", "frequency": "BD", "instructions": "Increase from 500 mg"},
            {"drug": "Telmisartan", "strength": "40 mg", "frequency": "OD", "instructions": "Add for BP"},
        ],
        "plan": "Increase metformin to 1 g BD. Add telmisartan 40 mg. Renal panel in 4 weeks.",
    },
    # Walk-in only patients (no linked user account) — the India walk-in flow
    {
        "doctor_idx": 0,
        "user_idx": None,
        "demographics": {
            "name": "Kavita Deshmukh",
            "phone": "+919812345604",
            "age": 45,
            "gender": "female",
            "address": "Warje, Pune",
        },
        "vitals": {"bp": "118/76", "bp_systolic": 118, "bp_diastolic": 76, "pulse": 74, "temp_c": 37.4},
        "diagnosis": "Viral URI — day 3. No red flags.",
        "diagnoses": ["Viral upper respiratory infection"],
        "medications": [],
        "plan": "Supportive: paracetamol PRN, warm fluids. Return if fever >5 days or breathing changes.",
    },
    {
        "doctor_idx": 0,
        "user_idx": None,
        "demographics": {
            "name": "Vikram Singh",
            "phone": "+919812345605",
            "age": 62,
            "gender": "male",
            "address": "Kalyani Nagar, Pune",
        },
        "vitals": {"bp": "138/84", "bp_systolic": 138, "bp_diastolic": 84, "pulse": 72, "weight_kg": 71},
        "diagnosis": "Osteoarthritis, both knees. Grade 2 on last X-ray.",
        "diagnoses": ["Osteoarthritis (both knees)"],
        "medications": [
            {
                "drug": "Paracetamol",
                "strength": "500 mg",
                "frequency": "TID",
                "instructions": "Continue; physio 3×/week",
            },
        ],
        "plan": "Continue paracetamol 500 mg TID. Physio 3×/week. Weight loss counseling.",
    },
    {
        "doctor_idx": 1,
        "user_idx": None,
        "demographics": {
            "name": "Aarav Sharma",
            "phone": "+919812345606",
            "age": 6,
            "gender": "male",
            "address": "Indiranagar, Bengaluru",
        },
        "vitals": {"temp_c": 38.6, "pulse": 110, "weight_kg": 22},
        "diagnosis": "Acute otitis media (right ear).",
        "diagnoses": ["Acute otitis media (right)"],
        "medications": [
            {"drug": "Amoxicillin", "strength": "250 mg", "frequency": "TID", "instructions": "×5 days"},
        ],
        "plan": "Amoxicillin 250 mg TID × 5 days. Follow up in 1 week if symptoms persist.",
    },
]

# Appointments — days_from_now can be negative for past visits
APPOINTMENTS = [
    {"patient_idx": 0, "days_from_now": 1, "hour": 10, "minute": 0, "duration_min": 20, "reason": "BP review"},
    {
        "patient_idx": 1,
        "days_from_now": 2,
        "hour": 15,
        "minute": 30,
        "duration_min": 20,
        "reason": "Migraine follow-up",
    },
    {
        "patient_idx": 2,
        "days_from_now": 3,
        "hour": 11,
        "minute": 0,
        "duration_min": 30,
        "reason": "Diabetes review + labs",
    },
    {
        "patient_idx": 3,
        "days_from_now": -1,
        "hour": 9,
        "minute": 30,
        "duration_min": 15,
        "reason": "URI follow-up",
        "status": "completed",
    },
    {
        "patient_idx": 5,
        "days_from_now": 0,
        "hour": 16,
        "minute": 0,
        "duration_min": 20,
        "reason": "Ear infection recheck",
    },
]

# One prescription per patient with a diagnosis+plan (skip the walk-ins)
PRESCRIPTION_TARGETS = [0, 1, 2, 5]  # indexes into PATIENTS

# One certificate for the URI patient
CERTIFICATE_TARGETS = [3]


# ────────────────────────────────────────────────────────────
# Seeding logic
# ────────────────────────────────────────────────────────────


async def _get_or_create_doctor(db, spec: dict) -> tuple[Doctor, bool]:
    result = await db.execute(select(Doctor).where(Doctor.email == spec["email"]))
    existing = result.scalar_one_or_none()
    if existing:
        # Ensure it's verified even if it was created previously in unverified state
        changed = False
        if existing.verification_status != "verified":
            existing.verification_status = "verified"
            existing.verified_at = datetime.now(timezone.utc)
            existing.qualification = existing.qualification or spec.get("qualification")
            changed = True
        return existing, changed

    doctor = Doctor(
        id=uuid.uuid4(),
        email=spec["email"],
        name=spec["name"],
        speciality=spec["speciality"],
        clinic_name=spec["clinic_name"],
        clinic_address=spec["clinic_address"],
        pincode=spec["pincode"],
        phone=spec["phone"],
        registration_number=spec["registration_number"],
        password_hash=pwd_context.hash(spec["password"]),
        verification_status="verified",
        verified_at=datetime.now(timezone.utc),
        state_medical_council=spec.get("state_medical_council"),
        year_of_registration=spec.get("year_of_registration"),
        qualification=spec.get("qualification"),
        settings={
            "notification_preferences": {
                "new_booking": {"in_app": True, "email": False, "sms": False},
                "cancellation": {"in_app": True, "email": False, "sms": False},
                "report_available": {"in_app": True, "email": False, "sms": False},
                "verification_status_changed": {"in_app": True, "email": True, "sms": False},
                "walk_in_registered": {"in_app": True, "email": False, "sms": False},
            },
            "working_hours_json": {
                "mon": [["09:00", "13:00"], ["16:00", "20:00"]],
                "tue": [["09:00", "13:00"], ["16:00", "20:00"]],
                "wed": [["09:00", "13:00"], ["16:00", "20:00"]],
                "thu": [["09:00", "13:00"], ["16:00", "20:00"]],
                "fri": [["09:00", "13:00"], ["16:00", "20:00"]],
                "sat": [["10:00", "14:00"]],
            },
            "default_consult_duration": 20,
            "buffer_minutes_between_consults": 5,
            "patient_booking_enabled": True,
            "auto_confirm_booking": False,
        },
    )
    db.add(doctor)
    if spec.get("latitude") is not None and spec.get("longitude") is not None:
        from sqlalchemy import text as _sa_text

        await db.execute(
            _sa_text(
                "UPDATE doctors SET location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography WHERE id = :id"
            ),
            {"lng": spec["longitude"], "lat": spec["latitude"], "id": str(doctor.id)},
        )
    return doctor, True


async def _get_or_create_user(db, spec: dict) -> tuple[User, bool]:
    result = await db.execute(select(User).where(User.email == spec["email"]))
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    dob = datetime.now(timezone.utc) - timedelta(days=spec["dob_years_ago"] * 365)
    user = User(
        id=uuid.uuid4(),
        email=spec["email"],
        password_hash=pwd_context.hash(spec["password"]),
        name=spec["name"],
        phone=spec["phone"],
        phone_hash=_phone_hash(spec["phone"]),
        dob=dob,
        gender=spec["gender"],
        blood_group=spec.get("blood_group"),
        allergies=spec.get("allergies"),
        known_conditions=spec.get("known_conditions"),
    )
    db.add(user)
    return user, True


async def _mint_initial_version(
    db,
    patient: Patient,
    doctor_id: uuid.UUID,
    state: dict,
    summary: str,
    tags: list[str],
) -> PatientVersion:
    """Inline copy of _mint_version — kept self-contained so this script has
    zero dependencies on FastAPI request-scoped helpers."""
    result = await db.execute(
        select(func.coalesce(func.max(PatientVersion.version_number), 0)).where(PatientVersion.patient_id == patient.id)
    )
    next_ver = (result.scalar() or 0) + 1

    version = PatientVersion(
        id=uuid.uuid4(),
        patient_id=patient.id,
        doctor_id=doctor_id,
        parent_version_id=None,
        version_number=next_ver,
        state_jsonb=state,
        version_hash=PatientVersion.compute_hash(state),
        author=f"seed:{doctor_id}",
        edit_type="manual",
        summary=summary,
        tags=tags,
        clinical_significance=0.5,
    )
    db.add(version)
    await db.flush()
    patient.head_version_id = version.id
    await db.flush()
    return version


async def _find_existing_patient(db, doctor_id: uuid.UUID, name: str) -> Optional[Patient]:
    """Idempotency key for patients: doctor + demographics.name."""
    result = await db.execute(
        select(Patient, PatientVersion)
        .join(PatientVersion, Patient.head_version_id == PatientVersion.id)
        .where(Patient.doctor_id == doctor_id)
    )
    for pat, ver in result.all():
        demo = (ver.state_jsonb or {}).get("demographics", {})
        if demo.get("name") == name:
            return pat
    return None


async def _create_patient(
    db,
    doctor: Doctor,
    user: Optional[User],
    spec: dict,
) -> tuple[Patient, bool]:
    existing = await _find_existing_patient(db, doctor.id, spec["demographics"]["name"])
    if existing:
        return existing, False

    patient = Patient(
        id=uuid.uuid4(),
        doctor_id=doctor.id,
        user_id=user.id if user else None,
    )
    db.add(patient)
    await db.flush()

    state = {
        "demographics": spec["demographics"],
        "vitals": spec.get("vitals", {}),
        "assessment": {
            "diagnosis": spec.get("diagnosis", ""),
            "plan": spec.get("plan", ""),
        },
        "clinical": {
            "diagnoses": spec.get("diagnoses", []),
            "medications": spec.get("medications", []),
        },
    }
    await _mint_initial_version(
        db,
        patient,
        doctor.id,
        state=state,
        summary=spec.get("diagnosis", "Initial patient record"),
        tags=["seed", "initial"],
    )
    # Optional follow-up version so the UI can demonstrate per-version
    # diagnoses / medications / vitals changing as you click Version History.
    if spec.get("followup"):
        fu = spec["followup"]
        fu_state = {
            "demographics": spec["demographics"],
            "vitals": fu.get("vitals", spec.get("vitals", {})),
            "assessment": {
                "diagnosis": fu.get("diagnosis", ""),
                "plan": fu.get("plan", ""),
            },
            "clinical": {
                "diagnoses": fu.get("diagnoses", []),
                "medications": fu.get("medications", []),
            },
        }
        await _mint_initial_version(
            db,
            patient,
            doctor.id,
            state=fu_state,
            summary=fu.get("summary", "Follow-up visit"),
            tags=fu.get("tags", ["seed", "followup"]),
        )
    return patient, True


async def _create_appointment(db, doctor: Doctor, patient: Patient, spec: dict) -> bool:
    # Spec hour/minute are LOCAL (IST) wall-clock. Convert to UTC for storage.
    base_local = (datetime.now(timezone.utc) + IST_OFFSET).date()
    target_local = base_local + timedelta(days=spec["days_from_now"])
    local_dt = datetime(target_local.year, target_local.month, target_local.day, spec["hour"], spec["minute"])
    start = (local_dt - IST_OFFSET).replace(tzinfo=timezone.utc)
    end = start + timedelta(minutes=spec["duration_min"])

    # Idempotency: skip if an appointment exists for the same patient+start
    existing = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor.id,
            Appointment.patient_id == patient.id,
            Appointment.start_at == start,
        )
    )
    if existing.scalar_one_or_none():
        return False

    appt = Appointment(
        id=uuid.uuid4(),
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_at=start,
        end_at=end,
        status=spec.get("status", "confirmed"),
        reason=spec.get("reason", ""),
    )
    db.add(appt)
    # Flush now: the caller re-scopes RLS identity per doctor, and an
    # unflushed row autoflushed later under a DIFFERENT doctor's scope would
    # violate the tenant policy.
    await db.flush()
    return True


async def _create_prescription(db, doctor: Doctor, patient: Patient, spec: dict) -> bool:
    # Idempotency: skip if any prescription already exists for this patient
    existing = await db.execute(select(PrescriptionBox).where(PrescriptionBox.patient_id == patient.id))
    if existing.scalar_one_or_none():
        return False

    rx_jsonb = {
        "diagnosis_short": spec.get("diagnosis", "")[:80],
        "diagnosis": spec.get("diagnosis", ""),
        "medications": [{"name": "Amlodipine", "dose": "5 mg", "frequency": "OD", "duration": "30 days"}]
        if "hypertension" in spec.get("diagnosis", "").lower()
        else [{"name": "Paracetamol", "dose": "500 mg", "frequency": "TID", "duration": "5 days"}],
        "advice": spec.get("plan", ""),
    }
    # PrescriptionBox requires a version_id — attach to the patient's head version.
    if not patient.head_version_id:
        return False
    rx = PrescriptionBox(
        id=uuid.uuid4(),
        version_id=patient.head_version_id,
        doctor_id=doctor.id,
        patient_id=patient.id,
        rx_jsonb=rx_jsonb,
    )
    db.add(rx)
    # Flush now: caller re-scopes RLS identity per doctor (see _create_appointment).
    await db.flush()
    return True


async def _create_certificate(db, doctor: Doctor, patient: Patient, patient_name: str) -> bool:
    existing = await db.execute(select(Certificate).where(Certificate.patient_id == patient.id))
    if existing.scalar_one_or_none():
        return False

    cert = Certificate(
        id=uuid.uuid4(),
        doctor_id=doctor.id,
        patient_id=patient.id,
        cert_type="sick_leave",
        cert_jsonb={
            "reason": "Viral upper respiratory infection",
            "days_off": 2,
            "issued_for": patient_name,
        },
        # Unique across the table — mint a short deterministic-ish code so
        # re-running doesn't collide with a prior seed's certificate.
        verification_code=f"SEED-{uuid.uuid4().hex[:12].upper()}",
        issued_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(cert)
    # Flush now: caller re-scopes RLS identity per doctor (see _create_appointment).
    await db.flush()
    return True


# ────────────────────────────────────────────────────────────
# Orchestration
# ────────────────────────────────────────────────────────────


async def main() -> None:
    log.info("── SoloPrac demo seed ──")

    async with async_session_maker() as db:
        # Doctors
        doctors: list[Doctor] = []
        for spec in DOCTORS:
            doc, created = await _get_or_create_doctor(db, spec)
            doctors.append(doc)
            log.info(f"  [doctor] {'+' if created else '='} {spec['email']} (verified)")
        await db.flush()

        # Users
        users: list[User] = []
        for spec in USERS:
            u, created = await _get_or_create_user(db, spec)
            users.append(u)
            log.info(f"  [user]   {'+' if created else '='} {spec['email']}")
        await db.flush()

        # Patients
        patients: list[Patient] = []
        for spec in PATIENTS:
            doc = doctors[spec["doctor_idx"]]
            user = users[spec["user_idx"]] if spec["user_idx"] is not None else None
            # Scope the shared seed session to this doctor so RLS admits the
            # inserts. local=False (session-scoped): helpers commit mid-flow,
            # which would clear a transaction-scoped var.
            await set_rls_context(db, doctor_id=str(doc.id), local=False)
            pat, created = await _create_patient(db, doc, user, spec)
            patients.append(pat)
            link = f" (linked→{user.email})" if user else " (walk-in)"
            log.info(f"  [patient] {'+' if created else '='} {spec['demographics']['name']}{link}")
        await db.flush()

        # Appointments — pull the display name from the seed spec, not from
        # patient.head_version (that would lazy-load the relationship in an
        # async session and MissingGreenlet crashes the whole thing).
        for spec in APPOINTMENTS:
            pat = patients[spec["patient_idx"]]
            pat_name = PATIENTS[spec["patient_idx"]]["demographics"]["name"]
            doc = next((d for d in doctors if d.id == pat.doctor_id), doctors[0])
            await set_rls_context(db, doctor_id=str(doc.id), local=False)
            created = await _create_appointment(db, doc, pat, spec)
            when = f"day{spec['days_from_now']:+d} {spec['hour']:02d}:{spec['minute']:02d}"
            log.info(f"  [appt]    {'+' if created else '='} {pat_name} @ {when}")
        await db.flush()

        # Prescriptions
        for idx in PRESCRIPTION_TARGETS:
            pat = patients[idx]
            doc = next((d for d in doctors if d.id == pat.doctor_id), doctors[0])
            await set_rls_context(db, doctor_id=str(doc.id), local=False)
            created = await _create_prescription(db, doc, pat, PATIENTS[idx])
            log.info(f"  [rx]      {'+' if created else '='} for {PATIENTS[idx]['demographics']['name']}")

        # Certificates
        for idx in CERTIFICATE_TARGETS:
            pat = patients[idx]
            doc = next((d for d in doctors if d.id == pat.doctor_id), doctors[0])
            await set_rls_context(db, doctor_id=str(doc.id), local=False)
            created = await _create_certificate(db, doc, pat, PATIENTS[idx]["demographics"]["name"])
            log.info(f"  [cert]    {'+' if created else '='} for {PATIENTS[idx]['demographics']['name']}")

        await db.commit()

    # Print the copy-paste credentials
    log.info("")
    log.info("═══════════════════════════════════════════════════════")
    log.info("  DEMO LOGINS  (password same for all: Demo@1234)")
    log.info("═══════════════════════════════════════════════════════")
    log.info("  Doctors (verified) — login at /login:")
    for d in DOCTORS:
        log.info(f"    • {d['email']}  ({d['name']}, {d['speciality']})")
    log.info("")
    log.info("  Users — login at /patient/login:")
    for u in USERS:
        log.info(f"    • {u['email']}  ({u['name']}, phone {u['phone']})")
    log.info("═══════════════════════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
