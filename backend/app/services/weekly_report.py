"""Feature F — Significance-Aware Weekly Reports.

Scoring formula: significance = clinical_significance × information_gain ×
novelty × trend_strength × recency_decay

3 layout templates: Executive (compact), Clinical (all metrics),
Family-friendly (plain language).

Usage:
    from app.services.weekly_report import WeeklyReportService
    service = WeeklyReportService()
    report = await service.generate_report(doctor_id, patient_id)
"""

from __future__ import annotations

import json
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient, PatientVersion
from app.agents.synthesizer import MaverickSynthesizer

logger = logging.getLogger(__name__)

# ─── Significance Scorer Constants ─────────────────────────

# Default tau (half-life in days) per tag type (from temporal_rag.py)
TAU: Dict[str, int] = {
    "vitals": 7,
    "lab": 14,
    "diagnosis": 90,
    "demographics": 365,
}

# Clinical significance tier weights
TIER_WEIGHTS: Dict[str, float] = {
    "new_diagnosis": 1.0,
    "medication_change": 0.9,
    "abnormal_lab": 0.8,
    "critical_vitals": 0.8,
    "deterioration": 0.9,
    "improvement": 0.6,
    "routine_visit": 0.3,
    "missed_appointment": 0.5,
    "referral": 0.7,
    "follow_up": 0.4,
}

# Default weights if tag is unknown
TIER_WEIGHTS_DEFAULT = 0.5

REPORT_LAYOUTS = ["executive", "clinical", "family_friendly"]


def clinical_significance_from_tags(tags: List[str]) -> float:
    """Map tags to clinical significance weight (max across tags)."""
    if not tags:
        return TIER_WEIGHTS_DEFAULT
    weights = [TIER_WEIGHTS.get(t, TIER_WEIGHTS_DEFAULT) for t in tags]
    return max(weights)


def temporal_decay_weight(
    event_time: datetime,
    query_time: Optional[datetime] = None,
    tau_days: int = 7,
) -> float:
    """Exponential decay: weight = e^(-dt/tau).

    Events older than tau days get weight < 0.37.
    """
    if query_time is None:
        query_time = datetime.now(timezone.utc)
    delta_days = (query_time - event_time).total_seconds() / 86400.0
    if delta_days <= 0:
        return 1.0
    return math.exp(-delta_days / tau_days)


# ─── 5-Component Significance Scorer ──────────────────────

def compute_significance(
    clinical_significance: float,
    information_gain: float,
    novelty: float,
    trend_strength: float,
    recency: float,
) -> float:
    """5-component significance score.

    Args:
        clinical_significance: Weight from tag tier (0-1)
        information_gain: How much new info this version adds (0-1)
        novelty: How different from previous versions (0-1)
        trend_strength: How strong a trend this indicates (0-1)
        recency: Temporal recency weight (0-1)

    Returns:
        Composite significance score (0-1)
    """
    return clinical_significance * information_gain * novelty * trend_strength * recency


