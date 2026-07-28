"""PII De-identification — strip patient identity before it reaches external
LLMs or the vector index, and provide a deterministic pseudonym for re-association.

Industry pattern: **De-identification before Inference + client-side re-association.**
The external LLM (NIM / Groq) and the Qdrant vector store see only a pseudonymous
clinical profile ("P-8f3a1b2c, 28M, BP 140/90, ..."), never patient identity.
Patient identity is re-attached on the frontend from the local tenant DB — the LLM
never learns who the patient is.

Extensibility
-------------
To protect a NEW sensitive field, add its (lowercase) name to ``PII_FIELDS`` — that
is the only change required. ``strip_pii`` is applied at every boundary (index time
and inference time), so a one-line addition here removes that field everywhere.

Usage
-----
    from app.services.pii import strip_pii, pseudonymize_id

    safe_state   = strip_pii(version.state_jsonb)          # for embedding / LLM
    safe_context = strip_pii(patient_context, patient_id)  # injects patient_ref
    ref          = pseudonymize_id(patient_id)             # "P-8f3a1b2c"
"""

from __future__ import annotations

from typing import Any, Optional

# ─── Configuration ───────────────────────────────────────────
# Field names considered PII. Matched case-insensitively against dict keys at any
# nesting depth. ADD A NEW FIELD HERE (one line) to strip it everywhere.
PII_FIELDS: set[str] = {
    # Names
    "name",
    "first_name",
    "last_name",
    "full_name",
    "middle_name",
    "guardian_name",
    "father_name",
    "mother_name",
    "spouse_name",
    "next_of_kin",
    "emergency_contact",
    "emergency_contact_name",
    # Phone
    "phone",
    "phone_number",
    "mobile",
    "mobile_number",
    "alternate_phone",
    "phone_enc",
    # Email
    "email",
    "email_address",
    "email_enc",
    # Postal / location (only full address is PII when combined with name)
    "address",
    "address_line",
    "address_enc",
    "clinic_address",
    # Government / national identifiers
    "aadhaar",
    "aadhaar_number",
    "abha_id",
    "abha_number",
    "pan",
    "pan_number",
    "ssn",
    "national_id",
    "passport",
    "passport_number",
    "voter_id",
    "driving_license",
    # Dates / age (DOB + name = identity)
    "date_of_birth",
    "dob",
    "birth_date",
    # Internal IDs (must never reach external LLM)
    "patient_id",
    "medical_record_number",
    "mrn",
    "hospital_id",
    # Insurance
    "insurance_id",
    "insurance_number",
    "insurance_provider",
    # Occupation (identifying in small towns)
    "occupation",
    "employer",
    "workplace",
    # Sensitive (Indian context)
    "religion",
    "caste",
    "nationality",
    # Digital identifiers
    "ip_address",
    "device_id",
    "geolocation",
    "latitude",
    "longitude",
    # Misc direct identifiers
    "photo",
    "photo_url",
    "signature",
}

PSEUDONYM_PREFIX = "P-"
PSEUDONYM_ID_LEN = 8

# Key under which the pseudonym is injected into a de-identified context object.
PSEUDONYM_KEY = "patient_ref"


# ─── Pseudonym ───────────────────────────────────────────────
def pseudonymize_id(patient_id: Any) -> str:
    """Deterministic, storage-free pseudonym for a patient — e.g. ``P-8f3a1b2c``.

    The same ``patient_id`` always maps to the same pseudonym, so an LLM can refer
    to "P-8f3a1b2c" consistently within a conversation without ever learning who
    the patient is. Re-association happens client-side from the local DB.
    """
    if patient_id is None:
        return f"{PSEUDONYM_PREFIX}unknown"
    pid = str(patient_id).replace("-", "")
    return f"{PSEUDONYM_PREFIX}{pid[:PSEUDONYM_ID_LEN]}"


# ─── Core stripper ───────────────────────────────────────────
def is_pii_key(key: Any) -> bool:
    """True if a dict key names a PII field (case-insensitive)."""
    return isinstance(key, str) and key.strip().lower() in PII_FIELDS


