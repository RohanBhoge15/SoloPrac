"""AI Notification Generator — Maverick generates notification content per event type.

Notification types (from UpdatedIdea.MD):
  - appointment_reminder — configurable n-hours before
  - booking_confirmation — after booking
  - reschedule_notification — appointment moved
  - cancellation_notification — appointment cancelled
  - report_available — new lab/report added
  - invoice_generated — new invoice
  - certificate_issued — new certificate

Each notification has:
  - subject: Short AI-generated subject line
  - body: Natural language message with patient context

Usage:
    from app.services.notification_generator import generate_notification
    result = await generate_notification("booking_confirmation", patient_name="Priya", ...)
    # -> {"subject": "...", "body": "..."}
"""

from __future__ import annotations

import logging
from typing import Dict

from app.agents.synthesizer import MaverickSynthesizer

logger = logging.getLogger(__name__)

EVENT_TYPES = [
    "appointment_reminder",
    "booking_confirmation",
    "reschedule_notification",
    "cancellation_notification",
    "report_available",
    "prescription_issued",
    "invoice_generated",
    "certificate_issued",
]

PROMPT_TEMPLATES: Dict[str, str] = {
    "appointment_reminder": (
        "Generate a friendly appointment reminder notification for a patient. "
        "Patient: {patient_name}. Appointment: {date} at {time}. "
        "Output JSON with 'subject' and 'body' fields. Keep it warm and helpful."
    ),
    "booking_confirmation": (
        "Generate a booking confirmation notification. "
        "Patient: {patient_name}. Date: {date}. Time: {time}. Doctor: {doctor_name}. "
        "Output JSON with 'subject' and 'body'. Include what to bring if available."
    ),
    "reschedule_notification": (
        "Generate a reschedule notification. "
        "Patient: {patient_name}. Old: {old_date} {old_time}. New: {new_date} {new_time}. "
        "Output JSON with 'subject' and 'body'. Apologize briefly and state new time clearly."
    ),
    "cancellation_notification": (
        "Generate a cancellation notification. "
        "Patient: {patient_name}. Appointment was on {date} at {time}. "
        "Output JSON with 'subject' and 'body'. Inform about cancellation and next steps."
    ),
    "report_available": (
        "Generate a notification that a new medical report is available. "
        "Patient: {patient_name}. Report type: {report_type}. "
        "Output JSON with 'subject' and 'body'. Explain what the report contains briefly."
    ),
    "prescription_issued": (
        "Generate a notification that a new prescription has been issued. "
        "Patient: {patient_name}. Doctor: {doctor_name} ({doctor_speciality}) at {clinic_name}. "
        "Medications prescribed: {medications}. "
        "Output JSON with 'subject' and 'body' fields. The body should briefly list the prescribed medications."
    ),
    "invoice_generated": (
        "Generate an invoice notification. "
        "Patient: {patient_name}. Amount: {amount}. Invoice: {invoice_number}. "
        "Output JSON with 'subject' and 'body'."
    ),
    "certificate_issued": (
        "Generate a certificate issued notification. "
        "Patient: {patient_name}. Certificate type: {cert_type}. "
        "Output JSON with 'subject' and 'body'."
    ),
}

FALLBACK_TEMPLATES: Dict[str, Dict[str, str]] = {
    "appointment_reminder": {
        "subject": "Appointment Reminder - Tomorrow at {time}",
        "body": "Dear {patient_name}, this is a reminder for your appointment tomorrow at {time}. Please arrive 10 minutes early.",
    },
    "booking_confirmation": {
        "subject": "Appointment Confirmed - {date}",
        "body": "Dear {patient_name}, your appointment has been confirmed for {date} at {time} with {doctor_name}.",
    },
    "reschedule_notification": {
        "subject": "Appointment Rescheduled",
        "body": "Dear {patient_name}, your appointment has been moved to {new_date} at {new_time}.",
    },
    "cancellation_notification": {
        "subject": "Appointment Cancelled",
        "body": "Dear {patient_name}, your appointment on {date} has been cancelled. Please contact the clinic to reschedule.",
    },
    "report_available": {
        "subject": "New Report Available",
        "body": "Dear {patient_name}, a new {report_type} report is now available in your portal.",
    },
    "prescription_issued": {
        "subject": "Prescription Issued - {doctor_name}",
        "body": "Dear {patient_name}, Dr. {doctor_name} has issued a new prescription. Medications: {medications}.",
    },
    "invoice_generated": {
        "subject": "Invoice #{invoice_number} Generated",
        "body": "Dear {patient_name}, invoice #{invoice_number} for {amount} has been generated.",
    },
    "certificate_issued": {
        "subject": "Certificate Issued",
        "body": "Dear {patient_name}, your {cert_type} certificate has been issued and is available for download.",
    },
    "weekly_report_ready": {
        "subject": "Weekly Clinical Report Ready - {layout} Layout",
        "body": "Dear {patient_name}, your weekly clinical report ({layout}) is now ready to download from your patient portal.",
    },
}


