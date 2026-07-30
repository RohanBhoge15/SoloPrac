# Patient Portal API — public endpoints for patient-facing features.
#
# Endpoints:
#   POST /api/public/auth/register — Register new patient account
#   POST /api/public/auth/login — Patient email/password login (sets HttpOnly cookies)
#   POST /api/public/auth/logout — Patient logout (clears cookies)
#   GET  /api/public/doctors/search — Search doctors by location/name/speciality
#   GET  /api/public/doctors/{id} — Doctor detail + available slots
#   POST /api/public/appointments — Patient books an appointment
#   GET  /api/patient/me/profile — Patient profile
#   PUT  /api/patient/me/profile — Update patient profile
#   GET  /api/patient/me/inbox — Patient notifications
#   GET  /api/patient/me/reports — Patient reports
#   GET  /api/patient/me/appointments — Patient's appointments

from __future__ import annotations

import uuid
import json
import logging
import asyncio
from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status, Response
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Doctor, Patient, User, Appointment, PatientNotification, PrescriptionBox, Invoice, Certificate, PatientVersion
from app.dependencies import get_optional_doctor, get_current_user
from app.services.calendar_service import find_available_slots, create_appointment
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

# Main portal router - no prefix, mounted at /api/v1
router = APIRouter(tags=["portal"])

# Public endpoints (no auth required)
public_router = APIRouter(prefix="/public", tags=["portal"])

# Patient authenticated endpoints
patient_router = APIRouter(prefix="/patient", tags=["portal"])

# Mount sub-routers
router.include_router(public_router)
router.include_router(patient_router)


# ─── Cookie helpers for patient auth ───

def _set_patient_cookies(response: Response, access_token: str) -> None:
    """Set HttpOnly, Secure, SameSite=Lax cookies for patient access token.
    
    Cookies are scoped to /api path so they're only sent to API endpoints.
    """
    from app.config import get_settings
    settings = get_settings()
    cookie_kwargs = {
        "httponly": True,
        "secure": not settings.DEBUG,  # Secure in production, allow HTTP in dev
        "samesite": "lax",
        "path": "/api",
    }
    # Access token: 30 days
    response.set_cookie("patient_token", access_token, max_age=30 * 86400, **cookie_kwargs)


def _clear_patient_cookies(response: Response) -> None:
    """Clear patient auth cookies on logout."""
    from app.config import get_settings
    settings = get_settings()
    cookie_kwargs = {
        "httponly": True,
        "secure": not settings.DEBUG,
        "samesite": "lax",
        "path": "/api",
    }
    response.delete_cookie("patient_token", **cookie_kwargs)


# ─── WebSocket Manager (Redis-backed for multi-worker) ──────────────────────────────

PATIENT_CHANNEL = "ws:notifications"
DOCTOR_CHANNEL = "ws:doctor_notifications"


