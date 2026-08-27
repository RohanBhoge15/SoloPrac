"""Clinical significance — single source of truth.

Consolidates the previously duplicated `clinical_significance_from_tags`
implementations (which had drifted apart: one returned 0.0 for unknown tags,
the other returned a 0.5 default) and the two divergent TIER_WEIGHTS tables.

Per the paper (Section IV, Feature A): s(v_i) is the maximum tier weight of
the version's tags. This module is the one place that maps tags → weight;
both the temporal RAG scorer and the weekly-report scorer import it.
"""

from __future__ import annotations

from typing import List, Optional

# ─── Clinical Significance Tier Weights (single table) ─────────────────
# Union of the paper-style tags and the tags the app actually writes at
# version-mint time (image, document, prescription, demographics, ...).
TIER_WEIGHTS: dict[str, float] = {
    # Paper-style semantic tiers
    "new_diagnosis": 1.0,
    "medication_change": 0.9,
    "abnormal_lab": 0.8,
    "critical_vitals": 0.8,
    "deterioration": 0.9,
    "improvement": 0.6,
    "ai_risk_alert": 0.75,
    "missed_appointment": 0.5,
    "referral": 0.7,
    "follow_up": 0.4,
    "routine_visit": 0.3,
    "vitals_in_range": 0.05,
    # App-written tags (what routers/background jobs actually mint)
    "demographics": 0.1,
    "image": 0.3,
    "image_comparison": 0.5,
    "document": 0.3,
    "uploaded": 0.3,
    "prescription": 0.5,
    "revert": 0.5,
    # Generic modality tags that can appear on manual edits
    "vitals": 0.4,
    "lab": 0.6,
    "labs": 0.6,
    "diagnosis": 0.8,
    "medication": 0.6,
    "symptoms": 0.5,
}

# Weight applied when NO tag in the version's tag list matches a known tier.
# Chosen as a mild default so unknown-tag versions still rank above noise but
# well below clearly significant events.
DEFAULT_WEIGHT = 0.3


def clinical_significance_from_tags(tags: Optional[List[str]]) -> float:
    """Compute clinical significance from version tags (max across tags).

    Returns `DEFAULT_WEIGHT` when no tag matches a known tier.
    """
    if not tags:
        return DEFAULT_WEIGHT
    best = 0.0
    for tag in tags:
        if not tag:
            continue
        weight = TIER_WEIGHTS.get(str(tag).strip().lower(), DEFAULT_WEIGHT)
        if weight > best:
            best = weight
    return best
