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


# ─── Tool 5: Query Calendar NL ──────────────────────

async def query_calendar_nl(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    query: str,
    date_range: Optional[Tuple[date, date]] = None,
) -> Dict[str, Any]:
    """Natural language calendar query using LLM.

    Examples:
      - "When am I free next week?"
      - "Show all diabetic follow-ups this month"
      - "What appointments do I have on Tuesday?"
    """
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if not doctor:
        return {"error": "Doctor not found"}

    query_lower = query.lower()
    today = date.today()

    if date_range:
        date_from, date_to = date_range
    else:
        date_from = today
        date_to = today + timedelta(days=7)

    if "free" in query_lower or "available" in query_lower:
        slots = await find_available_slots(db, doctor_id, date_from, date_to)
        return {"type": "available_slots", "slots": slots, "summary": f"Found {len(slots)} available slots"}

    if "diabetic" in query_lower or "diabetes" in query_lower:
        appts = await list_appointments(db, doctor_id, date_from, date_to)
        filtered = [a for a in appts if "diabet" in a.get("reason", "").lower()]
        return {"type": "filtered_appointments", "appointments": filtered, "summary": f"Found {len(filtered)} diabetes-related appointments"}

    if "tuesday" in query_lower or "monday" in query_lower or "wednesday" in query_lower or "thursday" in query_lower or "friday" in query_lower:
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4}
        for day_name, day_num in [("tuesday", 1), ("monday", 0), ("wednesday", 2), ("thursday", 3), ("friday", 4)]:
            if day_name in query_lower:
                dates = get_date_range_for_slot(day_num, today)
                slots = []
                for d in dates:
                    day_slots = await find_available_slots(db, doctor_id, d, d)
                    slots.extend(day_slots)
                return {"type": "available_slots", "slots": slots, "summary": f"Available on {day_name.capitalize()}s"}

    return {"type": "unknown", "summary": "Could not parse query. Try: 'When am I free next week?' or 'Show diabetic follow-ups this month'"}


# ─── Tool 6: Bulk Reschedule ────────────────────────

async def bulk_reschedule(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    appointment_ids: List[uuid.UUID],
    new_window: Tuple[date, date],
    notify_template: str = "Your appointment has been rescheduled to {new_time}. Please confirm.",
) -> Dict[str, Any]:
    """Reschedule multiple appointments to fit within a new date window.

    Used for scenarios like:
      - Doctor going on leave
      - Clinic closure
      - Emergency requiring mass reschedule
    """
    if not appointment_ids:
        return {"error": "No appointments provided"}

    results = {"rescheduled": [], "failed": []}

    window_start, window_end = new_window
    slots = await find_available_slots(
        db, doctor_id, window_start, window_end,
        duration_minutes=20, prefer_morning=True
    )

    if not slots:
        return {"error": "No available slots in the specified window"}

    slots.sort(key=lambda s: s["start"])

    for i, apt_id in enumerate(appointment_ids):
        if i >= len(slots):
            results["failed"].append({"appointment_id": str(apt_id), "error": "No more available slots"})
            continue

        try:
            slot = slots[i]
            new_start = datetime.fromisoformat(slot["start"])
            new_end = datetime.fromisoformat(slot["end"])

            result = await reschedule_appointment(
                db=db, doctor_id=doctor_id,
                appointment_id=apt_id,
                new_start=new_start, new_end=new_end,
                reason="Bulk reschedule", notify_patient=True,
            )
            results["rescheduled"].append({
                "appointment_id": str(apt_id),
                "old_slot": "TBD",
                "new_start": slot["start"],
                "new_end": slot["end"],
            })
        except Exception as exc:
            results["failed"].append({"appointment_id": str(apt_id), "error": str(exc)})

    return {
        "rescheduled_count": len(results["rescheduled"]),
        "failed_count": len(results["failed"]),
        "details": results,
    }


# ─── Tool 7: Block Doctor Time ─────────────────────

