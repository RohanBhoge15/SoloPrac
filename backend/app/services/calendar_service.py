"""Calendar Service — working hours, slot management, appointment CRUD, buffer enforcement.

Tools 1–4 (Week 10):
  - find_available_slots(date_range, duration, prefer_morning)
  - create_appointment(patient_id, slot, reason, send_notification)
  - reschedule_appointment(appointment_id, new_slot, reason)
  - cancel_appointment(appointment_id, reason, notify_patient)

Doctor config (from doctor_settings JSONB):
  - working_hours_json: {"mon": [["09:00","13:00"], ["16:00","20:00"]]}
  - buffer_minutes_between_consults: 5 (default)
  - default_consult_duration: 20 (default)

Patient preference learning:
  - Every confirmed appointment logs (patient_id, weekday, hour_bucket) to patient_time_preferences
"""

from __future__ import annotations

import uuid
import json
import logging
from datetime import datetime, timezone, timedelta, date, time
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Patient, PatientTimePreference, Doctor, AuditLog
from app.services.email_queue import email_queue

logger = logging.getLogger(__name__)

WEEKDAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_BUFFER_MINUTES = 5
DEFAULT_DURATION_MINUTES = 20


# ─── Working Hours Parser ──────────────────────────

def parse_working_hours(settings_json: dict) -> Dict[int, List[Tuple[int, int]]]:
    """Parse doctor_settings.working_hours_json into weekday → slot ranges.

    Input: {"mon": [["09:00","13:00"], ["16:00","20:00"]], "tue": [["09:00","13:00"]]}
    Output: {0: [(540, 780), (960, 1200)], 1: [(540, 780)]}
        where each slot is (start_minutes_from_midnight, end_minutes_from_midnight)
    """
    raw = settings_json.get("working_hours_json", {})
    if isinstance(raw, str):
        raw = json.loads(raw)

    parsed: Dict[int, List[Tuple[int, int]]] = {}

    for day_key, windows in raw.items():
        weekday = WEEKDAY_MAP.get(day_key.lower()[:3], -1)
        if weekday < 0:
            continue
        slots = []
        for window in windows:
            if isinstance(window, list) and len(window) == 2:
                start = _time_to_minutes(window[0])
                end = _time_to_minutes(window[1])
                if start < end:
                    slots.append((start, end))
        if slots:
            parsed[weekday] = slots

    return parsed


def _time_to_minutes(t_str: str) -> int:
    """Convert '09:00' or '09:00 AM' to minutes from midnight."""
    t_str = t_str.strip().upper()
    is_pm = "PM" in t_str
    t_str = t_str.replace("AM", "").replace("PM", "").strip()
    parts = t_str.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    if is_pm and h != 12:
        h += 12
    if not is_pm and h == 12:
        h = 0
    return h * 60 + m


def _minutes_to_time(m: int) -> str:
    """Convert minutes from midnight to 'HH:MM'."""
    return f"{m // 60:02d}:{m % 60:02d}"


def get_doctor_settings(doctor: Doctor) -> dict:
    """Get merged doctor settings with defaults."""
    settings = doctor.settings or {}
    return {
        "buffer_minutes": settings.get("buffer_minutes_between_consults", DEFAULT_BUFFER_MINUTES),
        "default_duration": settings.get("default_consult_duration", DEFAULT_DURATION_MINUTES),
        "working_hours": parse_working_hours(settings),
        "auto_email": settings.get("auto_email_on_change", True),
        "max_future_days": settings.get("max_future_booking_days", 30),
    }


def get_date_range_for_slot(weekday: int, ref_date: Optional[date] = None) -> List[date]:
    """Get all dates of a given weekday between ref_date and ref_date + 14 days."""
    ref = ref_date or datetime.now(timezone.utc).date()
    dates = []
    for i in range(14):
        d = ref + timedelta(days=i)
        if d.weekday() == weekday:
            dates.append(d)
    return dates


# ─── Tool 1: Find Available Slots ──────────────────

