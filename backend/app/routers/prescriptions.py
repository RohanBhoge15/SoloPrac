"""Prescription Box Router — create, get, list, download PDF, approve to version.

Endpoints:
  POST   /patients/{id}/prescriptions — Create a prescription box
  POST   /prescriptions/{id}/approve — Approve prescription and create patient version
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
from app.services.notification_generator import generate_and_dispatch
from app.services.storage import storage_service

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

    # Generate PDF with dynamic clinic branding
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
            db=db,
            doctor_id=doctor.id,
        )
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc)
        pdf_path = None

    # Ensure patient has a head version before referencing it
    if not patient.head_version_id:
        raise HTTPException(
            status_code=400,
            detail="Patient has no versioned record. Create a patient version first.",
        )

    # Store in DB
    rx = PrescriptionBox(
        id=uuid.uuid4(),
        version_id=patient.head_version_id,
        patient_id=patient.id,
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

    # ── AI Notification to patient ──
    med_names = ", ".join(m.get("drug", "") for m in meds) if meds else diagnosis
    try:
        await generate_and_dispatch(
            db,
            event_type="prescription_issued",
            patient_id=patient.id,
            doctor_id=doctor.id,
            meta={
                "resource_type": "prescription",
                "resource_id": str(rx.id),
                "pdf_url": f"/api/v1/prescriptions/{rx.id}/pdf" if pdf_path else None,
            },
            patient_name=body.get("patient_name", "Patient"),
            doctor_name=doctor.name,
            doctor_speciality=doctor.speciality or "General Practice",
            clinic_name=doctor.clinic_name or "Clinic",
            medications=med_names,
        )
    except Exception as exc:
        logger.warning("Prescription notification dispatch failed: %s", exc)

    return {
        "id": str(rx.id),
        "patient_id": str(patient_id),
        "doctor_id": str(doctor.id),
        "pdf_path": pdf_path,
        "medications": meds,
        "diagnosis": diagnosis,
        "created_at": rx.created_at.isoformat() if rx.created_at else None,
    }


# ── Approval: Create PatientVersion from Prescription ──
# Separate router for the approve endpoint (different prefix)
approve_router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@approve_router.post("/{prescription_id}/approve")
async def approve_prescription(
    prescription_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Approve a prescription and create a new PatientVersion with clinical data.

    This is the human-in-the-loop step: doctor generates a prescription,
    reviews it, then explicitly approves it to become part of the patient record.
    """
    # Fetch prescription
    result = await db.execute(
        select(PrescriptionBox).where(
            PrescriptionBox.id == prescription_id,
            PrescriptionBox.doctor_id == doctor.id,
        )
    )
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Fetch patient
    patient_result = await db.execute(
        select(Patient).where(Patient.id == rx.patient_id, Patient.doctor_id == doctor.id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get current head version state (if exists)
    current_state = {}
    if patient.head_version_id:
        head_result = await db.execute(
            select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
        )
        head = head_result.scalar_one_or_none()
        if head and head.state_jsonb:
            current_state = dict(head.state_jsonb)

    # Build new state from prescription data
    rx_data = rx.rx_jsonb or {}
    diagnosis = rx_data.get("diagnosis", "") or rx_data.get("diagnosis_short", "")
    medications = rx_data.get("medications", [])

    # Update demographics if not present
    if "demographics" not in current_state:
        current_state["demographics"] = {}

    # Update clinical section with prescription data
    if "clinical" not in current_state:
        current_state["clinical"] = {}

    clinical = current_state["clinical"]

    # Add/update diagnoses
    if diagnosis:
        existing_diagnoses = clinical.get("diagnoses", [])
        if isinstance(existing_diagnoses, list):
            if diagnosis not in existing_diagnoses:
                existing_diagnoses.append(diagnosis)
            clinical["diagnoses"] = existing_diagnoses
        else:
            clinical["diagnoses"] = [diagnosis]

    # Add/update medications
    if medications:
        existing_meds = clinical.get("medications", [])
        if isinstance(existing_meds, list):
            # Add new medications (avoid duplicates by drug name)
            existing_drug_names = {m.get("drug", "").lower() for m in existing_meds if isinstance(m, dict)}
            for med in medications:
                if isinstance(med, dict) and med.get("drug", "").lower() not in existing_drug_names:
                    existing_meds.append(med)
            clinical["medications"] = existing_meds
        else:
            clinical["medications"] = medications

    # Create new version via _mint_version
    from app.routers.patients import _mint_version

    new_version = await _mint_version(
        db=db,
        patient=patient,
        doctor_id=doctor.id,
        state=current_state,
        edit_type="manual",
        author=f"doctor:{doctor.id}",
        parent_version_id=patient.head_version_id,
        summary=f"Prescription: {diagnosis}" if diagnosis else "Prescription approved",
        tags=["prescription"] + (["new_diagnosis"] if diagnosis and diagnosis not in clinical.get("diagnoses", [])[:-1] else []),
        clinical_significance=0.7 if diagnosis else 0.3,
    )

    # Link prescription to the new version
    rx.version_id = new_version.id
    await db.commit()

    # Audit log
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            patient_id=patient.id,
            actor=f"doctor:{doctor.id}",
            action="write",
            resource_type="version",
            resource_id=new_version.id,
            payload_jsonb={"prescription_id": str(prescription_id), "diagnosis": diagnosis},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    return {
        "status": "ok",
        "version_id": str(new_version.id),
        "version_number": new_version.version_number,
        "prescription_id": str(prescription_id),
        "message": f"Prescription approved. Patient record updated to v{new_version.version_number}.",
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
        .where(PrescriptionBox.patient_id == patient_id, PrescriptionBox.doctor_id == doctor.id)
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
        select(PrescriptionBox).where(
            PrescriptionBox.id == prescription_id,
            PrescriptionBox.doctor_id == doctor.id,
        )
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
        select(PrescriptionBox).where(
            PrescriptionBox.id == prescription_id,
            PrescriptionBox.doctor_id == doctor.id,
        )
    )
    rx = result.scalar_one_or_none()
    if not rx or not rx.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    
    # Generate presigned URL for S3 access
    presigned_url = await storage_service.get_presigned_url("pdfs", rx.pdf_path)
    if presigned_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=presigned_url)
    
    # Fallback: serve from local filesystem if S3 is unavailable
    import os
    if os.path.isabs(rx.pdf_path) and os.path.exists(rx.pdf_path):
        from fastapi.responses import FileResponse
        return FileResponse(rx.pdf_path, media_type="application/pdf", filename=f"prescription_{prescription_id}.pdf")
    
    raise HTTPException(status_code=404, detail="PDF file not found on storage")
