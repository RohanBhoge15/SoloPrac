"""Calendar Router — appointment CRUD, slot search, working hours config.

Endpoints:
  GET   /calendar/slots?date_from=&date_to=&duration=&prefer_morning=
  POST  /calendar/appointments
  PATCH /calendar/appointments/{id}/reschedule
  POST  /calendar/appointments/{id}/cancel
  GET   /calendar/appointments?date_from=&date_to=&status=
  GET   /calendar/appointments/{id}
  GET   /calendar/working-hours
  PUT   /calendar/working-hours
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient, Appointment
from app.services.calendar_service import (
    find_available_slots, create_appointment, reschedule_appointment,
    cancel_appointment, list_appointments, validate_working_hours,
    parse_working_hours, DEFAULT_BUFFER_MINUTES, DEFAULT_DURATION_MINUTES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/slots")
async def get_available_slots(
    date_from: date = Query(..., description="Start date"),
    date_to: date = Query(..., description="End date"),
    duration: int = Query(DEFAULT_DURATION_MINUTES, ge=10, le=120, description="Appointment duration in minutes"),
    prefer_morning: bool = Query(False, description="Prefer morning slots first"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Find available appointment slots within a date range."""
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be after date_from")
    if (date_to - date_from).days > 60:
        raise HTTPException(status_code=400, detail="Date range too large (max 60 days)")

    slots = await find_available_slots(
        db=db,
        doctor_id=doctor.id,
        date_from=date_from,
        date_to=date_to,
        duration_minutes=duration,
        prefer_morning=prefer_morning,
    )

    return {"slots": slots, "count": len(slots)}


@router.post("/appointments", status_code=status.HTTP_201_CREATED)
async def create_new_appointment(
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new appointment."""
    patient_id = body.get("patient_id")
    start_at_s = body.get("start_at")
    end_at_s = body.get("end_at")
    reason = body.get("reason", "")

    if not patient_id or not start_at_s or not end_at_s:
        raise HTTPException(status_code=400, detail="patient_id, start_at, end_at required")

    try:
        start_at = datetime.fromisoformat(start_at_s)
        end_at = datetime.fromisoformat(end_at_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format (use ISO-8601)")

    if end_at <= start_at:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")

    try:
        result = await create_appointment(
            db=db, doctor_id=doctor.id,
            patient_id=uuid.UUID(patient_id),
            start_at=start_at, end_at=end_at,
            reason=reason, source="manual",
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/appointments/{appointment_id}/reschedule")
async def reschedule_existing_appointment(
    appointment_id: uuid.UUID,
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Reschedule an appointment."""
    new_start_s = body.get("start_at")
    new_end_s = body.get("end_at")
    reason = body.get("reason", "")

    if not new_start_s or not new_end_s:
        raise HTTPException(status_code=400, detail="start_at and end_at required")

    try:
        new_start = datetime.fromisoformat(new_start_s)
        new_end = datetime.fromisoformat(new_end_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    try:
        result = await reschedule_appointment(
            db=db, doctor_id=doctor.id,
            appointment_id=appointment_id,
            new_start=new_start, new_end=new_end,
            reason=reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/appointments/{appointment_id}/cancel")
async def cancel_existing_appointment(
    appointment_id: uuid.UUID,
    body: dict = {},
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an appointment."""
    reason = body.get("reason", "")
    try:
        result = await cancel_appointment(
            db=db, doctor_id=doctor.id,
            appointment_id=appointment_id,
            reason=reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/appointments")
async def get_appointments(
    date_from: date = Query(..., description="Start date"),
    date_to: date = Query(..., description="End date"),
    status: Optional[str] = Query(None, description="Filter by status: scheduled|done|cancelled"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """List appointments within a date range."""
    appts = await list_appointments(
        db=db, doctor_id=doctor.id,
        date_from=date_from, date_to=date_to,
        status_filter=status,
    )
    return {"appointments": appts, "count": len(appts)}


@router.get("/appointments/{appointment_id}")
async def get_appointment(
    appointment_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get a single appointment detail."""
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == doctor.id,
        )
    )
    apt = result.scalar_one_or_none()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Get patient name
    patient_name = "Unknown"
    pat_result = await db.execute(select(Patient).where(Patient.id == apt.patient_id))
    patient = pat_result.scalar_one_or_none()
    if patient:
        patient_name = str(apt.patient_id)[:8]

    return {
        "id": str(apt.id),
        "patient_id": str(apt.patient_id),
        "patient_name": patient_name,
        "start_at": apt.start_at.isoformat(),
        "end_at": apt.end_at.isoformat(),
        "reason": apt.reason,
        "status": apt.status,
        "source": apt.source,
        "created_at": apt.created_at.isoformat() if apt.created_at else None,
    }


@router.get("/working-hours")
async def get_working_hours(
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get current doctor's working hours config."""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor.id))
    doc = result.scalar_one_or_none()
    settings = doc.settings or {}
    return {
        "working_hours_json": settings.get("working_hours_json", {}),
        "buffer_minutes": settings.get("buffer_minutes_between_consults", DEFAULT_BUFFER_MINUTES),
        "default_duration": settings.get("default_consult_duration", DEFAULT_DURATION_MINUTES),
    }


@router.put("/working-hours")
async def update_working_hours(
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Update doctor's working hours and buffer config."""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor.id))
    doc = result.scalar_one_or_none()

    # Validate working hours if provided
    wh = body.get("working_hours_json")
    if wh:
        validation = validate_working_hours(wh)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation["errors"])

    settings = dict(doc.settings or {})
    if wh:
        settings["working_hours_json"] = wh
    if "buffer_minutes" in body:
        bm = body["buffer_minutes"]
        if not isinstance(bm, int) or bm < 0 or bm > 60:
            raise HTTPException(status_code=400, detail="buffer_minutes must be 0-60")
        settings["buffer_minutes_between_consults"] = bm
    if "default_duration" in body:
        dd = body["default_duration"]
        if not isinstance(dd, int) or dd < 5 or dd > 120:
            raise HTTPException(status_code=400, detail="default_duration must be 5-120")
        settings["default_consult_duration"] = dd

    doc.settings = settings
    await db.commit()

    return {"status": "ok", "working_hours_json": settings.get("working_hours_json", {}),
            "buffer_minutes": settings.get("buffer_minutes_between_consults", DEFAULT_BUFFER_MINUTES),
            "default_duration": settings.get("default_consult_duration", DEFAULT_DURATION_MINUTES)}
