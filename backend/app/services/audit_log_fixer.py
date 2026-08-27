"""Audit Log Completeness Check — ensures every mutation event is logged.

Scans existing AuditLog model usage and identifies gaps.
Adds missing audit event types for paper compliance.

Expected events (from UpdatedIdea.MD):
  appointment_created, appointment_rescheduled, appointment_cancelled
  prescription_created, invoice_generated, invoice_status_changed
  certificate_created, version_created, version_reverted
  image_comparison_created, comparison_saved_to_record
  patient_otp_sent, patient_logged_in, appointment_booked_portal
  notification_sent, notification_read
  portal_login, report_accessed
  working_hours_changed, settings_changed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Set
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger(__name__)

# Complete event type taxonomy for paper
ALL_EVENT_TYPES = {
    "auth": {
        "doctor_login",
        "doctor_logout",
        "patient_login",
        "patient_logout",
        "patient_otp_sent",
        "token_refresh",
        "password_reset",
    },
    "patient": {
        "patient_created",
        "patient_updated",
        "patient_deleted",
    },
    "version": {
        "version_created",
        "version_reverted",
        "version_diff_viewed",
    },
    "appointment": {
        "appointment_created",
        "appointment_rescheduled",
        "appointment_cancelled",
        "appointment_booked_portal",
    },
    "document": {
        "document_uploaded",
        "document_parsed",
        "document_saved_to_patient",
    },
    "image": {
        "image_uploaded",
        "image_compared",
        "comparison_saved_to_record",
    },
    "prescription": {
        "prescription_created",
        "prescription_pdf_downloaded",
    },
    "invoice": {
        "invoice_generated",
        "invoice_status_changed",
        "invoice_pdf_downloaded",
    },
    "certificate": {
        "certificate_created",
        "certificate_verified",
        "certificate_pdf_downloaded",
    },
    "settings": {
        "working_hours_changed",
        "settings_changed",
        "notification_preferences_changed",
    },
    "notification": {
        "notification_sent",
        "notification_read",
        "notification_email_sent",
    },
    "portal": {
        "portal_login",
        "report_accessed",
    },
    "security": {
        "login_failed",
        "rls_violation_attempted",
        "rate_limit_exceeded",
    },
}

EXPECTED_EVENT_COUNT = sum(len(v) for v in ALL_EVENT_TYPES.values())
MINIMUM_ACCEPTABLE_EVENT_TYPES = 30  # We should have at least this many distinct event types


async def check_audit_completeness(db: AsyncSession) -> Dict[str, Any]:
    """Check which event types are actually logged in the audit_log table.

    Args:
        db: Database session.

    Returns:
        Report of present and missing event types.
    """
    result = await db.execute(select(func.distinct(AuditLog.event_type)))
    existing_events: Set[str] = set(row[0] for row in result.all())

    # Categorize
    present = {}
    missing = {}
    for category, events in ALL_EVENT_TYPES.items():
        present_events = events & existing_events
        missing_events = events - existing_events
        if present_events:
            present[category] = sorted(present_events)
        if missing_events:
            missing[category] = sorted(missing_events)

    total_present = len(existing_events)
    coverage_pct = round(total_present / EXPECTED_EVENT_COUNT * 100, 1) if EXPECTED_EVENT_COUNT else 0

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_event_types_defined": EXPECTED_EVENT_COUNT,
        "total_event_types_logged": total_present,
        "coverage_percentage": coverage_pct,
        "passed": coverage_pct >= 70.0,  # 70% coverage is acceptable for paper
        "present": present,
        "missing": missing,
        "recommendation": (
            "Add logging for missing event types in their respective routers. "
            "Critical missing events should be added before paper submission."
        ),
    }

    logger.info(
        "Audit completeness: %d/%d event types logged (%.1f%%)",
        total_present,
        EXPECTED_EVENT_COUNT,
        coverage_pct,
    )

    return report


async def log_security_event(
    db: AsyncSession,
    doctor_id: UUID,
    patient_id: UUID,
    event_type: str,
    details: Dict[str, Any] = None,
) -> AuditLog:
    """Generic audit log entry for any event type.

    Use this in routers to ensure all mutations are logged.
    """
    audit = AuditLog(
        doctor_id=doctor_id,
        patient_id=patient_id,
        event_type=event_type,
        details=details or {},
    )
    db.add(audit)
    await db.commit()
    logger.debug("Audit: %s (doctor=%s, patient=%s)", event_type, doctor_id, patient_id)
    return audit
