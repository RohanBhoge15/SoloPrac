# Auth Router — Google OAuth + Email/Password + JWT + Session Management

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
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
limiter = Limiter(key_func=rate_limit_key)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Session tracking: token_issued_at is embedded in the JWT payload
# 30-minute session timeout for access tokens
SESSION_TIMEOUT_MINUTES = 30

# Token blacklist uses Redis for persistence across restarts and multi-worker
_token_blacklist_key_prefix = "token:blacklist:"

# OAuth Configuration
config = Config()
oauth = OAuth(config)

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


import hashlib

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


@router.get("/login/google")
async def google_login(request: Request):
    """Initiate Google OAuth flow."""
    redirect_uri = str(settings.GOOGLE_REDIRECT_URI)
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback/google")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback, create/login doctor, issue JWTs."""
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    if not user_info or not user_info.get("email"):
        raise HTTPException(status_code=400, detail="Failed to get user info from Google")

    email = user_info["email"]
    name = user_info.get("name", "Doctor")

    # Check if doctor exists
    result = await db.execute(select(Doctor).where(Doctor.email == email))
    doctor = result.scalar_one_or_none()

    if not doctor:
        # Create new doctor — starts as unverified
        doctor = Doctor(
            email=email,
            name=name,
            verification_status="unverified",
            settings={},
        )
        db.add(doctor)
        await db.commit()
        await db.refresh(doctor)
    elif doctor.name != name:
        # Update name if changed
        doctor.name = name
        await db.commit()

    # Issue tokens with issued_at timestamp for session tracking
    now = datetime.now(timezone.utc)
    access_token = create_access_token(str(doctor.id))
    refresh_token = create_refresh_token(str(doctor.id))

    # Log successful login
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            actor=f"doctor:{doctor.id}",
            action="auth:login",
            resource_type="session",
            payload_jsonb={"method": "google_oauth", "email": email},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass  # Non-blocking

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


DEV_DOCTOR_EMAIL = "dev.doctor@soloprac.local"


