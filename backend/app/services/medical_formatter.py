"""Maverick Structured Output — Medical document formatter for Rx/Invoice/Certificate.

Generates structured JSON for three document types using Maverick LLM
with Pydantic validation. Each type has a schema and prompt template.

Usage:
    from app.services.medical_formatter import MedicalFormatter
    formatter = MedicalFormatter()
    rx = await formatter.format_prescription(doctor_notes="...")
    inv = await formatter.format_invoice(consultation_data={...})
    cert = await formatter.format_certificate(doctor_notes="...")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, Field, ValidationError

from app.agents.synthesizer import MaverickSynthesizer
from app.services.sanitizer import safe_parse_json

logger = logging.getLogger(__name__)

# ─── Pydantic Schemas ───


class PrescriptionOutput(BaseModel):
    diagnosis: str = Field("", description="Short diagnosis (≤120 chars)")
    medications: list[dict] = Field(
        default_factory=list, description="List of medications with drug/strength/dose/frequency/duration/instructions"
    )
    investigations: list[str] = Field(default_factory=list)
    lifestyle_advice: list[str] = Field(default_factory=list)
    follow_up: str = Field("", description="Follow-up instructions")
    doctor_notes: str = Field("", description="Additional notes")


class InvoiceOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="Line items with description/qty/rate/amount")
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    notes: str = ""


class CertificateOutput(BaseModel):
    body: str = Field("", description="Certificate body text")
    cert_type: str = Field("other", description="sick_leave|fitness|school|disability|other")
    recommended_rest: str = Field("", description="Recommended rest duration")


# ─── Prompt Templates ───

PRESCRIPTION_PROMPT = """You are a medical documentation assistant. Generate a structured prescription JSON from the doctor's notes.

Schema:
{
  "diagnosis": "Short diagnosis (≤120 chars)",
  "medications": [{"drug": "Metformin", "strength": "500 mg", "dose": "1 tab", "frequency": "BD", "duration": "30 days", "instructions": "After meals"}],
  "investigations": ["HbA1c", "Fasting Glucose"],
  "lifestyle_advice": ["Reduce refined carbs", "30 min walk daily"],
  "follow_up": "Review in 4 weeks",
  "doctor_notes": ""
}

Rules:
- Use standard medical abbreviations (OD, BD, TID, QID, PRN, HS, etc.)
- Include strength with each medication
- Be concise but complete
- Return ONLY valid JSON

Doctor's notes: {notes}

Output:"""

INVOICE_PROMPT = """You are a medical billing assistant. Generate an invoice JSON from consultation data.

Schema:
{
  "items": [{"description": "Consultation fee", "qty": 1, "rate": 500, "amount": 500}],
  "subtotal": 500.0,
  "tax": 0.0,
  "total": 500.0,
  "notes": ""
}

Rules:
- Calculate subtotal = sum of amounts
- Total = subtotal + tax
- Use INR (₹) for monetary values stored as float
- Return ONLY valid JSON

Consultation data: {notes}

Output:"""

CERTIFICATE_PROMPT = """You are a medical certificate assistant. Generate a structured certificate JSON.

Schema:
{
  "body": "This patient is under my care for...",
  "cert_type": "sick_leave",
  "recommended_rest": "3 days"
}

cert_type options: sick_leave, fitness, school, disability, other

Rules:
- Body should be 2-4 sentences of professional medical text
- Include specific medical context if provided
- Return ONLY valid JSON

Doctor's notes: {notes}

Output:"""


# ─── Medical Formatter ───


class MedicalFormatter:
    """Generates structured medical documents using Maverick LLM."""

    def __init__(self):
        self._synthesizer = MaverickSynthesizer()

    async def format_prescription(self, notes: str, patient_context: Optional[dict] = None) -> Dict[str, Any]:
        return await self._format(PRESCRIPTION_PROMPT, PrescriptionOutput, notes=notes)

    async def format_invoice(self, notes: str, consultation_data: Optional[dict] = None) -> Dict[str, Any]:
        return await self._format(INVOICE_PROMPT, InvoiceOutput, notes=notes)

    async def format_certificate(self, notes: str, patient_context: Optional[dict] = None) -> Dict[str, Any]:
        return await self._format(CERTIFICATE_PROMPT, CertificateOutput, notes=notes)

    async def _format(
        self,
        prompt_template: str,
        schema: Type[BaseModel],
        **kwargs,
    ) -> Dict[str, Any]:
        """Format a medical document through the pipeline.

        Pipeline:
          1. Build prompt with context
          2. Maverick generates JSON
          3. Parse + validate with Pydantic
          4. Return structured output or fallback
        """
        notes = kwargs.get("notes", "")

        if self._synthesizer.is_available:
            try:
                prompt = prompt_template.format(**kwargs)
                response = await self._synthesizer.synthesize(
                    query=prompt,
                    context={},
                    structured_output={"type": "json_object"},
                )

                raw = response.get("response", "")
                parsed = safe_parse_json(raw)

                if parsed:
                    validated = schema.model_validate(parsed)
                    return {
                        "status": "ok",
                        "data": validated.model_dump(exclude_none=True),
                        "model": response.get("model", "maverick"),
                    }
            except ValidationError as ve:
                logger.warning("Medical formatter validation failed: %s", ve)
            except Exception as exc:
                logger.warning("Medical formatter LLM failed: %s", exc)

        # Fallback: basic extraction
        return self._fallback(notes, schema)

    def _fallback(self, notes: str, schema: Type[BaseModel]) -> Dict[str, Any]:
        """Fallback: basic structure from available data."""
        if schema == PrescriptionOutput:
            return {
                "status": "fallback",
                "data": PrescriptionOutput(
                    diagnosis=notes[:120],
                    medications=[],
                    doctor_notes=notes,
                ).model_dump(exclude_none=True),
                "model": "fallback",
            }
        elif schema == CertificateOutput:
            return {
                "status": "fallback",
                "data": CertificateOutput(
                    body=notes[:500],
                    cert_type="other",
                ).model_dump(exclude_none=True),
                "model": "fallback",
            }
        else:
            return {
                "status": "fallback",
                "data": schema().model_dump(exclude_none=True),
                "model": "fallback",
            }
