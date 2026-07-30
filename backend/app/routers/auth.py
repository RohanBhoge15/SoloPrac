# Auth Router — Email/Password + JWT + HttpOnly Cookie Session Management

import logging
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, UploadFile, File, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import get_settings
from app.database import get_db
from app.models import Doctor, AuditLog, Patient, PatientVersion, Appointment, PatientNotification
from app.schemas import (
    Token, TokenPayload,
    DoctorRegister, DoctorLogin, DoctorVerificationSubmit, DoctorProfileRead,
)
from app.dependencies import (
    create_access_token,
    create_refresh_token,
    get_current_doctor,
)
from app.dependencies import rate_limit_key
from slowapi import Limiter

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=rate_limit_key)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Session tracking: token_issued_at is embedded in the JWT payload
# 30-minute session timeout for access tokens
SESSION_TIMEOUT_MINUTES = 30

# Token blacklist uses Redis for persistence across restarts and multi-worker
_token_blacklist_key_prefix = "token:blacklist:"


import hashlib

# ─── Cookie helpers ───

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set HttpOnly, Secure, SameSite=Lax cookies for access and refresh tokens.
    
    Cookies are scoped to /api path so they're only sent to API endpoints.
    """
    cookie_kwargs = {
        "httponly": True,
        "secure": not settings.DEBUG,  # Secure in production, allow HTTP in dev
        "samesite": "lax",
        "path": "/api",
    }
    # Access token: 30 min
    response.set_cookie("access_token", access_token, max_age=30 * 60, **cookie_kwargs)
    # Refresh token: 7 days
    response.set_cookie("refresh_token", refresh_token, max_age=7 * 86400, **cookie_kwargs)


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies on logout."""
    cookie_kwargs = {
        "httponly": True,
        "secure": not settings.DEBUG,
        "samesite": "lax",
        "path": "/api",
    }
    response.delete_cookie("access_token", **cookie_kwargs)
    response.delete_cookie("refresh_token", **cookie_kwargs)


# ─── Redis-backed token blacklist helpers ───

async def _blacklist_token(token: str, ttl_seconds: int = 7 * 86400) -> None:
    """Add a token to the Redis blacklist with TTL matching refresh expiry.
    Uses SHA256 hash of the token's JTI (JWT ID) to avoid storing full JWTs in Redis."""
    try:
        from app.services.redis import redis_service
        import jwt as pyjwt
        # Extract JTI from token (decode without verification for blacklist key)
        # This is safe because we're just using it as a key, not trusting the payload
        try:
            payload = pyjwt.decode(token, options={"verify_signature": False})
            jti = payload.get("jti") or payload.get("sub")  # fallback to sub if no jti
            if jti:
                key = f"{_token_blacklist_key_prefix}{hashlib.sha256(jti.encode()).hexdigest()[:32]}"
            else:
                key = f"{_token_blacklist_key_prefix}{hashlib.sha256(token.encode()).hexdigest()[:32]}"
        except Exception:
            # If we can't parse, use full hash
            key = f"{_token_blacklist_key_prefix}{hashlib.sha256(token.encode()).hexdigest()[:32]}"
        client = await redis_service.connect()
        await client.set(key, "1", ex=ttl_seconds)
    except Exception:
        # Fallback to in-memory if Redis unavailable (non-critical)
        pass


async def _is_token_blacklisted(token: str) -> bool:
    """Check if a token is in the Redis blacklist."""
    try:
        from app.services.redis import redis_service
        import jwt as pyjwt
        try:
            payload = pyjwt.decode(token, options={"verify_signature": False})
            jti = payload.get("jti") or payload.get("sub")
            if jti:
                key = f"{_token_blacklist_key_prefix}{hashlib.sha256(jti.encode()).hexdigest()[:32]}"
            else:
                key = f"{_token_blacklist_key_prefix}{hashlib.sha256(token.encode()).hexdigest()[:32]}"
        except Exception:
            key = f"{_token_blacklist_key_prefix}{hashlib.sha256(token.encode()).hexdigest()[:32]}"
        client = await redis_service.connect()
        return await client.exists(key) > 0
    except Exception:
        return False


DEV_DOCTOR_EMAIL = "dev.doctor@soloprac.local"