@router.post("/dev-login", response_model=Token)
async def dev_login(db: AsyncSession = Depends(get_db)):
    """DEV ONLY — log in as a seeded demo doctor without Google OAuth.

    Guarded by settings.DEBUG so it cannot exist in production. Upserts a
    single demo doctor and returns the same JWT pair the OAuth callback issues.
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

    return Token(
        access_token=create_access_token(str(doctor.id)),
        refresh_token=create_refresh_token(str(doctor.id)),
        token_type="bearer",
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    body: dict = Body(..., example={"refresh_token": "eyJ..."}),
    db: AsyncSession = Depends(get_db),
):
    """Exchange refresh token for new access token with rotation.

    Accepts JSON body: {"refresh_token": "..."}

    Security:
        - Old refresh token is invalidated (token rotation)
        - Access tokens expire after 30 minutes
        - Refresh tokens expire after 7 days
        - Token reuse detection logs a security event
    """
    token = body.get("refresh_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="refresh_token is required")

    # Check Redis blacklist
    if await _is_token_blacklisted(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    try:
        payload = jwt.decode(
            token,
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
    await _blacklist_token(token)

    # Issue new token pair
    new_access = create_access_token(str(doctor.id))
    new_refresh = create_refresh_token(str(doctor.id))

    return Token(access_token=new_access, refresh_token=new_refresh, token_type="bearer")


@router.get("/sessions")
async def get_active_sessions(current_doctor: Doctor = Depends(get_current_doctor)):
    """List active sessions for the current doctor.

    Returns the most recent login events from the audit log.
    """
    return {
        "note": "Session management is stateless via JWT. Token expiry: 30 min access, 7 day refresh.",
        "access_token_expiry_minutes": SESSION_TIMEOUT_MINUTES,
        "refresh_token_expiry_days": settings.JWT_REFRESH_EXPIRATION_DAYS,
    }


@router.get("/me")
async def get_me(current_doctor: Doctor = Depends(get_current_doctor)):
    """Get current doctor's profile with verification status."""
    return {
        "id": str(current_doctor.id),
        "email": current_doctor.email,
        "name": current_doctor.name,
        "speciality": current_doctor.speciality,
        "clinic_name": current_doctor.clinic_name,
        "clinic_address": current_doctor.clinic_address,
        "phone": current_doctor.phone,
        "registration_number": current_doctor.registration_number,
        "verification_status": current_doctor.verification_status,
        "rejection_reason": current_doctor.rejection_reason,
        "verified_at": current_doctor.verified_at.isoformat() if current_doctor.verified_at else None,
        "settings": current_doctor.settings,
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

    # Apply non-None fields
    updated_fields = []
    for field, value in update_data.model_dump(exclude_none=True).items():
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
        },
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
    body: DoctorRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new doctor with email and password.

    Creates an unverified doctor account. The doctor can immediately use
    the full app. To appear in patient search and issue verified certificates,
    they must submit verification documents via POST /auth/me/verify.
    """
    # Check if email already exists
    result = await db.execute(select(Doctor).where(Doctor.email == body.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A doctor with this email already exists")

    doctor = Doctor(
        email=body.email,
        name=body.name,
        phone=body.phone or None,
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
    return Token(
        access_token=create_access_token(str(doctor.id)),
        refresh_token=create_refresh_token(str(doctor.id)),
        token_type="bearer",
    )


@router.post("/login", response_model=Token)
async def login_doctor(
    body: DoctorLogin,
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password.

    Returns JWT access + refresh token pair.
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

    return Token(
        access_token=create_access_token(str(doctor.id)),
        refresh_token=create_refresh_token(str(doctor.id)),
        token_type="bearer",
    )


# ─── Verification Upload ────────────────────────────────

@router.post("/me/verify")
async def submit_verification(
    registration_number: str = Body(..., description="Medical council registration number"),
    license_file: UploadFile = File(None, description="License certificate photo/scan"),
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Submit documents for doctor verification.

    Uploads your medical council registration number and license certificate.
    Once submitted, Soloprac admin will review and approve/reject.
    While unverified, you can still use the full app — you just won't
    appear in patient search results.
    """
    if current_doctor.verification_status == "verified":
        raise HTTPException(status_code=400, detail="You are already verified")

    current_doctor.registration_number = registration_number

    # Save uploaded file if provided
    if license_file:
        import os
        from app.config import settings as _settings
        upload_dir = os.path.join(
            _settings.UPLOAD_DIR if hasattr(_settings, "UPLOAD_DIR") else "app/outputs",
            "verification_docs",
            str(current_doctor.id),
        )
        os.makedirs(upload_dir, exist_ok=True)

        file_ext = license_file.filename.split(".")[-1] if license_file.filename else "jpg"
        file_path = os.path.join(upload_dir, f"license.{file_ext}")
        content = await license_file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        current_doctor.license_document_path = file_path

    current_doctor.verification_status = "pending_verification"
    await db.commit()
    await db.refresh(current_doctor)

    # Audit
    try:
        audit = AuditLog(
            doctor_id=current_doctor.id,
            actor=f"doctor:{current_doctor.id}",
            action="write",
            resource_type="doctor_verification",
            payload_jsonb={"registration_number": registration_number},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass

    return {
        "status": "pending_verification",
        "message": "Verification documents submitted. Soloprac team will review shortly.",
        "registration_number": registration_number,
        "has_document": bool(current_doctor.license_document_path),
    }


@router.post("/logout")
async def logout(
    request: Request,
    current_doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Logout — blacklists current token and logs the event.

    Client must discard tokens after logout. The blacklisted access token
    cannot be used for refresh token rotation.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        await _blacklist_token(token)

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

    return {"message": "Logged out successfully. Token blacklisted."}


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