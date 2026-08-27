"""Prompt Injection Defense — OCR text sanitization and LLM input validation.

Provides:
  1. OCR text sanitization — strip control chars, truncate, detect injection patterns
  2. Structured output enforcement — JSON Schema validation via Pydantic
  3. Input validation — detect and neutralize my capabilities injection attempts before they reach the LLM

Usage:
    from app.services.sanitizer import sanitize_ocr_text, validate_structured_output, detect_injection

    # Sanitize OCR text before LLM
    safe_text = sanitize_ocr_text(raw_ocr_output)

    # Validate structured LLM output against schema
    result = validate_structured_output(llm_json, expected_schema)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# ─── Constants ───

MAX_OCR_TEXT_LENGTH = 100_000  # 100KB max input to LLM
MAX_SINGLE_LINE_LENGTH = 10_000

# Suspicious patterns that indicate prompt injection attempts
INJECTION_PATTERNS: List[re.Pattern] = [
    # System instruction override attempts
    re.compile(
        r"(?i)(ignore|disregard|override|forget)\s+(all\s+)?(previous|above|system|instruction|prompt)", re.IGNORECASE
    ),
    re.compile(
        r"(?i)(you are|act as|pretend to be|from now on)\s+(a\s+)?(different|free|unrestricted|chatgpt|gpt)",
        re.IGNORECASE,
    ),
    # Role-playing escape
    re.compile(r"(?i)(new\s+)?(role|identity|persona|character):\s*(admin|developer|hacker|root)", re.IGNORECASE),
    # Command injection
    re.compile(r"(?i)(run|execute|eval|exec)\s*(`|'|\"|\[|\(|system|cmd|shell|bash)", re.IGNORECASE),
    # Data extraction attempts
    re.compile(
        r"(?i)(reveal|spill|leak|dump|show)\s*(your|the)\s*(my capabilities|my capabilities|instructions|system|prompt|config|API key|password|secret)",
        re.IGNORECASE,
    ),
    # Delimiter breaking
    re.compile(r"(?i)(ignore|disregard)\s*(all\s+)?(above|previous|instructions|text|content)", re.IGNORECASE),
    # Hidden text / white-on-white
    re.compile(r"(?i)(white\s*text|hidden\s*text|invisible|color:\s*white|font-size:\s*0)", re.IGNORECASE),
    # Repeated tokens / jailbreak
    re.compile(r"(\b[A-Za-z]\b\s*){50,}"),  # single letters repeated
    re.compile(r"(?i)(DAN|jailbreak|no filter|unfiltered|censorship|bypass)", re.IGNORECASE),
]

# High-risk keywords that should trigger a strip or block
HIGH_RISK_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)\b(BEGIN|END)\s+(INPUT|PROMPT|TEXT|DOCUMENT|OCR|OUTPUT)\b", re.IGNORECASE),
    re.compile(r"(?i)<\s*(system|user|assistant|role|instruction)\s*>", re.IGNORECASE),
    re.compile(r"(?i)\[system\]|\[assistant\]|\[user\]|\[INST\]|<\|", re.IGNORECASE),
]


# ─── OCR Sanitization ───


def sanitize_ocr_text(text: str, max_length: int = MAX_OCR_TEXT_LENGTH) -> str:
    """Sanitize OCR-extracted text before passing to an LLM.

    Steps:
      1. Remove null bytes and control characters (except newlines/tabs)
      2. Truncate very long single lines
      3. Strip known injection delimiter markers
      4. Detect and log injection attempts
      5. Truncate to max total length

    Args:
        text: Raw text from OCR engine.
        max_length: Maximum total characters allowed.

    Returns:
        Sanitized text safe for LLM consumption.
    """
    if not text:
        return ""

    # Step 1: Remove null bytes and non-printable control chars
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Step 2: Truncate excessively long single lines (likely scanner artifacts)
    lines = cleaned.split("\n")
    truncated_lines = []
    for line in lines:
        original_len = len(line)
        if len(line) > MAX_SINGLE_LINE_LENGTH:
            line = line[:MAX_SINGLE_LINE_LENGTH] + " [TRUNCATED - line too long]"
            logger.warning("Truncated OCR line from %d to %d chars", original_len, MAX_SINGLE_LINE_LENGTH)
        truncated_lines.append(line)
    cleaned = "\n".join(truncated_lines)

    # Step 3: Strip high-risk delimiter markers
    for pattern in HIGH_RISK_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Step 4: Detect injection patterns
    detected = detect_injection(cleaned)
    if detected:
        logger.warning("Injection pattern detected in OCR text: %s", detected[:3])

    # Step 5: Final truncation
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "\n[TRUNCATED - content exceeds maximum length]"
        logger.info("Truncated OCR input from %d to %d", len(cleaned), max_length)

    return cleaned.strip()


def detect_injection(text: str) -> List[str]:
    """Detect potential prompt injection patterns in input text.

    Returns a list of matched pattern descriptions (empty if clean).
    """
    matches = []
    for i, pattern in enumerate(INJECTION_PATTERNS):
        match = pattern.search(text)
        if match:
            matched_text = match.group(0)[:80]
            matches.append(f"Pattern {i}: '{matched_text}'")
    return matches


def sanitize_for_doc_type(text: str, doc_type: str = "general") -> str:
    """Document-type-specific sanitization.

    Different document types need different handling:
      - Prescriptions: preserve medication names, doses, instructions
      - Lab reports: preserve numerical values, units, reference ranges
      - Discharge summaries: preserve medical terminology, timeline
    """
    if doc_type == "prescription":
        # Preserve: medication names (capitalized), doses (mg, mcg, ml), instructions
        # Strip: excess whitespace, normalize line breaks
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return "\n".join(lines)

    elif doc_type == "lab_report":
        # Preserve: numerical values, units, test names
        # Normalize: ensure units are spaced properly
        text = re.sub(r"(\d+)(mg|g|mcg|ml|dl|L|%|mmol)", r"\1 \2", text)
        return text.strip()

    elif doc_type in ("discharge_summary", "referral_letter"):
        # Preserve full medical narrative
        # Strip only control chars
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()

    return sanitize_ocr_text(text)


def strip_suspicious_content(text: str) -> str:
    """Remove suspicious blocks from text (e.g., delimiter-wrapped injection attempts)."""
    # Remove content between known delimiter pairs that might indicate injection
    patterns = [
        (r"(?i)---+\s*BEGIN\s+(PROMPT|INPUT|TEXT|SYSTEM)\s*---+.*?---+", ""),
        (r"(?i)<\s*(system|user|assistant)\s*[^>]*>.*?</\s*(system|user|assistant)\s*>", ""),
        (r"(?i)\[system\].*?\[/system\]", ""),
        (r"(?i)\[assistant\].*?\[/assistant\]", ""),
    ]
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.DOTALL | re.IGNORECASE)
    return result


# ─── Structured Output Validation ───


def validate_structured_output(
    data: Dict[str, Any],
    schema_model: Type[BaseModel],
) -> Dict[str, Any]:
    """Validate a structured output (JSON dict) against a Pydantic model.

    Args:
        data: The parsed JSON dictionary from the LLM.
        schema_model: A Pydantic BaseModel subclass defining the expected schema.

    Returns:
        The validated data dict (with defaults applied).

    Raises:
        ValueError: With details of all validation errors if validation fails.
    """
    try:
        validated = schema_model.model_validate(data)
        return validated.model_dump()
    except ValidationError as e:
        errors = []
        for err in e.errors():
            field = " -> ".join(str(loc) for loc in err.get("loc", []))
            errors.append(f"  - {field}: {err.get('msg', 'unknown error')} (type={err.get('type')})")
        error_msg = f"Structured output validation failed ({len(errors)} error(s)):\n" + "\n".join(errors)
        logger.error(error_msg)
        raise ValueError(error_msg)


def safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON from LLM output, handling markdown fences."""
    if not text:
        return None

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n```\s*$", "", text)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, list):
                return {"results": result}
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from LLM output")
    return None


# ─── Schema Definitions ───


# Prescription output schema
class PrescriptionSchema(BaseModel):
    doctor_id: str
    patient_id: str
    issued_at: str
    diagnosis_short: str
    medications: List[Dict[str, str]]
    investigations: List[str] = []
    lifestyle: List[str] = []
    follow_up: Dict[str, Any]
    doctor_notes: Optional[str] = None
    ai_disclaimer_acknowledged: bool = True


# Appointment booking schema
class AppointmentSchema(BaseModel):
    patient_id: str
    doctor_id: str
    start_at: str
    end_at: str
    reason: Optional[str] = None
    source: str = "manual"


# Weekly report schema
class WeeklyReportSchema(BaseModel):
    patient_id: str
    week_start: str
    week_end: str
    summary: str
    changes: List[Dict[str, Any]] = []
    recommendations: List[str] = []
    significance_score: float = 0.0
