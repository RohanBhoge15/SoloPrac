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

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, get_db
from app.dependencies import get_current_user
from app.models import (
    Appointment,
    Certificate,
    Doctor,
    Invoice,
    Patient,
    PatientNotification,
    PatientVersion,
    PrescriptionBox,
    User,
)
from app.services.calendar_service import create_appointment, find_available_slots
from app.services.clinical_significance import clinical_significance_from_tags
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


async def _link_walkins_to_user(db: AsyncSession, user: User) -> int:
    """Auto-link every STRONG walk-in match for this user (phone + dob or
    phone + fuzzy-name). Weak (phone-only) matches are left unlinked and
    surface on the pending-matches list, where the user can self-claim.

    Returns count of walk-ins auto-linked.
    """
    from app.services.linking import strong_link_walkins_to_user

    return await strong_link_walkins_to_user(db, user)


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
        self.register(patient_id, websocket)

    def register(self, patient_id: str, websocket: WebSocket):
        """Add an ALREADY-accepted socket to a patient stream.

        Split out from connect() because one portal socket subscribes to several
        keys at once (the user id plus every clinic patient row it owns), and
        websocket.accept() may only be called once per connection.
        """
        self._patient_connections.setdefault(patient_id, []).append(websocket)
        logger.info(
            "WebSocket connected: patient=%s (%d active)", patient_id, len(self._patient_connections[patient_id])
        )

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

    Auth: reads JWT from `?token=` query param OR the `patient_token` HttpOnly cookie
    (same cookie that the HTTP APIs use). This matches the browser flow where the
    cookie is already set by /public/auth/login and JS cannot read it to append
    to the WS URL.
    """
    # Verify patient JWT token before accepting connection
    from jose import JWTError as _JWTError
    from jose import jwt as _jwt

    from app.config import settings as _settings

    # Cookie fallback — browsers automatically attach the same-origin cookie on
    # the WS handshake.
    if not token:
        token = websocket.cookies.get("patient_token", "") or ""

    try:
        payload = _jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
        if payload.get("type") != "patient":
            await websocket.close(code=4001, reason="Unauthorized")
            return
        user_id = payload.get("sub")
    except _JWTError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Resolve which notification streams this socket may subscribe to.
    #
    # The URL param is historically named `patient_id`, but the portal only ever
    # knows the logged-in User id (`/patient/me/profile` returns the user row) —
    # a User owns MANY Patient rows, one per clinic they visit. Meanwhile the
    # SENDER keys events by Patient id (notification_generator.notify_patient).
    #
    # So we accept either form and always subscribe to the *set* of patient row
    # ids owned by this user:
    #   - user id  → every Patient row with user_id == sub
    #   - patient id → that row, but only if it is owned by sub
    #
    # Previously the endpoint required a `patient_id` JWT claim that
    # create_user_token never sets, so every handshake closed 4001 (a 403 in the
    # browser) — and even had it passed, the frontend subscribes with the user
    # id while the sender publishes to patient ids, so no event could ever be
    # delivered. Both halves are fixed here.
    try:
        _req_uuid = uuid.UUID(patient_id)
    except ValueError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    try:
        async with async_session_maker() as _s:
            from app.database import set_rls_context

            # WebSockets bypass the HTTP middleware — set the user identity so
            # the patient_self_access RLS policy admits this user's rows.
            await set_rls_context(_s, user_id=str(user_id))
            _owned = (
                (await _s.execute(select(Patient.id).where(Patient.user_id == uuid.UUID(str(user_id))))).scalars().all()
            )
            owned_ids = {str(pid) for pid in _owned}

            if str(_req_uuid) in owned_ids:
                # Subscribed by a specific patient row this user owns.
                keys = {str(_req_uuid)}
            elif str(_req_uuid) == str(user_id):
                # Subscribed by user id — fan out over every clinic record.
                keys = set(owned_ids)
            else:
                # Neither their own user id nor a row they own → reject.
                await websocket.close(code=4001, reason="Unauthorized")
                return
    except Exception as _exc:
        logger.warning("WS auth ownership lookup failed for %s: %s", patient_id, _exc)
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Always register the user id too, so events published before the first
    # clinic record exists (and any user-scoped events) still arrive.
    keys.add(str(user_id))

    await websocket.accept()
    for k in keys:
        ws_manager.register(k, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        for k in keys:
            await ws_manager.disconnect(k, websocket)
    except Exception as exc:
        logger.warning("WebSocket error for patient %s: %s", patient_id, exc)
        for k in keys:
            await ws_manager.disconnect(k, websocket)


# ─── Public: Patient Auth ────────────────────────────


@public_router.post("/auth/register", status_code=201)
async def patient_register(
    response: Response,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Register a new patient with email and password.

    Sets JWT patient token as HttpOnly cookie.
    """
    import hashlib

    from passlib.context import CryptContext

    from app.schemas import UserRegister

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

    # Backfill any pre-existing walk-in Patient rows whose phone matches this
    # user, so a doctor's manual entry auto-connects on signup.
    linked_count = 0
    matched_doctor_ids: set = set()
    try:
        # C-9 (Piece 5.2): peek at every candidate walk-in BEFORE the strong
        # linker mutates the DB so we can notify the doctors whose walk-ins
        # matched (both strong-linked and weak/pending). Dedup by doctor_id.
        try:
            from app.services.linking import find_candidates_for_user

            candidates = await find_candidates_for_user(db, user)
            matched_doctor_ids = {c.patient.doctor_id for c in candidates if c.patient and c.patient.doctor_id}
        except Exception as exc:
            logger.debug("candidate scan for doctor notify failed: %s", exc)

        linked_count = await _link_walkins_to_user(db, user)
        if linked_count:
            await db.commit()
    except Exception as exc:
        logger.warning("Walk-in auto-link failed for user %s: %s", user.id, exc)
        await db.rollback()

    # C-9 (Piece 5.2): dispatch pending_matches_available to each matched
    # doctor (deduped). Never re-raise — a notification failure must not
    # sink the user's registration.
    if matched_doctor_ids:
        try:
            from app.services.notification_generator import dispatch_doctor_event

            for did in matched_doctor_ids:
                try:
                    await dispatch_doctor_event(
                        db,
                        event_type="pending_matches_available",
                        doctor_id=did,
                        subject="New account matches your patient record",
                        body=(
                            f"A new user ({user.name}) just registered with a phone "
                            f"number that matches one of your walk-in patient records. "
                            f"Review pending matches in the patient portal."
                        ),
                        meta={
                            "resource_type": "pending_matches",
                            "user_id": str(user.id),
                            "patient_name": user.name,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "dispatch_doctor_event(pending_matches_available) doctor=%s failed: %s",
                        did,
                        exc,
                    )
        except Exception as exc:
            logger.warning("pending_matches notification batch failed: %s", exc)

    from app.dependencies import create_user_token

    token = create_user_token(str(user.id))

    _set_patient_cookies(response, token)

    return {
        "status": "ok",
        "user_id": str(user.id),
        "email": user.email,
        "profile_complete": False,
        "linked_walkins": linked_count,
        "access_token": token,
        "token": token,
        "token_type": "bearer",
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
    from passlib.context import CryptContext

    from app.schemas import UserLogin

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

    # Re-run walk-in linking on every login so that doctors added AFTER signup
    # also get auto-connected. Cheap when no candidates exist (SELECT + empty
    # loop); avoids the "I signed up but doctor added me later" gap.
    try:
        n = await _link_walkins_to_user(db, user)
        if n:
            await db.commit()
    except Exception as exc:
        logger.warning("login walk-in link failed for user %s: %s", user.id, exc)
        await db.rollback()

    from app.dependencies import create_user_token

    token = create_user_token(str(user.id))

    profile_complete = bool(user.blood_group)

    _set_patient_cookies(response, token)

    return {
        "status": "ok",
        "user_id": str(user.id),
        "email": user.email,
        "profile_complete": profile_complete,
        "access_token": token,
        "token": token,
        "token_type": "bearer",
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

    import hashlib

    from passlib.context import CryptContext

    from app.dependencies import create_user_token

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

    # Backfill any walk-ins matching this dev user's phone, so that a doctor
    # who added a walk-in with phone 9999999999 sees it linked next dev-login.
    try:
        n = await _link_walkins_to_user(db, user)
        if n:
            await db.commit()
    except Exception as exc:
        logger.warning("dev-login walk-in link failed: %s", exc)
        await db.rollback()

    profile_complete = bool(user.blood_group)
    token = create_user_token(str(user.id))
    # Actually set the HttpOnly cookie so subsequent authenticated requests work
    # (the JS layer cannot read HttpOnly cookies to attach as Authorization).
    _set_patient_cookies(response, token)

    return {
        "token": token,
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
        # PostGIS geography distance query (ST_Distance returns metres)
        patient_point = text(f"ST_SetSRID(ST_MakePoint({lng}, {lat}), 4326)::geography")
        distance_col = func.ST_Distance(Doctor.location, patient_point).label("distance_m")
        query = query.add_columns(distance_col)
        # Only return doctors within the requested radius (metres)
        query = query.where(func.ST_DWithin(Doctor.location, patient_point, radius_km * 1000))
        query = query.order_by(distance_col)

    if speciality:
        query = query.where(Doctor.speciality.ilike(f"%{speciality}%"))
    if pincode:
        query = query.where(Doctor.pincode == pincode)
    if q:
        query = query.where(
            Doctor.name.ilike(f"%{q}%")
            | Doctor.clinic_name.ilike(f"%{q}%")
            | Doctor.clinic_address.ilike(f"%{q}%")
            | Doctor.speciality.ilike(f"%{q}%")
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
            distance_m = row[1] if len(row) > 1 else None
            distance = round(float(distance_m) / 1000.0, 2) if distance_m is not None else None
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
            d["distance_km"] = distance
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
        "location": str(doc.location) if doc.location else None,
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
    from app.services.encryption import decrypt_value
    from app.utils.phone import phones_match

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
        select(Patient)
        .where(
            Patient.user_id == user.id,
            Patient.doctor_id == doctor_uuid,
        )
        .order_by(Patient.created_at.desc())
        .limit(1)
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
                clinical_significance=clinical_significance_from_tags(["demographics"]),
            )
            db.add(version)
            await db.flush()
            patient.head_version_id = version.id
            await db.flush()
            logger.info(
                "Created patient %s for user %s under doctor %s (first booking)",
                patient.id,
                user.id,
                doctor_uuid,
            )
        else:
            # ── Walk-in patient found — link to this user ──
            patient.user_id = user.id
            await db.flush()
            logger.info(
                "Linked walk-in patient %s to user %s (phone match under doctor %s)",
                patient.id,
                user.id,
                doctor_uuid,
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
        # C-9 (Piece 5.1): tell the doctor a patient just booked. Wrapped so
        # a notification failure never rolls back the booking itself.
        try:
            from app.services.notification_generator import dispatch_doctor_event

            appt_id = apt.get("id") if isinstance(apt, dict) else getattr(apt, "id", None)
            start_fmt = start_at.strftime("%a %b %d, %I:%M %p")
            await dispatch_doctor_event(
                db,
                event_type="appointment_booked_by_patient",
                doctor_id=doctor_uuid,
                subject=f"New booking from {user.name}",
                body=(f"{user.name} booked an appointment for {start_fmt}. Reason: {reason or 'not specified'}."),
                meta={
                    "resource_type": "appointment",
                    "resource_id": str(appt_id) if appt_id else None,
                    "patient_name": user.name,
                    "appointment_time": start_at.isoformat(),
                },
                patient_id=patient.id,
            )
        except Exception as exc:  # noqa: BLE001 — never break booking on notif failure
            logger.warning("dispatch_doctor_event(appointment_booked_by_patient) failed: %s", exc)
        return apt
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@patient_router.get("/me/profile")
async def get_patient_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's profile including medical details.

    Also returns pending_matches_count so the frontend can show a "N clinic
    records match your phone — tap to review" banner without an extra roundtrip.
    """
    profile_complete = bool(user.blood_group)

    # Count weak-match walk-ins the user hasn't claimed/rejected yet.
    # Kept cheap — same scan the /pending-matches endpoint does.
    pending_count = 0
    try:
        from app.services.linking import find_candidates_for_user

        matches = await find_candidates_for_user(db, user)
        pending_count = sum(1 for m in matches if not m.strong)
    except Exception as exc:
        logger.debug("pending_matches_count failed: %s", exc)

    # Historical note: four patient pages (DoctorSearch, PatientReports,
    # PatientAppointments, PatientInbox) read `user_id`, one reads `id ?? user_id`,
    # and this router originally returned only `id`. That silently broke every
    # `user_id`-reading page — `patientId` stayed empty and the page showed
    # "Please log in" to authenticated users. Emit BOTH keys so all callers work
    # without a coordinated frontend deploy.
    return {
        "id": str(user.id),
        "user_id": str(user.id),
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
        "pending_matches_count": pending_count,
    }


@patient_router.put("/me/profile")
async def update_patient_profile(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile fields — medical details, contact info, etc."""
    from pydantic import ValidationError

    from app.schemas import UserUpdate

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
    rx_result = await db.execute(select(PrescriptionBox).where(PrescriptionBox.patient_id.in_(patient_ids)))
    rxs = rx_result.scalars().all()

    # Invoices
    inv_result = await db.execute(select(Invoice).where(Invoice.patient_id.in_(patient_ids)))
    invs = inv_result.scalars().all()

    # Certificates
    cert_result = await db.execute(select(Certificate).where(Certificate.patient_id.in_(patient_ids)))
    certs = cert_result.scalars().all()

    return {
        "prescriptions": [
            {
                "id": str(r.id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "has_pdf": bool(r.pdf_path),
            }
            for r in rxs
        ],
        "invoices": [
            {
                "id": str(i.id),
                "invoice_number": i.invoice_number,
                "total": i.total,
                "status": i.status,
                "has_pdf": bool(i.pdf_path),
            }
            for i in invs
        ],
        "certificates": [
            {
                "id": str(c.id),
                "cert_type": c.cert_type,
                "verification_code": c.verification_code,
                "has_pdf": bool(c.pdf_path),
            }
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

    # Serve the PDF bytes directly so clients (browser/portal) can download it
    from fastapi.responses import Response

    try:
        pdf_bytes = await storage_service.download_file("pdfs", rx.pdf_path)
    except Exception as exc:
        logger.warning("Failed to fetch prescription PDF from storage: %s", exc)
        pdf_bytes = None

    if pdf_bytes:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="prescription_{prescription_id}.pdf"'},
        )

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

    from fastapi.responses import Response

    try:
        pdf_bytes = await storage_service.download_file("pdfs", inv.pdf_path)
    except Exception as exc:
        logger.warning("Failed to fetch invoice PDF from storage: %s", exc)
        pdf_bytes = None

    if pdf_bytes:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="invoice_{inv.invoice_number}.pdf"'},
        )

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

    from fastapi.responses import Response

    try:
        pdf_bytes = await storage_service.download_file("pdfs", cert.pdf_path)
    except Exception as exc:
        logger.warning("Failed to fetch certificate PDF from storage: %s", exc)
        pdf_bytes = None

    if pdf_bytes:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="certificate_{certificate_id}.pdf"'},
        )

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
        select(Appointment).where(Appointment.patient_id.in_(patient_ids)).order_by(Appointment.start_at.desc())
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


@patient_router.post("/me/appointments/{appointment_id}/cancel")
async def patient_cancel_appointment(
    appointment_id: uuid.UUID,
    body: dict = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient cancels their own appointment. The doctor's calendar updates live."""
    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(status_code=404, detail="No patient record found")

    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.patient_id.in_(patient_ids),
        )
    )
    apt = result.scalar_one_or_none()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if apt.status == "cancelled":
        return {"id": str(apt.id), "status": "cancelled"}

    reason = (body or {}).get("reason") or "Cancelled by patient"
    # Allow the appointment update under RLS by setting the clinic context.
    await db.execute(
        text("SELECT set_config('app.current_doctor_id', :did, true)"),
        {"did": str(apt.doctor_id)},
    )
    from app.services import calendar_service

    await calendar_service.cancel_appointment(
        db,
        doctor_id=apt.doctor_id,
        appointment_id=apt.id,
        reason=reason,
        notify_patient=True,
    )

    # Notify the doctor explicitly (inbox + bell), not just a silent calendar change.
    try:
        from app.services.notification_generator import dispatch_doctor_event

        start_fmt = apt.start_at.strftime("%a %b %d, %I:%M %p")
        await dispatch_doctor_event(
            db,
            event_type="appointment_cancelled_by_patient",
            doctor_id=apt.doctor_id,
            subject=f"Cancellation from {user.name}",
            body=f"{user.name} cancelled their appointment scheduled for {start_fmt}.",
            meta={"resource_type": "appointment", "resource_id": str(apt.id)},
            patient_id=apt.patient_id,
        )
    except Exception as exc:  # noqa: BLE001 — never break cancel on notif failure
        logger.warning("dispatch_doctor_event(appointment_cancelled_by_patient) failed: %s", exc)

    return {"id": str(apt.id), "status": "cancelled"}


@patient_router.post("/me/appointments/{appointment_id}/reschedule")
async def patient_reschedule_appointment(
    appointment_id: uuid.UUID,
    body: dict = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient reschedules (postpone/prepone) to a new slot from doctor availability."""
    start_at_s = (body or {}).get("start_at")
    end_at_s = (body or {}).get("end_at")
    if not all([start_at_s, end_at_s]):
        raise HTTPException(status_code=400, detail="start_at and end_at required")
    try:
        new_start = datetime.fromisoformat(start_at_s)
        new_end = datetime.fromisoformat(end_at_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    patient_ids = await _get_user_patient_ids(db, user.id)
    if not patient_ids:
        raise HTTPException(status_code=404, detail="No patient record found")

    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.patient_id.in_(patient_ids),
        )
    )
    apt = result.scalar_one_or_none()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if apt.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot reschedule a cancelled appointment")

    await db.execute(
        text("SELECT set_config('app.current_doctor_id', :did, true)"),
        {"did": str(apt.doctor_id)},
    )
    from app.services import calendar_service

    await calendar_service.reschedule_appointment(
        db,
        doctor_id=apt.doctor_id,
        appointment_id=apt.id,
        new_start=new_start,
        new_end=new_end,
        reason="Rescheduled by patient",
        notify_patient=True,
    )

    # Notify the doctor explicitly (inbox + bell) about the patient-initiated move.
    try:
        from app.services.notification_generator import dispatch_doctor_event

        start_fmt = new_start.strftime("%a %b %d, %I:%M %p")
        await dispatch_doctor_event(
            db,
            event_type="appointment_rescheduled_by_patient",
            doctor_id=apt.doctor_id,
            subject=f"Reschedule from {user.name}",
            body=f"{user.name} moved their appointment to {start_fmt}.",
            meta={"resource_type": "appointment", "resource_id": str(apt.id)},
            patient_id=apt.patient_id,
        )
    except Exception as exc:  # noqa: BLE001 — never break reschedule on notif failure
        logger.warning("dispatch_doctor_event(appointment_rescheduled_by_patient) failed: %s", exc)

    return {
        "id": str(apt.id),
        "start_at": new_start.isoformat(),
        "end_at": new_end.isoformat(),
        "status": apt.status,
    }


# ─── Pending matches (walk-in disambiguation) ───


@patient_router.get("/me/pending-matches")
async def patient_pending_matches(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List walk-in Patient records that phone-match this user but are NOT
    strong-linked (dob/name differ). The patient reviews these one at a time
    on the portal and taps Claim or Not-me. Doctors never see this list.

    Each entry includes the clinic name/doctor so the patient can recognise
    the context (e.g. "Dr. Mehta's clinic added a record on 12 Mar").
    """
    from app.services.linking import find_candidates_for_user

    matches = await find_candidates_for_user(db, user)
    # Only weak candidates go here — strong ones were already linked automatically.
    weak = [m for m in matches if not m.strong]
    if not weak:
        return []

    doctor_ids = {uuid.UUID(m.patient.doctor_id) for m in weak}
    doctor_rows = await db.execute(select(Doctor).where(Doctor.id.in_(doctor_ids)))
    doctor_map = {d.id: d for d in doctor_rows.scalars().all()}

    out = []
    for m in weak:
        d = doctor_map.get(uuid.UUID(m.patient.doctor_id))
        demo = m.patient.head_demo or {}
        out.append(
            {
                "patient_id": m.patient.id,
                "clinic_name": d.clinic_name if d else None,
                "doctor_name": d.name if d else None,
                "doctor_speciality": d.speciality if d else None,
                "created_at": m.patient.created_at.isoformat() if m.patient.created_at else None,
                # Show enough demographics to help the user recognise the record —
                # never leak someone else's phone number.
                "record_name": demo.get("name"),
                "record_dob": demo.get("dob"),
                "record_gender": demo.get("gender"),
            }
        )
    return out


@patient_router.post("/me/claim/{patient_id}")
async def patient_claim_walkin(
    patient_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient confirms 'yes, that walk-in is me'. Sets Patient.user_id.

    Only walk-ins whose phone matches this user AND are still unlinked can
    be claimed — protects against a malicious user trying to grab records
    that belong to a different phone number.
    """
    from app.services.linking import find_candidates_for_user

    # Verify eligibility via the same matcher — cheap, and prevents any bypass.
    # (The walk-in row itself is invisible under RLS — user_id IS NULL — so the
    # claim update runs through the sanctioned SECURITY DEFINER helper.)
    matches = await find_candidates_for_user(db, user)
    eligible = {m.patient.id for m in matches}
    if str(patient_id) not in eligible:
        raise HTTPException(status_code=403, detail="Not eligible to claim this record")

    res = await db.execute(
        text("SELECT public.claim_walkin(:pid, :uid)"),
        {"pid": str(patient_id), "uid": str(user.id)},
    )
    claimed = res.scalar()
    if not claimed:
        raise HTTPException(status_code=409, detail="Already claimed")
    logger.info("User %s manually claimed walk-in %s", user.id, patient_id)
    return {"status": "ok", "patient_id": str(patient_id)}


@patient_router.post("/me/reject/{patient_id}")
async def patient_reject_walkin(
    patient_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient says 'no, that walk-in isn't me'. Adds this user to the
    patient's rejected list so we never re-surface it to them.
    """
    # The row is invisible under RLS (user_id IS NULL) — the append runs via
    # the sanctioned SECURITY DEFINER helper, which also no-ops on already-
    # claimed walk-ins and is idempotent per user.
    res = await db.execute(
        text("SELECT public.reject_walkin(:pid, :uid)"),
        {"pid": str(patient_id), "uid": str(user.id)},
    )
    if res.scalar():
        logger.info("User %s rejected walk-in %s", user.id, patient_id)
    return {"status": "ok", "patient_id": str(patient_id)}


@patient_router.get("/me/weekly-report/pdf")
async def patient_weekly_report_pdf(
    layout: str = Query("family_friendly", description="Layout: clinical, executive, family_friendly"),
    days: int = Query(7, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download patient's weekly clinical report as PDF (patient portal)."""
    from app.services.pdf_generator import pdf_generator
    from app.services.weekly_report import REPORT_LAYOUTS, WeeklyReportService

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
        from app.config import settings as _settings
        from app.services.pdf_security import PDFSecurityService

        pss = PDFSecurityService()
        verification_code = f"WR-{uuid.uuid4().hex[:8].upper()}-{datetime.now(timezone.utc).strftime('%Y%m')}"
        # Prior URL had TWO bugs: (1) hardcoded `http://localhost/...` — a QR
        # scanned outside the dev machine would resolve to the scanner's own
        # localhost; (2) it pointed at `/certificates/verify/{code}` but the
        # code is WR-prefixed (weekly report). The doctor-side weekly-report
        # router already uses the correct pattern — mirror it.
        _domain = _settings.DOMAIN or "localhost"
        _port = _settings.PORT
        verify_url = f"http://{_domain}:{_port}/api/v1/weekly-report/verify/{verification_code}"
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

    if not pdf_path:
        raise HTTPException(status_code=404, detail="Report PDF could not be generated")

    # Serve the PDF bytes directly so clients (browser/portal) can download it
    from fastapi.responses import Response

    try:
        pdf_bytes = await storage_service.download_file("pdfs", pdf_path)
    except Exception as exc:
        logger.warning("Failed to fetch weekly report PDF from storage: %s", exc)
        pdf_bytes = None

    if pdf_bytes:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    import os

    if os.path.isabs(pdf_path) and os.path.exists(pdf_path):
        from fastapi.responses import FileResponse

        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=filename,
        )

    raise HTTPException(status_code=404, detail="Report PDF file not found on storage")


# ── WebSocket endpoints (mounted under api_router) ──


@router.websocket("/ws/doctor/{doctor_id}")
async def doctor_websocket(doctor_id: str, websocket: WebSocket, token: str = Query("")):
    """WebSocket for doctor real-time alerts (risk alerts, notifications).

    Auth: reads JWT from `?token=` query param OR the `access_token` HttpOnly cookie
    (same cookie that the HTTP APIs use).

    C-9: this socket is also the delivery channel for doctor-side notifications
    dispatched by app.services.notification_generator.dispatch_doctor_event.
    Auth here rejects patient JWTs (type=="patient") and enforces sub==doctor_id
    so one doctor can't subscribe to another's stream.

    Registers with ws_manager so background jobs (Feature E risk scan) can
    push alerts here via ws_manager.notify_doctor.
    """
    from jose import JWTError as _JWTError
    from jose import jwt as _jwt

    from app.config import settings as _settings

    # Cookie fallback (browsers auto-send same-origin cookies with WS handshake)
    if not token:
        token = websocket.cookies.get("access_token", "") or ""

    try:
        payload = _jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
        # Access OR refresh both acceptable — doctor JWTs are type=access|refresh.
        if payload.get("type") == "patient":
            await websocket.close(code=4001, reason="Unauthorized")
            return
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
    result = await db.execute(select(Patient.id).where(Patient.user_id == user_id))
    return list(result.scalars().all())