class ConnectionManager:
    """Manages WebSocket connections for real-time patient + doctor delivery.

    Local sockets are held in-process. A single Redis pub/sub subscriber
    (started once in the app lifespan) forwards events published by any
    worker — including the arq background worker — to the sockets held by
    THIS process. That's what lets a cron job running in the arq worker
    push a risk alert to a doctor connected to the web process.
    """

    def __init__(self):
        self._patient_connections: Dict[str, List[WebSocket]] = {}
        self._doctor_connections: Dict[str, List[WebSocket]] = {}
        self._redis = None
        self._pubsub = None
        self._listener_task = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                from app.config import settings
                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            except Exception:
                logger.warning("Redis not available — WebSocket notifications limited to local worker")
                self._redis = False
        return self._redis

    # ─── Lifespan-managed pub/sub subscriber ───

    async def start_subscriber(self):
        """Subscribe to Redis channels and fan out to local sockets.

        Called once on app startup. Safe to call when Redis is unavailable
        (no-op — delivery falls back to local-only).
        """
        if self._listener_task is not None:
            return
        redis = await self._get_redis()
        if not redis:
            return
        try:
            self._pubsub = redis.pubsub()
            await self._pubsub.subscribe(PATIENT_CHANNEL, DOCTOR_CHANNEL)
            self._listener_task = asyncio.create_task(self._listen())
            logger.info("WebSocket pub/sub subscriber started")
        except Exception as exc:
            logger.warning("Failed to start WebSocket subscriber: %s", exc)

    async def stop_subscriber(self):
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pubsub:
            try:
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

    async def _listen(self):
        try:
            async for message in self._pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                except (ValueError, KeyError):
                    continue
                channel = message.get("channel")
                if channel == PATIENT_CHANNEL and payload.get("patient_id"):
                    await self._send_local(self._patient_connections, payload["patient_id"], payload.get("event", {}))
                elif channel == DOCTOR_CHANNEL and payload.get("doctor_id"):
                    await self._send_local(self._doctor_connections, payload["doctor_id"], payload.get("event", {}))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("WebSocket subscriber loop ended: %s", exc)

    # ─── Connection registry ───

    async def connect(self, patient_id: str, websocket: WebSocket):
        await websocket.accept()
        self._patient_connections.setdefault(patient_id, []).append(websocket)
        logger.info("WebSocket connected: patient=%s (%d active)", patient_id, len(self._patient_connections[patient_id]))

    async def disconnect(self, patient_id: str, websocket: WebSocket):
        self._drop(self._patient_connections, patient_id, websocket)

    async def connect_doctor(self, doctor_id: str, websocket: WebSocket):
        await websocket.accept()
        self._doctor_connections.setdefault(doctor_id, []).append(websocket)
        logger.info("WebSocket connected: doctor=%s (%d active)", doctor_id, len(self._doctor_connections[doctor_id]))

    async def disconnect_doctor(self, doctor_id: str, websocket: WebSocket):
        self._drop(self._doctor_connections, doctor_id, websocket)

    @staticmethod
    def _drop(registry: Dict[str, List[WebSocket]], key: str, websocket: WebSocket):
        if key in registry:
            registry[key] = [ws for ws in registry[key] if ws != websocket]
            if not registry[key]:
                del registry[key]

    async def _send_local(self, registry: Dict[str, List[WebSocket]], key: str, event: Dict[str, Any]):
        """Send to sockets held by this process; prune any that are dead."""
        dead = []
        for ws in registry.get(key, []):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._drop(registry, key, ws)

    # ─── Notify (local + cross-worker) ───

    async def notify_patient(self, patient_id: str, event: Dict[str, Any]):
        """Push a notification to all active connections for a patient.

        Single delivery path: when Redis is up, publish only — the subscriber
        (running in every process, including this one) fans out to local
        sockets, so publishing also covers this process. Only fall back to a
        direct local send when Redis is unavailable, to avoid double delivery.
        """
        redis = await self._get_redis()
        if redis:
            try:
                await redis.publish(PATIENT_CHANNEL, json.dumps({"patient_id": patient_id, "event": event}))
                return
            except Exception:
                pass
        await self._send_local(self._patient_connections, patient_id, event)

    async def notify_doctor(self, doctor_id: str, event: Dict[str, Any]):
        """Push a notification to a doctor's active connections.

        Publishes to Redis so other processes (e.g. the arq worker running the
        risk scan) reach doctors connected to the web process. Falls back to a
        direct local send when Redis is unavailable. See notify_patient for why
        this is publish-or-local, never both.
        """
        redis = await self._get_redis()
        if redis:
            try:
                await redis.publish(DOCTOR_CHANNEL, json.dumps({"doctor_id": doctor_id, "event": event}))
                return
            except Exception:
                pass
        await self._send_local(self._doctor_connections, doctor_id, event)

    @property
    def active_connections(self) -> int:
        patients = sum(len(v) for v in self._patient_connections.values())
        doctors = sum(len(v) for v in self._doctor_connections.values())
        return patients + doctors


ws_manager = ConnectionManager()