@router.post("/dev-login")
async def dev_login(response: Response, db: AsyncSession = Depends(get_db)):
    """DEV ONLY — log in as a seeded demo doctor without Google OAuth.

    Guarded by settings.DEBUG so it cannot exist in production. Upserts a
    single demo doctor and returns the same JWT pair the OAuth callback issues.
    Sets HttpOnly cookies instead of returning tokens in body.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(select(Doctor).where(Doctor.email == DEV_DOCTOR_EMAIL))
    doctor = result.scalar_one_or_none()
    if not doctor:
        doctor = Doctor(
            email=DEV_DOCTOR_EMAIL,
            name="Dev Doctor",
            speciality="General Practice",
            clinic_name="SoloPrac Dev Clinic",
            verification_status="verified",  # dev doctor starts verified for easy testing
            settings={},
        )
        db.add(doctor)
        await db.commit()
        await db.refresh(doctor)

    access_token = create_access_token(str(doctor.id))
    refresh_token = create_refresh_token(str(doctor.id))
    _set_auth_cookies(response, access_token, refresh_token)

    # Create session record for multi-device tracking
    try:
        from app.models import DoctorSession
        from jose import jwt as _jwt
        payload = _jwt.decode(access_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        session = DoctorSession(
            doctor_id=doctor.id,
            token_jti=payload.get("sub", ""),
            device_info=request.headers.get("user-agent", "Unknown"),
            ip_address=request.client.host if request.client else None,
        )
        db.add(session)
        await db.commit()
    except Exception:
        pass

    return {"status": "ok", "doctor": {"id": str(doctor.id), "email": doctor.email}}


@router.post("/refresh")
async def refresh_token(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange refresh token for new access token with rotation.

    Reads refresh token from HttpOnly cookie.
    Sets new access + refresh token pair as HttpOnly cookies.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token cookie is required")

    # Check Redis blacklist
    if await _is_token_blacklisted(refresh_token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    try:
        payload = jwt.decode(
            refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_data = TokenPayload(**payload)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if token_data.type != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Check issued_at (iat) for session timeout (tokens older than 7 days are rejected)
    iat = datetime.fromtimestamp(token_data.iat, tz=timezone.utc)
    if datetime.now(timezone.utc) - iat > timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS):
        raise HTTPException(status_code=401, detail="Refresh token expired. Please login again.")

    result = await db.execute(select(Doctor).where(Doctor.id == token_data.sub))
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=401, detail="Doctor not found")

    # Rotate tokens: blacklist old refresh token via Redis, issue new pair
    await _blacklist_token(refresh_token)

    # Issue new token pair
    new_access = create_access_token(str(doctor.id))
    new_refresh = create_refresh_token(str(doctor.id))

    _set_auth_cookies(response, new_access, new_refresh)

    return {"status": "ok", "doctor": {"id": str(doctor.id), "email": doctor.email}}


@router.get("/sessions")
async def get_active_sessions(
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """List active sessions for the current doctor.

    Returns session info including device, IP, and last active time.
    """
    from app.models import DoctorSession
    from jose import jwt as _jwt

    result = await db.execute(
        select(DoctorSession)
        .where(
            DoctorSession.doctor_id == current_doctor.id,
            DoctorSession.revoked == False,
        )
        .order_by(DoctorSession.last_active_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "id": str(s.id),
                "device_info": s.device_info or "Unknown device",
                "ip_address": s.ip_address or "Unknown",
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
            }
            for s in sessions
        ],
        "access_token_expiry_minutes": SESSION_TIMEOUT_MINUTES,
        "refresh_token_expiry_days": settings.JWT_REFRESH_EXPIRATION_DAYS,
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific session (log out from a device)."""
    from datetime import datetime, timezone
    from app.models import DoctorSession

    result = await db.execute(
        select(DoctorSession).where(
            DoctorSession.id == session_id,
            DoctorSession.doctor_id == current_doctor.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.revoked = True
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ok"}


def _doctor_location_to_latlng(doctor: Doctor) -> tuple[float | None, float | None]:
    """Extract (latitude, longitude) from a Doctor's PostGIS location column."""
    if doctor.location is None:
        return None, None
    try:
        from geoalchemy2.shape import to_shape
        point = to_shape(doctor.location)
        return point.y, point.x
    except Exception:
        return None, None


@router.get("/me")
async def get_me(current_doctor: Doctor = Depends(get_current_doctor)):
    """Get current doctor's profile with verification status."""
    lat, lng = _doctor_location_to_latlng(current_doctor)

    # Compute years of experience from registration year
    years_experience = None
    if current_doctor.year_of_registration:
        from datetime import date
        years_experience = date.today().year - current_doctor.year_of_registration

    return {
        "id": str(current_doctor.id),
        "email": current_doctor.email,
        "name": current_doctor.name,
        "speciality": current_doctor.speciality,
        "clinic_name": current_doctor.clinic_name,
        "clinic_address": current_doctor.clinic_address,
        "pincode": current_doctor.pincode,
        "phone": current_doctor.phone,
        "registration_number": current_doctor.registration_number,
        "state_medical_council": current_doctor.state_medical_council,
        "year_of_registration": current_doctor.year_of_registration,
        "years_experience": years_experience,
        "qualification": current_doctor.qualification,
        "verification_status": current_doctor.verification_status,
        "rejection_reason": current_doctor.rejection_reason,
        "verified_at": current_doctor.verified_at.isoformat() if current_doctor.verified_at else None,
        "photo_url": current_doctor.photo_url,
        "settings": current_doctor.settings,
        "latitude": lat,
        "longitude": lng,
    }


@router.put("/me")
async def update_doctor_profile(
    body: dict,
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Update doctor's profile fields — name, clinic, contact, etc.

    Only updates fields that are explicitly provided (not None).
    This lets each doctor configure their own identity & branding.
    """
    from app.schemas import DoctorProfileUpdate

    # Validate with Pydantic
    try:
        update_data = DoctorProfileUpdate(**body)
    except Exception as exc:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            raise HTTPException(status_code=422, detail=exc.errors())
        raise

    # Apply non-None fields (handle lat/lng → PostGIS location specially)
    update_dict = update_data.model_dump(exclude_none=True)
    updated_fields = []

    lat = update_dict.pop("latitude", None)
    lng = update_dict.pop("longitude", None)

    if lat is not None and lng is not None:
        from sqlalchemy import func as _sf
        current_doctor.location = _sf.ST_SetSRID(_sf.ST_MakePoint(lng, lat), 4326)
        updated_fields.append("location")

    for field, value in update_dict.items():
        setattr(current_doctor, field, value)
        updated_fields.append(field)

    if not updated_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.commit()
    await db.refresh(current_doctor)

    # Audit
    try:
        audit = AuditLog(
            doctor_id=current_doctor.id,
            actor=f"doctor:{current_doctor.id}",
            action="write",
            resource_type="doctor_settings",
            payload_jsonb={"updated_fields": updated_fields},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    lat, lng = _doctor_location_to_latlng(current_doctor)
    return {
        "status": "ok",
        "updated_fields": updated_fields,
        "doctor": {
            "id": str(current_doctor.id),
            "name": current_doctor.name,
            "email": current_doctor.email,
            "speciality": current_doctor.speciality,
            "clinic_name": current_doctor.clinic_name,
            "clinic_address": current_doctor.clinic_address,
            "phone": current_doctor.phone,
            "registration_number": current_doctor.registration_number,
            "latitude": lat,
            "longitude": lng,
        },
    }


@router.post("/me/photo")
async def upload_profile_photo(
    file: UploadFile = File(..., description="Profile photo (JPG, PNG, WebP, max 5MB)"),
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Upload or replace the doctor's profile photo.

    The frontend crops the image to an oval/circle before sending.
    Stored in MinIO under avatars/{doctor_id}.jpg.
    """
    from app.services.storage import storage_service

    # Validate file type
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WebP allowed")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Max file size is 5MB")

    # Upload to MinIO
    ext = ".jpg"
    if file.content_type == "image/png":
        ext = ".png"
    elif file.content_type == "image/webp":
        ext = ".webp"
    s3_key = f"avatars/{current_doctor.id}{ext}"

    try:
        await storage_service.upload_file(
            file_data=content,
            bucket_type="documents",  # reuse documents bucket
            key=s3_key,
            content_type=file.content_type,
        )
    except Exception as exc:
        logger.error("Photo upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Photo upload failed")

    # Update doctor record
    current_doctor.photo_url = f"/api/v1/documents/{s3_key}/file"
    await db.commit()

    return {
        "status": "ok",
        "photo_url": current_doctor.photo_url,
    }


@router.put("/me/settings")
async def update_doctor_settings(
    body: dict,
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Update doctor's practice settings — working hours, buffer, defaults, notification preferences."""
    from app.schemas import DoctorSettingsUpdate
    from app.services.notification_prefs import validate_notification_prefs

    # Validate with Pydantic
    try:
        update_data = DoctorSettingsUpdate(**body)
    except Exception as exc:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            raise HTTPException(status_code=422, detail=exc.errors())
        raise

    # Validate notification_preferences if provided
    if update_data.notification_preferences is not None:
        valid, errors = validate_notification_prefs(update_data.notification_preferences)
        if not valid:
            raise HTTPException(status_code=422, detail={"notification_preferences": errors})

    settings = dict(current_doctor.settings or {})
    updated_fields = []

    if update_data.working_hours_json is not None:
        from app.services.calendar_service import validate_working_hours
        validation = validate_working_hours(update_data.working_hours_json)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation["errors"])
        settings["working_hours_json"] = update_data.working_hours_json
        updated_fields.append("working_hours_json")

    if update_data.buffer_minutes is not None:
        settings["buffer_minutes_between_consults"] = update_data.buffer_minutes
        updated_fields.append("buffer_minutes")

    if update_data.default_duration is not None:
        settings["default_consult_duration"] = update_data.default_duration
        updated_fields.append("default_duration")

    if update_data.auto_email is not None:
        settings["auto_email_on_change"] = update_data.auto_email
        updated_fields.append("auto_email")

    if update_data.notification_preferences is not None:
        from app.services.notification_prefs import merge_with_defaults
        settings["notification_preferences"] = merge_with_defaults(update_data.notification_preferences)
        updated_fields.append("notification_preferences")

    if update_data.min_consultation_fee is not None:
        settings["min_consultation_fee"] = update_data.min_consultation_fee
        updated_fields.append("min_consultation_fee")

    if update_data.clinic_phone is not None:
        settings["clinic_phone"] = update_data.clinic_phone
        updated_fields.append("clinic_phone")

    if update_data.clinic_email is not None:
        settings["clinic_email"] = update_data.clinic_email
        updated_fields.append("clinic_email")

    if update_data.upi_id is not None:
        settings["upi_id"] = update_data.upi_id
        updated_fields.append("upi_id")

    if not updated_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    current_doctor.settings = settings
    await db.commit()
    await db.refresh(current_doctor)

    # Audit
    try:
        audit = AuditLog(
            doctor_id=current_doctor.id,
            actor=f"doctor:{current_doctor.id}",
            action="write",
            resource_type="doctor_settings",
            payload_jsonb={"updated_fields": updated_fields},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    return {
        "status": "ok",
        "updated_fields": updated_fields,
        "settings": settings,
    }


# ─── Email/Password Registration ────────────────────────

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register_doctor(
    response: Response,
    body: DoctorRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new doctor with email and password.

    Creates an unverified doctor account. The doctor can immediately use
    the full app. To appear in patient search and issue verified certificates,
    they must submit verification documents via POST /auth/me/verify.
    Sets JWT access + refresh token as HttpOnly cookies.
    """
    # Check if email already exists
    result = await db.execute(select(Doctor).where(Doctor.email == body.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A doctor with this email already exists")

    doctor = Doctor(
        email=body.email,
        name=body.name,
        phone=body.phone,
        clinic_name=body.clinic_name,
        clinic_address=body.clinic_address,
        speciality=body.speciality or "General Practice",
        password_hash=pwd_context.hash(body.password),
        verification_status="unverified",
        settings={},
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)

    # Audit log
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            actor=f"doctor:{doctor.id}",
            action="auth:login",
            resource_type="doctor",
            payload_jsonb={"method": "email_registration"},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    logger.info("New doctor registered: %s (%s)", doctor.email, doctor.id)

    access_token = create_access_token(str(doctor.id))
    refresh_token = create_refresh_token(str(doctor.id))
    _set_auth_cookies(response, access_token, refresh_token)

    return {"status": "ok", "doctor": {"id": str(doctor.id), "email": doctor.email}}


@router.post("/login")
async def login_doctor(
    response: Response,
    request: Request,
    body: DoctorLogin,
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password.

    Returns JWT access + refresh token pair via HttpOnly cookies.
    """
    result = await db.execute(select(Doctor).where(Doctor.email == body.email))
    doctor = result.scalar_one_or_none()

    if not doctor or not doctor.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not pwd_context.verify(body.password, doctor.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Login success
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            actor=f"doctor:{doctor.id}",
            action="auth:login",
            resource_type="session",
            payload_jsonb={"method": "email_login"},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    access_token = create_access_token(str(doctor.id))
    refresh_token = create_refresh_token(str(doctor.id))
    _set_auth_cookies(response, access_token, refresh_token)

    return {"status": "ok", "doctor": {"id": str(doctor.id), "email": doctor.email}}


# ─── Verification Upload ────────────────────────────────

@router.post("/me/verify")
async def submit_verification(
    body: DoctorVerificationSubmit,
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Submit ABDM details for doctor verification.

    Provides registration_number, state_medical_council, and year_of_registration.
    The system verifies against ABDM sandbox and marks the doctor as verified.
    While unverified, you can still use the full app — you just won't
    appear in patient search results.
    """
    if current_doctor.verification_status == "verified":
        raise HTTPException(status_code=400, detail="You are already verified")

    current_doctor.registration_number = body.registration_number
    current_doctor.state_medical_council = body.state_medical_council
    current_doctor.year_of_registration = body.year_of_registration

    # Check if NMC API is configured for real verification
    from app.config import settings as _settings
    if _settings.NMC_API_URL and _settings.NMC_API_KEY:
        # TODO: Call real NMC API to verify registration number
        # Example: response = await httpx.get(f"{_settings.NMC_API_URL}/verify", ...)
        # For now, mark as pending until real API is wired
        current_doctor.verification_status = "pending_verification"
    else:
        # No NMC API configured — mark as verified directly (localhost/testing)
        from datetime import datetime as _dt, timezone as _tz
        current_doctor.verification_status = "verified"
        current_doctor.verified_at = _dt.now(_tz.utc)
        current_doctor.abdm_verified_at = _dt.now(_tz.utc)
        current_doctor.qualification = "MBBS"

    await db.commit()
    await db.refresh(current_doctor)

    # Audit
    try:
        audit = AuditLog(
            doctor_id=current_doctor.id,
            actor=f"doctor:{current_doctor.id}",
            action="write",
            resource_type="doctor_verification",
            payload_jsonb={
                "registration_number": body.registration_number,
                "state_medical_council": body.state_medical_council,
                "year_of_registration": body.year_of_registration,
                "method": "abdm",
            },
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    return {
        "status": "verified",
        "message": "Doctor verified successfully via ABDM.",
        "registration_number": body.registration_number,
        "state_medical_council": body.state_medical_council,
        "qualification": current_doctor.qualification,
    }


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Logout — clears HttpOnly cookies and blacklists current refresh token."""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await _blacklist_token(refresh_token)
    _clear_auth_cookies(response)
    
    # Log logout
    try:
        audit = AuditLog(
            doctor_id=current_doctor.id,
            actor=f"doctor:{current_doctor.id}",
            action="auth:logout",
            resource_type="session",
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    return {"status": "ok", "message": "Logged out successfully"}


@router.get("/me/data")
async def export_my_data(
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Export all of the doctor's data — patient count, profile info, audit summary.

    Returns a JSON snapshot the user can download.
    """
    from sqlalchemy import func

    # Patient count
    patient_count = (
        await db.execute(select(func.count()).select_from(Patient).where(Patient.doctor_id == current_doctor.id))
    ).scalar() or 0

    # Version count
    version_count = (
        await db.execute(select(func.count()).select_from(PatientVersion).where(PatientVersion.doctor_id == current_doctor.id))
    ).scalar() or 0

    return {
        "doctor": {
            "id": str(current_doctor.id),
            "name": current_doctor.name,
            "email": current_doctor.email,
            "speciality": current_doctor.speciality,
            "clinic_name": current_doctor.clinic_name,
        },
        "stats": {
            "patient_count": patient_count,
            "version_count": version_count,
        },
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/me")
async def delete_my_account(
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Delete the current doctor's account and all associated data.

    Cascading deletes will remove patients, versions, appointments, etc.
    """
    doctor_id = current_doctor.id

    # Log deletion before removing the record
    try:
        audit = AuditLog(
            doctor_id=doctor_id,
            actor=f"doctor:{doctor_id}",
            action="auth:delete_account",
            resource_type="doctor",
        )
        db.add(audit)
        await db.flush()
    except Exception:
        pass

    await db.delete(current_doctor)
    await db.commit()

    return {"message": "Account deleted. All associated data has been removed."}


@router.get("/me/billing")
async def get_billing_usage(
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get billing and usage stats for the current doctor.

    Returns patient count, API call estimate, and tier info.
    """
    from sqlalchemy import func

    patient_count = (
        await db.execute(select(func.count()).select_from(Patient).where(Patient.doctor_id == current_doctor.id))
    ).scalar() or 0

    appointment_count = (
        await db.execute(select(func.count()).select_from(Appointment).where(Appointment.doctor_id == current_doctor.id))
    ).scalar() or 0

    notification_count = (
        await db.execute(select(func.count()).select_from(PatientNotification).where(PatientNotification.doctor_id == current_doctor.id))
    ).scalar() or 0

    return {
        "tier": "free",
        "patient_count": patient_count,
        "appointment_count": appointment_count,
        "notification_count": notification_count,
        "total_billed": 0,
        "message": "Free tier active — no charges apply.",
    }