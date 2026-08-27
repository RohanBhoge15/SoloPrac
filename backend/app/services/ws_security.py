"""WebSocket Security — authenticated connections for voice scheduling.

Provides:
  1. WebSocket authentication via JWT token validation
  2. Voice session audit logging — every command logged
  3. Rate limiting on voice endpoints
  4. Two-step confirm for destructive actions (cancel, block)

Usage:
    from app.services.ws_security import WebSocketSecurity
    ws_sec = WebSocketSecurity()
    user_id = await ws_sec.authenticate(websocket)
    await ws_sec.log_voice_command(db, doctor_id, command, intent)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from jose import JWTError, jwt

from app.config import settings
from app.models import AuditLog

logger = logging.getLogger(__name__)

VOICE_RATE_LIMIT_RPM = 20  # 20 voice commands per minute per doctor


class VoiceRateLimiter:
    """Per-doctor rate limiter for voice commands."""

    def __init__(self, default_rpm: int = VOICE_RATE_LIMIT_RPM):
        self.default_rpm = default_rpm
        self._buckets: Dict[str, List[float]] = defaultdict(list)

    async def check_rate_limit(self, doctor_id: str) -> Tuple[bool, Dict[str, Any]]:
        now = time.time()
        bucket = self._buckets[doctor_id]
        self._buckets[doctor_id] = [t for t in bucket if now - t < 60]
        current = len(self._buckets[doctor_id])
        allowed = current < self.default_rpm
        oldest = min(self._buckets[doctor_id]) if self._buckets[doctor_id] else now
        return allowed, {
            "current_rpm": current,
            "limit": self.default_rpm,
            "remaining": max(0, self.default_rpm - current),
            "reset_after": round(max(0, 60 - (now - oldest)), 1),
        }

    async def record_request(self, doctor_id: str):
        self._buckets[doctor_id].append(time.time())


class WebSocketSecurity:
    """Security layer for WebSocket voice connections."""

    def __init__(self):
        self.voice_limiter = VoiceRateLimiter()

    async def authenticate(self, token: str) -> Optional[str]:
        """Validate JWT token and return doctor_id or None."""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            return payload.get("sub")
        except JWTError:
            return None

    @staticmethod
    async def log_voice_command(
        db_session,
        doctor_id: uuid.UUID,
        command_text: str,
        intent: str,
        confidence: float,
        success: bool = True,
        details: Optional[Dict] = None,
    ):
        """Log a voice command to the audit trail."""
        try:
            entry = AuditLog(
                doctor_id=doctor_id,
                actor=f"doctor:{doctor_id}",
                action="voice:command",
                resource_type="voice_session",
                payload_jsonb={
                    "command": command_text[:200],
                    "intent": intent,
                    "confidence": confidence,
                    "success": success,
                    **(details or {}),
                },
            )
            db_session.add(entry)
            await db_session.commit()
        except Exception as exc:
            logger.warning("Voice audit log failed: %s", exc)
            await db_session.rollback()

    @staticmethod
    def require_two_step_confirm(action: str) -> bool:
        """Check if an action requires two-step confirmation."""
        return action in ("cancel_appointment", "block_doctor_time", "bulk_reschedule")

    @staticmethod
    def generate_confirm_token() -> str:
        return uuid.uuid4().hex

    def get_voice_limiter(self) -> VoiceRateLimiter:
        return self.voice_limiter
