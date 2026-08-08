"""DPDP Consent Router — consent management + data erasure for DPDP Act compliance.

Endpoints:
    GET  /patient/me/consent — Get consent status
    PUT  /patient/me/consent — Update consent (grant/revoke)
    DELETE /patient/me — Erase personal data (anonymize PII)
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ConsentRecord, Patient, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patient", tags=["dpdp-consent"])


class ConsentUpdate(BaseModel):
    data_sharing: Optional[bool] = None
    marketing: Optional[bool] = None
    research: Optional[bool] = None


CONSENT_TYPES = ["data_sharing", "marketing", "research"]


async def _get_user_patient_ids(db: AsyncSession, user_id: uuid.UUID):
    """All Patient records belonging to this user (one per doctor they visit)."""
    result = await db.execute(select(Patient.id).where(Patient.user_id == user_id))
    return list(result.scalars().all())


@router.get("/me/consent")
async def get_consent_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get consent status for the current patient (aggregated across clinics)."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    consent_map = {}
    if patient_ids:
        result = await db.execute(select(ConsentRecord).where(ConsentRecord.patient_id.in_(patient_ids)))
        for r in result.scalars().all():
            if r.consent_type not in consent_map:
                consent_map[r.consent_type] = {
                    "granted": r.granted,
                    "purpose": r.purpose,
                    "granted_at": r.granted_at.isoformat() if r.granted_at else None,
                    "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                }

    # Return defaults for missing types
    for ct in CONSENT_TYPES:
        if ct not in consent_map:
            consent_map[ct] = {
                "granted": False,
                "purpose": None,
                "granted_at": None,
                "revoked_at": None,
            }

    return {"consent": consent_map}


@router.put("/me/consent")
async def update_consent(
    body: ConsentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update consent preferences (grant or revoke) for every clinic the user visits."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(
            status_code=404,
            detail="No patient records found — book an appointment first to set consent preferences",
        )

    result = await db.execute(select(Patient).where(Patient.id.in_(patient_ids)))
    patients = result.scalars().all()

    now = datetime.now(timezone.utc)
    updated = []

    for consent_type in CONSENT_TYPES:
        value = getattr(body, consent_type, None)
        if value is None:
            continue

        for patient in patients:
            rec_result = await db.execute(
                select(ConsentRecord).where(
                    ConsentRecord.patient_id == patient.id,
                    ConsentRecord.consent_type == consent_type,
                )
            )
            record = rec_result.scalar_one_or_none()

            if record is None:
                record = ConsentRecord(
                    patient_id=patient.id,
                    doctor_id=patient.doctor_id,
                    consent_type=consent_type,
                    granted=value,
                    granted_at=now if value else None,
                    revoked_at=None if value else now,
                )
                db.add(record)
            else:
                record.granted = value
                if value:
                    record.granted_at = now
                    record.revoked_at = None
                else:
                    record.revoked_at = now

        updated.append(consent_type)

    await db.commit()
    return {"status": "ok", "updated": updated}


@router.delete("/me")
async def erase_personal_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Erase personal data (anonymize PII) per DPDP Act right to erasure.

    Clinical records are preserved for audit trail compliance.
    Personal identifiers are replaced with anonymized hashes.
    """
    now = datetime.now(timezone.utc)
    anonymized_id = hashlib.sha256(f"{user.id}{now.isoformat()}".encode()).hexdigest()[:12]

    # Anonymize User PII
    placeholder_hash = hashlib.sha256(f"deleted_{anonymized_id}".encode()).hexdigest()
    user.name = f"DELETED_USER_{anonymized_id}"
    user.email = f"deleted_{anonymized_id}@anonymized.local"
    user.phone = f"0{anonymized_id}"
    user.phone_hash = placeholder_hash
    user.dob = None
    user.gender = None
    user.address = None
    user.blood_group = None
    user.allergies = None
    user.known_conditions = None
    user.height_cm = None
    user.weight_kg = None
    user.emergency_contact_name = None
    user.emergency_contact_phone = None
    user.insurance_info = None
    user.password_hash = placeholder_hash

    # Anonymize Patient records (demographics in state_jsonb)
    result = await db.execute(select(Patient).where(Patient.user_id == user.id))
    patients = result.scalars().all()
    for patient in patients:
        if patient.head_version and patient.head_version.state_jsonb:
            state = patient.head_version.state_jsonb
            if "demographics" in state:
                state["demographics"]["name"] = f"DELETED_{anonymized_id}"
                state["demographics"]["phone"] = None
                state["demographics"]["email"] = None
                state["demographics"]["address"] = None
                flag_modified(patient.head_version, "state_jsonb")

    # Revoke all consents
    patient_ids = await _get_user_patient_ids(db, user.id)
    if patient_ids:
        result = await db.execute(select(ConsentRecord).where(ConsentRecord.patient_id.in_(patient_ids)))
        consents = result.scalars().all()
        for c in consents:
            c.granted = False
            c.revoked_at = now

    await db.commit()
    logger.info("Personal data erased for user %s (anonymized_id=%s)", user.id, anonymized_id)
    return {
        "status": "ok",
        "message": "Personal data has been anonymized. Clinical records are preserved for audit compliance.",
    }
