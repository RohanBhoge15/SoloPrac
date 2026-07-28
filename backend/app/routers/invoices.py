"""Invoice Router — simple consultation + medicine invoice.

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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, text

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient, Invoice, AuditLog
from app.services.pdf_generator import pdf_generator
from app.services.notification_generator import generate_and_dispatch
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}/invoices", tags=["invoices"])


def _amount_in_words(amount: int) -> str:
    """Convert integer amount to Indian English words. E.g., 500 -> 'Rupees Five Hundred Only'."""
    if amount == 0:
        return "Rupees Zero Only"

    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _chunk(n: int) -> str:
        if n == 0:
            return ""
        elif n < 20:
            return ones[n]
        elif n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
        else:
            return ones[n // 100] + " Hundred" + (" and " + _chunk(n % 100) if n % 100 else "")

    parts = []
    rupees = amount
    if rupees >= 10000000:
        parts.append(_chunk(rupees // 10000000) + " Crore")
        rupees %= 10000000
    if rupees >= 100000:
        parts.append(_chunk(rupees // 100000) + " Lakh")
        rupees %= 100000
    if rupees >= 1000:
        parts.append(_chunk(rupees // 1000) + " Thousand")
        rupees %= 1000
    if rupees > 0:
        parts.append(_chunk(rupees))

    return "Rupees " + " ".join(parts) + " Only"


async def _generate_invoice_number(db: AsyncSession, doctor_id) -> str:
    """Generate sequential invoice number: INV-YYYY-NNNN."""
    now = datetime.now(timezone.utc)
    year = now.year
    result = await db.execute(
        select(func.count()).select_from(Invoice).where(
            Invoice.doctor_id == doctor_id,
            Invoice.invoice_number.like(f"INV-{year}-%"),
        )
    )
    count = result.scalar() or 0
    return f"INV-{year}-{count + 1:04d}"


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    patient_id: uuid.UUID,
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new invoice with auto-generated number and PDF.

    Request body:
    {
        "consultation_fee": 500,      // required, in rupees
        "medicine_cost": 0,           // optional, default 0
        "payment_method": "cash",     // required: cash|upi|card|insurance
        "notes": ""                   // optional
    }
    """
    # Verify patient belongs to doctor
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get patient name from head version
    patient_name = "Patient"
    if patient.head_version_id:
        from app.models import PatientVersion
        hv_result = await db.execute(
            select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
        )
        hv = hv_result.scalar_one_or_none()
        if hv and hv.state_jsonb:
            patient_name = hv.state_jsonb.get("demographics", {}).get("name", "Patient")

    # Parse amounts
    consultation_fee = body.get("consultation_fee", 0)
    medicine_cost = body.get("medicine_cost", 0)
    payment_method = body.get("payment_method")
    notes = body.get("notes", "")

    if not payment_method:
        raise HTTPException(status_code=400, detail="payment_method is required")

    # Build line items for the PDF
    items = []
    if consultation_fee > 0:
        items.append({"description": "Consultation Fee", "qty": 1, "rate": consultation_fee, "amount": consultation_fee})
    if medicine_cost > 0:
        items.append({"description": "Medicine Cost", "qty": 1, "rate": medicine_cost, "amount": medicine_cost})

    subtotal = consultation_fee + medicine_cost
    total = subtotal  # no GST for solo clinics

    # Generate invoice number
    invoice_number = await _generate_invoice_number(db, doctor.id)

    # Get doctor settings for UPI QR
    doctor_settings = doctor.settings or {}
    upi_id = doctor_settings.get("upi_id", "")

    # Generate PDF
    try:
        pdf_path = await pdf_generator.generate_invoice(
            patient_name=patient_name,
            invoice_number=invoice_number,
            items=items,
            subtotal=subtotal,
            tax=0,
            total=total,
            amount_in_words=_amount_in_words(total),
            payment_method=payment_method,
            upi_id=upi_id if payment_method == "upi" else "",
            status="pending",
            notes=notes,
            db=db,
            doctor_id=doctor.id,
        )
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc)
        pdf_path = None

    # Store in DB (items stored as JSONB)
    inv = Invoice(
        id=uuid.uuid4(),
        patient_id=patient_id,
        doctor_id=doctor.id,
        invoice_number=invoice_number,
        items=items,
        subtotal=subtotal,
        tax=0,
        total=total,
        status="pending",
        payment_method=payment_method,
        notes=notes,
        pdf_path=pdf_path,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)

    # Audit log (non-blocking, separate session)
    try:
        from app.database import async_session_maker as _audit_session_maker
        async with _audit_session_maker() as audit_db:
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

    # AI Notification to patient
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
            patient_name=patient_name,
            amount=f"₹{total:,}",
            invoice_number=invoice_number,
        )
    except Exception as exc:
        logger.warning("Invoice notification dispatch failed: %s", exc)

    return {
        "id": str(inv.id),
        "invoice_number": invoice_number,
        "patient_id": str(patient_id),
        "total": total,
        "status": "pending",
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
            "payment_method": inv.payment_method,
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
        select(Invoice).where(Invoice.id == invoice_id, Invoice.doctor_id == doctor.id)
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

    presigned_url = await storage_service.get_presigned_url("pdfs", inv.pdf_path)
    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate PDF URL")

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=presigned_url)


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