class WeeklyReportService:
    """Generates significance-scored weekly reports."""

    def __init__(self):
        self.synthesizer = MaverickSynthesizer()

    async def get_recent_versions(
        self,
        db: AsyncSession,
        patient_id: UUID,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Get patient versions from the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await db.execute(
            select(PatientVersion)
            .where(
                PatientVersion.patient_id == patient_id,
                PatientVersion.created_at >= cutoff,
            )
            .order_by(PatientVersion.created_at.desc())
        )
        versions = result.scalars().all()
        return [
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "created_at": v.created_at,
                "state_jsonb": v.state_jsonb,
                "summary": v.summary,
                "tags": v.tags,
                "edit_type": v.edit_type,
                "clinical_significance": v.clinical_significance,
            }
            for v in versions
        ]

    def score_versions(
        self,
        versions: List[Dict],
    ) -> List[Dict[str, Any]]:
        """Score each version with the 5-component significance formula."""
        scored = []
        for i, v in enumerate(versions):
            # Clinical significance from tags
            tags = v.get("tags", [])
            cs = clinical_significance_from_tags(tags)

            # Recency decay
            created = v.get("created_at")
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            recency = temporal_decay_weight(created, tau_days=7)

            # Information gain: how much new info vs previous
            info_gain = 1.0
            if i > 0 and versions[i - 1].get("state_jsonb"):
                prev_state = versions[i - 1].get("state_jsonb", {})
                curr_state = v.get("state_jsonb", {})
                # Simple proxy: different summary = new info
                if v.get("summary") != versions[i - 1].get("summary"):
                    info_gain = 0.8
                else:
                    info_gain = 0.3

            # Novelty: how different from all previous
            novelty = 1.0
            if i >= 2 and tags:
                # Repetition reduces novelty
                prev_tags = [x.get("tags", []) for x in versions[:i]]
                all_prev_tags = [t for sub in prev_tags for t in sub] if prev_tags else []
                repeated = sum(1 for tag in tags if tag in all_prev_tags)
                total_prev = len(all_prev_tags) if all_prev_tags else 1
                repetition_ratio = repeated / max(total_prev, 1)
                novelty = 1.0 - (repetition_ratio * 0.5)  # scale to 0.5-1.0

            # Trend strength: consecutive similar findings
            trend_strength = 0.5
            if i >= 2:
                # Check if same diagnosis appears across recent versions
                for j in range(1, min(3, i + 1)):
                    prev = versions[i - j]
                    prev_tags = prev.get("tags", [])
                    overlap = set(tags) & set(prev_tags)
                    if overlap:
                        trend_strength = min(1.0, trend_strength + 0.2 * j)

            # Composite score
            score = compute_significance(cs, info_gain, novelty, trend_strength, recency)

            scored.append({
                **v,
                "score_components": {
                    "clinical_significance": round(cs, 3),
                    "information_gain": round(info_gain, 3),
                    "novelty": round(novelty, 3),
                    "trend_strength": round(trend_strength, 3),
                    "recency": round(recency, 3),
                },
                "significance_score": round(score, 3),
                "tier": self._score_tier(score),
            })

        # Sort by significance (highest first)
        scored.sort(key=lambda x: -x["significance_score"])
        return scored

    def _score_tier(self, score: float) -> str:
        if score >= 0.7:
            return "critical"
        elif score >= 0.4:
            return "notable"
        elif score >= 0.2:
            return "routine"
        return "informational"

    # ─── Layout Templates ─────────────────────────────────

    def build_executive_layout(self, patient_name: str, scored_versions: List[Dict]) -> Dict[str, Any]:
        """Executive layout — compact, key findings only."""
        significant = [v for v in scored_versions if v["tier"] in ("critical", "notable")]

        sections = []
        for v in significant[:7]:
            sections.append({
                "date": self._fmt_date(v.get("created_at")),
                "summary": v.get("summary", ""),
                "tier": v["tier"],
                "score": v["significance_score"],
                "components": v["score_components"],
                "tags": v.get("tags", []),
            })

        return {
            "layout": "executive",
            "patient_name": patient_name,
            "title": f"Weekly Clinical Executive Summary — {patient_name}",
            "description": "Key findings requiring attention",
            "total_events": len(scored_versions),
            "significant_events": len(significant),
            "sections": sections,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def build_clinical_layout(self, patient_name: str, scored_versions: List[Dict]) -> Dict[str, Any]:
        """Clinical layout — all metrics, full detail."""
        sections = []
        for v in scored_versions:
            sections.append({
                "date": self._fmt_date(v.get("created_at")),
                "version": v.get("version_number"),
                "summary": v.get("summary", ""),
                "tier": v["tier"],
                "score": v["significance_score"],
                "components": v["score_components"],
                "tags": v.get("tags", []),
                "edit_type": v.get("edit_type", "manual"),
                "state_preview": self._state_preview(v.get("state_jsonb", {})),
            })

        # Group by tier
        critical = [s for s in sections if s["tier"] == "critical"]
        notable = [s for s in sections if s["tier"] == "notable"]
        routine = [s for s in sections if s["tier"] in ("routine", "informational")]

        return {
            "layout": "clinical",
            "patient_name": patient_name,
            "title": f"Weekly Clinical Report — {patient_name}",
            "description": "Complete clinical data for the week with significance scoring",
            "critical_count": len(critical),
            "notable_count": len(notable),
            "routine_count": len(routine),
            "critical": critical,
            "notable": notable,
            "routine": routine,
            "total_events": len(scored_versions),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def build_family_layout(self, patient_name: str, scored_versions: List[Dict]) -> Dict[str, Any]:
        """Family-friendly layout — plain language, no jargon."""
        sections = []
        for v in scored_versions[:10]:
            summary = v.get("summary", "")
            tags = v.get("tags", [])
            plain_summary = self._to_plain_language(summary, tags)

            sections.append({
                "date": self._fmt_date(v.get("created_at")),
                "summary": plain_summary,
                "tier": v["tier"],
            })

        return {
            "layout": "family_friendly",
            "patient_name": patient_name,
            "title": f"Your Health Report — {patient_name}",
            "description": "A simple overview of recent health events",
            "introduction": f"Dear {patient_name.split()[-1]}, here's a summary of your recent health information.",
            "sections": sections,
            "total_events": len(scored_versions),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─── Helpers ──────────────────────────────────────────

    def _fmt_date(self, dt) -> str:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        return dt.strftime("%b %d") if dt else ""

    def _state_preview(self, state: dict) -> dict:
        clinical = state.get("clinical", {}) if isinstance(state, dict) else {}
        vitals = clinical.get("vitals", {}) if isinstance(clinical, dict) else {}
        diagnoses = clinical.get("diagnoses", []) if isinstance(clinical, dict) else []
        return {
            "vitals": vitals,
            "diagnoses": diagnoses[:3],
        }

    def _to_plain_language(self, summary: str, tags: List[str]) -> str:
        """Convert clinical summary to patient-friendly language."""
        if not summary:
            return "A routine visit with no significant changes."

        replacements = {
            "follow-up": "check-up",
            "diagnosis": "finding",
            "medication": "medicine",
            "abnormal": "unusual",
            "hypertension": "high blood pressure",
            "hypothyroidism": "low thyroid",
        }

        result = summary
        for clinical, plain in replacements.items():
            result = result.replace(clinical, plain)

        if tags:
            if "new_diagnosis" in tags:
                result += " A new health finding was recorded."
            if "medication_change" in tags:
                result += " Your medicines were updated."

        return result

    # ─── Generator ────────────────────────────────────────

    async def generate_report(
        self,
        db: AsyncSession,
        patient_id: UUID,
        layout: str = "clinical",
        days: int = 7,
    ) -> Dict[str, Any]:
        """Generate a complete weekly report.

        Args:
            db: Database session.
            patient_id: Patient UUID.
            layout: One of "executive", "clinical", "family_friendly".
            days: Lookback window.

        Returns:
            Report dict matching the requested layout.
        """
        # Get patient info
        result = await db.execute(select(Patient).where(Patient.id == patient_id))
        patient = result.scalar_one_or_none()
        if not patient:
            return {"error": "Patient not found"}

        # Get patient name from head version or fallback
        patient_name = f"Patient {str(patient_id)[:8]}"
        if patient.head_version_id:
            vr = await db.execute(
                select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
            )
            head = vr.scalar_one_or_none()
            if head and head.state_jsonb:
                demo = head.state_jsonb.get("demographics", {})
                if isinstance(demo, dict) and demo.get("name"):
                    patient_name = demo["name"]

        # Get and score recent versions
        versions = await self.get_recent_versions(db, patient_id, days)
        if not versions:
            return {
                "layout": layout,
                "patient_name": patient_name,
                "title": f"Weekly Report — {patient_name}",
                "description": "No clinical events this week",
                "total_events": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        scored = self.score_versions(versions)

        # Build requested layout
        if layout == "executive":
            return self.build_executive_layout(patient_name, scored)
        elif layout == "family_friendly":
            return self.build_family_layout(patient_name, scored)
        else:
            return self.build_clinical_layout(patient_name, scored)

    async def generate_ai_summary(
        self,
        report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate AI narrative summary of a weekly report using Maverick."""
        if not report.get("sections") and not report.get("critical"):
            return {"summary": "No significant events to summarize."}

        try:
            response = await self.synthesizer.synthesize(
                query=f"Generate a brief clinical narrative summary for this weekly report: {json.dumps(report, indent=2)[:3000]}",
                context={"mode": "weekly_summary"},
                structured_output={"type": "json_object"},
            )
            raw = response.get("response", "")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {}
            summary = parsed.get("summary", raw[:500])
        except Exception:
            summary = "Weekly report generated. Review the significant events for clinical action."

        return {"summary": summary}


# ─── Likert Evaluation Design ──────────────────────────────

LIKERT_SURVEY_TEMPLATE = {
    "title": "Weekly Report Quality Assessment — Doctor Likert Rating",
    "instructions": (
        "Please rate each report on a 1-5 scale (1=Strongly Disagree, 5=Strongly Agree). "
        "This helps us evaluate the clinical usefulness of AI-generated weekly reports."
    ),
    "dimensions": [
        {
            "id": "completeness",
            "label": "Completeness",
            "question": "All clinically relevant events from this week are captured",
        },
        {
            "id": "accuracy",
            "label": "Accuracy",
            "question": "The clinical data presented is accurate and error-free",
        },
        {
            "id": "relevance",
            "label": "Relevance / Usefulness",
            "question": "The report highlights what I actually need to know",
        },
        {
            "id": "layout",
            "label": "Layout Preference",
            "question": "The report layout makes information easy to find",
        },
        {
            "id": "significance",
            "label": "Significance Scoring",
            "question": "The significance scores (critical/notable/routine) match my clinical judgment",
        },
        {
            "id": "time_saved",
            "label": "Time Saved",
            "question": "This report saves me time compared to reviewing records manually",
        },
    ],
    "scoring": "1=Strongly Disagree, 2=Disagree, 3=Neutral, 4=Agree, 5=Strongly Agree",
}


def build_likert_study(
    doctors: int = 5,
    reports_per_doctor: int = 3,
) -> Dict[str, Any]:
    """Build a Likert rating study design.

    Args:
        doctors: Number of participating doctors.
        reports_per_doctor: Reports each doctor rates.

    Returns:
        Study design dict for paper appendix.
    """
    return {
        "study_name": "Feature F — Weekly Report Significance Evaluation",
        "design": "Within-subjects (each doctor rates all 3 layouts for each report)",
        "participants": doctors,
        "reports_per_participant": reports_per_doctor,
        "layouts": REPORT_LAYOUTS,
        "ratings_per_participant": reports_per_doctor * len(REPORT_LAYOUTS) * len(LIKERT_SURVEY_TEMPLATE["dimensions"]),
        "survey": LIKERT_SURVEY_TEMPLATE,
        "analysis": {
            "primary": "Mean Likert score per layout across all dimensions",
            "secondary": "Preference distribution (which layout is ranked highest per doctor)",
            "significance_test": "Friedman test (non-parametric repeated measures, 3 layouts × 5 raters)",
        },
        "expected_outcomes": (
            "Clinical layout expected to score highest on completeness and accuracy; "
            "executive on time_saved; family_friendly on layout preference. "
            "Overall significance scoring expected >= 4.0."
        ),
    }
