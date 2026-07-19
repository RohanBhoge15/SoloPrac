"""Email Queue Service — arq-based async email sending via SMTP.

Enqueues notifications for appointment confirmations, reminders, reschedules, cancellations.
Backed by Redis via arq worker.

Usage:
    from app.services.email_queue import email_queue
    await email_queue.enqueue(email_type="booking_confirmation", doctor_id=..., patient_id=..., ...)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)


class EmailQueueService:
    """Email queue using arq (Redis-backed async task queue)."""

    def __init__(self):
        self._enabled = bool(settings.SMTP_USER and settings.SMTP_PASSWORD)

    async def enqueue(self, email_type: str, **kwargs) -> bool:
        """Enqueue an email notification.

        email_type: booking_confirmation, reschedule_notification, cancellation_notification, appointment_reminder
        kwargs: doctor_id, patient_id, appointment_id, start_at, reason, etc.
        """
        if not self._enabled:
            logger.info("Email queue disabled (no SMTP credentials). Would send: %s %s", email_type, kwargs)
            return False

        try:
            import aioredis
            redis = await aioredis.from_url(settings.REDIS_URL)
            job = {
                "function": "send_email",
                "email_type": email_type,
                "kwargs": kwargs,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.rpush("arq:queue", json.dumps(job))
            await redis.close()
            logger.info("Enqueued email: %s for patient %s", email_type, kwargs.get("patient_id"))
            return True
        except Exception as exc:
            logger.warning("Failed to enqueue email: %s", exc)
            return False


email_queue = EmailQueueService()


# ─── Arq Worker Function ───────────────────────────

async def send_email(ctx, email_type: str, **kwargs):
    """Arq worker function to actually send email via SMTP."""
    import smtplib
    from email.mime.text import MIMEText

    patient_id = kwargs.get("patient_id", "")
    doctor_id = kwargs.get("doctor_id", "")
    start_at = kwargs.get("start_at", "")

    # Build email content based on type
    subjects = {
        "booking_confirmation": f"Appointment Confirmed - {start_at}",
        "reschedule_notification": f"Appointment Rescheduled - {start_at}",
        "cancellation_notification": "Appointment Cancelled",
        "appointment_reminder": f"Reminder: Appointment Tomorrow - {start_at}",
    }

    bodies = {
        "booking_confirmation": f"Your appointment has been booked for {start_at}.",
        "reschedule_notification": f"Your appointment has been rescheduled to {start_at}.",
        "cancellation_notification": f"Your appointment has been cancelled. Reason: {kwargs.get('reason', 'N/A')}",
        "appointment_reminder": f"This is a reminder for your appointment at {start_at}.",
    }

    subject = subjects.get(email_type, "Notification from SoloPrac AI")
    body = bodies.get(email_type, "You have a new notification from your healthcare provider.")

    # Get patient email (in production, decrypt from patient record)
    to_email = f"patient-{patient_id[:8]}@example.com"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM or "noreply@soloprac.ai"
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Email sent: %s to %s", subject, to_email)
        return {"status": "sent", "to": to_email}
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return {"status": "error", "error": str(exc)}


class WorkerSettings:
    """Arq worker configuration for email jobs."""
    functions = [send_email]
    max_burst_jobs = 5
    keep_result_seconds = 3600
    poll_delay = 2.0
    burst = False