async def find_available_slots(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    date_from: date,
    date_to: date,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    prefer_morning: bool = False,
) -> List[Dict[str, Any]]:
    """Find available appointment slots within a date range.

    Considers:
      - Working hours (per weekday)
      - Buffer between appointments
      - Existing appointments
      - Duration requested
    """
    # Get doctor settings
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if not doctor:
        return []

    settings = get_doctor_settings(doctor)
    buffer = settings["buffer_minutes"]
    default_dur = settings["default_duration"]
    dur = duration_minutes or default_dur
    working_hours = settings["working_hours"]
    total_slot_time = dur + buffer

    # Get existing appointments for the date range
    existing = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.start_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc),
            Appointment.start_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc),
            Appointment.status.in_(["scheduled", "done"]),
        )
    )
    existing_appts = existing.scalars().all()

    # Build occupied slot map: (date_iso, start_minutes) -> appointment
    occupied: Dict[Tuple[str, int], Appointment] = {}
    for apt in existing_appts:
        day_key = apt.start_at.date().isoformat()
        occupied[(day_key, apt.start_at.hour * 60 + apt.start_at.minute)] = apt

    slots: List[Dict[str, Any]] = []
    current = date_from

    while current <= date_to:
        weekday = current.weekday()
        day_key = current.isoformat()

        if weekday in working_hours:
            for wh_start, wh_end in working_hours[weekday]:
                slot_start = wh_start
                while slot_start + dur <= wh_end:
                    slot_end = slot_start + dur

                    # Check if slot conflicts with existing appointment (including buffer)
                    has_conflict = False
                    for occ_start, occ_apt in occupied.items():
                        if occ_start[0] != day_key:
                            continue
                        occ_end = occ_start[1] + (
                            (occ_apt.end_at.hour * 60 + occ_apt.end_at.minute) -
                            occ_start[1]
                        )
                        # Check overlap with buffer
                        if not (slot_end + buffer <= occ_start[1] or slot_start >= occ_end + buffer):
                            has_conflict = True
                            break

                    if not has_conflict:
                        start_dt = datetime.combine(current, time(0, 0), tzinfo=timezone.utc) + timedelta(minutes=slot_start)
                        end_dt = start_dt + timedelta(minutes=dur)
                        slots.append({
                            "start": start_dt.isoformat(),
                            "end": end_dt.isoformat(),
                            "date": day_key,
                            "time": _minutes_to_time(slot_start),
                            "duration_minutes": dur,
                            "doctor_id": str(doctor_id),
                        })

                    slot_start += total_slot_time

        current += timedelta(days=1)

    # Sort by date/time and respect preference
    slots.sort(key=lambda s: s["start"])
    if prefer_morning:
        morning = [s for s in slots if int(s["time"].split(":")[0]) < 12]
        afternoon = [s for s in slots if int(s["time"].split(":")[0]) >= 12]
        return morning + afternoon

    return slots[:50]  # Limit to 50 slots per query


# ─── Tool 2: Create Appointment ────────────────────

