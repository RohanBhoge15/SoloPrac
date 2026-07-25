"""Email Queue Service — arq-based async email sending via SMTP.

Enqueues notifications for appointment confirmations, reminders, reschedules, cancellations.
Backed by Redis via arq worker.

Usage:
    from app.services.email_queue import email_queue
    await email_queue.enqueue(email_type="booking_confirmation", doctor_id=..., patient_id=..., ...)

Real patient emails are decrypted from Patient.email_enc using pgcrypto.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from app.config import settings
from app.services.redis import redis_service

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
            client = await redis_service.connect()
            job = {
                "function": "send_email",
                "email_type": email_type,
                "kwargs": kwargs,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await client.rpush("arq:queue", json.dumps(job))
            logger.info("Enqueued email: %s for patient %s", email_type, kwargs.get("patient_id"))
            return True
        except Exception as exc:
            logger.warning("Failed to enqueue email: %s", exc)
            return False


email_queue = EmailQueueService()


# ─── Arq Worker Function ───────────────────────────

async def send_email(ctx, email_type: str, **kwargs):
    """Arq worker function to actually send email via SMTP.

    Decrypts patient email from DB using pgcrypto before sending.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    patient_id = kwargs.get("patient_id", "")
    doctor_id = kwargs.get("doctor_id", "")
    start_at = kwargs.get("start_at", "")

    # ─── Resolve real patient email from DB ───
    to_email = await _resolve_patient_email(ctx, patient_id)
    if not to_email:
        logger.warning("Cannot send %s: no valid email for patient %s", email_type, patient_id)
        return {"status": "error", "error": "no_patient_email"}

    # Build email content based on type
    subjects = {
        "booking_confirmation": f"Appointment Confirmed - {start_at}",
        "reschedule_notification": f"Appointment Rescheduled - {start_at}",
        "cancellation_notification": "Appointment Cancelled",
        "appointment_reminder": f"Reminder: Appointment Tomorrow - {start_at}",
        "prescription_issued": f"Prescription Issued by {kwargs.get('doctor_name', 'Doctor')}",
        "report_available": "New Report Available",
        "invoice_generated": f"Invoice Generated - {kwargs.get('invoice_number', '')}",
        "certificate_issued": f"Certificate Issued - {kwargs.get('cert_type', '')}",
        "weekly_report_ready": f"Weekly Clinical Report - {kwargs.get('layout', 'clinical')} Layout",
    }

    bodies = {
        "booking_confirmation": f"Your appointment has been booked for {start_at}.",
        "reschedule_notification": f"Your appointment has been rescheduled to {start_at}.",
        "cancellation_notification": f"Your appointment has been cancelled. Reason: {kwargs.get('reason', 'N/A')}",
        "appointment_reminder": f"This is a reminder for your appointment at {start_at}.",
        "prescription_issued": f"Dear Patient, Dr. {kwargs.get('doctor_name', 'your doctor')} has issued a new prescription. Please check your inbox for details.",
        "report_available": f"A new {kwargs.get('report_type', 'report')} is now available in your portal.",
        "invoice_generated": f"Invoice #{kwargs.get('invoice_number', '')} for {kwargs.get('total', '')} has been generated.",
        "certificate_issued": f"Your {kwargs.get('cert_type', 'medical')} certificate has been issued and is available for download.",
        "weekly_report_ready": f"Your weekly clinical report ({kwargs.get('layout', 'clinical')}) is now ready for download in your patient portal.",
    }

    subject = subjects.get(email_type, "Notification from SoloPrac AI")
    body = bodies.get(email_type, "You have a new notification from your healthcare provider.")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM or "noreply@soloprac.ai"
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))

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


async def _resolve_patient_email(ctx, patient_id: str) -> Optional[str]:
    """Decrypt patient's real email from the database.

    Uses the arq worker's db pool to run pgp_sym_decrypt on Patient.email_enc.
    """
    if not patient_id:
        return None

    try:
        # The arq worker ctx has a 'db' connection pool
        # We'll use the standard async_session_maker pattern
        from app.database import async_session_maker
        from app.models import Patient
        from sqlalchemy import select
        from app.services.encryption import decrypt_value

        async with async_session_maker() as session:
            result = await session.execute(
                select(Patient).where(Patient.id == patient_id)
            )
            patient = result.scalar_one_or_none()
            if not patient:
                logger.warning("Patient %s not found for email lookup", patient_id)
                return None

            if not patient.email_enc:
                logger.info("Patient %s has no encrypted email on file", patient_id)
                return None

            # Decrypt the email
            email = await decrypt_value(session, patient.email_enc, "patient-email")
            return email

    except Exception as exc:
        logger.error("Failed to resolve patient email for %s: %s", patient_id, exc)
        return None


async def run_risk_scan(ctx):
    """Arq scheduled job — Feature E live risk scan across all doctors.

    Imported lazily inside the function to avoid pulling heavy ML deps
    (numpy/clustering) into the API process at import time.
    """
    from app.services.risk_scan import scan_all_doctors
    return await scan_all_doctors()


def _redis_settings():
    """Build arq RedisSettings from app config."""
    from arq.connections import RedisSettings
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
    )


def _cron_jobs():
    """Cron schedule — risk scan every 30 minutes."""
    from arq import cron
    return [cron(run_risk_scan, minute={0, 30}, run_at_startup=False)]


class WorkerSettings:
    """Arq worker configuration for email jobs + scheduled risk scan."""
    functions = [send_email, run_risk_scan]
    cron_jobs = _cron_jobs()
    redis_settings = _redis_settings()
    max_burst_jobs = 5
    keep_result_seconds = 3600
    poll_delay = 2.0
    burst = False