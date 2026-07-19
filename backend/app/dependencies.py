# SoloPrac Backend Dependencies

from __future__ import annotations

from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.database import get_db
from app.models import Doctor, Patient
from app.schemas import TokenPayload
from jose import jwt, JWTError

settings = get_settings()
security = HTTPBearer(auto_error=False)


async def get_current_doctor(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Doctor:
    """Extract and validate JWT, return the Doctor instance."""
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


async def get_current_patient(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    """Extract and validate patient JWT, return the Patient instance."""
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

    if token_data.type != "patient":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected patient token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # token_data.sub is patient_id (UUID as string)
    result = await db.execute(select(Patient).where(Patient.id == token_data.sub))
    patient = result.scalar_one_or_none()

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Patient not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return patient


def create_access_token(sub: str, token_type: str = "access") -> str:
    """Create a short-lived access token (30 minutes)."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    payload = TokenPayload(sub=sub, exp=expire, iat=now, type=token_type)
    return jwt.encode(payload.model_dump(), settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(sub: str) -> str:
    """Create a long-lived refresh token (7 days)."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS)
    payload = TokenPayload(sub=sub, exp=expire, iat=now, type="refresh")
    return jwt.encode(payload.model_dump(), settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_patient_token(patient_id: str) -> str:
    """Create a patient access token (30 days)."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=30)
    payload = TokenPayload(sub=patient_id, exp=expire, iat=now, type="patient")
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
    ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
    return f"ip:{ip}"