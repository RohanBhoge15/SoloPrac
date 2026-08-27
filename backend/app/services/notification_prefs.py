"""Notification Preferences Service — doctor-toggleable per event type validation.

Follows UpdatedIdea.MD spec for notification_preferences JSON schema:

    {
      "appointment_reminder": {"enabled": true, "hours_before": 2, "channels": ["in_app", "email"]},
      "new_report": {"enabled": true, "channels": ["in_app", "email"]},
      ...
    }

Usage:
    from app.services.notification_prefs import validate_notification_prefs, get_enabled_channels
    valid, errors = validate_notification_prefs(raw_dict)
    channels = get_enabled_channels(settings, "appointment_reminder")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

REQUIRED_EVENT_TYPES = [
    "appointment_reminder",
    "new_report",
    "invoice_generated",
    "booking_confirmation",
    "reschedule_notification",
    "certificate_issued",
]

ALLOWED_CHANNELS = {"in_app", "email"}

DEFAULT_PREFERENCES: Dict[str, Dict[str, Any]] = {
    "appointment_reminder": {"enabled": True, "hours_before": 2, "channels": ["in_app"]},
    "new_report": {"enabled": True, "channels": ["in_app", "email"]},
    "invoice_generated": {"enabled": True, "channels": ["in_app"]},
    "booking_confirmation": {"enabled": True, "channels": ["in_app"]},
    "reschedule_notification": {"enabled": True, "channels": ["in_app"]},
    "certificate_issued": {"enabled": True, "channels": ["in_app"]},
}


def validate_notification_prefs(
    prefs: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Validate notification preferences against the expected schema.

    Args:
        prefs: Raw dict from doctor_settings.notification_preferences.

    Returns:
        (valid: bool, errors: list[str])
    """
    errors = []

    if not isinstance(prefs, dict):
        return False, ["notification_preferences must be a dict"]

    for event_type in REQUIRED_EVENT_TYPES:
        config = prefs.get(event_type)
        if not isinstance(config, dict):
            errors.append(f"Missing or invalid config for '{event_type}'")
            continue

        if "enabled" in config and not isinstance(config["enabled"], bool):
            errors.append(f"'{event_type}.enabled' must be boolean")

        if "hours_before" in config:
            hb = config["hours_before"]
            if not isinstance(hb, (int, float)) or hb < 0 or hb > 720:
                errors.append(f"'{event_type}.hours_before' must be 0-720")

        if "channels" in config:
            channels = config["channels"]
            if not isinstance(channels, list):
                errors.append(f"'{event_type}.channels' must be a list")
            else:
                for ch in channels:
                    if ch not in ALLOWED_CHANNELS:
                        errors.append(f"Unknown channel '{ch}' in '{event_type}'. Allowed: {ALLOWED_CHANNELS}")
        else:
            errors.append(f"'{event_type}' missing 'channels' field")

    return len(errors) == 0, errors


def get_enabled_channels(
    doctor_settings: Dict[str, Any],
    event_type: str,
) -> List[str]:
    """Get enabled notification channels for an event type.

    Returns default channels if the event type is not configured.
    """
    prefs = doctor_settings.get("notification_preferences", {})
    config = prefs.get(event_type) or DEFAULT_PREFERENCES.get(event_type, {})

    if not config.get("enabled", True):
        return []

    return config.get("channels", ["in_app"])


def get_hours_before(
    doctor_settings: Dict[str, Any],
    event_type: str,
) -> int:
    """Get hours_before for reminder-type notifications."""
    prefs = doctor_settings.get("notification_preferences", {})
    config = prefs.get(event_type) or DEFAULT_PREFERENCES.get(event_type, {})
    return config.get("hours_before", 0)


def merge_with_defaults(
    custom_prefs: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge custom preferences with defaults (custom overrides defaults)."""
    merged = dict(DEFAULT_PREFERENCES)
    for event_type, config in custom_prefs.items():
        if event_type in merged and isinstance(config, dict):
            merged[event_type] = {**merged[event_type], **config}
        elif event_type in REQUIRED_EVENT_TYPES:
            merged[event_type] = config
    return merged
