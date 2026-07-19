# Patients Router — Version-Controlled Patient Records
# Each write mints an immutable version; the chain is content-addressed via SHA256.

import uuid
from typing import Optional
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

router = APIRouter()


def _check_patient_ownership(patient: Patient, doctor_id: uuid.UUID):
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
    commit: bool = True,
) -> PatientVersion:
    """Create a new version in the chain and update head pointer."""
    # Compute next version number atomically
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

    if commit:
        await db.commit()
    else:
        # caller will commit
        pass

    return version


# ────────────────────────────────────────────
# Patient CRUD
# ────────────────────────────────────────────

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