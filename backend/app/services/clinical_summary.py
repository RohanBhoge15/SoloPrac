"""Clinical Summary Generator — Maverick-powered wound/skin assessment from comparison.

Generates a structured clinical summary from image comparison metrics using
Maverick (Llama-4 via NIM). Follows the structured output pattern with
Pydantic validation.

Usage:
    from app.services.clinical_summary import ClinicalSummaryGenerator
    result = await ClinicalSummaryGenerator.generate_summary(metrics={...})
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.agents.synthesizer import MaverickSynthesizer

logger = logging.getLogger(__name__)

# ─── Structured Output Schema ───

class ClinicalSummary(BaseModel):
    """Structured clinical summary for wound/skin comparison."""
    area_change_pct: Optional[float] = None
    edge_convergence_score: Optional[float] = None
    color_histogram_shift: Optional[float] = None
    assessment: str = ""
    healing_stage: str = ""
    clinical_interpretation: str = ""
    recommendations: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    summary: str
    confidence: float
    structured: Optional[ClinicalSummary] = None
    model: str


# ─── Clinical Summary Generator ───

class ClinicalSummaryGenerator:
    """Generates clinical summaries from image comparison metrics using Maverick."""

    def __init__(self):
        self._synthesizer = MaverickSynthesizer()
        self._system_prompt = self._build_system_prompt()

    @staticmethod
    def _build_system_prompt() -> str:
        return """You are a clinical documentation specialist generating wound/skin assessment summaries for medical records.

Input: Quantitative metrics from an ORB-based image comparison between two wound/skin photographs taken at different time points.

Metrics you receive:
- area_change_pct: Percentage of tissue area change (positive = increase, negative = decrease)
- edge_convergence_score: Edge alignment score 0-1 (higher = better edge approximation)
- color_histogram_shift: Bhattacharyya distance 0-1 (lower = more similar colors, 0 = identical)
- Additional context: num_matches, homography_confidence

Your task:
1. Provide a concise clinical summary (2-3 sentences) describing the wound progression
2. Include a structured JSON output with:
   - assessment: "improving" | "stable" | "worsening" | "inconclusive"
   - healing_stage: "proliferative" | "maturation" | "inflammatory" | "unknown"
   - clinical_interpretation: One sentence medical interpretation
   - recommendations: List of clinical next steps
   - concerns: List of red flags if any

Guidelines:
- Negative area_change_pct + high edge_convergence + low color_shift → "improving"
- Positive area_change_pct + low edge_convergence + high color_shift → "worsening"
- Near-zero changes + moderate edge convergence → "stable"
- Always use "wound area reduced by X%" format (not "decreased by -X%")
- Be concise, clinical, and cautious — this is AI-assisted, doctor-validated
- End summary with: "Verified by AI · Doctor review recommended."

Output format: JSON only, no markdown, no extra text.
"""

    async def generate(
        self,
        metrics: Dict[str, Any],
        patient_name: str = "the patient",
    ) -> Dict[str, Any]:
        """Generate a clinical summary from comparison metrics."""
        if not self._synthesizer.is_available:
            logger.warning("Maverick not available, using fallback summary")
            return self._fallback_summary(metrics, patient_name)

        # Build user prompt with metrics
        user_prompt = self._build_user_prompt(metrics, patient_name)

        try:
            response = await self._synthesizer.synthesize(
                query=user_prompt,
                context={},
                structured_output={"type": "json_object"},
            )

            raw_output = response.get("response", "")
            parsed = self._parse_response(raw_output)

            # Validate with Pydantic
            try:
                structured = ClinicalSummary.model_validate(parsed.get("structured", {}))
                structured_dict = structured.model_dump(exclude_none=True)
            except Exception:
                structured_dict = {}

            return {
                "summary": parsed.get("summary", "").strip(),
                "confidence": parsed.get("confidence", 0.7),
                "structured": structured_dict,
                "model": response.get("model", settings.MAVERICK_MODEL),
            }

        except Exception as exc:
            logger.error("Clinical summary LLM call failed: %s", exc)
            return self._fallback_summary(metrics, patient_name)

    def _build_user_prompt(self, metrics: Dict[str, Any], patient_name: str) -> str:
        """Build the user prompt with metrics."""
        area_change = metrics.get("area_change_pct", 0)
        edge_score = metrics.get("edge_convergence_score", 0)
        color_shift = metrics.get("color_histogram_shift", 0)
        num_matches = metrics.get("num_matches", 0)
        homography_conf = metrics.get("homography_confidence", 0)

        # Determine direction
        if area_change < -5:
            area_desc = f"wound area reduced by {abs(area_change):.1f}%"
        elif area_change > 5:
            area_desc = f"wound area increased by {area_change:.1f}%"
        else:
            area_desc = f"wound area stable (change: {area_change:.1f}%)"

        if edge_score > 0.7:
            edge_desc = "edges well approximated"
        elif edge_score > 0.4:
            edge_desc = "edges partially approximated"
        else:
            edge_desc = "edges poorly approximated"

        return f"""Patient: {patient_name}

Comparison Metrics:
- Area change: {area_desc}
- Edge convergence score: {edge_score:.3f} ({edge_desc})
- Color histogram shift: {color_shift:.3f}
- ORB feature matches: {num_matches}
- Homography confidence: {homography_conf:.3f}

Generate the clinical summary JSON as specified."""

    def _parse_response(self, raw_output: str) -> Dict[str, Any]:
        """Parse LLM response, handling code fences and JSON parsing."""
        # Strip markdown fences
        raw_output = raw_output.strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]
        raw_output = raw_output.strip()

        try:
            return json.loads(raw_output)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse clinical summary JSON: %s", exc)
            return {}

    def _fallback_summary(self, metrics: Dict[str, Any], patient_name: str) -> Dict[str, Any]:
        """Generate a basic fallback summary when Maverick is unavailable."""
        area_change = metrics.get("area_change_pct", 0)
        edge_score = metrics.get("edge_convergence_score", 0)

        if area_change < -5:
            assessment = "improving"
            healing_stage = "proliferative"
        elif area_change > 5:
            assessment = "worsening"
            healing_stage = "inflammatory"
        else:
            assessment = "stable"
            healing_stage = "maturation"

        summary = (
            f"Wound comparison for {patient_name}: {area_change:.1f}% area change. "
            f"Edge convergence score {metrics.get('edge_convergence_score', 0):.2f}. "
            f"Assessment: {assessment}. "
            "Verified by AI · Doctor review recommended."
        )

        return {
            "summary": summary,
            "confidence": 0.5,
            "structured": {
                "assessment": assessment,
                "healing_stage": healing_stage,
                "clinical_interpretation": f"Area change: {metrics.get('area_change_pct', 0):.1f}%",
                "recommendations": ["Continue current treatment plan", "Reassess in 1-2 weeks"],
                "concerns": [],
            },
            "model": "fallback",
        }


# ─── Convenience Function ───

async def generate_summary(
    metrics: Dict[str, Any],
    patient_name: str = "the patient",
) -> Dict[str, Any]:
    """Convenience function to generate a clinical summary."""
    generator = ClinicalSummaryGenerator()
    return await generator.generate(metrics, patient_name)