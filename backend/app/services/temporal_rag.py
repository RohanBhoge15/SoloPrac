"""Feature A — Temporal Multimodal RAG ⭐ Primary Research Contribution.

Given query `q` at time `t_q`, patient `p`, doctor `d`, retrieve top-`k` versions:

    score(v_i, q, t_q) =
          α · cos(MedCPT(q), v_i.medical_text)
        + β · hybrid_score(BGE-M3(q), v_i.hybrid, v_i.sparse)
        + γ · cos(NVCLIP(q_img), v_i.image)          [if query has image]
        + δ · temporal_decay(t_q − v_i.timestamp)
        + ε · clinical_significance(v_i)
    subject to: v_i.timestamp ≤ t_q,  v_i.doctor_id == d

Temporal decay: exp(-Δt / τ), where τ is tuned per modality.

Usage:
    from app.services.temporal_rag import TemporalMultimodalRetriever
    retriever = TemporalMultimodalRetriever()
    results = await retriever.retrieve(
        query="BP trend",
        patient_id=...,
        doctor_id=...,
        query_time=datetime.now(timezone.utc),
        k=8,
    )
"""

from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    Range,
    ScoredPoint,
    SearchParams,
    SparseVector,
    SearchRequest,
)

from app.config import settings
from app.services.embeddings import embedding_service
from app.services.qdrant import qdrant_service, PATIENT_VERSION_COLLECTION
from app.services.rag_audit import RAGAuditService, validate_no_future_leak

logger = logging.getLogger(__name__)

# ─── Scoring Weights (tunable hyperparameters) ───

ALPHA = 0.30  # MedCPT text similarity weight
BETA = 0.25   # BGE-M3 hybrid (dense + sparse) weight
GAMMA = 0.20  # NV-CLIP image similarity weight
DELTA = 0.15  # Temporal decay weight
EPSILON = 0.10  # Clinical significance weight

# ─── Temporal Decay Constants (τ in days, per modality) ───
# Vitals decay fast (7 days), diagnoses slow (90 days), family history slowest (365 days)
TAU: Dict[str, float] = {
    "vitals": 7.0,
    "lab": 14.0,
    "medication": 30.0,
    "diagnosis": 90.0,
    "procedure": 60.0,
    "demographics": 365.0,
    "family_history": 365.0,
    "image": 180.0,
    "text": 30.0,       # default for general text
    "hybrid": 30.0,    # default for hybrid
    "default": 30.0,
}

# ─── Clinical Significance Tier Weights (Feature F, reused here) ───
TIER_WEIGHTS: Dict[str, float] = {
    "new_diagnosis": 1.0,
    "medication_change": 0.9,
    "abnormal_lab": 0.8,
    "ai_risk_alert": 0.75,
    "missed_appointment": 0.5,
    "routine_visit": 0.2,
    "vitals_in_range": 0.05,
}

# ─── Retrieval Constants ───
OVERSAMPLE_FACTOR = 4  # over-fetch per modality before fusion


def temporal_decay(days_elapsed: float, modality: str = "default") -> float:
    """Compute temporal decay factor: exp(-Δt / τ).

    Args:
        days_elapsed: Days between query time and version timestamp (must be ≥ 0).
        modality: Modality name for τ lookup (vitals, lab, diagnosis, etc.).

    Returns:
        Decay factor in [0, 1], where 1.0 = now, approaching 0 as Δt → ∞.
    """
    if days_elapsed < 0:
        days_elapsed = 0.0
    tau = TAU.get(modality, TAU["default"])
    return math.exp(-days_elapsed / tau)


def clinical_significance_from_tags(tags: List[str]) -> float:
    """Compute clinical significance score from version tags.

    Uses the highest-weighted tag found in the version's tags.
    Returns 0.0 if no tags match known tiers.
    """
    if not tags:
        return 0.0
    best = 0.0
    for tag in tags:
        weight = TIER_WEIGHTS.get(tag.lower(), 0.0)
        if weight > best:
            best = weight
    return best


# ─── Scoring Functions ───

