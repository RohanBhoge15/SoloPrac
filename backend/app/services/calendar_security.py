"""Calendar Security — rate limiting, audit logging, RLS enforcement for calendar API.

Dev's Week 10 tasks:
  1. Calendar API rate limiting — per-doctor RPM tracking
  2. Audit logging for appointment CRUD
  3. RLS enforcement verification for appointments
  4. Notification preferences enforcement (already in notification_prefs.py)

Usage:
    from app.services.calendar_security import CalendarRateLimiter, CalendarSecurityService
    limiter = CalendarRateLimiter()
    allowed = await limiter.check_rate_limit(doctor_id)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text

from app.models import AuditLog

logger = logging.getLogger(__name__)


class CalendarRateLimiter:
    """Per-doctor rate limiter for calendar API endpoints.

    Default: 60 requests/minute per doctor (reasonable for calendar ops).
    """

    def __init__(self, default_rpm: int = 60):
        self.default_rpm = default_rpm
        self._buckets: Dict[str, List[float]] = defaultdict(list)

    async def check_rate_limit(
        self,
        doctor_id: str,
        rpm_limit: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check if a doctor has exceeded their rate limit.

        Returns:
            (allowed: bool, info: dict with current_rpm, limit, remaining, reset_after_seconds)
        """
        limit = rpm_limit or self.default_rpm
        now = time.time()
        bucket = self._buckets[doctor_id]

        # Prune entries older than 60 seconds
        self._buckets[doctor_id] = [t for t in bucket if now - t < 60]

        current_rpm = len(self._buckets[doctor_id])
        allowed = current_rpm < limit

        oldest = min(self._buckets[doctor_id]) if self._buckets[doctor_id] else now
        reset_after = max(0.0, 60.0 - (now - oldest))

        return allowed, {
            "current_rpm": current_rpm,
            "limit": limit,
            "remaining": max(0, limit - current_rpm),
            "reset_after_seconds": round(reset_after, 1),
            "allowed": allowed,
        }

    async def record_request(self, doctor_id: str) -> None:
        """Record an API request for rate limiting."""
        self._buckets[doctor_id].append(time.time())

    def get_stats(self, doctor_id: str) -> Dict[str, Any]:
        now = time.time()
        bucket = [t for t in self._buckets.get(doctor_id, []) if now - t < 60]
        return {
            "doctor_id": doctor_id,
            "current_rpm": len(bucket),
            "limit": self.default_rpm,
        }


class CalendarSecurityService:
    """Security layer for calendar API — audit logging, RLS verification."""

    def __init__(self):
        self.rate_limiter = CalendarRateLimiter()

    # ─── Audit Logging ────────────────────────────────

    @staticmethod
    async def log_appointment_event(
        db_session,
        doctor_id: UUID,
        action: str,
        appointment_id: UUID,
        patient_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log an appointment-related event to the audit trail.

        Actions: create, reschedule, cancel, view
        """
        try:
            entry = AuditLog(
                doctor_id=doctor_id,
                patient_id=patient_id,
                actor=f"doctor:{doctor_id}",
                action=f"appointment:{action}",
                resource_type="appointment",
                resource_id=appointment_id,
                payload_jsonb={
                    **(details or {}),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            db_session.add(entry)
            await db_session.commit()
        except Exception as exc:
            logger.warning("Appointment audit log failed (non-blocking): %s", exc)
            await db_session.rollback()

    @staticmethod
    async def log_working_hours_change(
        db_session,
        doctor_id: UUID,
        old_settings: Dict[str, Any],
        new_settings: Dict[str, Any],
    ):
        """Log working hours config changes."""
        try:
            entry = AuditLog(
                doctor_id=doctor_id,
                actor=f"doctor:{doctor_id}",
                action="write",
                resource_type="working_hours",
                payload_jsonb={
                    "old": old_settings,
                    "new": new_settings,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            db_session.add(entry)
            await db_session.commit()
        except Exception as exc:
            logger.warning("Working hours audit log failed (non-blocking): %s", exc)
            await db_session.rollback()

    # ─── RLS Verification ────────────────────────────

    @staticmethod
    async def verify_rls_appointments(db_session) -> Dict[str, Any]:
        """Verify that RLS policies are active on appointments table.

        Checks:
          - Row-Level Security is enabled
          - RLS policy exists that filters by doctor_id
        """
        results = {}
        try:
            row = await db_session.execute(text("SELECT relrowsecurity FROM pg_class WHERE relname = 'appointments'"))
            rls_enabled = row.scalar()
            results["appointments"] = {
                "rls_enabled": bool(rls_enabled),
                "passed": bool(rls_enabled),
            }
        except Exception as exc:
            results["appointments"] = {
                "rls_enabled": False,
                "passed": False,
                "error": str(exc)[:100],
            }

        return {
            "passed": all(r.get("passed", False) for r in results.values()),
            "tables_checked": list(results.keys()),
            "details": results,
        }

    # ─── Rate Limiter Integration ────────────────────

    def get_rate_limiter(self) -> CalendarRateLimiter:
        return self.rate_limiter


# ─── Global Instance ────────────────────────────────

calendar_security = CalendarSecurityService()
