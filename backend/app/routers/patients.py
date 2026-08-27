# Patients Router — Version-Controlled Patient Records
# Each write mints an immutable version; the chain is content-addressed via SHA256.

import copy
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import AuditLog, Patient, PatientVersion
from app.schemas import (
    DemographicsPatch,
    PatientFieldUpdate,
    PatientRead,
    PatientVersionCreate,
    PatientVersionDiff,
    PatientVersionRead,
    PatientVersionTimeline,
)
from app.services.clinical_significance import clinical_significance_from_tags

logger = logging.getLogger(__name__)

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
    await db.execute(select(Patient).where(Patient.id == patient.id).with_for_update())
    await db.flush()

    # Compute next version number atomically (now safe under row lock)
    result = await db.execute(
        select(func.coalesce(func.max(PatientVersion.version_number), 0)).where(PatientVersion.patient_id == patient.id)
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

        logging.getLogger(__name__).warning("Version audit log write failed (non-blocking): %s", exc)

    return version


# ────────────────────────────────────────────
# Patient CRUD
# ────────────────────────────────────────────


@router.get("/search", response_model=List[dict])
async def search_patients(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Search patients by name, phone, email, etc. across versions.

    Uses pg_trgm index on patient_versions.name for fast ILIKE search.
    """
    q_safe = q.lower()

    # Search via ILIKE on head version demographics (uses pg_trgm index)
    join_query = (
        select(Patient)
        .outerjoin(PatientVersion, PatientVersion.id == Patient.head_version_id)
        .where(Patient.doctor_id == doctor.id)
        .limit(limit)
    )

    # Use ILIKE with wildcards - this will use the pg_trgm GIN index
    name_condition = func.coalesce(PatientVersion.state_jsonb["demographics"]["name"].astext, "").ilike(f"%{q_safe}%")
    phone_condition = func.coalesce(PatientVersion.state_jsonb["demographics"]["phone"].astext, "").ilike(f"%{q_safe}%")
    email_condition = func.coalesce(PatientVersion.state_jsonb["demographics"]["email"].astext, "").ilike(f"%{q_safe}%")

    result = await db.execute(join_query.where(name_condition | phone_condition | email_condition))
    all_patients = result.scalars().all()

    output = []
    for p in all_patients:
        name = f"Patient {str(p.id)[:8]}"
        phone = None
        gender = None
        age = None
        dob_str = None
        if p.head_version_id and p.head_version and p.head_version.state_jsonb:
            demo = p.head_version.state_jsonb.get("demographics", {})
            if isinstance(demo, dict):
                if demo.get("name"):
                    name = demo["name"]
                phone = demo.get("phone")
                gender = demo.get("gender")
                dob_str = demo.get("dob")

        # Compute initials from name
        parts = name.strip().split()
        initials = "".join(w[0].upper() for w in parts[:2]) if parts else "P"

        # Compute age from dob
        if dob_str:
            try:
                from datetime import date as _date

                dob = _date.fromisoformat(dob_str)
                today = _date.today()
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            except (ValueError, TypeError):
                pass

        output.append(
            {
                "id": str(p.id),
                "name": name,
                "initials": initials,
                "age": age,
                "gender": gender,
                "phone": phone,
                "head_version_id": str(p.head_version_id) if p.head_version_id else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
        )
    return output


@router.get("", response_model=List[dict])
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
        # Promote the demographics fields most callers actually want to the
        # top level so pages don't have to reach through `head_version.state_jsonb.demographics.*`
        # every time. WeeklyReport picker, Scratchpad save dialog, and the
        # dashboard's recent-patients list all read a flat `.name` — matches
        # what `/patients/search` already returns.
        top_name: str | None = None
        top_phone: str | None = None
        top_gender: str | None = None
        top_age: int | None = None
        if p.head_version:
            head = {
                "id": str(p.head_version.id),
                "version_number": p.head_version.version_number,
                "state_jsonb": p.head_version.state_jsonb,
                "edit_type": p.head_version.edit_type,
                "summary": p.head_version.summary,
                "timestamp": p.head_version.timestamp.isoformat() if p.head_version.timestamp else None,
            }
            state = p.head_version.state_jsonb or {}
            demo = state.get("demographics") or {}
            if isinstance(demo, dict):
                top_name = demo.get("name")
                top_phone = demo.get("phone")
                top_gender = demo.get("gender")
                dob_str = demo.get("dob")
                if dob_str:
                    try:
                        from datetime import date as _date

                        _dob = _date.fromisoformat(dob_str)
                        _today = _date.today()
                        top_age = _today.year - _dob.year - ((_today.month, _today.day) < (_dob.month, _dob.day))
                    except (ValueError, TypeError):
                        top_age = None
        output.append(
            {
                "id": str(p.id),
                "doctor_id": str(p.doctor_id),
                "user_id": str(p.user_id) if p.user_id else None,
                "head_version_id": str(p.head_version_id) if p.head_version_id else None,
                "consent_for_share": p.consent_for_share,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "name": top_name,
                "phone": top_phone,
                "gender": top_gender,
                "age": top_age,
                "head_version": head,
            }
        )
    return output


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PatientVersionRead)
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=PatientVersionRead)
async def create_patient(
    payload: PatientVersionCreate,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new patient with an initial version (v1).

    If a User account exists with a matching phone number (from demographics),
    the patient is automatically linked to that User.
    """
    # Check for existing User with matching phone (walk-in → user linking)
    existing_user_id = None
    phone = (payload.state_jsonb or {}).get("demographics", {}).get("phone", "")
    if phone:
        from app.models import User
        from app.utils.phone import normalize_phone

        normalized = normalize_phone(phone)
        if len(normalized) == 10:
            # Narrow at the DB level to users whose plaintext phone ends with the
            # normalized 10-digit tail (handles "+91-", "0" prefixes without a
            # phone_hash lookup — signup stores phone_hash of the raw string, so
            # normalized hashes don't align). Bounded to 500 rows as a hard cap
            # so a bad wildcard can never scan the whole users table.
            from app.utils.phone import phones_match

            user_result = await db.execute(select(User).where(User.phone.like(f"%{normalized}")).limit(500))
            for u in user_result.scalars().all():
                if u.phone and phones_match(u.phone, phone):
                    existing_user_id = u.id
                    logger.info(
                        "Auto-linking walk-in patient to existing user %s (phone match)",
                        u.id,
                    )
                    break

    patient = Patient(
        id=uuid.uuid4(),
        doctor_id=doctor.id,
        user_id=existing_user_id,
    )
    db.add(patient)
    await db.flush()

    version = await _mint_version(
        db,
        patient,
        doctor.id,
        state=payload.state_jsonb,
        edit_type=payload.edit_type,
        author=f"doctor:{doctor.id}",
        summary=payload.summary or "Initial patient record",
        tags=payload.tags,
        clinical_significance=payload.clinical_significance
        if payload.clinical_significance is not None
        else clinical_significance_from_tags(payload.tags or []),
    )
    await db.refresh(version)
    return _build_version_number(version)


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(
    patient_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get patient metadata (head pointer, timestamps)."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return PatientRead.model_validate(patient)


@router.get("/{patient_id}/head", response_model=PatientVersionRead)
async def get_patient_head(
    patient_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get current (head) version — the latest patient state."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    _check_patient_ownership(patient, doctor.id)

    if not patient.head_version_id:
        raise HTTPException(status_code=404, detail="Patient has no versions")

    v_result = await db.execute(select(PatientVersion).where(PatientVersion.id == patient.head_version_id))
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
    doctor=Depends(get_current_doctor),
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
    return [PatientVersionTimeline.model_validate(v) for v in versions.scalars().all()]


@router.get("/{patient_id}/at_version/{version_number}", response_model=PatientVersionRead)
async def get_patient_at_version(
    patient_id: uuid.UUID,
    version_number: int,
    doctor=Depends(get_current_doctor),
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
    doctor=Depends(get_current_doctor),
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
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Mint a new version whose state matches an older version (Git revert semantics)."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
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
        db,
        patient,
        doctor.id,
        state=target_version.state_jsonb,
        edit_type="revert",
        author=f"doctor:{doctor.id}",
        parent_version_id=patient.head_version_id,
        summary=f"Reverted to version {version_number}",
        tags=["revert"],
        clinical_significance=clinical_significance_from_tags(["revert"]),
    )
    return _build_version_number(new_version)


@router.patch("/{patient_id}/fields", response_model=PatientVersionRead)
async def patch_patient_fields(
    patient_id: uuid.UUID,
    payload: dict,
    expected_version: int = Query(..., ge=1, description="Optimistic lock — expected current version"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Inline field edit with optimistic locking on version_number (conflict → 409).

    Accepts either:
      { "demographics": { "name": "...", "phone": "..." } }  (structured)
      OR
      { "name": "...", "phone": "..." }                       (flat — legacy UI)
    Only whitelisted demographic fields (see DemographicsPatch) are persisted;
    unknown keys are ignored.
    """
    # Coerce flat payloads into the demographics wrapper so validation is uniform.
    if "demographics" not in payload and any(k in payload for k in DemographicsPatch.model_fields.keys()):
        payload = {"demographics": {k: v for k, v in payload.items() if k in DemographicsPatch.model_fields}}

    try:
        field_updates = PatientFieldUpdate.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid payload: {e}")
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    _check_patient_ownership(patient, doctor.id)

    if not patient.head_version_id:
        raise HTTPException(status_code=400, detail="Patient has no base version yet")

    head_result = await db.execute(select(PatientVersion).where(PatientVersion.id == patient.head_version_id))
    head = head_result.scalar_one_or_none()

    if head.version_number != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: expected v{expected_version}, current v{head.version_number}. Reload and retry.",
            headers={"X-Current-Version": str(head.version_number)},
        )

    new_state = dict(head.state_jsonb or {})

    # Apply validated updates
    updated_fields = []
    if field_updates.demographics is not None:
        demo = field_updates.demographics.model_dump(exclude_none=True)
        if not demo:
            raise HTTPException(status_code=400, detail="No demographic fields to update")

        if "demographics" not in new_state:
            new_state["demographics"] = {}
        new_state["demographics"].update(demo)
        updated_fields = list(demo.keys())

    if not updated_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    new_version = await _mint_version(
        db,
        patient,
        doctor.id,
        state=new_state,
        edit_type="manual",
        author=f"doctor:{doctor.id}",
        parent_version_id=head.id,
        summary=f"Updated {len(updated_fields)} field(s): {', '.join(updated_fields)}",
        tags=updated_fields,
        clinical_significance=clinical_significance_from_tags(updated_fields),
    )

    # Index the new version inline so it is immediately retrievable/groundable
    # (the backend container has the embedding models; the arq worker may not).
    try:
        from app.services.indexer import index_version

        await index_version(db, new_version, patient, doctor.id)
    except Exception as exc:
        logger.warning("Failed to index version %s: %s", new_version.id, exc)

    return _build_version_number(new_version)


@router.post("/{patient_id}/versions/note", response_model=PatientVersionRead)
async def create_status_note_version(
    patient_id: uuid.UUID,
    payload: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new version that *inherits* the current head state and appends a
    free-text clinical status note (e.g. "Patient recovered from hypertension").

    This is the intended "New Version" action for clinical status changes — it
    does NOT edit personal/demographic data. The note is injected into
    ``state_jsonb`` (so it is embedded + retrievable for temporal RAG grounding)
    and recorded in ``summary`` (so it shows in the version chain with a
    citation). The new version carries forward the entire prior state, so a query
    at the new version still sees the inherited history (e.g. prior diagnoses)
    plus the new status.
    """
    note = (payload or {}).get("note", "")
    if isinstance(note, str):
        note = note.strip()
    if not note:
        raise HTTPException(status_code=422, detail="note (non-empty string) is required")

    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    _check_patient_ownership(patient, doctor.id)

    if not patient.head_version_id:
        raise HTTPException(status_code=400, detail="Patient has no base version yet")

    head_result = await db.execute(select(PatientVersion).where(PatientVersion.id == patient.head_version_id))
    head = head_result.scalar_one_or_none()
    if not head:
        raise HTTPException(status_code=400, detail="Patient head version not found")

    # Deep-copy the prior state so the new version inherits everything.
    new_state = copy.deepcopy(head.state_jsonb or {})

    # Maintain a provenance list of status notes + a "latest" pointer.
    status_notes = list(new_state.get("status_notes") or [])
    if not isinstance(status_notes, list):
        status_notes = [str(status_notes)]
    status_notes.append(note)
    new_state["status_notes"] = status_notes
    new_state["status_note"] = note

    new_version = await _mint_version(
        db,
        patient,
        doctor.id,
        state=new_state,
        edit_type="status_update",
        author=f"doctor:{doctor.id}",
        parent_version_id=head.id,
        summary=note,
        tags=["status_update"],
        clinical_significance=0.0,
    )

    # Index the new version inline so it is immediately retrievable/groundable.
    try:
        from app.services.indexer import index_version

        await index_version(db, new_version, patient, doctor.id)
    except Exception as exc:
        logger.warning("Failed to index status-note version %s: %s", new_version.id, exc)

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
    Body: { name, phone (optional), email (optional), dob (optional YYYY-MM-DD),
            gender (optional), address (optional) }
    The patient is created with a v1 version and owned by this doctor.

    If a User already exists whose phone matches, we auto-link ONLY when the
    match is strong (phone + dob or phone + fuzzy-name). Weak matches are
    left unlinked and appear on the User's /pending-matches list so they can
    claim/reject themselves — the doctor never has to disambiguate.
    """
    name = body.get("name", "").strip()
    phone = body.get("phone", "").strip()
    email = body.get("email", "").strip()
    dob = (body.get("dob") or "").strip()
    gender = (body.get("gender") or "").strip()
    address = (body.get("address") or "").strip()

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

    # Build demographics up front so the reverse-matcher can compare dob/name.
    demographics = {
        "name": name,
        "phone": phone or None,
        "email": email or None,
    }
    if dob:
        demographics["dob"] = dob
    if gender:
        demographics["gender"] = gender
    if address:
        demographics["address"] = address

    # Auto-link ONLY on strong matches. Weak matches (phone-only, different
    # dob/name) go on the User's pending list where they can self-claim.
    linked_user_id = None
    if phone:
        from app.services.linking import find_user_for_walkin

        candidate_user, is_strong = await find_user_for_walkin(db, phone, demographics)
        if candidate_user and is_strong:
            linked_user_id = candidate_user.id
            logger.info(
                "Manual walk-in strong-linked to existing user %s",
                candidate_user.id,
            )
        elif candidate_user:
            logger.info(
                "Manual walk-in weakly matches user %s — will surface as pending",
                candidate_user.id,
            )

    patient = Patient(
        doctor_id=doctor.id,
        user_id=linked_user_id,
        phone_enc=phone_enc,
        email_enc=email_enc,
    )
    db.add(patient)
    await db.flush()

    # Mint v1 version
    initial_state = {
        "demographics": demographics,
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
        clinical_significance=clinical_significance_from_tags(["demographics"]),
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