async def block_doctor_time(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    date_range: Tuple[date, date],
    reason: str = "Doctor unavailable",
) -> Dict[str, Any]:
    """Block off a date range for the doctor (holiday, conference, emergency)."""
    date_from, date_to = date_range

    if date_to < date_from:
        return {"error": "date_to must be after date_from"}

    blocked_appts = []
    current = date_from
    while current <= date_to:
        blocked = Appointment(
            id=uuid.uuid4(),
            doctor_id=doctor_id,
            patient_id=uuid.uuid4(),
            start_at=datetime.combine(current, time(0, 0), tzinfo=timezone.utc),
            end_at=datetime.combine(current + timedelta(days=1), time(0, 0), tzinfo=timezone.utc),
            reason=reason,
            status="blocked",
            source="blocked",
        )
        db.add(blocked)
        blocked_appts.append(str(blocked.id))
        current += timedelta(days=1)

    await db.commit()

    return {
        "status": "ok",
        "blocked_dates": [str(date_from), str(date_to)],
        "blocked_appointment_ids": blocked_appts,
        "reason": reason,
    }


# ─── Tool 8: Smart Rearrange ───────────────────────

async def smart_rearrange(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    date_range: Tuple[date, date],
    optimization: str = "minimize_patient_disruption",
) -> Dict[str, Any]:
    """Smart rearrange appointments within a date range.

    Optimization strategies:
      - minimize_patient_disruption: prefer keeping same time/day
      - maximize_throughput: pack appointments tightly
      - balance_workload: distribute evenly across days
    """
    date_from, date_to = date_range

    appts = await list_appointments(db, doctor_id, date_from, date_to)
    scheduled_appts = [a for a in appts if a["status"] == "scheduled"]

    if not scheduled_appts:
        return {"message": "No appointments to rearrange", "proposals": []}

    slots = await find_available_slots(db, doctor_id, date_from, date_to)
    slots.sort(key=lambda s: s["start"])

    patient_ids = [uuid.UUID(a["patient_id"]) for a in scheduled_appts]
    prefs_result = await db.execute(
        select(PatientTimePreference).where(PatientTimePreference.patient_id.in_(patient_ids))
    )
    prefs = prefs_result.scalars().all()

    pref_map = defaultdict(lambda: defaultdict(int))
    for p in prefs:
        pref_map[str(p.patient_id)][(p.weekday, p.hour_bucket)] = p.count

    proposals = []

    for appt in scheduled_appts:
        patient_id = appt["patient_id"]
        appt_time = datetime.fromisoformat(appt["start_at"])
        appt_weekday = appt_time.weekday()
        appt_hour = appt_time.hour

        best_slot = None
        best_score = -1

        for slot in slots:
            slot_time = datetime.fromisoformat(slot["start"])
            slot_weekday = slot_time.weekday()
            slot_hour = slot_time.hour

            pref_score = pref_map[patient_id].get((slot_weekday, slot_hour), 0)

            if optimization == "minimize_patient_disruption":
                if slot_weekday == appt_weekday:
                    pref_score += 10
                if abs(slot_hour - appt_hour) <= 1:
                    pref_score += 5

            if pref_score > best_score:
                best_score = pref_score
                best_slot = slot

        if best_slot:
            proposals.append({
                "appointment_id": appt["id"],
                "patient_id": appt["patient_id"],
                "current_start": appt["start_at"],
                "current_end": appt["end_at"],
                "proposed_start": best_slot["start"],
                "proposed_end": best_slot["end"],
                "confidence": min(best_score / 20.0, 1.0),
                "reason": f"Optimized for {optimization}",
            })
            slots.remove(best_slot)

    return {"proposals": proposals, "summary": f"Generated {len(proposals)} rearrangement proposals", "optimization": optimization}


# ─── Tool 9: Find Optimal Window ───────────────────

async def find_optimal_window(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    constraints: Dict[str, Any],
) -> Dict[str, Any]:
    """Find the optimal appointment window given constraints."""
    duration = constraints.get("duration_minutes", 20)
    date_from = constraints.get("earliest_date", date.today())
    date_to = constraints.get("latest_date", date.today() + timedelta(days=30))
    preferred_days = constraints.get("preferred_days", list(range(7)))
    preferred_time = constraints.get("preferred_time", "any")
    patient_id = constraints.get("patient_id")

    slots = await find_available_slots(db, doctor_id, date_from, date_to, duration)

    if preferred_days:
        slots = [s for s in slots if datetime.fromisoformat(s["start"]).weekday() in preferred_days]

    if preferred_time != "any":
        time_ranges = {"morning": (0, 12), "afternoon": (12, 17), "evening": (17, 22)}
        min_h, max_h = time_ranges.get(preferred_time, (0, 24))
        slots = [s for s in slots if min_h <= datetime.fromisoformat(s["start"]).hour < max_h]

    if patient_id:
        prefs_result = await db.execute(
            select(PatientTimePreference).where(PatientTimePreference.patient_id == patient_id)
        )
        prefs = prefs_result.scalars().all()
        pref_map = {(p.weekday, p.hour_bucket): p.count for p in prefs}

        for slot in slots:
            dt = datetime.fromisoformat(slot["start"])
            pref_score = pref_map.get((dt.weekday(), dt.hour), 0)
            slot["preference_score"] = pref_score

        slots.sort(key=lambda s: s.get("preference_score", 0), reverse=True)

    return {
        "optimal_slots": slots[:10],
        "total_found": len(slots),
        "constraints": constraints,
    }


