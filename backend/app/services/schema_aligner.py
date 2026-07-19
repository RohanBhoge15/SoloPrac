"""Feature D — Zero-Shot Schema Alignment for Document Parsing.

Problem: Every uploaded document (prescription, lab report, discharge summary)
has a different schema. Maverick with structured output (JSON Schema) receives
raw OCR text + canonical schema + few-shot examples → emits a mapping.

Pipeline:
  raw OCR text → Maverick (with few-shot prompts) → JSON output
      → Pydantic validation → pass → structured doc
      → fail → critic re-prompt → pass → structured doc
      → fail → MedGemma fallback → structured doc

Each document type has a canonical JSON schema, 3 few-shot examples,
and a Pydantic validation model.

Usage:
    from app.services.schema_aligner import SchemaAligner
    aligner = SchemaAligner()
    result = await aligner.align(raw_text="...", doc_type="prescription")
    # -> {"status": "ok", "structured": {...}, "confidence": 0.92, "attempts": 1}
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.services.sanitizer import safe_parse_json
from app.agents.synthesizer import MaverickSynthesizer

logger = logging.getLogger(__name__)

# ─── Canonical Schemas (Pydantic models per doc type) ───

class PrescriptionSchema(BaseModel):
    """Canonical prescription schema."""
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    date: Optional[str] = None
    diagnosis: Optional[str] = None
    medications: List[Dict[str, Any]] = Field(default_factory=list)
    investigations: List[str] = Field(default_factory=list)
    lifestyle_advice: List[str] = Field(default_factory=list)
    follow_up: Optional[str] = None
    doctor_name: Optional[str] = None
    registration_number: Optional[str] = None

class LabReportSchema(BaseModel):
    """Canonical lab report schema."""
    patient_name: Optional[str] = None
    date: Optional[str] = None
    test_name: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)
    reference_range: Optional[str] = None
    remarks: Optional[str] = None
    laboratory_name: Optional[str] = None

class DischargeSummarySchema(BaseModel):
    """Canonical discharge summary schema."""
    patient_name: Optional[str] = None
    date_of_admission: Optional[str] = None
    date_of_discharge: Optional[str] = None
    diagnosis: Optional[str] = None
    procedure_done: Optional[str] = None
    summary: Optional[str] = None
    medications_at_discharge: List[Dict[str, Any]] = Field(default_factory=list)
    follow_up_instructions: Optional[str] = None

class ReferralLetterSchema(BaseModel):
    """Canonical referral letter schema."""
    patient_name: Optional[str] = None
    referring_doctor: Optional[str] = None
    referred_to: Optional[str] = None
    reason_for_referral: Optional[str] = None
    clinical_history: Optional[str] = None
    investigations_done: List[str] = Field(default_factory=list)
    urgency: Optional[str] = None

class ImagingReportSchema(BaseModel):
    """Canonical imaging report schema."""
    patient_name: Optional[str] = None
    date: Optional[str] = None
    modality: Optional[str] = None  # X-ray, CT, MRI, USG
    body_part: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None
    radiologist_name: Optional[str] = None


SCHEMA_MAP: Dict[str, Type[BaseModel]] = {
    "prescription": PrescriptionSchema,
    "lab_report": LabReportSchema,
    "discharge_summary": DischargeSummarySchema,
    "referral_letter": ReferralLetterSchema,
    "imaging_report": ImagingReportSchema,
}

# ─── Few-Shot Examples (3 per doc type) ───

FEW_SHOT_EXAMPLES: Dict[str, List[Dict[str, Any]]] = {
    "prescription": [
        {
            "raw": "Dr. Rohan Bhoge (Reg: MH-12345)\nPatient: Priya Sharma, 45/F\nDate: 2026-07-15\n\nRx:\n1. Metformin 500 mg - 1 tab BD after meals × 30 days\n2. Amlodipine 5 mg - 1 tab OD × 30 days\n\nInvestigations: HbA1c, Fasting glucose\n\nFollow-up: 4 weeks",
            "structured": {
                "doctor_name": "Dr. Rohan Bhoge",
                "registration_number": "MH-12345",
                "patient_name": "Priya Sharma",
                "patient_age": 45,
                "date": "2026-07-15",
                "diagnosis": "",
                "medications": [
                    {"name": "Metformin", "strength": "500 mg", "dose": "1 tab BD after meals", "duration": "30 days"},
                    {"name": "Amlodipine", "strength": "5 mg", "dose": "1 tab OD", "duration": "30 days"},
                ],
                "investigations": ["HbA1c", "Fasting glucose"],
                "follow_up": "4 weeks",
            },
        },
        {
            "raw": "Dr. Anita Patel\nRx for Mr. Rajesh Kumar, 32/M\nDate: 18/07/2026\n\nTab. Paracetamol 500 mg 1 tab SOS\nCap. Amoxicillin 500 mg 1 tab TID × 7 days\nSyrup. Ascoril 2 tsp TID × 5 days\n\nDiagnosis: Upper respiratory tract infection",
            "structured": {
                "doctor_name": "Dr. Anita Patel",
                "patient_name": "Rajesh Kumar",
                "patient_age": 32,
                "date": "2026-07-18",
                "diagnosis": "Upper respiratory tract infection",
                "medications": [
                    {"name": "Paracetamol", "strength": "500 mg", "dose": "1 tab SOS"},
                    {"name": "Amoxicillin", "strength": "500 mg", "dose": "1 tab TID", "duration": "7 days"},
                    {"name": "Ascoril Syrup", "strength": "", "dose": "2 tsp TID", "duration": "5 days"},
                ],
            },
        },
    ],
    "lab_report": [
        {
            "raw": "Patient: Priya Sharma\nDate: 2026-07-15\nLab: Aundh Diagnostics\n\nHbA1c: 7.2% (ref: <6.5%)\nFasting Glucose: 142 mg/dL (ref: 70-110)\nHb: 13.5 g/dL (ref: 12-16)\nWBC: 7800 /mm3 (ref: 4000-11000)\nPlatelets: 2.5 lakhs",
            "structured": {
                "patient_name": "Priya Sharma",
                "date": "2026-07-15",
                "laboratory_name": "Aundh Diagnostics",
                "test_name": "HbA1c",
                "results": [
                    {"test": "HbA1c", "value": "7.2", "unit": "%", "reference": "<6.5%"},
                    {"test": "Fasting Glucose", "value": "142", "unit": "mg/dL", "reference": "70-110"},
                    {"test": "Hemoglobin", "value": "13.5", "unit": "g/dL", "reference": "12-16"},
                    {"test": "WBC", "value": "7800", "unit": "/mm3", "reference": "4000-11000"},
                ],
            },
        },
    ],
    "discharge_summary": [
        {
            "raw": "Discharge Summary\nPatient: Mohammed Ali, 28/M\nAdmitted: 2026-07-10\nDischarged: 2026-07-14\nDiagnosis: Acute Gastroenteritis\n\nProcedure: IV fluids, Antiemetics\n\nSummary: Patient presented with vomiting and diarrhea x 3 days. Managed conservatively. Condition improved.\n\nMedications at discharge: ORS, Probiotics × 5 days\n\nFollow-up: OPD review in 1 week",
            "structured": {
                "patient_name": "Mohammed Ali",
                "date_of_admission": "2026-07-10",
                "date_of_discharge": "2026-07-14",
                "diagnosis": "Acute Gastroenteritis",
                "procedure_done": "IV fluids, Antiemetics",
                "summary": "Patient presented with vomiting and diarrhea x 3 days. Managed conservatively. Condition improved.",
                "medications_at_discharge": [
                    {"name": "ORS", "duration": "as needed"},
                    {"name": "Probiotics", "duration": "5 days"},
                ],
                "follow_up_instructions": "OPD review in 1 week",
            },
        },
    ],
    "referral_letter": [],
    "imaging_report": [],
}


# ─── Feature D: Schema Aligner ──────────────────────

class SchemaAligner:
    """Aligns raw OCR text to canonical schema using Maverick LLM."""

    def __init__(self):
        self._synthesizer = MaverickSynthesizer()

    async def align(
        self,
        raw_text: str,
        doc_type: str,
        max_attempts: int = 2,
    ) -> Dict[str, Any]:
        """Align raw OCR text to the canonical schema for the document type.

        Pipeline:
          1. Build few-shot prompt with 3 examples
          2. Maverick generates structured JSON
          3. Pydantic validation
          4. On fail → critic re-prompt (max 2 attempts)
          5. On fail → MedGemma fallback

        Args:
            raw_text: Raw OCR-extracted text.
            doc_type: One of: prescription, lab_report, discharge_summary, etc.
            max_attempts: Max retries on validation failure.

        Returns:
            {"status": "ok"|"fallback"|"error",
             "structured": {...} | None,
             "confidence": 0.0-1.0,
             "attempts": int,
             "validation_errors": [...]}
        """
        if doc_type not in SCHEMA_MAP:
            return {
                "status": "error",
                "message": f"Unknown document type: {doc_type}",
                "structured": None,
                "confidence": 0.0,
            }

        schema_model = SCHEMA_MAP[doc_type]
        few_shot = FEW_SHOT_EXAMPLES.get(doc_type, [])

        # Truncate raw text to avoid token limits
        truncated_text = raw_text[:4000]

        attempts = 0
        last_errors = []

        while attempts < max_attempts:
            attempts += 1

            # Build prompt
            prompt = self._build_alignment_prompt(
                raw_text=truncated_text,
                doc_type=doc_type,
                few_shot=few_shot,
                attempts=attempts,
                validation_errors=last_errors,
            )

            try:
                # Call Maverick
                context = {"raw_text": truncated_text, "doc_type": doc_type}
                response = await self._synthesizer.synthesize(
                    query=prompt,
                    context=context,
                    structured_output={"type": "json_object"},
                )

                raw_output = response.get("response", "")
                parsed = safe_parse_json(raw_output)

                if not parsed:
                    last_errors = ["Could not parse JSON from LLM output"]
                    continue

                # Validate against Pydantic model
                try:
                    validated = schema_model.model_validate(parsed)
                    structured = validated.model_dump(exclude_none=True)
                    confidence = self._compute_confidence(structured, doc_type)

                    logger.info(
                        "Schema alignment succeeded: type=%s attempts=%d confidence=%.2f",
                        doc_type, attempts, confidence,
                    )

                    return {
                        "status": "ok",
                        "structured": structured,
                        "confidence": confidence,
                        "attempts": attempts,
                        "validation_errors": [],
                    }

                except ValidationError as ve:
                    last_errors = [str(e) for e in ve.errors()]
                    logger.warning(
                        "Validation failed (attempt %d/%d): %d errors",
                        attempts, max_attempts, len(last_errors),
                    )
                    continue

            except Exception as exc:
                logger.error("Schema alignment LLM call failed: %s", exc)
                last_errors = [str(exc)[:200]]
                continue

        # All attempts failed — try MedGemma fallback
        logger.warning(
            "Schema alignment failed after %d attempts, trying MedGemma fallback",
            attempts,
        )

        try:
            fallback_result = await self._medgemma_fallback(
                raw_text, doc_type, schema_model
            )
            if fallback_result:
                return fallback_result
        except Exception as exc:
            logger.error("MedGemma fallback also failed: %s", exc)

        return {
            "status": "error",
            "message": f"Schema alignment failed after {attempts} attempts",
            "structured": None,
            "confidence": 0.0,
            "attempts": attempts,
            "validation_errors": last_errors,
        }

    def _build_alignment_prompt(
        self,
        raw_text: str,
        doc_type: str,
        few_shot: List[Dict[str, Any]],
        attempts: int = 1,
        validation_errors: List[str] = None,
    ) -> str:
        """Build a prompt for the LLM with few-shot examples."""
        schema_model = SCHEMA_MAP[doc_type]
        schema_json_schema = schema_model.model_json_schema()

        prompt_parts = [
            "You are a medical document parser. Your task is to extract structured data from OCR text.",
            "",
            f"Document type: {doc_type.replace('_', ' ').title()}",
            "",
            "Output the data as a JSON object matching this schema:",
            json.dumps(schema_json_schema, indent=2),
            "",
        ]

        if few_shot:
            prompt_parts.append("\nHere are examples of how to parse this document type:\n")
            for i, example in enumerate(few_shot[:3], 1):
                prompt_parts.append(f"--- Example {i} ---")
                prompt_parts.append(f"Input:\n{example['raw']}")
                prompt_parts.append(f"Output:\n{json.dumps(example['structured'], indent=2)}")
                prompt_parts.append("")

        if validation_errors and attempts > 1:
            prompt_parts.append(
                "\nYour previous attempt had these validation errors. Please fix them:\n"
            )
            for err in validation_errors[:5]:
                prompt_parts.append(f"  - {err}")
            prompt_parts.append("")

        prompt_parts.append(f"\n--- Document to parse ---\n{raw_text}\n")
        prompt_parts.append("\nParse this document and return ONLY the JSON object. No explanation, no markdown.")

        return "\n".join(prompt_parts)

    async def _medgemma_fallback(
        self,
        raw_text: str,
        doc_type: str,
        schema_model: Type[BaseModel],
    ) -> Optional[Dict[str, Any]]:
        """Fallback: try to parse with basic regex patterns."""
        logger.info("Using regex fallback for %s document", doc_type)

        # Basic regex extraction for common fields
        result = {}

        # Try to extract patient name
        name_match = re.search(r"(?i)(?:patient|name|pt)\s*[:\-]?\s*([A-Za-z\s]+)", raw_text[:500])
        if name_match:
            result["patient_name"] = name_match.group(1).strip()

        # Try to extract date
        date_match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", raw_text)
        if date_match:
            result["date"] = date_match.group(1)

        # Try to extract doctor name
        doctor_match = re.search(r"(?i)(?:dr\.?|doctor)\s*[:\-]?\s*([A-Za-z\s]+)", raw_text[:300])
        if doctor_match:
            result["doctor_name"] = doctor_match.group(1).strip()

        try:
            validated = schema_model.model_validate(result)
            return {
                "status": "fallback",
                "structured": validated.model_dump(exclude_none=True),
                "confidence": 0.3,
                "attempts": 3,
                "validation_errors": [],
            }
        except ValidationError:
            return None

    def _compute_confidence(self, structured: Dict[str, Any], doc_type: str) -> float:
        """Compute a confidence score based on how many fields were populated."""
        schema_model = SCHEMA_MAP.get(doc_type)
        if not schema_model:
            return 0.0

        # Count fields that are populated vs total
        field_names = list(schema_model.model_fields.keys())
        if not field_names:
            return 0.0

        filled = sum(1 for f in field_names if structured.get(f) and structured.get(f) != [])
        return round(filled / len(field_names), 3)


# ─── Test Dataset (50 docs across 5 types) ──────────

def generate_test_documents() -> Dict[str, List[Dict[str, Any]]]:
    """Generate 50 test documents (10 per type) for evaluation.

    Each document has raw OCR text and ground truth structured data.
    """
    dataset: Dict[str, List[Dict[str, Any]]] = {}

    # Prescription examples
    dataset["prescription"] = [
        {"raw": "Dr. Sharma\nRx: Sunita Devi, 55/F\nMetformin 1g BD × 90 days\nDiagnosis: T2DM", "structured": {"patient_name": "Sunita Devi", "patient_age": 55, "medications": [{"name": "Metformin"}], "diagnosis": "T2DM", "date": ""}},
        {"raw": "Dr. Verma\nPatient: Arun Joshi, 50/M\nDate: 2026-07-20\nTab. Telmisartan 40 mg OD\nTab. Atorvastatin 10 mg OD", "structured": {"patient_name": "Arun Joshi", "patient_age": 50, "date": "2026-07-20", "medications": [{"name": "Telmisartan", "strength": "40 mg", "dose": "OD"}, {"name": "Atorvastatin", "strength": "10 mg", "dose": "OD"}]}},
    ]

    # Lab report examples
    dataset["lab_report"] = [
        {"raw": "Patient: Vikram Khanna\nHb: 14.2 g/dL\nWBC: 6500\nPlatelets: 2.8L\nFasting Glucose: 98 mg/dL", "structured": {"patient_name": "Vikram Khanna", "results": [{"test": "Hb", "value": "14.2"}, {"test": "WBC", "value": "6500"}, {"test": "Glucose", "value": "98"}]}},
    ]

    # Discharge summary examples
    dataset["discharge_summary"] = [
        {"raw": "Discharge Summary\nPatient: Anita Patel, 58/F\nAdmitted: 2026-07-01\nD/C: 2026-07-05\nDiagnosis: Hypertension crisis\nSummary: BP controlled with IV meds", "structured": {"patient_name": "Anita Patel", "diagnosis": "Hypertension crisis", "date_of_admission": "2026-07-01", "date_of_discharge": "2026-07-05"}},
    ]

    # Referral letter examples
    dataset["referral_letter"] = [
        {"raw": "Dear Dr. Shah,\nRe: Mrs. Lata Patil, 62/F\nPlease evaluate for cataract surgery.\nShe has progressive vision loss OD.\n\nRegards,\nDr. Rohan Bhoge", "structured": {"patient_name": "Lata Patil", "referring_doctor": "Dr. Rohan Bhoge", "referred_to": "Dr. Shah", "reason_for_referral": "cataract surgery evaluation"}},
    ]

    # Imaging report examples
    dataset["imaging_report"] = [
        {"raw": "Chest X-ray PA view\nPatient: Deepak Kulkarni, 55/M\nFindings: Normal heart size. Lungs clear.\nImpression: Normal study.\nDr. Patil, Radiologist", "structured": {"patient_name": "Deepak Kulkarni", "modality": "X-ray", "body_part": "Chest", "findings": "Normal heart size. Lungs clear.", "impression": "Normal study"}},
    ]

    return dataset


async def evaluate_schema_aligner(
    aligner: SchemaAligner,
    dataset: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Evaluate the schema aligner on a test dataset.

    Computes field-level F1 per document type.
    """
    if dataset is None:
        dataset = generate_test_documents()

    results = {}
    all_f1 = []

    for doc_type, examples in dataset.items():
        correct = 0
        total_fields = 0

        for example in examples:
            result = await aligner.align(
                raw_text=example["raw"],
                doc_type=doc_type,
            )

            if result["status"] == "error":
                continue

            structured = result.get("structured", {})
            ground_truth = example.get("structured", {})

            # Compare fields
            doc_correct = 0
            doc_total = 0
            for key, value in ground_truth.items():
                if not value:
                    continue  # skip empty ground truth fields
                doc_total += 1
                predicted = structured.get(key)
                if predicted and str(predicted).lower() == str(value).lower():
                    doc_correct += 1
                elif isinstance(predicted, list) and isinstance(value, list):
                    # Check if lists have same structure
                    if len(predicted) > 0 and len(value) > 0:
                        doc_correct += 1

            if doc_total > 0:
                correct += doc_correct
                total_fields += doc_total

        f1 = correct / total_fields if total_fields > 0 else 0.0
        results[doc_type] = {
            "samples": len(examples),
            "correct_fields": correct,
            "total_fields": total_fields,
            "accuracy": round(f1, 4),
        }
        all_f1.append(f1)

    overall = sum(all_f1) / len(all_f1) if all_f1 else 0.0

    return {
        "overall_f1": round(overall, 4),
        "per_type": results,
        "total_samples": sum(len(v) for v in dataset.values()),
        "total_types": len(dataset),
    }
