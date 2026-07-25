"""Admin Router — doctor verification management.

Endpoints:
  GET    /admin/verifications/pending         — List doctors pending review
  POST   /admin/verifications/{id}/approve    — Approve a doctor
  POST   /admin/verifications/{id}/reject     — Reject a doctor with reason

Access is restricted to soloprac admin accounts (checked via email).
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, AuditLog
from app.schemas import VerificationPending, VerificationAction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_EMAILS = {
    "admin@soloprac.io",
    # Add more admin emails as needed
}


async def _require_admin(
    current_doctor: Doctor = Depends(get_current_doctor),
) -> Doctor:
    """Dependency: ensure the current doctor is a Soloprac admin."""
    if current_doctor.email not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_doctor


@router.get("/verifications/pending")
async def list_pending_verifications(
    admin: Doctor = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all doctors pending verification review."""
    result = await db.execute(
        select(Doctor).where(
            Doctor.verification_status == "pending_verification"
        ).order_by(Doctor.created_at.asc())
    )
    doctors = result.scalars().all()
    return [
        VerificationPending(
            id=d.id,
            email=d.email,
            name=d.name,
            speciality=d.speciality,
            clinic_name=d.clinic_name,
            clinic_address=d.clinic_address,
            phone=d.phone,
            registration_number=d.registration_number,
            license_document_path=d.license_document_path,
            created_at=d.created_at,
        )
        for d in doctors
    ]


@router.post("/verifications/{doctor_id}/approve")
async def approve_doctor(
    doctor_id: uuid.UUID,
    admin: Doctor = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve a doctor's verification request."""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if doctor.verification_status != "pending_verification":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve: status is '{doctor.verification_status}'",
        )

    doctor.verification_status = "verified"
    doctor.verified_at = datetime.now(timezone.utc)
    doctor.rejection_reason = None
    await db.commit()
    await db.refresh(doctor)

    # Audit
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            actor=f"admin:{admin.email}",
            action="write",
            resource_type="doctor_verification",
            payload_jsonb={"action": "approved"},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    logger.info("Doctor %s (%s) verified by admin %s", doctor.name, doctor.email, admin.email)
    return {
        "status": "verified",
        "doctor_id": str(doctor.id),
        "doctor_name": doctor.name,
        "message": "Doctor verified successfully. They will now appear in patient search.",
    }


@router.post("/verifications/{doctor_id}/reject")
async def reject_doctor(
    doctor_id: uuid.UUID,
    body: VerificationAction,
    admin: Doctor = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reject a doctor's verification request with a reason."""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if doctor.verification_status != "pending_verification":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject: status is '{doctor.verification_status}'",
        )

    reason = body.reason or "Verification documents did not meet requirements"
    doctor.verification_status = "rejected"
    doctor.rejection_reason = reason
    doctor.verified_at = None
    await db.commit()
    await db.refresh(doctor)

    # Audit
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            actor=f"admin:{admin.email}",
            action="write",
            resource_type="doctor_verification",
            payload_jsonb={"action": "rejected", "reason": reason},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    logger.info("Doctor %s (%s) rejected by admin %s: %s", doctor.name, doctor.email, admin.email, reason)
    return {
        "status": "rejected",
        "doctor_id": str(doctor.id),
        "doctor_name": doctor.name,
        "reason": reason,
        "message": "Verification rejected. The doctor can resubmit with corrected documents.",
    }
