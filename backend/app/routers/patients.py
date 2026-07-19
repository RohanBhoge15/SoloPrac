# Patients Router — Versioned Patient Records

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Patient, PatientVersion
from app.schemas import (
    PatientVersionCreate,
    PatientVersionRead,
    PatientVersionDiff,
)
from app.dependencies import get_current_doctor

router = APIRouter()
settings = get_settings()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=PatientVersionRead)
async def create_patient(
    patient_data: PatientVersionCreate,
    current_doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new patient with initial version."""
    # Create patient record
    patient = Patient(
        doctor_id=current_doctor.id,
        head_version_id=None,  # will be set after version created
    )
    db.add(patient)
    await db.flush()

    # Create initial version
    version = PatientVersion(
        patient_id=patient.id,
        doctor_id=current_doctor.id,
        parent_version_id=None,
        version_number=1,
        state_jsonb=patient_data.state_jsonb,
        version_hash=PatientVersion.compute_hash(patient_data.state_jsonb),
        author=f"doctor:{current_doctor.id}",
        edit_type=patient_data.edit_type,
        summary=patient_data.summary or "Initial patient record",
        tags=patient_data.tags,
        clinical_significance=patient_data.clinical_significance,
        image_comparison=patient_data.image_comparison,
    )
    db.add(version)
    await db.flush()

    # Update patient head pointer
    patient.head_version_id = version.id
    await db.commit()
    await db.refresh(version)

    return PatientVersionRead.model_validate(version)


@router.get("/{patient_id}", response_model=PatientVersionRead)
async def get_patient_current(
    patient_id: UUID,
    current_doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get current head state of a patient."""
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == current_doctor.id,
        )
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if not patient.head_version_id:
        raise HTTPException(status_code=404, detail="Patient has no versions")

    version_result = await db.execute(
        select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
    )
    version = version_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Head version not found")

    return PatientVersionRead.model_validate(version)


@router.get("/{patient_id}/timeline", response_model=list[PatientVersionRead])
async def get_patient_timeline(
    patient_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get patient version timeline (most recent first)."""
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == current_doctor.id,
        )
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    version_result = await db.execute(
        select(PatientVersion)
        .where(PatientVersion.patient_id == patient_id)
        .order_by(desc(PatientVersion.timestamp))
        .limit(limit)
        .offset(offset)
    )
    versions = version_result.scalars().all()
    return [PatientVersionRead.model_validate(v) for v in versions]


@router.get("/{patient_id}/at_version/{version_number}", response_model=PatientVersionRead)
async def get_patient_at_version(
    patient_id: UUID,
    version_number: int,
    current_doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Reconstruct patient state at a specific version."""
    result = await db.execute(
        select(PatientVersion).where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.version_number == version_number,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return PatientVersionRead.model_validate(version)


@router.get("/{patient_id}/diff", response_model=PatientVersionDiff)
async def diff_patient_versions(
    patient_id: UUID,
    v1: int = Query(..., description="First version number"),
    v2: int = Query(..., description="Second version number"),
    current_doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Field-level diff between two versions."""
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == current_doctor.id,
        )
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    v1_result = await db.execute(
        select(PatientVersion).where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.version_number == v1,
        )
    )
    version1 = v1_result.scalar_one_or_none()

    v2_result = await db.execute(
        select(PatientVersion).where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.version_number == v2,
        )
    )
    version2 = v2_result.scalar_one_or_none()

    if not version1 or not version2:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    # Compute field-level diff
    state1 = version1.state_jsonb or {}
    state2 = version2.state_jsonb or {}
    all_keys = set(state1.keys()) | set(state2.keys())

    added = {}
    removed = {}
    modified = {}

    for key in all_keys:
        val1 = state1.get(key)
        val2 = state2.get(key)
        if key not in state1:
            added[key] = val2
        elif key not in state2:
            removed[key] = val1
        elif val1 != val2:
            modified[key] = {"from": val1, "to": val2}

    return PatientVersionDiff(added=added, removed=removed, modified=modified)


@router.post("/{patient_id}/revert/{version_number}", response_model=PatientVersionRead)
async def revert_patient(
    patient_id: UUID,
    version_number: int,
    current_doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create new version with state from historical version."""
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == current_doctor.id,
        )
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get target version to revert to
    target_result = await db.execute(
        select(PatientVersion).where(
            PatientVersion.patient_id == patient_id,
            PatientVersion.version_number == version_number,
        )
    )
    target_version = target_result.scalar_one_or_none()
    if not target_version:
        raise HTTPException(status_code=404, detail="Target version not found")

    # Get current head version
    head_result = await db.execute(
        select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
    )
    head_version = head_result.scalar_one_or_none()

    # Get next version number
    max_version_result = await db.execute(
        select(func.max(PatientVersion.version_number)).where(
            PatientVersion.patient_id == patient_id
        )
    )
    next_version = (max_version_result.scalar() or 0) + 1

    # Create new version with reverted state
    new_version = PatientVersion(
        patient_id=patient.id,
        doctor_id=current_doctor.id,
        parent_version_id=head_version.id if head_version else None,
        version_number=next_version,
        state_jsonb=target_version.state_jsonb,
        version_hash=PatientVersion.compute_hash(target_version.state_jsonb),
        author=f"doctor:{current_doctor.id}",
        edit_type="revert",
        summary=f"Reverted to version {version_number}",
        tags=["revert"],
        clinical_significance=0.5,
    )
    db.add(new_version)
    await db.flush()

    # Update head pointer
    patient.head_version_id = new_version.id
    await db.commit()
    await db.refresh(new_version)

    return PatientVersionRead.model_validate(new_version)


@router.patch("/{patient_id}/fields", response_model=PatientVersionRead)
async def patch_patient_fields(
    patient_id: UUID,
    field_updates: dict,
    expected_version: int = Query(..., description="Expected current version for optimistic locking"),
    current_doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Inline field edit with optimistic locking on version number."""
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == current_doctor.id,
        )
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get current head version
    head_result = await db.execute(
        select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
    )
    head_version = head_result.scalar_one_or_none()
    if not head_version:
        raise HTTPException(status_code=404, detail="Patient has no versions")

    # Optimistic locking check
    if head_version.version_number != expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"Version conflict. Expected {expected_version}, current is {head_version.version_number}",
        )

    # Merge updates
    new_state = dict(head_version.state_jsonb or {})
    new_state.update(field_updates)

    # Get next version number
    max_version_result = await db.execute(
        select(func.max(PatientVersion.version_number)).where(
            PatientVersion.patient_id == patient_id
        )
    )
    next_version = (max_version_result.scalar() or 0) + 1

    # Create new version
    new_version = PatientVersion(
        patient_id=patient.id,
        doctor_id=current_doctor.id,
        parent_version_id=head_version.id,
        version_number=next_version,
        state_jsonb=new_state,
        version_hash=PatientVersion.compute_hash(new_state),
        author=f"doctor:{current_doctor.id}",
        edit_type="manual",
        summary=f"Updated {len(field_updates)} field(s)",
        tags=list(field_updates.keys()),
        clinical_significance=0.3,
    )
    db.add(new_version)
    await db.flush()

    # Update head pointer
    patient.head_version_id = new_version.id
    await db.commit()
    await db.refresh(new_version)

    return PatientVersionRead.model_validate(new_version)