"""Patient Authentication Service — OTP-based login for patient portal.

Uses Redis for OTP storage with auto-expiry.
Creates/authenticates cross-tenant **User** records (not Patient records).

Flow:
  1. User enters phone number
  2. OTP stored in Redis with 5-min TTL
  3. User enters OTP → verified → User created/returned → JWT issued

The JWT carries the User ID (sub). Patient records are created later,
when the user actually books an appointment with a specific doctor.

In production, swap Redis URL to a managed Redis instance.
"""

from __future__ import annotations

import hashlib
import secrets
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from uuid import UUID
from jose import jwt, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

# Redis key prefixes
OTP_PREFIX = "soloprac:otp:"
USER_PHONE_HASH_PREFIX = "soloprac:user_phone_hash:"

OTP_TTL_SECONDS = 300  # 5 minutes


class PatientAuthService:
    """User authentication via OTP — Redis-backed + DB User lookup."""

    @staticmethod
    async def _get_redis():
        """Get Redis connection via shared singleton (connection pooled)."""
        try:
            from app.services.redis import redis_service
            return await redis_service.connect()
        except Exception:
            logger.warning("Redis not available, falling back to in-memory OTP")
            return None

    @staticmethod
    def _phone_hash(phone: str) -> str:
        """SHA256 hash of phone for fast lookup."""
        return hashlib.sha256(phone.encode("utf-8")).hexdigest()

    @staticmethod
    async def send_otp(phone: str) -> dict:
        """Send OTP to phone number.

        Stores OTP in Redis with 5-min TTL.
        In production, this would trigger an SMS gateway — for now,
        the OTP is logged (dev mode) and returned for testing.
        """
        if not phone or len(phone) < 10:
            return {"success": False, "error": "Invalid phone number"}

        # Generate 6-digit OTP
        otp = str(secrets.randbelow(1000000)).zfill(6)

        # Try Redis first
        redis = await PatientAuthService._get_redis()
        if redis:
            try:
                await redis.setex(f"{OTP_PREFIX}{phone}", OTP_TTL_SECONDS, otp)
                logger.info("OTP stored in Redis for %s", phone)
                return {"success": True, "message": "OTP sent"}
            except Exception as exc:
                logger.warning("Redis OTP storage failed: %s", exc)

        # Fallback: in-memory (non-persistent, dev only, thread-safe via lock)
        from app.services.patient_auth import _in_memory_otp_lock, _in_memory_otp_store
        with _in_memory_otp_lock:
            _in_memory_otp_store[phone] = {
                "otp": otp,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            }

        # Don't log OTP in production — only log that it was sent
        logger.info("OTP sent to %s (in-memory)", phone)
        return {"success": True, "message": "OTP sent"}

    @staticmethod
    async def verify_otp(phone: str, otp: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Verify OTP and return (success, token, user_id).

        On success:
        - Looks up or creates a User record in the DB (via phone hash)
        - Generates a patient JWT token scoped to the User
        - Does NOT create any Patient record — that happens at booking time

        Args:
            phone: User's phone number.
            otp: 6-digit OTP to verify.

        Returns:
            (True, token_str, user_id_str) on success
            (False, None, None) on failure
        """
        if not phone or not otp:
            return False, None, None

        # Verify OTP from Redis first
        redis = await PatientAuthService._get_redis()
        stored_otp = None

        if redis:
            try:
                stored_otp = await redis.get(f"{OTP_PREFIX}{phone}")
                if stored_otp:
                    await redis.delete(f"{OTP_PREFIX}{phone}")
            except Exception:
                pass

        # Fallback: in-memory (thread-safe via lock)
        if not stored_otp:
            from app.services.patient_auth import _in_memory_otp_lock, _in_memory_otp_store
            with _in_memory_otp_lock:
                stored = _in_memory_otp_store.get(phone)
                if stored:
                    if datetime.now(timezone.utc) > stored["expires_at"]:
                        del _in_memory_otp_store[phone]
                        stored_otp = None
                    else:
                        stored_otp = stored["otp"]
                        del _in_memory_otp_store[phone]

        if not stored_otp:
            return False, None, None

        if stored_otp != otp:
            return False, None, None

        # OTP verified — now get or create User in the DB
        try:
            user_id = await PatientAuthService._resolve_or_create_user(phone)
        except Exception as exc:
            logger.error("Failed to resolve user from DB: %s", exc)
            return False, None, None

        if not user_id:
            return False, None, None

        # Generate JWT
        token = PatientAuthService._create_token(str(user_id))

        logger.info("User %s authenticated via OTP (phone=%s)", user_id, phone)
        return True, token, str(user_id)

    @staticmethod
    async def _resolve_or_create_user(phone: str) -> Optional[UUID]:
        """Find or create a User record by phone hash.

        Uses SHA256(phone) for fast indexed lookup — no O(n) decryption.
        Does NOT create a Patient record (no doctor context yet).
        """
        from app.database import async_session_maker
        from app.models import User as UserModel
        from sqlalchemy import select

        phone_hash = PatientAuthService._phone_hash(phone)

        # Check Redis cache first
        redis = await PatientAuthService._get_redis()
        cached_user_id = None
        if redis:
            try:
                cached_user_id = await redis.get(f"{USER_PHONE_HASH_PREFIX}{phone_hash}")
            except Exception:
                pass

        if cached_user_id:
            try:
                return UUID(cached_user_id)
            except ValueError:
                pass

        async with async_session_maker() as db:
            # Fast indexed lookup by phone_hash
            result = await db.execute(
                select(UserModel).where(UserModel.phone_hash == phone_hash)
            )
            user = result.scalar_one_or_none()

            if user:
                # Cache in Redis (24h TTL)
                if redis:
                    try:
                        await redis.setex(
                            f"{USER_PHONE_HASH_PREFIX}{phone_hash}",
                            86400,
                            str(user.id),
                        )
                    except Exception:
                        pass
                return user.id

            # No existing user — create one
            user = UserModel(
                phone=phone,
                phone_hash=phone_hash,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            # Cache in Redis
            if redis:
                try:
                    await redis.setex(
                        f"{USER_PHONE_HASH_PREFIX}{phone_hash}",
                        86400,
                        str(user.id),
                    )
                except Exception:
                    pass

            logger.info("Created new user %s (phone=%s)", user.id, phone)
            return user.id

    @staticmethod
    def _create_token(user_id: str) -> str:
        """Create a user (patient portal) JWT token (30 day expiry)."""
        from app.dependencies import create_user_token
        return create_user_token(user_id)

    @staticmethod
    def verify_token(token: str) -> Optional[str]:
        """Verify patient JWT and return user_id or None."""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("type") != "patient":
                return None
            return payload.get("sub")
        except JWTError:
            return None


# ─── In-memory OTP fallback (dev mode when Redis is down) ───
_in_memory_otp_store: dict = {}
_in_memory_otp_lock = threading.Lock()