@router.websocket("/ws/patient/{patient_id}")
async def patient_websocket(patient_id: str, websocket: WebSocket, token: str = Query("")):
    """WebSocket for real-time patient notifications.

    Connect: ws://host/api/v1/ws/patient/{patient_id}?token=JWT_TOKEN
    The patient JWT token (user-level) is required as a query parameter.
    Verifies that the patient_id in the URL belongs to the authenticated user.
    Events received:
      {"type": "notification", "data": {...}}
      {"type": "ping"}
    """
    # Verify patient JWT token before accepting connection
    from jose import jwt as _jwt, JWTError as _JWTError
    from app.config import settings as _settings
    try:
        payload = _jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
        if payload.get("type") != "patient":
            await websocket.close(code=4001, reason="Unauthorized")
            return
        user_id = payload.get("sub")
    except _JWTError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Verify the patient_id matches the token's subject (user_id).
    # The patient_id URL param is used for routing notifications to the correct
    # connection. If the token has a patient_id claim, it must match.
    token_patient_id = payload.get("patient_id")
    if token_patient_id and str(token_patient_id) != patient_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return
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

@public_router.post("/auth/register")
async def patient_register(
    response: Response,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Register a new patient with email and password.

    Sets JWT patient token as HttpOnly cookie.
    """
    from app.schemas import UserRegister
    from passlib.context import CryptContext
    import hashlib

    try:
        data = UserRegister(**body)
    except Exception as exc:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            raise HTTPException(status_code=422, detail=exc.errors())
        raise

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == data.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Create user
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    phone_hash = hashlib.sha256(data.phone.encode("utf-8")).hexdigest()

    from datetime import datetime as _dt
    dob_parsed = None
    if data.dob:
        try:
            dob_parsed = _dt.fromisoformat(data.dob)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid dob format. Use YYYY-MM-DD")

    user = User(
        email=data.email,
        password_hash=pwd_context.hash(data.password),
        name=data.name,
        phone=data.phone,
        phone_hash=phone_hash,
        dob=dob_parsed,
        gender=data.gender,
        address=data.address,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    from app.dependencies import create_user_token
    token = create_user_token(str(user.id))

    _set_patient_cookies(response, token)

    return {
        "status": "ok",
        "user_id": str(user.id),
        "profile_complete": False,
    }


@public_router.post("/auth/login")
async def patient_login(
    body: dict,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login patient with email and password.
    
    Sets HttpOnly cookie instead of returning token in body.
    """
    from app.schemas import UserLogin
    from passlib.context import CryptContext

    try:
        data = UserLogin(**body)
    except Exception as exc:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            raise HTTPException(status_code=422, detail=exc.errors())
        raise

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    if not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    from app.dependencies import create_user_token
    token = create_user_token(str(user.id))

    profile_complete = bool(user.blood_group)

    _set_patient_cookies(response, token)

    return {
        "status": "ok",
        "user_id": str(user.id),
        "profile_complete": profile_complete,
    }


@public_router.post("/auth/logout")
async def patient_logout(response: Response):
    """Logout patient — clears HttpOnly auth cookie."""
    _clear_patient_cookies(response)
    return {"status": "ok"}


@public_router.post("/auth/dev-login")
async def patient_dev_login(response: Response, db: AsyncSession = Depends(get_db)):
    """DEV ONLY — log in as a seeded demo user without registration.

    Guarded by settings.DEBUG. Creates/returns a demo User and returns
    a patient JWT + user_id in the same shape as login for backward compat.
    Sets HttpOnly cookie.
    """
    from app.config import settings as _settings
    if not _settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    from app.dependencies import create_user_token
    from passlib.context import CryptContext
    import hashlib

    DEV_EMAIL = "dev.patient@soloprac.local"
    DEV_PASSWORD = "devpass123"
    DEV_PHONE = "9999999999"
    phone_hash = hashlib.sha256(DEV_PHONE.encode("utf-8")).hexdigest()

    # Find or create dev user
    result = await db.execute(select(User).where(User.email == DEV_EMAIL).limit(1))
    user = result.scalar_one_or_none()

    if not user:
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        user = User(
            email=DEV_EMAIL,
            password_hash=pwd_context.hash(DEV_PASSWORD),
            name="Dev User",
            phone=DEV_PHONE,
            phone_hash=phone_hash,
            gender="other",
            address="Dev Address",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    profile_complete = bool(user.blood_group)

    return {
        "token": create_user_token(str(user.id)),
        "user_id": str(user.id),
        "patient_id": str(user.id),  # backward compat for existing frontend
        "token_type": "bearer",
        "profile_complete": profile_complete,
    }


# ─── Public: Doctor Search ──────────────────────────

@public_router.get("/doctors/search")
async def search_doctors(
    lat: Optional[float] = Query(None, ge=-90, le=90, description="Patient's latitude"),
    lng: Optional[float] = Query(None, ge=-180, le=180, description="Patient's longitude"),
    radius_km: float = Query(10.0, ge=1, le=100, description="Search radius in km"),
    speciality: Optional[str] = Query(None, description="Filter by speciality"),
    pincode: Optional[str] = Query(None, min_length=6, max_length=6, description="Indian PIN code"),
    q: Optional[str] = Query(None, description="Free-text search (name, clinic)"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search for doctors by location, speciality, name, or clinic address.

    Only returns verified doctors (they have submitted credentials).
    Uses PostGIS distance query when lat/lng provided.
    Falls back to text search on name/speciality/clinic/address.
    """
    query = select(Doctor).where(Doctor.verification_status == "verified")

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
    if pincode:
        query = query.where(Doctor.pincode == pincode)
    if q:
        query = query.where(
            Doctor.name.ilike(f"%{q}%") |
            Doctor.clinic_name.ilike(f"%{q}%") |
            Doctor.clinic_address.ilike(f"%{q}%") |
            Doctor.speciality.ilike(f"%{q}%")
        )

    query = query.limit(limit)
    result = await db.execute(query)
    has_distance = lat is not None and lng is not None
    if has_distance:
        rows = result.all()
    else:
        rows = result.scalars().all()

    doctors = []
    for row in rows:
        if has_distance:
            doc = row[0]
            distance = row[1] if len(row) > 1 else None
        else:
            doc = row
            distance = None

        d = {
            "id": str(doc.id),
            "name": doc.name,
            "speciality": doc.speciality,
            "clinic_name": doc.clinic_name,
            "clinic_address": doc.clinic_address,
            "location": str(doc.location) if doc.location else None,
            "phone": doc.phone,
            "registration_number": doc.registration_number,
            "verification_status": doc.verification_status,
            "photo_url": doc.photo_url,
            "years_experience": (datetime.now().year - doc.year_of_registration) if doc.year_of_registration else None,
        }
        if distance is not None:
            d["distance_km"] = round(float(distance), 2)
        doctors.append(d)

    # Sort by distance if available
    if doctors and doctors[0].get("distance_km") is not None:
        doctors.sort(key=lambda x: x["distance_km"])

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
        "verification_status": doc.verification_status,
        "photo_url": doc.photo_url,
        "years_experience": (datetime.now().year - doc.year_of_registration) if doc.year_of_registration else None,
        "settings": {
            "patient_booking_enabled": doc.settings.get("patient_booking_enabled", True),
            "auto_confirm_booking": doc.settings.get("auto_confirm_booking", False),
            "buffer_minutes": doc.settings.get("buffer_minutes_between_consults", 5),
            "default_duration": doc.settings.get("default_consult_duration", 20),
        },
        "available_slots": slots,
    }


async def _match_walkin_by_phone(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    user: User,
) -> Optional[Patient]:
    """Find an existing walk-in patient with matching phone and link to user.

    When a doctor manually creates a patient (walk-in), the patient has user_id=NULL.
    If that same person later registers as a User, we match by normalized phone number
    and link the existing Patient record to the new User account.

    Returns the matched Patient (now linked), or None if no match found.
    """
    from app.utils.phone import phones_match
    from app.services.encryption import decrypt_value

    if not user.phone:
        return None

    # Find all unlinked patients under this doctor
    result = await db.execute(
        select(Patient).where(
            Patient.doctor_id == doctor_id,
            Patient.user_id.is_(None),
        )
    )
    candidates = result.scalars().all()

    for patient in candidates:
        if not patient.phone_enc:
            continue
        try:
            plaintext = await decrypt_value(db, patient.phone_enc, "patient-phone")
            if phones_match(plaintext, user.phone):
                return patient
        except Exception as exc:
            logger.debug("Phone decrypt failed for patient %s: %s", patient.id, exc)
            continue

    return None


@patient_router.post("/appointments", status_code=status.HTTP_201_CREATED)
async def patient_book_appointment(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient books an appointment from the portal.

    Body: { doctor_id, start_at, end_at, reason }
    The user_id is taken from the authenticated patient JWT.
    If the user has no Patient record under this doctor, one is created
    on first booking (linked via user_id).
    """
    doctor_id = body.get("doctor_id")
    start_at_s = body.get("start_at")
    end_at_s = body.get("end_at")
    reason = body.get("reason", "")

    if not all([doctor_id, start_at_s, end_at_s]):
        raise HTTPException(status_code=400, detail="doctor_id, start_at, end_at required")

    doctor_uuid = uuid.UUID(doctor_id)

    # Verify doctor exists and has booking enabled
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_uuid))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if not doc.settings.get("patient_booking_enabled", True):
        raise HTTPException(status_code=403, detail="Doctor not accepting online bookings")

    try:
        start_at = datetime.fromisoformat(start_at_s)
        end_at = datetime.fromisoformat(end_at_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    # Set RLS session variable so Patient/PatientVersion DML doesn't fail
    await db.execute(
        text("SELECT set_config('app.current_doctor_id', :did, true)"),
        {"did": str(doctor_uuid)},
    )

    # Find or create Patient record for this user under this doctor
    result = await db.execute(
        select(Patient).where(
            Patient.user_id == user.id,
            Patient.doctor_id == doctor_uuid,
        ).order_by(Patient.created_at.desc()).limit(1)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        # ── Phone matching: check for existing walk-in patient ──
        # If the doctor manually created a patient (walk-in) with the same phone,
        # link it to this user instead of creating a duplicate.
        patient = await _match_walkin_by_phone(db, doctor_uuid, user)

        if not patient:
            # No match found — create new patient
            patient = Patient(
                doctor_id=doctor_uuid,
                user_id=user.id,
            )
            db.add(patient)
            await db.flush()
            # Mint v1 version — auto-fill from User profile
            demographics = {
                "name": user.name,
                "phone": user.phone,
                "email": user.email,
            }
            if user.dob:
                demographics["dob"] = user.dob.isoformat()
            if user.gender:
                demographics["gender"] = user.gender
            if user.address:
                demographics["address"] = user.address
            # Auto-fill medical profile if available
            if user.blood_group:
                demographics["blood_group"] = user.blood_group
            if user.allergies:
                demographics["allergies"] = user.allergies
            if user.known_conditions:
                demographics["known_conditions"] = user.known_conditions
            if user.height_cm:
                demographics["height_cm"] = user.height_cm
            if user.weight_kg:
                demographics["weight_kg"] = user.weight_kg
            if user.emergency_contact_name:
                demographics["emergency_contact_name"] = user.emergency_contact_name
            if user.emergency_contact_phone:
                demographics["emergency_contact_phone"] = user.emergency_contact_phone
            if user.insurance_info:
                demographics["insurance_info"] = user.insurance_info

            initial_state = {
                "demographics": demographics,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            version = PatientVersion(
                patient_id=patient.id,
                doctor_id=doctor_uuid,
                version_number=1,
                state_jsonb=initial_state,
                version_hash=PatientVersion.compute_hash(initial_state),
                author=f"user:{user.id}",
                edit_type="manual",
                summary="Auto-created on first booking",
                tags=["demographics"],
                clinical_significance=0.0,
            )
            db.add(version)
            await db.flush()
            patient.head_version_id = version.id
            await db.flush()
            logger.info(
                "Created patient %s for user %s under doctor %s (first booking)",
                patient.id, user.id, doctor_uuid,
            )
        else:
            # ── Walk-in patient found — link to this user ──
            patient.user_id = user.id
            await db.flush()
            logger.info(
                "Linked walk-in patient %s to user %s (phone match under doctor %s)",
                patient.id, user.id, doctor_uuid,
            )

    try:
        apt = await create_appointment(
            db=db,
            doctor_id=doctor_uuid,
            patient_id=patient.id,
            start_at=start_at,
            end_at=end_at,
            reason=reason,
            source="patient_portal",
            send_notification=True,
            telemedicine_consent=body.get("telemedicine_consent", False),
        )
        return apt
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@patient_router.get("/me/profile")
async def get_patient_profile(
    user: User = Depends(get_current_user),
):
    """Get current user's profile including medical details."""
    profile_complete = bool(user.blood_group)
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "phone": user.phone,
        "dob": user.dob.isoformat() if user.dob else None,
        "gender": user.gender,
        "address": user.address,
        "blood_group": user.blood_group,
        "allergies": user.allergies,
        "known_conditions": user.known_conditions,
        "height_cm": user.height_cm,
        "weight_kg": user.weight_kg,
        "emergency_contact_name": user.emergency_contact_name,
        "emergency_contact_phone": user.emergency_contact_phone,
        "insurance_info": user.insurance_info,
        "profile_complete": profile_complete,
    }


@patient_router.put("/me/profile")
async def update_patient_profile(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile fields — medical details, contact info, etc."""
    from app.schemas import UserUpdate
    from pydantic import ValidationError

    try:
        update_data = UserUpdate(**body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    updated_fields = []
    for field, value in update_data.model_dump(exclude_none=True).items():
        if field == "dob" and value:
            from datetime import datetime as _dt
            try:
                value = _dt.fromisoformat(value)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid dob format. Use YYYY-MM-DD")
        setattr(user, field, value)
        updated_fields.append(field)

    if not updated_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.commit()
    await db.refresh(user)

    profile_complete = bool(user.blood_group)

    return {
        "status": "ok",
        "updated_fields": updated_fields,
        "profile_complete": profile_complete,
    }

@patient_router.get("/me/inbox")
async def patient_inbox(
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get patient's notifications across all doctors they visit.

    Each notification includes the doctor name/clinic so the user
    knows which clinic sent it.
    """
    # Collect all patient IDs for this user across doctors
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        return []

    result = await db.execute(
        select(PatientNotification, Doctor.name, Doctor.speciality, Doctor.clinic_name)
        .join(Doctor, Doctor.id == PatientNotification.doctor_id)
        .where(PatientNotification.patient_id.in_(patient_ids))
        .order_by(PatientNotification.created_at.desc())
        .limit(limit)
    )
    notifications = result.all()
    return [
        {
            "id": str(n.id),
            "kind": n.kind,
            "subject": n.subject,
            "body": n.body,
            "read": n.read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "doctor": {
                "name": doc_name,
                "speciality": doc_speciality,
                "clinic_name": doc_clinic,
            },
            "meta": n.meta,
        }
        for n, doc_name, doc_speciality, doc_clinic in notifications
    ]


@patient_router.patch("/me/inbox/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(status_code=404, detail="Notification not found")

    result = await db.execute(
        select(PatientNotification).where(
            PatientNotification.id == notification_id,
            PatientNotification.patient_id.in_(patient_ids),
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.read = True
    await db.commit()
    return {"ok": True, "read": True}


@patient_router.get("/me/reports")
async def patient_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get patient's medical reports across all doctors they visit."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        return {"prescriptions": [], "invoices": [], "certificates": []}

    # Prescriptions
    rx_result = await db.execute(
        select(PrescriptionBox).where(PrescriptionBox.patient_id.in_(patient_ids))
    )
    rxs = rx_result.scalars().all()

    # Invoices
    inv_result = await db.execute(
        select(Invoice).where(Invoice.patient_id.in_(patient_ids))
    )
    invs = inv_result.scalars().all()

    # Certificates
    cert_result = await db.execute(
        select(Certificate).where(Certificate.patient_id.in_(patient_ids))
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


@patient_router.get("/me/prescriptions/{prescription_id}/pdf")
async def patient_download_prescription_pdf(
    prescription_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a prescription PDF — patient version."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(status_code=404, detail="No patient records found")

    result = await db.execute(
        select(PrescriptionBox).where(
            PrescriptionBox.id == prescription_id,
            PrescriptionBox.patient_id.in_(patient_ids),
        )
    )
    rx = result.scalar_one_or_none()
    if not rx or not rx.pdf_path:
        raise HTTPException(status_code=404, detail="Prescription PDF not found")

    from fastapi.responses import RedirectResponse
    presigned_url = await storage_service.get_presigned_url("pdfs", rx.pdf_path)
    if presigned_url:
        return RedirectResponse(url=presigned_url, status_code=302)

    import os
    if os.path.isabs(rx.pdf_path) and os.path.exists(rx.pdf_path):
        from fastapi.responses import FileResponse
        return FileResponse(rx.pdf_path, media_type="application/pdf", filename=f"prescription_{prescription_id}.pdf")

    raise HTTPException(status_code=404, detail="PDF file not found on storage")


@patient_router.get("/me/invoices/{invoice_id}/pdf")
async def patient_download_invoice_pdf(
    invoice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download an invoice PDF — patient version."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(status_code=404, detail="No patient records found")

    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.patient_id.in_(patient_ids),
        )
    )
    inv = result.scalar_one_or_none()
    if not inv or not inv.pdf_path:
        raise HTTPException(status_code=404, detail="Invoice PDF not found")

    from fastapi.responses import RedirectResponse
    presigned_url = await storage_service.get_presigned_url("pdfs", inv.pdf_path)
    if presigned_url:
        return RedirectResponse(url=presigned_url, status_code=302)

    import os
    if os.path.isabs(inv.pdf_path) and os.path.exists(inv.pdf_path):
        from fastapi.responses import FileResponse
        return FileResponse(inv.pdf_path, media_type="application/pdf", filename=f"invoice_{inv.invoice_number}.pdf")

    raise HTTPException(status_code=404, detail="PDF file not found on storage")


@patient_router.get("/me/certificates/{certificate_id}/pdf")
async def patient_download_certificate_pdf(
    certificate_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a certificate PDF — patient version."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(status_code=404, detail="No patient records found")

    from app.models import Certificate
    result = await db.execute(
        select(Certificate).where(
            Certificate.id == certificate_id,
            Certificate.patient_id.in_(patient_ids),
        )
    )
    cert = result.scalar_one_or_none()
    if not cert or not cert.pdf_path:
        raise HTTPException(status_code=404, detail="Certificate PDF not found")

    from fastapi.responses import RedirectResponse
    presigned_url = await storage_service.get_presigned_url("pdfs", cert.pdf_path)
    if presigned_url:
        return RedirectResponse(url=presigned_url, status_code=302)

    import os
    if os.path.isabs(cert.pdf_path) and os.path.exists(cert.pdf_path):
        from fastapi.responses import FileResponse
        return FileResponse(cert.pdf_path, media_type="application/pdf", filename=f"certificate_{certificate_id}.pdf")

    raise HTTPException(status_code=404, detail="PDF file not found on storage")


@patient_router.get("/me/appointments")
async def patient_appointments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get patient's appointments across all doctors they visit."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        return []

    result = await db.execute(
        select(Appointment)
        .where(Appointment.patient_id.in_(patient_ids))
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


@patient_router.get("/me/weekly-report/pdf")
async def patient_weekly_report_pdf(
    layout: str = Query("family_friendly", description="Layout: clinical, executive, family_friendly"),
    days: int = Query(7, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download patient's weekly clinical report as PDF (patient portal)."""
    from app.services.weekly_report import WeeklyReportService, REPORT_LAYOUTS
    from app.services.pdf_generator import pdf_generator

    if layout not in REPORT_LAYOUTS:
        raise HTTPException(status_code=400, detail=f"Invalid layout. Choose from: {REPORT_LAYOUTS}")

    # Get the user's first patient record (primary doctor) for report generation
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(status_code=404, detail="No patient record found — book an appointment first")

    # Use the first patient for report generation
    patient_id = patient_ids[0]
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Generate the report for this patient
    service = WeeklyReportService()
    report = await service.generate_report(db, patient.id, layout, days)

    if report.get("error"):
        raise HTTPException(status_code=404, detail=report.get("error"))

    # Generate QR verification code for the patient report
    try:
        from app.services.pdf_security import PDFSecurityService
        pss = PDFSecurityService()
        verification_code = f"WR-{uuid.uuid4().hex[:8].upper()}-{datetime.now(timezone.utc).strftime('%Y%m')}"
        verify_url = f"http://{('localhost')}/api/v1/certificates/verify/{verification_code}"
        qr_path = await pss.generate_qr_code(verify_url, size=80)
        import base64
        with open(qr_path, "rb") as f:
            qr_b64 = base64.b64encode(f.read()).decode()
        qr_data_uri = f"data:image/png;base64,{qr_b64}"
        import os as _os
        try:
            _os.remove(qr_path)
        except OSError:
            pass
        report["qr_code"] = qr_data_uri
        report["verify_url"] = verify_url
    except Exception as exc:
        logger.warning("QR generation failed (non-blocking): %s", exc)
        report["qr_code"] = ""
        report["verify_url"] = ""

    # Generate PDF
    import uuid
    patient_name = report.get("patient_name", f"Patient {str(patient.id)[:8]}")
    filename = f"weekly_report_{patient.id}_{layout}_{uuid.uuid4().hex[:8]}.pdf"

    pdf_path = await pdf_generator.generate_weekly_report(
        report_data=report,
        db=db,
        doctor_id=patient.doctor_id,
    )

    # Read and return PDF
    import os
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ── WebSocket endpoints (mounted under api_router) ──

@router.websocket("/ws/doctor/{doctor_id}")
async def doctor_websocket(doctor_id: str, websocket: WebSocket, token: str = Query("")):
    """WebSocket for doctor real-time alerts (risk alerts, notifications).

    Connect: ws://host/api/v1/ws/doctor/{doctor_id}?token=JWT_TOKEN
    The doctor JWT token is required as a query parameter.
    Verifies that the doctor_id in the URL matches the authenticated doctor.

    Registers with ws_manager so background jobs (Feature E risk scan) can
    push alerts here via ws_manager.notify_doctor.
    """
    from jose import jwt as _jwt, JWTError as _JWTError
    from app.config import settings as _settings
    try:
        payload = _jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
        token_sub = payload.get("sub")
        if not token_sub or token_sub != doctor_id:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    except _JWTError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect_doctor(doctor_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_manager.disconnect_doctor(doctor_id, websocket)
    except Exception as exc:
        logger.warning("Doctor WebSocket error: %s", exc)
        await ws_manager.disconnect_doctor(doctor_id, websocket)


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection stats."""
    return {"active_connections": ws_manager.active_connections}


# ─── Helper: resolve User → Patient IDs across doctors ───

async def _get_user_patient_ids(db: AsyncSession, user_id: UUID) -> List[UUID]:
    """Return all Patient IDs belonging to this user across all doctors.

    A user can be a patient at multiple clinics — this collects all of them.
    Returns an empty list if the user hasn't been seen by any doctor yet.
    """
    result = await db.execute(
        select(Patient.id).where(Patient.user_id == user_id)
    )
    return list(result.scalars().all())