async def generate_notification(
    event_type: str,
    **context,
) -> Dict[str, str]:
    """Generate an AI notification using Maverick.

    Args:
        event_type: One of the EVENT_TYPES.
        **context: Patient-specific fields like patient_name, date, time, etc.

    Returns:
        {"subject": str, "body": str}
    """
    if event_type not in PROMPT_TEMPLATES:
        logger.warning("Unknown event type: %s, using fallback", event_type)
        return _fallback(event_type, context)

    # Try Maverick first
    synthesizer = MaverickSynthesizer()
    if synthesizer.is_available:
        try:
            prompt = PROMPT_TEMPLATES[event_type].format(**context)
            response = await synthesizer.synthesize(
                query=prompt,
                context={},
                structured_output={"type": "json_object"},
            )

            raw = response.get("response", "")
            import json as _json
            import re as _re

            raw = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            parsed = _json.loads(raw) if raw else {}
            subject = parsed.get("subject", "").strip()
            body = parsed.get("body", "").strip()
            if subject and body:
                return {"subject": subject, "body": body}
        except Exception as exc:
            logger.warning("Maverick notification generation failed: %s", exc)

    # Fallback
    return _fallback(event_type, context)


def _fallback(event_type: str, context: dict) -> Dict[str, str]:
    """Generate a template-based fallback notification."""
    template = FALLBACK_TEMPLATES.get(event_type, {})
    try:
        subject = template.get("subject", "Notification from SoloPrac AI").format(**context)
        body = template.get("body", "You have a new notification from your healthcare provider.").format(**context)
    except KeyError:
        subject = "Notification from SoloPrac AI"
        body = "You have a new notification from your healthcare provider."
    return {"subject": subject, "body": body}


# ─── Patient Notifications CRUD ────────────────────


async def create_patient_notification(
    db_session,
    patient_id,
    doctor_id,
    event_type: str,
    subject: str,
    body: str,
    channels: list = None,
    meta: dict = None,
) -> dict:
    """Create a patient notification record and push via WebSocket."""
    import uuid

    from app.models import PatientNotification

    notification = PatientNotification(
        id=uuid.uuid4(),
        patient_id=patient_id,
        doctor_id=doctor_id,
        kind=event_type,
        subject=subject[:255],
        body=body,
        channel=channels or ["in_app"],
        meta=meta,
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)

    # Push via WebSocket
    try:
        from app.routers.portal import ws_manager

        payload = {
            "type": "notification",
            "data": {
                "id": str(notification.id),
                "kind": event_type,
                "subject": subject,
                "body": body,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
            },
        }
        if meta:
            payload["data"]["meta"] = meta
        await ws_manager.notify_patient(str(patient_id), payload)
    except Exception as exc:
        logger.warning("WebSocket push failed: %s", exc)

    return {
        "id": str(notification.id),
        "kind": event_type,
        "subject": subject,
        "body": body,
        "meta": meta,
    }


# ─── Doctor Notifications (C-9) ────────────────────
# Doctor-facing events. Fires when a patient books, an admin approves the
# doctor's license, the weekly report is ready, etc. Mirrors the patient
# path above: insert row + push over the /ws/doctor/{id} socket.

