"""Shared patient lookup helpers for backend auth/search flows.

Provides both strong verification and fallback lookup modes so callers can:
- enforce phone/linked-doctor verification where required, or
- fall back to decrypted phone scan when needed for historic flows.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Doctor, Patient
from app.services.encryption import decrypt_value

logger = logging.getLogger(__name__)


class PatientLookupError(Exception):
    """Raised when lookup flow cannot safely resolve a patient."""


def _phone_hash(phone: str) -> str:
    """SHA256 of the phone number — matches Patient.phone_hash and the value
    computed in patient_auth.PatientAuthService._phone_hash + portal signup."""
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()


async def lookup_patient_verified(
    db: AsyncSession,
    phone: str,
    doctor: Doctor,
) -> Optional[Patient]:
    """Return the patient for this phone within the given doctor, if verified.

    P1.10 — was O(n) with `pgp_sym_decrypt` on every row of a doctor's roster.
    Now O(1): SHA256(phone) is indexed on Patient.phone_hash, so this is a
    single covered-index lookup. We still confirm the encrypted phone matches
    for defence-in-depth — but only on the ≤1 candidate the hash returns.
    Also eager-loads head_version (P1.11) so callers don't fire an extra
    lazy-load round-trip.
    """
    if not phone or not doctor or not doctor.id:
        return None

    result = await db.execute(
        select(Patient)
        .options(selectinload(Patient.head_version))
        .where(
            Patient.doctor_id == doctor.id,
            Patient.phone_hash == _phone_hash(phone),
        )
        .limit(1)
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        return None

    # Belt-and-braces: verify the cipher decrypts to the same phone. Hash
    # collisions on SHA256 are practically impossible, but this guards against
    # an operator forgetting to re-hash after a phone edit.
    if patient.phone_enc:
        try:
            plaintext = await decrypt_value(db, patient.phone_enc, "patient-phone")
            if plaintext != phone:
                logger.warning("phone_hash matched but decrypt mismatched for %s", patient.id)
                return None
        except Exception as exc:
            logger.debug("Patient phone decrypt failed for %s: %s", patient.id, exc)
            return None

    return patient


async def lookup_patient_unverified(
    db: AsyncSession,
    phone: str,
    doctor: Doctor | None = None,
    *,
    require_doctor: bool = False,
) -> Patient:
    """Return any matching patient by phone_hash (indexed, fast).

    P1.10 — dropped the full-table scan + per-row decrypt. Uses the same
    covered index as `lookup_patient_verified`.
    """
    if not phone:
        raise PatientLookupError("Missing phone")

    stmt = select(Patient).options(selectinload(Patient.head_version)).where(Patient.phone_hash == _phone_hash(phone))
    if require_doctor and doctor is not None and doctor.id is not None:
        stmt = stmt.where(Patient.doctor_id == doctor.id)

    result = await db.execute(stmt.limit(1))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise PatientLookupError("Patient not found for phone")
    return patient


async def get_patient_or_404(
    db: AsyncSession,
    patient_id: UUID,
    doctor: Doctor,
) -> Patient:
    """Return a patient if it belongs to doctor, else raise 404-style error.

    P1.11 — eager-load head_version so downstream code (which reads
    demographics from it) doesn't emit a second SELECT.
    """
    result = await db.execute(
        select(Patient)
        .options(selectinload(Patient.head_version))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise PatientLookupError("Patient not found")
    return patient
