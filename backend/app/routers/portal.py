"""Patient Portal API — public endpoints for patient-facing features.

Endpoints:
  POST /api/public/auth/send-otp — Send OTP to patient phone
  POST /api/public/auth/verify-otp — Verify OTP and get JWT
  GET  /api/public/doctors/search — Search doctors by location/name/speciality
  GET  /api/public/doctors/{id} — Doctor detail + available slots
  POST /api/public/appointments — Patient books an appointment
  GET  /api/patient/me/inbox — Patient notifications
  GET  /api/patient/me/reports — Patient reports
  GET  /api/patient/me/appointments — Patient's appointments
"""

from __future__ import annotations

import uuid
import json
import logging
import asyncio
from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Doctor, Patient, Appointment, PatientNotification, PrescriptionBox, Invoice, Certificate, PatientVersion
from app.dependencies import get_optional_doctor, get_current_patient
from app.services.calendar_service import find_available_slots, create_appointment

logger = logging.getLogger(__name__)

router = APIRouter(tags=["portal"])
# Register public and patient routers under api_router
public_router = APIRouter(prefix="/api/public", tags=["portal"])
patient_router = APIRouter(prefix="/api/patient", tags=["portal"])


# ─── WebSocket Manager ──────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for real-time patient notifications."""

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, patient_id: str, websocket: WebSocket):
        await websocket.accept()
        if patient_id not in self._connections:
            self._connections[patient_id] = []
        self._connections[patient_id].append(websocket)
        logger.info("WebSocket connected: patient=%s (%d active)", patient_id, len(self._connections[patient_id]))

    async def disconnect(self, patient_id: str, websocket: WebSocket):
        if patient_id in self._connections:
            self._connections[patient_id] = [ws for ws in self._connections[patient_id] if ws != websocket]
            if not self._connections[patient_id]:
                del self._connections[patient_id]

    async def notify_patient(self, patient_id: str, event: Dict[str, Any]):
        """Push a notification to all active connections for a patient."""
        if patient_id not in self._connections:
            return
        dead = []
        for ws in self._connections[patient_id]:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(patient_id, ws)

    async def notify_doctor(self, doctor_id: str, event: Dict[str, Any]):
        """Push a notification to a doctor's active connections."""
        # Doctor WebSocket would be /ws/doctor/{doctor_id}
        pass

    @property
    def active_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())


ws_manager = ConnectionManager()


