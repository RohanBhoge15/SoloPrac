# Patients Router — Version-Controlled Patient Records
# Each write mints an immutable version; the chain is content-addressed via SHA256.

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Patient, PatientVersion, EDIT_TYPE_CHOICES
from app.schemas import (
    PatientCreate, PatientRead, PatientVersionCreate, PatientVersionRead,
    PatientVersionTimeline, PatientVersionDiff,
)
from app.dependencies import get_current_doctor
from app.models import AuditLog

router = APIRouter()


def _check_patient_ownership(patient: Patient | None, doctor_id: uuid.UUID) -> None:
    """Raise 404 if patient doesn't belong to the doctor."""
    if not patient or patient.doctor_id != doctor_id:
        raise HTTPException(status_code=404, detail="Patient not found")


def _build_version_number(db_version) -> PatientVersionRead:
    return PatientVersionRead.model_validate(db_version)


# ────────────────────────────────────────────
# Version Minting (Internal helper)
# ────────────────────────────────────────────

async def _mint_version(
    db: AsyncSession,
    patient: Patient,
    doctor_id: uuid.UUID,
    state: dict,
    edit_type: str,
    author: str,
    parent_version_id: Optional[uuid.UUID] = None,
    summary: Optional[str] = None,
    tags: Optional[list[str]] = None,
    clinical_significance: float = 0.0,
) -> PatientVersion:
    """Create a new version in the chain and update head pointer.

    Uses SELECT FOR UPDATE on the patient row to prevent concurrent
    version number conflicts.
    """
    # Lock the patient row to prevent concurrent version creation
    # Use SELECT ... FOR UPDATE on Patient row (real locking, not a no-op write)
    await db.execute(
        select(Patient).where(Patient.id == patient.id).with_for_update()
    )
    await db.flush()

    # Compute next version number atomically (now safe under row lock)
    result = await db.execute(
        select(func.coalesce(func.max(PatientVersion.version_number), 0))
        .where(PatientVersion.patient_id == patient.id)
    )
    next_ver = result.scalar() + 1

    version = PatientVersion(
        id=uuid.uuid4(),
        patient_id=patient.id,
        doctor_id=doctor_id,
        parent_version_id=parent_version_id,
        version_number=next_ver,
        state_jsonb=state,
        version_hash=PatientVersion.compute_hash(state),
        author=author,
        edit_type=edit_type,
        summary=summary or f"Version {next_ver}",
        tags=tags or [],
        clinical_significance=clinical_significance,
    )
    db.add(version)
    await db.flush()

    patient.head_version_id = version.id
    await db.flush()

    # ── Version Audit Log (Dev - RLS + audit) ──
    try:
        audit_entry = AuditLog(
            doctor_id=doctor_id,
            patient_id=patient.id,
            actor=author,
            action="write",
            resource_type="version",
            resource_id=version.id,
            payload_jsonb={
                "version_number": next_ver,
                "edit_type": edit_type,
                "parent_version_id": str(parent_version_id) if parent_version_id else None,
                "version_hash": version.version_hash,
                "clinical_significance": clinical_significance,
                "tags": tags or [],
            },
        )
        db.add(audit_entry)
        await db.flush()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Version audit log write failed (non-blocking): %s", exc
        )

    return version


# ────────────────────────────────────────────
# Patient CRUD
# ────────────────────────────────────────────

