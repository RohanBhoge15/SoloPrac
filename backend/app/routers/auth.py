# Auth Router — Google OAuth + JWT

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from jose import jwt

from app.config import get_settings
from app.database import get_db
from app.models import Doctor
from app.schemas import Token, TokenPayload
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
        # Create new doctor
        doctor = Doctor(
            email=email,
            name=name,
            settings={},
        )
        db.add(doctor)
        await db.commit()
        await db.refresh(doctor)
    elif doctor.name != name:
        # Update name if changed
        doctor.name = name
        await db.commit()

    # Issue tokens
    access_token = create_access_token(str(doctor.id))
    refresh_token = create_refresh_token(str(doctor.id))

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    """Exchange refresh token for new access token."""
    try:
        payload = jwt.decode(
            refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_data = TokenPayload(**payload)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_data.type != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    result = await db.execute(select(Doctor).where(Doctor.id == token_data.sub))
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=401, detail="Doctor not found")

    new_access = create_access_token(str(doctor.id))
    new_refresh = create_refresh_token(str(doctor.id))

    return Token(access_token=new_access, refresh_token=new_refresh)


@router.get("/me")
async def get_me(current_doctor: Doctor = Depends(get_current_doctor)):
    """Get current doctor's profile."""
    return {
        "id": str(current_doctor.id),
        "email": current_doctor.email,
        "name": current_doctor.name,
        "speciality": current_doctor.speciality,
        "clinic_name": current_doctor.clinic_name,
        "settings": current_doctor.settings,
    }


@router.post("/logout")
async def logout():
    """Logout — client should discard tokens."""
    return {"message": "Logged out successfully. Discard tokens on client."}