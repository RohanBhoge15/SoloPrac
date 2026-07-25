"""Invoice Router — auto-generate invoice number, calculate totals, PDF.

Endpoints:
  POST   /patients/{id}/invoices — Generate new invoice
  GET    /patients/{id}/invoices — List invoices for a patient
  GET    /invoices/{id} — Get invoice detail
  GET    /invoices/{id}/pdf — Download invoice PDF
  PATCH  /invoices/{id}/status — Mark paid/cancelled
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient, Invoice, AuditLog
from app.services.pdf_generator import pdf_generator
from app.services.notification_generator import generate_and_dispatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}/invoices", tags=["invoices"])


def _generate_invoice_number() -> str:
    """Generate unique invoice number: INV-YYYY-NNNN"""
    now = datetime.now(timezone.utc)
    return f"INV-{now.year}-{uuid.uuid4().hex[:4].upper()}"


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    patient_id: uuid.UUID,
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new invoice with auto-generated number and PDF."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    items = body.get("items", [])
    subtotal = body.get("subtotal", 0.0)
    tax = body.get("tax", 0.0)
    total = body.get("total", subtotal + tax)
    status_val = body.get("status", "pending")
    payment_method = body.get("payment_method")
    notes = body.get("notes", "")

    # Generate invoice number
    invoice_number = _generate_invoice_number()

    # Generate PDF with dynamic clinic branding
    try:
        pdf_path = await pdf_generator.generate_invoice(
            patient_name=body.get("patient_name", "Patient"),
            invoice_number=invoice_number,
            items=body.get("items", []),
            subtotal=subtotal,
            tax=tax,
            total=total,
            status=status_val,
            notes=notes,
            db=db,
            doctor_id=doctor.id,
        )
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc)
        pdf_path = None

    # Store in DB
    inv = Invoice(
        id=uuid.uuid4(),
        patient_id=patient_id,
        doctor_id=doctor.id,
        appointment_id=body.get("appointment_id"),
        invoice_number=invoice_number,
        items=body.get("items", []),
        subtotal=subtotal,
        tax=tax,
        total=total,
        status=status_val,
        payment_method=payment_method,
        notes=notes,
        pdf_path=pdf_path,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)

    # Audit log (non-blocking, use separate session to avoid rollback conflicts)
    try:
        from app.database import async_session_maker as _audit_session_maker
        async with _audit_session_maker() as audit_db:
            from app.database import _current_doctor_id
            from sqlalchemy import text
            did = str(doctor.id)
            await audit_db.execute(
                text("SELECT set_config('app.current_doctor_id', :did, true)"),
                {"did": did},
            )
            audit = AuditLog(
                doctor_id=doctor.id, patient_id=patient.id,
                actor=f"doctor:{doctor.id}", action="write",
                resource_type="invoice", resource_id=inv.id,
                payload_jsonb={"invoice_number": invoice_number, "total": total},
            )
            audit_db.add(audit)
            await audit_db.commit()
    except Exception:
        pass

    # ── AI Notification to patient ──
    try:
        await generate_and_dispatch(
            db,
            event_type="invoice_generated",
            patient_id=patient.id,
            doctor_id=doctor.id,
            meta={
                "resource_type": "invoice",
                "resource_id": str(inv.id),
                "pdf_url": f"/api/v1/invoices/{inv.id}/pdf" if pdf_path else None,
            },
            patient_name=body.get("patient_name", "Patient"),
            amount=f"₹{total/100:.2f}",
            invoice_number=invoice_number,
        )
    except Exception as exc:
        logger.warning("Invoice notification dispatch failed: %s", exc)

    return {
        "id": str(inv.id),
        "invoice_number": invoice_number,
        "patient_id": str(patient_id),
        "total": total,
        "status": status_val,
        "pdf_path": pdf_path,
        "created_at": inv.generated_at.isoformat() if inv.generated_at else None,
    }


@router.get("/")
async def list_invoices(
    patient_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invoice)
        .join(Patient, Patient.id == Invoice.patient_id)
        .where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
        .order_by(desc(Invoice.generated_at))
        .limit(limit)
    )
    invs = result.scalars().all()
    return [
        {
            "id": str(inv.id),
            "invoice_number": inv.invoice_number,
            "status": inv.status,
            "total": inv.total,
            "generated_at": inv.generated_at.isoformat() if inv.generated_at else None,
            "has_pdf": bool(inv.pdf_path),
        }
        for inv in invs
    ]


@router.get("/{invoice_id}")
async def get_invoice(
    patient_id: uuid.UUID,
    invoice_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {
        "id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "items": inv.items,
        "subtotal": inv.subtotal,
        "tax": inv.tax,
        "total": inv.total,
        "status": inv.status,
        "payment_method": inv.payment_method,
        "notes": inv.notes,
        "pdf_path": inv.pdf_path,
        "generated_at": inv.generated_at.isoformat() if inv.generated_at else None,
        "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
    }


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    patient_id: uuid.UUID,
    invoice_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.doctor_id == doctor.id)
    )
    inv = result.scalar_one_or_none()
    if not inv or not inv.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(inv.pdf_path, media_type="application/pdf", filename=f"invoice_{inv.invoice_number}.pdf")


@router.patch("/{invoice_id}/status")
async def update_invoice_status(
    patient_id: uuid.UUID,
    invoice_id: uuid.UUID,
    status_val: str = Query(..., description="New status: pending|paid|cancelled"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.doctor_id == doctor.id)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if status_val not in ("pending", "paid", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")

    old_status = inv.status
    inv.status = status_val
    if status_val == "paid" and not inv.paid_at:
        inv.paid_at = datetime.now(timezone.utc)
    await db.commit()

    # Audit log
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            actor=f"doctor:{doctor.id}",
            action="write",
            resource_type="invoice",
            resource_id=inv.id,
            payload_jsonb={"old_status": old_status, "new_status": status_val},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    return {"status": status_val, "updated_at": datetime.now(timezone.utc).isoformat()}