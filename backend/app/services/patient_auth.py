"""Patient Authentication Service — OTP-based login for patient portal.

Uses simple OTP flow with in-memory store (Redis in production).
Generates JWT tokens for authenticated patients.
"""

from __future__ import annotations

import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from jose import jwt, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory OTP store (use Redis in production)
# {phone: {"otp": str, "expires_at": datetime, "patient_id": str}}
_otp_store = {}

# In-memory patient store (use DB in production)
_patient_store = {}


class PatientAuthService:
    """Patient authentication via OTP."""

    @staticmethod
    async def send_otp(phone: str) -> dict:
        """Send OTP to phone number."""
        if not phone or len(phone) < 10:
            return {"success": False, "error": "Invalid phone number"}

        # Generate 6-digit OTP
        otp = str(secrets.randbelow(1000000)).zfill(6)

        # Create or get patient
        patient_id = None
        for pid, p in _patient_store.items():
            if p.get("phone") == phone:
                patient_id = pid
                break

        if not patient_id:
            patient_id = f"patient_{secrets.token_hex(8)}"
            _patient_store[patient_id] = {"phone": phone, "created_at": datetime.now(timezone.utc)}

        # Store OTP
        _otp_store[phone] = {
            "otp": otp,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "patient_id": patient_id,
        }

        logger.info("OTP sent to %s: %s", phone, otp)

        return {"success": True, "message": "OTP sent"}

    @staticmethod
    async def verify_otp(phone: str, otp: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Verify OTP and return (success, token, patient_id)."""
        stored = _otp_store.get(phone)
        if not stored:
            return False, None, None

        if datetime.now(timezone.utc) > stored["expires_at"]:
            del _otp_store[phone]
            return False, None, None

        if stored["otp"] != otp:
            return False, None, None

        # Generate JWT
        patient_id = stored["patient_id"]
        token = PatientAuthService._create_token(patient_id)

        # Clean up
        del _otp_store[phone]

        return True, token, patient_id

    @staticmethod
    def _create_token(patient_id: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": patient_id,
            "type": "patient",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=30)).timestamp()),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> Optional[str]:
        """Verify patient JWT and return patient_id or None."""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("type") != "patient":
                return None
            return payload.get("sub")
        except JWTError:
            return None