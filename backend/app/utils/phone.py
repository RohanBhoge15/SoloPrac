"""Phone normalization helpers for patient matching.

Normalizes phone numbers to a canonical 10-digit format for comparison.
Handles Indian phone formats: +91-9876543210, 919876543210, 09876543210, etc.
"""

from __future__ import annotations

import re


def normalize_phone(phone: str) -> str:
    """Normalize phone number to last 10 digits for comparison.

    Examples:
        "+91-9876543210" → "9876543210"
        "919876543210"   → "9876543210"
        "098765-43210"   → "9876543210"
        "98765 43210"    → "9876543210"
        "+1-555-1234567" → "5551234567"  (non-Indian, keeps last 10)
    """
    if not phone:
        return ""
    # Strip everything except digits
    digits = re.sub(r"\D", "", phone)
    # Take last 10 digits (handles +91 prefix, 0 prefix, etc.)
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def phones_match(phone_a: str, phone_b: str) -> bool:
    """Check if two phone numbers match after normalization."""
    return normalize_phone(phone_a) == normalize_phone(phone_b) and len(normalize_phone(phone_a)) == 10