# ─── Doctor-Off Scenario ──────────────────────────

async def handle_doctor_off(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    off_start: date,
    off_end: date,
    reason: str = "Doctor unavailable",
) -> Dict[str, Any]:
    """Handle 'I'm off' scenario:
      1. Block doctor's time
      2. Find all affected appointments
      3. Auto-reschedule using smart_rearrange
      4. Draft notification emails
      5. Return approval card
    """
    block_result = await block_doctor_time(db, doctor_id, (off_start, off_end), reason)

    affected = await list_appointments(db, doctor_id, off_start, off_end)
    affected_scheduled = [a for a in affected if a["status"] == "scheduled"]

    rearrange = await smart_rearrange(db, doctor_id, (off_start, off_end), "minimize_patient_disruption")

    affected_ids = {a["id"] for a in affected_scheduled}
    relevant_proposals = [p for p in rearrange["proposals"] if p["appointment_id"] in affected_ids]

    email_drafts = []
    for proposal in relevant_proposals:
        patient_result = await db.execute(select(Patient).where(Patient.id == uuid.UUID(proposal["patient_id"])))
        patient = patient_result.scalar_one_or_none()
        patient_name = "Patient"
        if patient and patient.head_version_id:
            from app.models import PatientVersion
            vr = await db.execute(select(PatientVersion).where(PatientVersion.id == patient.head_version_id))
            ver = vr.scalar_one_or_none()
            if ver and ver.state_jsonb:
                demo = ver.state_jsonb.get("demographics", {})
                if isinstance(demo, dict):
                    patient_name = demo.get("name", "Patient")

        old_start = datetime.fromisoformat(proposal["current_start"])
        new_start = datetime.fromisoformat(proposal["proposed_start"])

        email_drafts.append({
            "to": f"patient-{proposal['patient_id'][:8]}@example.com",
            "subject": "Appointment Rescheduled - Action Required",
            "body": f"""Dear {patient_name},

Your appointment has been rescheduled due to doctor's unavailability.

Original: {old_start.strftime('%A, %B %d at %I:%M %p')}
New: {new_start.strftime('%A, %B %d at %I:%M %p')}

Please confirm or request a different time.

SoloPrac AI""",
            "proposal_id": proposal["appointment_id"],
        })

    return {
        "status": "doctor_off_processed",
        "blocked": block_result,
        "affected_count": len(affected_scheduled),
        "proposals": relevant_proposals,
        "email_drafts": email_drafts,
        "approval_card": {
            "title": "Doctor Off — Approve Rescheduling",
            "message": f"Dr. is off {off_start} to {off_end}. {len(affected_scheduled)} appointments affected.",
            "actions": ["Approve All", "Review Individually", "Cancel All"],
        },
    }


# ─── LangGraph Subgraph Integration ──────────────────

def build_scheduling_subgraph() -> "StateGraph":
    """Build the voice scheduling LangGraph subgraph."""
    return {
        "nodes": [
            "asr_node",
            "intent_classifier",
            "tool_dispatcher",
            "synthesizer",
            "tts_node",
        ],
        "edges": [
            ("asr_node", "intent_classifier"),
            ("intent_classifier", "tool_dispatcher"),
            ("tool_dispatcher", "synthesizer"),
            ("synthesizer", "tts_node"),
        ],
        "tools": [
            "find_available_slots",
            "create_appointment",
            "reschedule_appointment",
            "cancel_appointment",
            "query_calendar_nl",
            "bulk_reschedule",
            "block_doctor_time",
            "smart_rearrange",
            "find_optimal_window",
        ],
    }
