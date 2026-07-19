"""Certificate Router — create, get, list, download PDF, verify QR.

Endpoints:
  POST   /patients/{id}/certificates — Generate certificate
  GET    /patients/{id}/certificates — List certificates
  GET    /certificates/{id} — Get certificate detail
  GET    /certificates/{id}/pdf — Download certificate PDF
  GET    /certificates/verify/{code} — Public verification endpoint (QR code)
"""

from __future__ import annotations

import uuid
import logging
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient, Certificate, AuditLog
from app.services.pdf_generator import pdf_generator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}/certificates", tags=["certificates"])


def _generate_verification_code() -> str:
    """Generate a short verification code for QR."""
    return "SPC-" + secrets.token_hex(4).upper() + "-" + secrets.token_hex(2).upper()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_certificate(
    patient_id: uuid.UUID,
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Generate a medical certificate with PDF."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    cert_type = body.get("cert_type", "other")
    verification_code = _generate_verification_code()

    # Generate PDF
    pdf_path = None
    try:
        pdf_path = await pdf_generator.generate_certificate(
            patient_name=body.get("patient_name", "Patient"),
            patient_age=body.get("patient_age", 0),
            cert_type=cert_type,
            body=body.get("body", ""),
            recommended_rest=body.get("recommended_rest", ""),
            verification_code=verification_code,
            verify_url=f"/api/v1/certificates/verify/{verification_code}",
        )
    except Exception as exc:
        logger.warning("Certificate PDF generation failed: %s", exc)

    cert = Certificate(
        id=uuid.uuid4(),
        patient_id=patient.id,
        doctor_id=doctor.id,
        cert_type=cert_type,
        cert_jsonb=body,
        pdf_path=pdf_path,
        verification_code=verification_code,
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)

    # Audit
    try:
        audit = AuditLog(
            doctor_id=doctor.id, patient_id=patient.id,
            actor=f"doctor:{doctor.id}", action="write",
            resource_type="certificate", resource_id=cert.id,
            payload_jsonb={"cert_type": cert_type, "has_pdf": bool(pdf_path)},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "id": str(cert.id),
        "cert_type": cert_type,
        "verification_code": verification_code,
        "pdf_path": pdf_path,
        "created_at": cert.issued_at.isoformat() if cert.issued_at else None,
    }


@router.get("/")
async def list_certificates(
    patient_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """List certificates for a patient."""
    result = await db.execute(
        select(Certificate)
        .where(Certificate.patient_id == patient_id, Certificate.doctor_id == doctor.id)
        .order_by(desc(Certificate.issued_at))
    )
    certs = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "cert_type": c.cert_type,
            "verification_code": c.verification_code,
            "has_pdf": bool(c.pdf_path),
            "issued_at": c.issued_at.isoformat() if c.issued_at else None,
        }
        for c in certs
    ]


@router.get("/{certificate_id}")
async def get_certificate(
    patient_id: uuid.UUID,
    certificate_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get a certificate detail."""
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id, Certificate.doctor_id == doctor.id)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return {
        "id": str(cert.id),
        "cert_type": cert.cert_type,
        "cert_jsonb": cert.cert_jsonb,
        "verification_code": cert.verification_code,
        "pdf_path": cert.pdf_path,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
    }


@router.get("/{certificate_id}/pdf")
async def download_certificate_pdf(
    patient_id: uuid.UUID,
    certificate_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Download certificate PDF."""
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id, Certificate.doctor_id == doctor.id)
    )
    cert = result.scalar_one_or_none()
    if not cert or not cert.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(cert.pdf_path, media_type="application/pdf", filename=f"certificate_{cert.cert_type}.pdf")


# ─── Public Verification (no auth required) ───

@router.get("/verify/{verification_code}")
async def verify_certificate(
    verification_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to verify a certificate via QR code."""
    result = await db.execute(
        select(Certificate).where(Certificate.verification_code == verification_code)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Invalid verification code")
    return {
        "valid": True,
        "cert_type": cert.cert_type,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
        "doctor_id": str(cert.doctor_id),
        "message": "Certificate verified — issued by SoloPrac AI",
    }


