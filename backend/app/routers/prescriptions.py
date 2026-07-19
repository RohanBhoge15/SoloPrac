"""Prescription Box Router — create, get, list, download PDF.

Endpoints:
  POST   /patients/{id}/prescriptions — Create a prescription box
  GET    /patients/{id}/prescriptions — List prescriptions for a patient
  GET    /prescriptions/{id} — Get prescription detail
  GET    /prescriptions/{id}/pdf — Download prescription PDF
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient, PatientVersion, PrescriptionBox, AuditLog
from app.services.pdf_generator import pdf_generator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}/prescriptions", tags=["prescriptions"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_prescription(
    patient_id: uuid.UUID,
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new prescription box and generate PDF."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    meds = body.get("medications", [])
    diagnosis = body.get("diagnosis", "")
    instructions = body.get("instructions", "")
    follow_up = body.get("follow_up", "")

    # Generate PDF
    try:
        pdf_path = await pdf_generator.generate_prescription(
            patient_name=body.get("patient_name", "Patient"),
            patient_age=body.get("patient_age", 0),
            patient_gender=body.get("patient_gender", ""),
            diagnosis=diagnosis,
            medications=meds,
            instructions=instructions,
            follow_up=follow_up,
            doctor_name=doctor.name,
        )
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc)
        pdf_path = None

    # Store in DB
    rx = PrescriptionBox(
        id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        doctor_id=doctor.id,
        rx_jsonb=body,
        pdf_path=pdf_path,
    )
    db.add(rx)
    await db.commit()
    await db.refresh(rx)

    # Audit log
    try:
        audit = AuditLog(
            doctor_id=doctor.id, patient_id=patient.id,
            actor=f"doctor:{doctor.id}", action="write",
            resource_type="prescription", resource_id=rx.id,
            payload_jsonb={"diagnosis": diagnosis, "med_count": len(meds)},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "id": str(rx.id),
        "patient_id": str(patient_id),
        "doctor_id": str(doctor.id),
        "pdf_path": pdf_path,
        "medications": meds,
        "diagnosis": diagnosis,
        "created_at": rx.created_at.isoformat() if rx.created_at else None,
    }


@router.get("/")
async def list_prescriptions(
    patient_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """List all prescriptions for a patient."""
    result = await db.execute(
        select(PrescriptionBox)
        .join(PatientVersion, PatientVersion.id == PrescriptionBox.version_id)
        .join(Patient, Patient.id == PatientVersion.patient_id)
        .where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
        .order_by(desc(PrescriptionBox.created_at))
        .limit(limit)
    )
    rxs = result.scalars().all()
    return [
        {
            "id": str(rx.id),
            "created_at": rx.created_at.isoformat() if rx.created_at else None,
            "has_pdf": bool(rx.pdf_path),
        }
        for rx in rxs
    ]


@router.get("/{prescription_id}")
async def get_prescription(
    patient_id: uuid.UUID,
    prescription_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get a single prescription detail."""
    result = await db.execute(
        select(PrescriptionBox).where(PrescriptionBox.id == prescription_id)
    )
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return {
        "id": str(rx.id),
        "rx_jsonb": rx.rx_jsonb,
        "pdf_path": rx.pdf_path,
        "created_at": rx.created_at.isoformat() if rx.created_at else None,
    }


@router.get("/{prescription_id}/pdf")
async def download_prescription_pdf(
    patient_id: uuid.UUID,
    prescription_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Download prescription PDF."""
    result = await db.execute(
        select(PrescriptionBox).where(PrescriptionBox.id == prescription_id)
    )
    rx = result.scalar_one_or_none()
    if not rx or not rx.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(rx.pdf_path, media_type="application/pdf", filename=f"prescription_{prescription_id}.pdf")
