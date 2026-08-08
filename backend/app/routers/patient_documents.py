"""Patient Documents Timeline — unified view of all patient documents.

Endpoint:
    GET /patients/{patient_id}/documents — All documents cited by version + date
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, get_db
from app.dependencies import get_current_doctor
from app.models import (
    Certificate,
    Invoice,
    Patient,
    PatientVersion,
    PrescriptionBox,
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
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # ─── P1.12 — Parallelize the 4 independent timeline queries ────────────
    # Each fan-out uses its own AsyncSession because a SQLAlchemy AsyncSession
    # can only handle one operation at a time (concurrent .execute() on the
    # same session raises InvalidRequestError). Total wall-clock drops from
    # `sum(4 queries)` to `max(4 queries)` — typically 4x on this endpoint.

    async def _fetch_prescriptions() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with async_session_maker() as s:
                rx_result = await s.execute(
                    select(PrescriptionBox)
                    .where(PrescriptionBox.patient_id == patient_id)
                    .order_by(PrescriptionBox.created_at.desc())
                )
                for rx in rx_result.scalars().all():
                    out.append(
                        {
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
                        }
                    )
        except Exception as exc:
            logger.warning("Failed to load prescriptions for patient %s: %s", patient_id, exc)
        return out

    async def _fetch_invoices() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with async_session_maker() as s:
                inv_result = await s.execute(
                    select(Invoice).where(Invoice.patient_id == patient_id).order_by(Invoice.generated_at.desc())
                )
                for inv in inv_result.scalars().all():
                    out.append(
                        {
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
                        }
                    )
        except Exception as exc:
            logger.warning("Failed to load invoices for patient %s: %s", patient_id, exc)
        return out

    async def _fetch_certificates() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with async_session_maker() as s:
                cert_result = await s.execute(
                    select(Certificate)
                    .where(Certificate.patient_id == patient_id)
                    .order_by(Certificate.created_at.desc())
                )
                for cert in cert_result.scalars().all():
                    out.append(
                        {
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
                        }
                    )
        except Exception as exc:
            logger.warning("Failed to load certificates for patient %s: %s", patient_id, exc)
        return out

    async def _fetch_versions() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with async_session_maker() as s:
                ver_result = await s.execute(
                    select(PatientVersion)
                    .where(PatientVersion.patient_id == patient_id)
                    .order_by(PatientVersion.timestamp.desc())
                    .limit(limit)
                )
                for ver in ver_result.scalars().all():
                    state = ver.state_jsonb or {}
                    doc_info = state.get("document", {})
                    if doc_info.get("s3_key"):
                        out.append(
                            {
                                "id": str(ver.id),
                                "type": "uploaded_document",
                                "title": doc_info.get("filename", "Uploaded Document"),
                                "date": ver.timestamp.isoformat() if ver.timestamp else None,
                                "has_pdf": doc_info.get("doc_type") == "prescription"
                                or doc_info.get("mime_type") == "application/pdf",
                                "pdf_url": f"/api/v1/documents/{doc_info.get('doc_id')}/file"
                                if doc_info.get("doc_id")
                                else None,
                                "version_number": ver.version_number,
                                "metadata": {
                                    "doc_type": doc_info.get("doc_type"),
                                    "doc_format": doc_info.get("doc_format"),
                                    "confidence": doc_info.get("confidence"),
                                    "edit_type": ver.edit_type,
                                    "author": ver.author,
                                },
                            }
                        )
        except Exception as exc:
            logger.warning("Failed to load versions for patient %s: %s", patient_id, exc)
        return out

    rx_docs, inv_docs, cert_docs, ver_docs = await asyncio.gather(
        _fetch_prescriptions(),
        _fetch_invoices(),
        _fetch_certificates(),
        _fetch_versions(),
    )
    docs: List[Dict[str, Any]] = [*rx_docs, *inv_docs, *cert_docs, *ver_docs]

    # ── Sort by date descending (newest first) ──
    docs.sort(key=lambda d: d.get("date") or "1970-01-01", reverse=True)

    return {
        "documents": docs[:limit],
        "total": len(docs),
    }