def compute_text_score(
    query_vector: List[float],
    version_vector: List[float],
) -> float:
    """Cosine similarity between query and version MedCPT vectors."""
    if not query_vector or not version_vector:
        return 0.0
    q = np.array(query_vector)
    v = np.array(version_vector)
    norm_q = np.linalg.norm(q)
    norm_v = np.linalg.norm(v)
    if norm_q == 0 or norm_v == 0:
        return 0.0
    return float(np.dot(q, v) / (norm_q * norm_v))


def compute_hybrid_score(
    query_dense: List[float],
    version_dense: List[float],
    query_sparse_indices: List[int] = None,
    query_sparse_values: List[float] = None,
    version_sparse_indices: List[int] = None,
    version_sparse_values: List[float] = None,
) -> float:
    """Combined dense + sparse score for BGE-M3 hybrid.

    Dense: cosine similarity.
    Sparse: dot product of overlapping sparse vectors (BM25-like).
    Final: weighted average (0.7 dense + 0.3 sparse).
    """
    # Dense score
    dense_score = compute_text_score(query_dense, version_dense)

    # Sparse score (overlap coefficient)
    sparse_score = 0.0
    if query_sparse_indices and version_sparse_indices:
        q_sparse = dict(zip(query_sparse_indices, query_sparse_values))
        v_sparse = dict(zip(version_sparse_indices, version_sparse_values))
        overlap_weights = []
        for idx, q_val in q_sparse.items():
            if idx in v_sparse:
                overlap_weights.append(q_val * v_sparse[idx])
        if overlap_weights:
            sparse_score = sum(overlap_weights) / (len(overlap_weights) + 1e-8)

    return 0.7 * dense_score + 0.3 * sparse_score


# ════════════════════════════════════════════════════
# Temporal Multimodal Retriever
# ════════════════════════════════════════════════════