@router.get("/search", response_model=List[dict])
async def search_patients(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Search patients by name, phone, email, etc. across versions."""
    # Search in head version demographics
    # Use DB-side text search on patient version state_jsonb for better perf
    from sqlalchemy import text
    q_safe = q.lower()
    # Search via jsonb containment + text pattern on head version demographics
    # We join patient -> head_version ON head_version_id = patient_versions.id
    # and search demographics text fields within state_jsonb
    # Use a lateral join approach for PostgreSQL jsonb search
    # First, find all patients for this doctor, then narrow via head version search
    join_query = (
        select(Patient)
        .outerjoin(PatientVersion, PatientVersion.id == Patient.head_version_id)
        .where(Patient.doctor_id == doctor.id)
        .limit(limit)
    )
    # Apply text search on the head version's state_jsonb demographics
    # PostgreSQL 16 supports jsonb_path_exists or jsonb_text_pattern
    # Use a simple ILIKE on demographics extracted as text
    name_condition = func.lower(
        func.coalesce(
            PatientVersion.state_jsonb["demographics"]["name"].astext(), ''
        )
    ).contains(q_safe)
    phone_condition = func.lower(
        func.coalesce(
            PatientVersion.state_jsonb["demographics"]["phone"].astext(), ''
        )
    ).contains(q_safe)
    email_condition = func.lower(
        func.coalesce(
            PatientVersion.state_jsonb["demographics"]["email"].astext(), ''
        )
    ).contains(q_safe)

    result = await db.execute(
        join_query.where(name_condition | phone_condition | email_condition)
    )
    all_patients = result.scalars().all()

    output = []
    for p in all_patients:
        name = f"Patient {str(p.id)[:8]}"
        if p.head_version_id and p.head_version and p.head_version.state_jsonb:
            demo = p.head_version.state_jsonb.get("demographics", {})
            if isinstance(demo, dict) and demo.get("name"):
                name = demo["name"]
        output.append({
            "id": str(p.id),
            "name": name,
            "head_version_id": str(p.head_version_id) if p.head_version_id else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })
    return output


@router.get("/", response_model=List[dict])
async def list_patients(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """List all patients for the current doctor, newest first."""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Patient)
        .options(selectinload(Patient.head_version))
        .where(Patient.doctor_id == doctor.id)
        .order_by(Patient.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    patients = result.scalars().all()
    output = []
    for p in patients:
        head = None
        if p.head_version:
            head = {
                "id": str(p.head_version.id),
                "version_number": p.head_version.version_number,
                "state_jsonb": p.head_version.state_jsonb,
                "edit_type": p.head_version.edit_type,
                "summary": p.head_version.summary,
                "timestamp": p.head_version.timestamp.isoformat() if p.head_version.timestamp else None,
            }
        output.append({
            "id": str(p.id),
            "doctor_id": str(p.doctor_id),
            "user_id": str(p.user_id) if p.user_id else None,
            "head_version_id": str(p.head_version_id) if p.head_version_id else None,
            "consent_for_share": p.consent_for_share,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "head_version": head,
        })
    return output


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=PatientVersionRead)
async def create_patient(
    payload: PatientVersionCreate,
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new patient with an initial version (v1)."""
    patient = Patient(
        id=uuid.uuid4(),
        doctor_id=doctor.id,
    )
    db.add(patient)
    await db.flush()

    version = await _mint_version(
        db, patient, doctor.id,
        state=payload.state_jsonb,
        edit_type=payload.edit_type,
        author=f"doctor:{doctor.id}",
        summary=payload.summary or "Initial patient record",
        tags=payload.tags,
        clinical_significance=payload.clinical_significance or 1.0,
    )
    await db.refresh(version)
    return _build_version_number(version)


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(
    patient_id: uuid.UUID,
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get patient metadata (head pointer, timestamps)."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return PatientRead.model_validate(patient)


@router.get("/{patient_id}/head", response_model=PatientVersionRead)
async def get_patient_head(
    patient_id: uuid.UUID,
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get current (head) version — the latest patient state."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    _check_patient_ownership(patient, doctor.id)

    if not patient.head_version_id:
        raise HTTPException(status_code=404, detail="Patient has no versions")

    v_result = await db.execute(
        select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
    )
    version = v_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=500, detail="Head version pointer broken — contact support")

    # Optional tamper check during retrieval
    if not version.verify_hash():
        raise HTTPException(status_code=500, detail="Data integrity check failed — version hash mismatch")

    return _build_version_number(version)


@router.get("/{patient_id}/timeline", response_model=list[PatientVersionTimeline])
async def get_patient_timeline(
    patient_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Ordered version history (newest first) — lightweight, no full state."""
    versions = await db.execute(
        select(PatientVersion)
        .where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.doctor_id == doctor.id,
        )
        .order_by(desc(PatientVersion.timestamp))
        .limit(limit)
        .offset(offset)
    )
    return [
        PatientVersionTimeline.model_validate(v)
        for v in versions.scalars().all()
    ]


@router.get("/{patient_id}/at_version/{version_number}", response_model=PatientVersionRead)
async def get_patient_at_version(
    patient_id: uuid.UUID,
    version_number: int,
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Reconstruct patient state at a specific historical version."""
    result = await db.execute(
        select(PatientVersion).where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.doctor_id == doctor.id,
            PatientVersion.version_number == version_number,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return _build_version_number(version)


@router.get("/{patient_id}/diff", response_model=PatientVersionDiff)
async def diff_patient_versions(
    patient_id: uuid.UUID,
    v1: int = Query(..., ge=1, description="First version"),
    v2: int = Query(..., ge=1, description="Second version"),
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Field-level diff between two versions — identifies added/removed/modified keys."""
    versions = await db.execute(
        select(PatientVersion).where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.doctor_id == doctor.id,
            PatientVersion.version_number.in_([v1, v2]),
        )
    )
    rows = versions.scalars().all()
    if len(rows) != 2:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    v1_data = rows[0].state_jsonb or {} if rows[0].version_number == v1 else rows[1].state_jsonb or {}
    v2_data = rows[1].state_jsonb or {} if rows[1].version_number == v2 else rows[0].state_jsonb or {}

    all_keys = set(v1_data.keys()) | set(v2_data.keys())
    added, removed, modified = {}, {}, {}

    for key in all_keys:
        if key not in v1_data:
            added[key] = v2_data[key]
        elif key not in v2_data:
            removed[key] = v1_data[key]
        elif v1_data[key] != v2_data[key]:
            modified[key] = {"from": v1_data[key], "to": v2_data[key]}

    return PatientVersionDiff(added=added, removed=removed, modified=modified)


@router.post("/{patient_id}/revert/{version_number}", response_model=PatientVersionRead)
async def revert_patient_to_version(
    patient_id: uuid.UUID,
    version_number: int,
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Mint a new version whose state matches an older version (Git revert semantics)."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    _check_patient_ownership(patient, doctor.id)

    target = await db.execute(
        select(PatientVersion).where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.version_number == version_number,
        )
    )
    target_version = target.scalar_one_or_none()
    if not target_version:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found")

    new_version = await _mint_version(
        db, patient, doctor.id,
        state=target_version.state_jsonb,
        edit_type="revert",
        author=f"doctor:{doctor.id}",
        parent_version_id=patient.head_version_id,
        summary=f"Reverted to version {version_number}",
        tags=["revert"],
        clinical_significance=0.5,
    )
    return _build_version_number(new_version)


@router.patch("/{patient_id}/fields", response_model=PatientVersionRead)
async def patch_patient_fields(
    patient_id: uuid.UUID,
    field_updates: dict,
    expected_version: int = Query(..., ge=1, description="Optimistic lock — expected current version"),
    doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Inline field edit with optimistic locking on version_number (conflict → 409)."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    _check_patient_ownership(patient, doctor.id)

    if not patient.head_version_id:
        raise HTTPException(status_code=400, detail="Patient has no base version yet")

    head_result = await db.execute(
        select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
    )
    head = head_result.scalar_one_or_none()

    if head.version_number != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: expected v{expected_version}, current v{head.version_number}. Reload and retry.",
            headers={"X-Current-Version": str(head.version_number)},
        )

    new_state = dict(head.state_jsonb or {})
    new_state.update(field_updates)
    if not new_state:
        raise HTTPException(status_code=400, detail="No fields to update")

    new_version = await _mint_version(
        db, patient, doctor.id,
        state=new_state,
        edit_type="manual",
        author=f"doctor:{doctor.id}",
        parent_version_id=head.id,
        summary=f"Updated {len(field_updates)} field(s): {', '.join(field_updates.keys())}",
        tags=list(field_updates.keys()),
        clinical_significance=0.3,
    )
    return _build_version_number(new_version)


# ────────────────────────────────────────────
# Manual Patient Creation (walk-in, no app user)
# ────────────────────────────────────────────
from app.models import PatientVersion as _PV
from app.services.encryption import encrypt_value


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def create_patient_manual(
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Manually create a patient record under the current doctor.

    Used for walk-in patients who don't use the patient portal.
    Body: { name, phone (optional), email (optional) }
    The patient is created with a v1 version and owned by this doctor.
    No User record is created — the patient exists only in this clinic's scope.
    """
    name = body.get("name", "").strip()
    phone = body.get("phone", "").strip()
    email = body.get("email", "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Patient name is required")

    # Encrypt PII if provided
    phone_enc = None
    email_enc = None
    if phone:
        try:
            phone_enc = await encrypt_value(db, phone, "patient-phone")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to encrypt phone: {exc}")
    if email:
        try:
            email_enc = await encrypt_value(db, email, "patient-email")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to encrypt email: {exc}")

    patient = Patient(
        doctor_id=doctor.id,
        user_id=None,  # not an app user
        phone_enc=phone_enc,
        email_enc=email_enc,
    )
    db.add(patient)
    await db.flush()

    # Mint v1 version
    initial_state = {
        "demographics": {
            "name": name,
            "phone": phone or None,
            "email": email or None,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    version = _PV(
        patient_id=patient.id,
        doctor_id=doctor.id,
        version_number=1,
        state_jsonb=initial_state,
        version_hash=_PV.compute_hash(initial_state),
        author=f"doctor:{doctor.id}",
        edit_type="manual",
        summary=f"Manual registration: {name}",
        tags=["demographics"],
        clinical_significance=0.0,
    )
    db.add(version)
    await db.flush()

    patient.head_version_id = version.id
    await db.commit()
    await db.refresh(patient)

    # Audit log
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            actor=f"doctor:{doctor.id}",
            action="write",
            resource_type="patient",
            resource_id=patient.id,
            payload_jsonb={"method": "manual_registration"},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "id": str(patient.id),
        "name": name,
        "has_phone": bool(phone),
        "has_email": bool(email),
        "message": "Patient created — no app user linked",
    }