async def create_appointment(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    patient_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    reason: str = "",
    source: str = "manual",
    send_notification: bool = True,
) -> Dict[str, Any]:
    """Create a new appointment with patient preference logging.

    Returns the created appointment data.
    """
    # Verify patient belongs to doctor
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise ValueError("Patient not found")

    # Check for conflicts
    conflict = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.start_at < end_at,
            Appointment.end_at > start_at,
            Appointment.status.in_(["scheduled", "done"]),
        )
    )
    if conflict.scalar_one_or_none():
        raise ValueError("Time slot conflicts with an existing appointment")

    # Create appointment
    apt = Appointment(
        id=uuid.uuid4(),
        doctor_id=doctor_id,
        patient_id=patient_id,
        start_at=start_at,
        end_at=end_at,
        reason=reason,
        status="scheduled",
        source=source,
    )
    db.add(apt)
    await db.flush()

    # Log patient preference (Nihal)
    await _log_patient_preference(db, patient_id, start_at)

    # Audit log (Dev)
    try:
        audit = AuditLog(
            doctor_id=doctor_id,
            patient_id=patient_id,
            actor=f"doctor:{doctor_id}",
            action="write",
            resource_type="appointment",
            resource_id=apt.id,
            payload_jsonb={
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "reason": reason,
                "source": source,
            },
        )
        db.add(audit)
        await db.flush()
    except Exception as exc:
        logger.warning("Appointment audit log failed: %s", exc)

    await db.commit()
    await db.refresh(apt)

    # Send notification (arq email queue)
    if send_notification:
        try:
            await email_queue.enqueue(
                email_type="booking_confirmation",
                doctor_id=str(doctor_id),
                patient_id=str(patient_id),
                appointment_id=str(apt.id),
                start_at=start_at.isoformat(),
            )
        except Exception as exc:
            logger.warning("Failed to enqueue booking notification: %s", exc)

    return {
        "id": str(apt.id),
        "patient_id": str(patient_id),
        "doctor_id": str(doctor_id),
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "reason": reason,
        "status": "scheduled",
        "source": source,
    }


async def _log_patient_preference(db: AsyncSession, patient_id: uuid.UUID, start_at: datetime):
    """Log patient time preference (Nihal)."""
    weekday = start_at.weekday()
    hour_bucket = start_at.hour

    # Upsert preference
    result = await db.execute(
        select(PatientTimePreference).where(
            PatientTimePreference.patient_id == patient_id,
            PatientTimePreference.weekday == weekday,
            PatientTimePreference.hour_bucket == hour_bucket,
        )
    )
    pref = result.scalar_one_or_none()

    if pref:
        pref.count = (pref.count or 0) + 1
        pref.last_seen = start_at
    else:
        pref = PatientTimePreference(
            patient_id=patient_id,
            weekday=weekday,
            hour_bucket=hour_bucket,
            count=1,
            last_seen=start_at,
        )
        db.add(pref)


# ─── Tool 3: Reschedule Appointment ────────────────

