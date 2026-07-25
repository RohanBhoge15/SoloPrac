"""Shared patient lookup helpers for backend auth/search flows.

Provides both strong verification and fallback lookup modes so callers can:
- enforce phone/linked-doctor verification where required, or
- fall back to decrypted phone scan when needed for historic flows.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient, Doctor
from app.services.encryption import decrypt_value

logger = logging.getLogger(__name__)


class PatientLookupError(Exception):
    """Raised when lookup flow cannot safely resolve a patient."""


async def lookup_patient_verified(
    db: AsyncSession,
    phone: str,
    doctor: Doctor,
) -> Optional[Patient]:
    """Return the patient for this phone within the given doctor, if verified.

    Verification requires all of the following:
    - patient row exists
    - doctor_id matches the target doctor
    - phone_enc exists and decrypts to the requested phone

    Returns None if verification cannot be completed.
    """
    if not phone or not doctor or not doctor.id:
        return None

    result = await db.execute(select(Patient).where(Patient.doctor_id == doctor.id))
    candidates = result.scalars().all()

    for patient in candidates:
        if not patient.phone_enc:
            continue
        try:
            plaintext = await decrypt_value(db, patient.phone_enc, "patient-phone")
            if plaintext == phone:
                return patient
        except Exception as exc:
            logger.debug("Patient phone decrypt failed for %s: %s", patient.id, exc)
            continue

    return None


async def lookup_patient_unverified(
    db: AsyncSession,
    phone: str,
    doctor: Doctor | None = None,
    *,
    require_doctor: bool = False,
) -> Patient:
    """Return any matching patient by decrypted phone across the dataset.

    This intentionally allows discovery from the doctor lookup path.
    It preserves prior compatibility for flows that accept older records,
    while still decoupling from global state.
    """
    if not phone:
        raise PatientLookupError("Missing phone")

    result = await db.execute(select(Patient))
    for patient in result.scalars().all():
        if require_doctor and doctor is not None:
            if patient.doctor_id != doctor.id:
                continue
        if not patient.phone_enc:
            continue
        try:
            plaintext = await decrypt_value(db, patient.phone_enc, "patient-phone")
        except Exception as exc:
            logger.debug("Decrypt failed while resolving phone: %s", exc)
            continue

        if plaintext == phone:
            return patient

    raise PatientLookupError("Patient not found for phone")


async def get_patient_or_404(
    db: AsyncSession,
    patient_id: UUID,
    doctor: Doctor,
) -> Patient:
    """Return a patient if it belongs to doctor, else raise 404-style error."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise PatientLookupError("Patient not found")
    return patient