def _strip(obj: Any) -> Any:
    """Recursively rebuild ``obj`` without any PII-keyed entries. Pure — never
    mutates the input (safe to call on live ``state_jsonb``)."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if not is_pii_key(k)}
    if isinstance(obj, list):
        return [_strip(item) for item in obj]
    return obj


def strip_pii(obj: Any, patient_id: Optional[Any] = None) -> Any:
    """Return a de-identified deep copy of ``obj`` with all PII fields removed.

    Recursively walks dicts and lists; any key in :data:`PII_FIELDS` is dropped at
    every depth. Non-PII clinical data (age, gender, vitals, diagnoses, meds, ...)
    is preserved verbatim.

    If ``patient_id`` is supplied and the result is a dict, a stable pseudonym is
    injected under :data:`PSEUDONYM_KEY` so the LLM has a non-identifying handle.

    Never mutates the input.
    """
    cleaned = _strip(obj)
    if patient_id is not None and isinstance(cleaned, dict):
        cleaned.setdefault(PSEUDONYM_KEY, pseudonymize_id(patient_id))
    return cleaned


# ─── Re-association ─────────────────────────────────────────
def reassociate_pseudonym(text: str, patient_name: str) -> str:
    """Replace all pseudonym references in *text* with the real patient name.

    The LLM may refer to "P-a1b2c3d4" throughout its response. This swaps
    those back to the patient's real name before the response reaches the
    frontend. Only the pseudonym format ``P-{8 hex chars}`` is replaced —
    any other ``P-`` prefix in clinical text is left untouched.

    Examples:
        >>> reassociate_pseudonym("P-a1b2c3d4 has BP 140/90", "Rohan Bhoge")
        'Rohan Bhoge has BP 140/90'
        >>> reassociate_pseudonym("Compare P-a1b2c3d4 with P-a1b2c3d4", "Priya")
        'Compare Priya with Priya'
    """
    import re
    # Match P- followed by exactly 8 hex characters (word boundary or end of string)
    pattern = rf"{PSEUDONYM_PREFIX}[0-9a-fA-F]{{{PSEUDONYM_ID_LEN}}}(?=\b|$|[.,;:!?)\]])"
    return re.sub(pattern, patient_name, text)


async def get_patient_name_for_reassociation(patient_id: Any) -> Optional[str]:
    """Look up the patient's real name from the local DB for re-association.

    Returns the name from ``state_jsonb.demographics.name`` of the head version,
    or ``None`` if the patient / version / name is missing. This is a single
    primary-key query with connection pooling — sub-millisecond overhead.

    Lazy-imports DB modules to avoid circular imports at module load time.
    """
    from uuid import UUID
    from sqlalchemy import select
    from app.database import async_session_maker
    from app.models import Patient

    if patient_id is None:
        return None

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Patient).where(Patient.id == UUID(str(patient_id)))
            )
            patient = result.scalar_one_or_none()
            if not patient or not patient.head_version_id:
                return None

            # Load head version to get demographics.name
            from app.models import PatientVersion
            version_result = await session.execute(
                select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
            )
            version = version_result.scalar_one_or_none()
            if not version or not version.state_jsonb:
                return None

            demographics = version.state_jsonb.get("demographics", {})
            return demographics.get("name")
    except Exception:
        # Never let re-association failure break the response
        return None


# ─── Citation Validation ────────────────────────────────────
def validate_citations(text: str, valid_citations: list[dict]) -> str:
    """Validate and sanitize citation references in LLM response text.

    Parses ``[v{N} · {date}]`` patterns from the text and verifies each one
    against the ``valid_citations`` list (from the retrieval step). Invalid
    citations (hallucinated version numbers or dates) are stripped from the
    response to prevent the doctor from following false references.

    Args:
        text: The LLM-generated response containing citation patterns.
        valid_citations: List of citation dicts from the retrieval step,
            each with ``version_number`` and ``date`` keys.

    Returns:
        The cleaned text with invalid citations removed.
    """
    import re

    if not valid_citations:
        return text

    # Build a set of valid (version_number, date) pairs from retrieval
    valid_pairs = set()
    for c in valid_citations:
        vn = c.get("version_number")
        date = c.get("date", "")
        if vn is not None:
            valid_pairs.add((int(vn), str(date)[:10]))  # normalize to YYYY-MM-DD

    # Pattern: [v{number} · {date}]
    citation_pattern = re.compile(r'\[v(\d+)\s*·\s*([\d-]+)\]')

    def _replace_invalid(match):
        vn = int(match.group(1))
        date = match.group(2)
        # Check if this citation is valid
        if (vn, date) in valid_pairs:
            return match.group(0)  # keep valid citation
        # Strip invalid citation (hallucinated reference)
        return ""

    cleaned = citation_pattern.sub(_replace_invalid, text)

    # Also strip orphaned citations with no date (e.g., "[v3]")
    orphan_pattern = re.compile(r'\[v(\d+)\](?!\s*·)')
    cleaned = orphan_pattern.sub("", cleaned)

    # Clean up double spaces left by removed citations
    cleaned = re.sub(r'  +', ' ', cleaned).strip()

    return cleaned