class TemporalMultimodalRetriever:
    """Feature A: Temporal-aware multimodal retrieval over patient versions.

    Combines text, hybrid, image, temporal decay, and clinical significance
    into a single relevance score. Uses Qdrant for vector search and RRF
    for cross-modal fusion.
    """

    def __init__(self):
        self.alpha = ALPHA
        self.beta = BETA
        self.gamma = GAMMA
        self.delta = DELTA
        self.epsilon = EPSILON

    async def retrieve(
        self,
        query: str,
        patient_id: str,
        doctor_id: str,
        query_time: Optional[datetime] = None,
        k: int = 8,
        image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Temporal multimodal retrieval — full scoring pipeline.

        Args:
            query: Natural language query from the doctor.
            patient_id: UUID of the patient.
            doctor_id: UUID of the doctor (for RLS isolation).
            query_time: Query timestamp (defaults to now). Used for temporal decay
                and future-leak prevention (v_i.timestamp ≤ query_time).
            k: Number of results to return.
            image_path: Optional path to an image for NV-CLIP query.

        Returns:
            {
                "results": [...] ranked versions with scores,
                "citations": [...] summary for rendering,
                "meta": { query, took_ms, modalities_used, etc. }
            }
        """
        if query_time is None:
            query_time = datetime.now(timezone.utc)

        start = datetime.now(timezone.utc)

        # Build base filter: doctor isolation + patient + no future-leak
        filter_conditions = [
            FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
            FieldCondition(key="timestamp", range=Range(lte=query_time.isoformat())),
        ]
        base_filter = Filter(must=filter_conditions)
        search_params = SearchParams(hnsw_ef=128, exact=False)
        limit_per_modality = OVERSAMPLE_FACTOR * k

        # ── Step 1: Encode query vectors ──
        medcpt_vector: List[float] = []
        hybrid_dense: List[float] = []
        sparse_indices: List[int] = []
        sparse_values: List[float] = []
        image_vector: List[float] = []

        try:
            medcpt_result = await embedding_service.encode_medcpt([query])
            if medcpt_result and len(medcpt_result) > 0:
                vec = medcpt_result[0]
                medcpt_vector = vec.tolist() if hasattr(vec, 'tolist') else vec
        except Exception as exc:
            logger.warning("MedCPT encoding failed: %s", exc)

        try:
            bge_result = await embedding_service.encode_bge_m3(
                [query], return_dense=True, return_sparse=True
            )
            if bge_result.get("dense"):
                hybrid_dense = bge_result["dense"][0]
            if bge_result.get("sparse"):
                sp = bge_result["sparse"]
                if isinstance(sp, list) and len(sp) > 0:
                    sp_data = sp[0]
                    if isinstance(sp_data, dict):
                        sparse_indices = sp_data.get("indices", [])
                        sparse_values = sp_data.get("values", [])
        except Exception as exc:
            logger.warning("BGE-M3 encoding failed: %s", exc)

        if image_path:
            try:
                image_vector = await embedding_service.encode_nvclip_image(image_path)
            except Exception as exc:
                logger.warning("NV-CLIP encoding failed: %s", exc)

        # ── Step 2: Multi-modal search ──
        all_hits: List[List[ScoredPoint]] = []

        # Medical text search (MedCPT 768d)
        if medcpt_vector:
            try:
                text_hits = qdrant_service._client.search(
                    collection_name=PATIENT_VERSION_COLLECTION,
                    query_vector=("medical_text", medcpt_vector),
                    query_filter=base_filter,
                    limit=limit_per_modality,
                    search_params=search_params,
                    with_payload=True,
                )
                all_hits.append(text_hits)
            except Exception as exc:
                logger.warning("MedCPT search failed: %s", exc)

        # Hybrid search (BGE-M3 dense 1024d + sparse)
        if hybrid_dense:
            try:
                hybrid_hits = qdrant_service._client.search(
                    collection_name=PATIENT_VERSION_COLLECTION,
                    query_vector=("hybrid", hybrid_dense),
                    query_filter=base_filter,
                    limit=limit_per_modality,
                    search_params=search_params,
                    with_payload=True,
                )
                all_hits.append(hybrid_hits)
            except Exception as exc:
                logger.warning("Hybrid search failed: %s", exc)

        # Sparse search (BGE-M3 sparse)
        if sparse_indices and sparse_values:
            try:
                sparse = SparseVector(indices=sparse_indices, values=sparse_values)
                sparse_hits = qdrant_service._client.search(
                    collection_name=PATIENT_VERSION_COLLECTION,
                    query_vector=sparse,
                    query_filter=base_filter,
                    limit=limit_per_modality,
                    search_params=search_params,
                    with_payload=True,
                )
                all_hits.append(sparse_hits)
            except Exception as exc:
                logger.warning("Sparse search failed: %s", exc)

        # Image search (NV-CLIP 512d)
        if image_vector:
            try:
                image_hits = qdrant_service._client.search(
                    collection_name=PATIENT_VERSION_COLLECTION,
                    query_vector=("image", image_vector),
                    query_filter=base_filter,
                    limit=limit_per_modality,
                    search_params=search_params,
                    with_payload=True,
                )
                all_hits.append(image_hits)
            except Exception as exc:
                logger.warning("Image search failed: %s", exc)

        # ── Step 3: Reciprocal Rank Fusion ──
        if not all_hits:
            return {
                "results": [],
                "citations": [],
                "meta": {
                    "query": query,
                    "patient_id": patient_id,
                    "took_ms": (datetime.now(timezone.utc) - start).total_seconds() * 1000,
                    "modalities_used": [],
                    "total_results": 0,
                },
            }

        fused = self._reciprocal_rank_fusion(all_hits, k=k)

        # ── Step 4: Re-score with temporal decay + clinical significance ──
        for point in fused:
            payload = point.payload
            ts_str = payload.get("timestamp", "")
            ts = self._parse_timestamp(ts_str)
            days_elapsed = (query_time - ts).total_seconds() / 86400 if ts else 0.0

            # Detect modality from payload for τ
            modality = payload.get("modality", "text")

            # Get tags for clinical significance
            tags = payload.get("tags", []) or []
            sig_score = clinical_significance_from_tags(tags)

            # Compute temporal decay
            decay = temporal_decay(days_elapsed, modality)

            # Get raw scores from RRF
            rrf_score = point.score

            # Enhanced score: combine RRF + temporal + clinical significance
            enhanced_score = (
                (1.0 - self.delta - self.epsilon) * rrf_score
                + self.delta * decay
                + self.epsilon * sig_score
            )
            point.score = enhanced_score

        # Re-sort by enhanced score
        fused.sort(key=lambda p: -p.score)

        # ── Step 5: Build response ──
        results = []
        citations = []
        for i, point in enumerate(fused[:k]):
            payload = point.payload
            ts_str = payload.get("timestamp", "")
            ts = self._parse_timestamp(ts_str)

            result_item = {
                "rank": i + 1,
                "score": round(point.score, 4),
                "version_id": payload.get("version_id", ""),
                "version_number": payload.get("version_number", 0),
                "patient_id": payload.get("patient_id", ""),
                "author": payload.get("author", ""),
                "edit_type": payload.get("edit_type", ""),
                "summary": payload.get("summary", ""),
                "tags": payload.get("tags", []) or [],
                "timestamp": ts_str,
                "clinical_significance": sig_score,
                "temporal_decay": round(decay, 4),
            }
            results.append(result_item)

            # Build citation for frontend
            version_num = payload.get("version_number", 0)
            date_str = ""
            if ts:
                date_str = ts.strftime("%Y-%m-%d")
            citations.append({
                "version_number": version_num,
                "date": date_str,
                "summary": payload.get("summary", ""),
                "score": round(point.score, 3),
                "edit_type": payload.get("edit_type", ""),
            })

        elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        logger.info(
            "Temporal RAG: query=%s patient=%s modalities=%d results=%d took=%.0fms",
            query[:50], patient_id, len([h for h in all_hits if h]), len(results), elapsed_ms,
        )

        return {
            "results": results,
            "citations": citations,
            "meta": {
                "query": query,
                "patient_id": patient_id,
                "query_time": query_time.isoformat(),
                "took_ms": round(elapsed_ms, 1),
                "modalities_used": len([h for h in all_hits if h]),
                "total_results": len(results),
                "alpha": self.alpha,
                "beta": self.beta,
                "gamma": self.gamma,
                "delta": self.delta,
                "epsilon": self.epsilon,
            },
        }

    # ─── Single-modality retrieval (for evaluation/baselines) ───

    async def retrieve_dense_only(
        self,
        query: str,
        patient_id: str,
        doctor_id: str,
        query_time: Optional[datetime] = None,
        k: int = 8,
    ) -> Dict[str, Any]:
        """Dense-only baseline (vanilla MedCPT, no temporal, no fusion)."""
        if query_time is None:
            query_time = datetime.now(timezone.utc)

        filter_conditions = [
            FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
            FieldCondition(key="timestamp", range=Range(lte=query_time.isoformat())),
        ]
        base_filter = Filter(must=filter_conditions)

        medcpt_result = await embedding_service.encode_medcpt([query])
        query_vector = medcpt_result[0].tolist() if medcpt_result else []

        if not query_vector:
            return {"results": [], "citations": [], "meta": {"total_results": 0}}

        hits = qdrant_service._client.search(
            collection_name=PATIENT_VERSION_COLLECTION,
            query_vector=("medical_text", query_vector),
            query_filter=base_filter,
            limit=k,
            with_payload=True,
        )

        results = []
        for i, point in enumerate(hits):
            payload = point.payload
            results.append({
                "rank": i + 1,
                "score": round(point.score, 4),
                "version_id": payload.get("version_id", ""),
                "version_number": payload.get("version_number", 0),
                "summary": payload.get("summary", ""),
                "timestamp": payload.get("timestamp", ""),
            })

        return {"results": results, "citations": [], "meta": {"total_results": len(results)}}

    # ─── Internal Helpers ───

    def _reciprocal_rank_fusion(
        self,
        result_lists: List[List[ScoredPoint]],
        k: int = 60,
        top_n: int = 20,
    ) -> List[ScoredPoint]:
        """Reciprocal Rank Fusion (RRF) combining multiple ranked result lists."""
        scores: Dict[str, float] = {}
        seen: Dict[str, ScoredPoint] = {}

        for rank_list in result_lists:
            for rank, point in enumerate(rank_list):
                point_id = str(point.id)
                scores[point_id] = scores.get(point_id, 0.0) + 1.0 / (k + rank + 1)
                if point_id not in seen:
                    seen[point_id] = point

        sorted_ids = sorted(scores.keys(), key=lambda pid: -scores[pid])
        fused = []
        for pid in sorted_ids[:top_n]:
            pt = seen[pid]
            pt.score = scores[pid]
            fused.append(pt)
        return fused

    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """Parse ISO-8601 timestamp string to datetime."""
        if not ts_str:
            return None
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