async def reschedule_appointment(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    appointment_id: uuid.UUID,
    new_start: datetime,
    new_end: datetime,
    reason: str = "",
    notify_patient: bool = True,
) -> Dict[str, Any]:
    """Reschedule an existing appointment."""
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == doctor_id,
        )
    )
    apt = result.scalar_one_or_none()
    if not apt:
        raise ValueError("Appointment not found")

    if apt.status == "cancelled":
        raise ValueError("Cannot reschedule a cancelled appointment")

    # Check conflicts with new slot
    conflict = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.id != appointment_id,
            Appointment.start_at < new_end,
            Appointment.end_at > new_start,
            Appointment.status.in_(["scheduled", "done"]),
        )
    )
    if conflict.scalar_one_or_none():
        raise ValueError("New time slot conflicts with an existing appointment")

    old_start = apt.start_at
    old_end = apt.end_at
    apt.start_at = new_start
    apt.end_at = new_end
    if reason:
        apt.reason = reason
    await db.commit()

    # Audit
    try:
        audit = AuditLog(
            doctor_id=doctor_id,
            patient_id=apt.patient_id,
            actor=f"doctor:{doctor_id}",
            action="write",
            resource_type="appointment",
            resource_id=apt.id,
            payload_jsonb={
                "action": "reschedule",
                "old_start": old_start.isoformat(),
                "new_start": new_start.isoformat(),
                "reason": reason,
            },
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    if notify_patient:
        try:
            await email_queue.enqueue(
                email_type="reschedule_notification",
                doctor_id=str(doctor_id),
                patient_id=str(apt.patient_id),
                appointment_id=str(apt.id),
                new_start=new_start.isoformat(),
            )
        except Exception as exc:
            logger.warning("Failed to enqueue reschedule notification: %s", exc)

    return {
        "id": str(apt.id),
        "start_at": new_start.isoformat(),
        "end_at": new_end.isoformat(),
        "status": apt.status,
    }


# ─── Tool 4: Cancel Appointment ────────────────────

async def cancel_appointment(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    appointment_id: uuid.UUID,
    reason: str = "",
    notify_patient: bool = True,
) -> Dict[str, Any]:
    """Cancel an appointment."""
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == doctor_id,
        )
    )
    apt = result.scalar_one_or_none()
    if not apt:
        raise ValueError("Appointment not found")

    apt.status = "cancelled"
    await db.commit()

    # Audit
    try:
        audit = AuditLog(
            doctor_id=doctor_id,
            patient_id=apt.patient_id,
            actor=f"doctor:{doctor_id}",
            action="write",
            resource_type="appointment",
            resource_id=apt.id,
            payload_jsonb={"action": "cancel", "reason": reason},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    if notify_patient:
        try:
            await email_queue.enqueue(
                email_type="cancellation_notification",
                doctor_id=str(doctor_id),
                patient_id=str(apt.patient_id),
                appointment_id=str(apt.id),
                reason=reason,
            )
        except Exception as exc:
            logger.warning("Failed to enqueue cancellation notification: %s", exc)

    return {"id": str(apt.id), "status": "cancelled"}


# ─── Working Hours Validation ──────────────────────

def validate_working_hours(working_hours_json: Any) -> Dict[str, Any]:
    """Validate working hours JSON structure.

    Returns {"valid": bool, "errors": [...]}
    """
    errors = []
    if not isinstance(working_hours_json, dict):
        return {"valid": False, "errors": ["working_hours_json must be a dict"]}

    valid_days = set(WEEKDAY_MAP.keys())
    for day_key, windows in working_hours_json.items():
        day_short = day_key.lower()[:3]
        if day_short not in valid_days:
            errors.append(f"Unknown day: {day_key} (use mon,tue,wed,thu,fri,sat,sun)")
            continue
        if not isinstance(windows, list):
            errors.append(f"Day '{day_key}' must contain a list of time windows")
            continue
        for w in windows:
            if not isinstance(w, list) or len(w) != 2:
                errors.append(f"Each window must be [start, end] format, got {w}")
                continue
            try:
                start = _time_to_minutes(w[0])
                end = _time_to_minutes(w[1])
                if start >= end:
                    errors.append(f"Window {w[0]}-{w[1]} on {day_key}: start must be before end")
                if start < 0 or end > 1440:
                    errors.append(f"Window {w[0]}-{w[1]} on {day_key}: times must be within 00:00-24:00")
            except Exception:
                errors.append(f"Invalid time format in window {w} on {day_key}")

    return {"valid": len(errors) == 0, "errors": errors}


# ─── List Appointments ────────────────────────────

async def list_appointments(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    date_from: date,
    date_to: date,
    status_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List appointments for a doctor within a date range."""
    query = select(Appointment).where(
        Appointment.doctor_id == doctor_id,
        Appointment.start_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc),
        Appointment.start_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )
    if status_filter:
        query = query.where(Appointment.status == status_filter)

    query = query.order_by(Appointment.start_at)
    result = await db.execute(query)
    appts = result.scalars().all()

    output = []
    for apt in appts:
        # Get patient name
        patient_name = f"Patient {str(apt.patient_id)[:8]}"
        patient_result = await db.execute(select(Patient).where(Patient.id == apt.patient_id))
        patient = patient_result.scalar_one_or_none()
        if patient:
            # Get head version for name
            if patient.head_version_id:
                from app.models import PatientVersion
                vr = await db.execute(
                    select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
                )
                ver = vr.scalar_one_or_none()
                if ver and ver.state_jsonb:
                    demo = ver.state_jsonb.get("demographics", {})
                    if isinstance(demo, dict):
                        patient_name = demo.get("name", patient_name)

        output.append({
            "id": str(apt.id),
            "patient_id": str(apt.patient_id),
            "patient_name": patient_name,
            "start_at": apt.start_at.isoformat(),
            "end_at": apt.end_at.isoformat(),
            "reason": apt.reason,
            "status": apt.status,
            "source": apt.source,
        })

    return output
