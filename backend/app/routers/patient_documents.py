"""Patient Documents Timeline — unified view of all patient documents.

Endpoint:
    GET /patients/{patient_id}/documents — All documents cited by version + date
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import (
    Patient, PatientVersion, PrescriptionBox, Invoice, Certificate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["patient-documents"])


@router.get("/{patient_id}/documents")
async def get_patient_documents(
    patient_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get all documents for a patient in chronological order.

    Returns a unified timeline of prescriptions, invoices, certificates,
    and uploaded documents, each cited with version number and date.
    """
    # Verify patient belongs to doctor
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    docs: List[Dict[str, Any]] = []

    # ── Prescriptions ──
    try:
        rx_result = await db.execute(
            select(PrescriptionBox).where(PrescriptionBox.patient_id == patient_id)
            .order_by(PrescriptionBox.created_at.desc())
        )
        for rx in rx_result.scalars().all():
            docs.append({
                "id": str(rx.id),
                "type": "prescription",
                "title": f"Prescription — {rx.diagnosis_short or 'Untitled'}",
                "date": rx.created_at.isoformat() if rx.created_at else None,
                "has_pdf": bool(rx.pdf_path),
                "pdf_url": f"/api/v1/prescriptions/{rx.id}/pdf" if rx.pdf_path else None,
                "version_number": None,
                "metadata": {
                    "diagnosis": rx.diagnosis_short,
                    "medications_count": len(rx.medications) if rx.medications else 0,
                },
            })
    except Exception as exc:
        logger.warning("Failed to load prescriptions for patient %s: %s", patient_id, exc)

    # ── Invoices ──
    try:
        inv_result = await db.execute(
            select(Invoice).where(Invoice.patient_id == patient_id)
            .order_by(Invoice.generated_at.desc())
        )
        for inv in inv_result.scalars().all():
            docs.append({
                "id": str(inv.id),
                "type": "invoice",
                "title": f"Invoice #{inv.invoice_number}",
                "date": inv.generated_at.isoformat() if inv.generated_at else None,
                "has_pdf": bool(inv.pdf_path),
                "pdf_url": f"/api/v1/invoices/{inv.id}/pdf" if inv.pdf_path else None,
                "version_number": None,
                "metadata": {
                    "total": inv.total,
                    "status": inv.status,
                    "payment_method": inv.payment_method,
                },
            })
    except Exception as exc:
        logger.warning("Failed to load invoices for patient %s: %s", patient_id, exc)

    # ── Certificates ──
    try:
        cert_result = await db.execute(
            select(Certificate).where(Certificate.patient_id == patient_id)
            .order_by(Certificate.created_at.desc())
        )
        for cert in cert_result.scalars().all():
            docs.append({
                "id": str(cert.id),
                "type": "certificate",
                "title": f"{cert.cert_type.replace('_', ' ').title()} Certificate",
                "date": cert.created_at.isoformat() if cert.created_at else None,
                "has_pdf": bool(cert.pdf_path),
                "pdf_url": f"/api/v1/certificates/{cert.id}/pdf" if cert.pdf_path else None,
                "version_number": None,
                "metadata": {
                    "verification_code": cert.verification_code,
                },
            })
    except Exception as exc:
        logger.warning("Failed to load certificates for patient %s: %s", patient_id, exc)

    # ── Version-based documents (OCR uploads, voice entries, etc.) ──
    try:
        ver_result = await db.execute(
            select(PatientVersion).where(PatientVersion.patient_id == patient_id)
            .order_by(PatientVersion.created_at.desc())
            .limit(limit)
        )
        for ver in ver_result.scalars().all():
            state = ver.state_jsonb or {}
            doc_info = state.get("document", {})
            if doc_info.get("s3_key"):
                docs.append({
                    "id": str(ver.id),
                    "type": "uploaded_document",
                    "title": doc_info.get("filename", "Uploaded Document"),
                    "date": ver.created_at.isoformat() if ver.created_at else None,
                    "has_pdf": doc_info.get("doc_type") == "prescription" or doc_info.get("mime_type") == "application/pdf",
                    "pdf_url": f"/api/v1/documents/{doc_info.get('doc_id')}/file" if doc_info.get("doc_id") else None,
                    "version_number": ver.version_number,
                    "metadata": {
                        "doc_type": doc_info.get("doc_type"),
                        "doc_format": doc_info.get("doc_format"),
                        "confidence": doc_info.get("confidence"),
                        "edit_type": ver.edit_type,
                        "author": ver.author,
                    },
                })
    except Exception as exc:
        logger.warning("Failed to load versions for patient %s: %s", patient_id, exc)

    # ── Sort by date descending (newest first) ──
    docs.sort(key=lambda d: d.get("date") or "1970-01-01", reverse=True)

    return {
        "documents": docs[:limit],
        "total": len(docs),
    }
