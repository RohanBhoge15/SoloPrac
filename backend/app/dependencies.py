# SoloPrac Backend Dependencies

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Doctor, Patient, User
from app.schemas import TokenPayload

settings = get_settings()
security = HTTPBearer(auto_error=False)


async def get_current_doctor(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> Doctor:
    """Extract and validate JWT, return the Doctor instance.

    First tries to use decoded payload from middleware (avoiding double decode).
    Falls back to decoding from Authorization header if middleware didn't run.
    """
    # Try to get token payload from request state (set by middleware)
    token_data = None
    if request and hasattr(request.state, "token_payload"):
        token_data = TokenPayload(**request.state.token_payload)
        # Verify token type
        if token_data.type not in ("access", "refresh"):
            token_data = None

    # Fallback: decode from Authorization header
    if not token_data:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            token_data = TokenPayload(**payload)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if token_data.type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

    result = await db.execute(select(Doctor).where(Doctor.id == token_data.sub))
    doctor = result.scalar_one_or_none()

    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Doctor not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return doctor


async def get_optional_doctor(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[Doctor]:
    """Optional authentication - returns None if not authenticated."""
    if not credentials:
        return None

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_data = TokenPayload(**payload)
        if token_data.type != "access":
            return None
        result = await db.execute(select(Doctor).where(Doctor.id == token_data.sub))
        return result.scalar_one_or_none()
    except JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> User:
    """Extract and validate patient JWT, return the User instance.

    The JWT `sub` claim carries the User ID (UUID as string).
    This User is cross-tenant — not scoped to any doctor.

    Reads from Authorization header first, falls back to patient_token cookie.
    """
    token = None
    if credentials:
        token = credentials.credentials
    if not token and request:
        token = request.cookies.get("patient_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_data = TokenPayload(**payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.type != "patient":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected patient token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # token_data.sub is user_id (UUID as string)
    result = await db.execute(select(User).where(User.id == token_data.sub))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_patient_for_doctor(
    doctor_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    """Get the Patient record linking a User to a specific doctor.

    Raises 404 if this user isn't a patient of this doctor.
    Used by endpoints that need the doctor-scoped Patient row.
    """
    result = await db.execute(
        select(Patient).where(
            Patient.user_id == user.id,
            Patient.doctor_id == doctor_id,
        )
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a patient of this doctor",
        )
    return patient


def _make_jti() -> str:
    """Generate a unique JWT ID for blacklist support."""
    import uuid

    return uuid.uuid4().hex


def create_access_token(sub: str, token_type: str = "access") -> str:
    """Create a short-lived access token (30 minutes)."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    payload = TokenPayload(sub=sub, jti=_make_jti(), exp=expire, iat=now, type=token_type)
    return jwt.encode(payload.model_dump(), settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(sub: str) -> str:
    """Create a long-lived refresh token (7 days)."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS)
    payload = TokenPayload(sub=sub, jti=_make_jti(), exp=expire, iat=now, type="refresh")
    return jwt.encode(payload.model_dump(), settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_user_token(user_id: str) -> str:
    """Create a user (patient portal) access token (30 days)."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=30)
    payload = TokenPayload(sub=user_id, jti=_make_jti(), exp=expire, iat=now, type="patient")
    return jwt.encode(payload.model_dump(), settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# Rate limiting key function
def rate_limit_key(request: Request) -> str:
    """Key function for slowapi rate limiter - per doctor."""
    # Try to get doctor_id from request state (set by auth middleware)
    doctor_id = getattr(request.state, "doctor_id", None)
    if doctor_id:
        return f"doctor:{doctor_id}"
    # Fallback to IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "unknown"
    return f"ip:{ip}"