@router.websocket("/ws/patient/{patient_id}")
async def patient_websocket(patient_id: str, websocket: WebSocket):
    """WebSocket for real-time patient notifications.

    Connect: ws://host/api/v1/ws/patient/{patient_id}
    Events received:
      {"type": "notification", "data": {...}}
      {"type": "ping"}
    """
    await ws_manager.connect(patient_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_manager.disconnect(patient_id, websocket)
    except Exception as exc:
        logger.warning("WebSocket error for patient %s: %s", patient_id, exc)
        await ws_manager.disconnect(patient_id, websocket)


# ─── Public: Patient Auth ────────────────────────────

@public_router.post("/auth/send-otp")
async def patient_send_otp(
    body: dict,
):
    """Send OTP to patient's phone for login."""
    phone = body.get("phone", "")
    if not phone:
        raise HTTPException(status_code=400, detail="phone required")

    from app.services.patient_auth import PatientAuthService
    result = await PatientAuthService.send_otp(phone)
    return result


@public_router.post("/auth/verify-otp")
async def patient_verify_otp(
    body: dict,
):
    """Verify OTP and return JWT token."""
    phone = body.get("phone", "")
    otp = body.get("otp", "")
    if not phone or not otp:
        raise HTTPException(status_code=400, detail="phone and otp required")

    from app.services.patient_auth import PatientAuthService
    success, token, patient_id = await PatientAuthService.verify_otp(phone, otp)

    if not success:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")

    return {
        "token": token,
        "patient_id": patient_id,
        "token_type": "bearer",
    }


# ─── Public: Doctor Search ──────────────────────────

@public_router.get("/doctors/search")
async def search_doctors(
    lat: Optional[float] = Query(None, ge=-90, le=90, description="Patient's latitude"),
    lng: Optional[float] = Query(None, ge=-180, le=180, description="Patient's longitude"),
    radius_km: float = Query(10.0, ge=1, le=100, description="Search radius in km"),
    speciality: Optional[str] = Query(None, description="Filter by speciality"),
    q: Optional[str] = Query(None, description="Free-text search (name, clinic)"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search for doctors by location, speciality, or name.

    Uses PostGIS distance query when lat/lng provided.
    Falls back to text search on name/speciality/clinic.
    """
    query = select(Doctor)

    if lat is not None and lng is not None:
        # PostGIS geography distance query
        # location is stored as GEOGRAPHY(Point, 4326)
        try:
            patient_point = text(f"ST_SetSRID(ST_MakePoint({lng}, {lat}), 4326)::geography")
            distance_col = func.ST_Distance(Doctor.location, patient_point).label("distance")
            query = query.add_columns(distance_col).order_by(distance_col)
        except Exception:
            pass

    if speciality:
        query = query.where(Doctor.speciality.ilike(f"%{speciality}%"))
    if q:
        query = query.where(
            Doctor.name.ilike(f"%{q}%") |
            Doctor.clinic_name.ilike(f"%{q}%") |
            Doctor.speciality.ilike(f"%{q}%")
        )

    query = query.limit(limit)
    result = await db.execute(query)
    rows = result.scalars().all()

    doctors = []
    for doc in rows:
        d = {
            "id": str(doc.id),
            "name": doc.name,
            "speciality": doc.speciality,
            "clinic_name": doc.clinic_name,
            "clinic_address": doc.clinic_address,
            "location": doc.location,
            "phone": doc.phone,
            "registration_number": doc.registration_number,
        }
        doctors.append(d)

    return {"doctors": doctors, "count": len(doctors)}


@public_router.get("/doctors/{doctor_id}")
async def get_doctor_detail(
    doctor_id: uuid.UUID,
    date_from: Optional[str] = Query(None, description="Start date for slots (ISO date)"),
    date_to: Optional[str] = Query(None, description="End date for slots (ISO date)"),
    db: AsyncSession = Depends(get_db),
):
    """Get doctor detail with available appointment slots."""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Get available slots
    slots = []
    if date_from and date_to:
        try:
            df = datetime.fromisoformat(date_from).date()
            dt = datetime.fromisoformat(date_to).date()
            slots = await find_available_slots(db, doctor_id, df, dt)
        except Exception as exc:
            logger.warning("Slot fetch failed: %s", exc)

    return {
        "id": str(doc.id),
        "name": doc.name,
        "speciality": doc.speciality,
        "clinic_name": doc.clinic_name,
        "clinic_address": doc.clinic_address,
        "location": doc.location,
        "phone": doc.phone,
        "registration_number": doc.registration_number,
        "settings": {
            "patient_booking_enabled": doc.settings.get("patient_booking_enabled", True),
            "auto_confirm_booking": doc.settings.get("auto_confirm_booking", False),
            "buffer_minutes": doc.settings.get("buffer_minutes_between_consults", 5),
            "default_duration": doc.settings.get("default_consult_duration", 20),
        },
        "available_slots": slots,
    }


@public_router.post("/appointments", status_code=status.HTTP_201_CREATED)
async def patient_book_appointment(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Patient books an appointment from the portal.

    Body: { doctor_id, patient_id, start_at, end_at, reason }
    """
    doctor_id = body.get("doctor_id")
    patient_id = body.get("patient_id")
    start_at_s = body.get("start_at")
    end_at_s = body.get("end_at")
    reason = body.get("reason", "")

    if not all([doctor_id, patient_id, start_at_s, end_at_s]):
        raise HTTPException(status_code=400, detail="doctor_id, patient_id, start_at, end_at required")

    # Verify doctor exists and has booking enabled
    result = await db.execute(select(Doctor).where(Doctor.id == uuid.UUID(doctor_id)))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if not doc.settings.get("patient_booking_enabled", True):
        raise HTTPException(status_code=403, detail="Doctor not accepting online bookings")

    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == uuid.UUID(patient_id)))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        start_at = datetime.fromisoformat(start_at_s)
        end_at = datetime.fromisoformat(end_at_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    try:
        apt = await create_appointment(
            db=db,
            doctor_id=uuid.UUID(doctor_id),
            patient_id=uuid.UUID(patient_id),
            start_at=start_at,
            end_at=end_at,
            reason=reason,
            source="patient_portal",
            send_notification=True,
        )
        return apt
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ─── Patient: Inbox / Reports / Appointments ────────

@patient_router.get("/me/inbox")
async def patient_inbox(
    patient: Patient = Depends(get_current_patient),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get patient's notifications."""
    result = await db.execute(
        select(PatientNotification)
        .where(PatientNotification.patient_id == patient.id)
        .order_by(PatientNotification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    return [
        {
            "id": str(n.id),
            "kind": n.kind,
            "subject": n.subject,
            "body": n.body,
            "read": n.read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


@patient_router.get("/me/reports")
async def patient_reports(
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    """Get patient's medical reports (prescriptions, invoices, certificates)."""
    pid = patient.id

    # Prescriptions
    rx_result = await db.execute(
        select(PrescriptionBox).where(PrescriptionBox.patient_id == pid)
    )
    rxs = rx_result.scalars().all()

    # Invoices
    inv_result = await db.execute(
        select(Invoice).where(Invoice.patient_id == pid)
    )
    invs = inv_result.scalars().all()

    # Certificates
    cert_result = await db.execute(
        select(Certificate).where(Certificate.patient_id == pid)
    )
    certs = cert_result.scalars().all()

    return {
        "prescriptions": [
            {"id": str(r.id), "created_at": r.created_at.isoformat() if r.created_at else None, "has_pdf": bool(r.pdf_path)}
            for r in rxs
        ],
        "invoices": [
            {"id": str(i.id), "invoice_number": i.invoice_number, "total": i.total, "status": i.status, "has_pdf": bool(i.pdf_path)}
            for i in invs
        ],
        "certificates": [
            {"id": str(c.id), "cert_type": c.cert_type, "verification_code": c.verification_code, "has_pdf": bool(c.pdf_path)}
            for c in certs
        ],
    }


@patient_router.get("/me/appointments")
async def patient_appointments(
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    """Get patient's appointments."""
    result = await db.execute(
        select(Appointment)
        .where(Appointment.patient_id == patient.id)
        .order_by(Appointment.start_at.desc())
    )
    appts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "doctor_id": str(a.doctor_id),
            "start_at": a.start_at.isoformat(),
            "end_at": a.end_at.isoformat(),
            "reason": a.reason,
            "status": a.status,
            "source": a.source,
        }
        for a in appts
    ]


# ── WebSocket endpoints (mounted under api_router) ──

@router.websocket("/ws/doctor/{doctor_id}")
async def doctor_websocket(doctor_id: str, websocket: WebSocket):
    """WebSocket for doctor real-time alerts (risk alerts, notifications)."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Doctor WebSocket error: %s", exc)


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection stats."""
    return {"active_connections": ws_manager.active_connections}