DOCTOR_EVENT_TYPES = [
    "appointment_booked_by_patient",
    "patient_registered",
    "verification_status_changed",
    "weekly_report_ready",
    "pending_matches_available",
    "system_message",
]


async def create_doctor_notification(
    db_session,
    doctor_id,
    event_type: str,
    subject: str,
    body: str,
    meta: dict = None,
    patient_id=None,
) -> dict:
    """C-9: Create a doctor notification row + push via WebSocket.

    Mirrors create_patient_notification.
    """
    import uuid

    from app.models import DoctorNotification

    notification = DoctorNotification(
        id=uuid.uuid4(),
        doctor_id=doctor_id,
        kind=event_type,
        subject=subject[:255],
        body=body,
        meta=meta,
        patient_id=patient_id,
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)

    # Push via WebSocket (notify_doctor already exists on ConnectionManager)
    try:
        from app.routers.portal import ws_manager

        payload = {
            "type": "notification",
            "data": {
                "id": str(notification.id),
                "kind": event_type,
                "subject": subject,
                "body": body,
                "patient_id": str(patient_id) if patient_id else None,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
            },
        }
        if meta:
            payload["data"]["meta"] = meta
        await ws_manager.notify_doctor(str(doctor_id), payload)
    except Exception as exc:
        logger.warning("Doctor WebSocket push failed: %s", exc)

    return {
        "id": str(notification.id),
        "kind": event_type,
        "subject": subject,
        "body": body,
        "meta": meta,
        "patient_id": str(patient_id) if patient_id else None,
    }


async def dispatch_doctor_event(
    db_session,
    event_type: str,
    doctor_id,
    subject: str,
    body: str,
    meta: dict = None,
    patient_id=None,
) -> dict:
    """C-9: Doctor-side dispatcher.

    Thin wrapper around create_doctor_notification that consults
    doctor.settings.notification_preferences to skip disabled events
    (mirroring generate_and_dispatch on the patient side).
    """
    from sqlalchemy import select

    from app.models import Doctor

    doc_result = await db_session.execute(select(Doctor).where(Doctor.id == doctor_id))
    doc = doc_result.scalar_one_or_none()
    settings = doc.settings or {} if doc else {}
    notification_prefs = settings.get("notification_preferences", {})
    event_config = notification_prefs.get(event_type, {})
    if not event_config.get("enabled", True):
        logger.info("Doctor notification '%s' disabled by doctor %s", event_type, doctor_id)
        return None

    return await create_doctor_notification(
        db_session,
        doctor_id=doctor_id,
        event_type=event_type,
        subject=subject,
        body=body,
        meta=meta,
        patient_id=patient_id,
    )


async def generate_and_dispatch(
    db_session,
    event_type: str,
    patient_id,
    doctor_id,
    meta: dict = None,
    **context,
) -> dict:
    """Generate notification and dispatch via WebSocket + email.

    One-shot for events like booking_confirmation, invoice_generated, etc.
    """
    # Generate content
    content = await generate_notification(event_type, **context)

    # Get doctor settings for channel preferences
    from sqlalchemy import select

    from app.models import Doctor

    doc_result = await db_session.execute(select(Doctor).where(Doctor.id == doctor_id))
    doc = doc_result.scalar_one_or_none()
    settings = doc.settings or {} if doc else {}
    notification_prefs = settings.get("notification_preferences", {})
    event_config = notification_prefs.get(event_type, {})
    if not event_config.get("enabled", True):
        logger.info("Notification type '%s' disabled by doctor %s", event_type, doctor_id)
        return None

    channels = event_config.get("channels", ["in_app"])

    # Create and dispatch
    result = await create_patient_notification(
        db_session,
        patient_id,
        doctor_id,
        event_type,
        content["subject"],
        content["body"],
        channels=channels,
        meta=meta,
    )

    # Email fallback
    if "email" in channels:
        try:
            from app.services.email_queue import email_queue

            await email_queue.enqueue(
                email_type=event_type,
                patient_id=str(patient_id),
                doctor_id=str(doctor_id),
                subject=content["subject"],
                body=content["body"],
            )
        except Exception as exc:
            logger.warning("Email dispatch failed: %s", exc)

    return result
