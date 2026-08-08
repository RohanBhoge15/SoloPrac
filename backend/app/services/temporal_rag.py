"""Feature A — Temporal Multimodal RAG ⭐ Primary Research Contribution.

Given query `q` at time `t_q`, patient `p`, doctor `d`, retrieve top-`k` versions:

    score(v_i, q, t_q) =
          α · cos(MedCPT(q), v_i.medical_text)
        + β · hybrid_score(BGE-M3(q), v_i.hybrid, v_i.sparse)
        + γ · cos(BiomedCLIP(q_img), v_i.image)          [if query has image]
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

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    Range,
    ScoredPoint,
    SearchParams,
    SparseVector,
)

from app.services.embeddings import embedding_service
from app.services.qdrant import PATIENT_VERSION_COLLECTION, qdrant_service

logger = logging.getLogger(__name__)

# ─── Scoring Weights (tunable hyperparameters) ───

ALPHA = 0.30  # MedCPT text similarity weight
BETA = 0.25  # BGE-M3 hybrid (dense + sparse) weight
GAMMA = 0.20  # BiomedCLIP image similarity weight
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
    "text": 30.0,  # default for general text
    "hybrid": 30.0,  # default for hybrid
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

    async def _cached_retrieve_get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """P3.31 — Fetch a previously-computed retrieval result from Redis."""
        try:
            import json as _json

            from app.services.redis import redis_service

            client = await redis_service.connect()
            raw = await client.get(cache_key)
            if raw:
                return _json.loads(raw)
        except Exception as exc:
            logger.debug("temporal_rag cache miss (get): %s", exc)
        return None

    async def _cached_retrieve_set(self, cache_key: str, value: Dict[str, Any]) -> None:
        try:
            import json as _json

            from app.services.redis import redis_service

            client = await redis_service.connect()
            # 60s TTL — long enough to absorb chat back-and-forth on the same
            # question, short enough that a newly-minted PatientVersion still
            # surfaces on the next real query.
            await client.setex(cache_key, 60, _json.dumps(value, default=str))
        except Exception as exc:
            logger.debug("temporal_rag cache set failed: %s", exc)

    async def retrieve(
        self,
        query: str,
        patient_id: str,
        doctor_id: str,
        query_time: Optional[datetime] = None,
        k: Optional[int] = None,
        image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Temporal multimodal retrieval — full scoring pipeline.

        Args:
            query: Natural language query from the doctor.
            patient_id: UUID of the patient.
            doctor_id: UUID of the doctor (for RLS isolation).
            query_time: Query timestamp (defaults to now). Used for temporal decay
                and future-leak prevention (v_i.timestamp ≤ query_time).
            k: Number of results to return (defaults to RETRIEVAL_TOP_K config).
            image_path: Optional path to an image for BiomedCLIP query.

        Returns:
            {
                "results": [...] ranked versions with scores,
                "citations": [...] summary for rendering,
                "meta": { query, took_ms, modalities_used, etc. }
            }
        """
        if query_time is None:
            query_time = datetime.now(timezone.utc)
        if k is None:
            from app.config import settings

            k = settings.RETRIEVAL_TOP_K

        start = datetime.now(timezone.utc)

        # ── P3.31 — Redis cache lookup ─────────────────────────────────────
        # Key = (doctor, patient, query, k, image?, scoring hyperparams).
        # We bucket query_time to the minute so back-to-back questions inside
        # a chat turn hit the cache; the 60s TTL prevents stale answers after
        # edits. The alpha/beta/gamma/delta/epsilon knobs MUST be part of the
        # key — otherwise ablations (e.g. delta=0 vs delta=0.15) collide on
        # the same key and return each other's cached results, which silently
        # broke Feature A eval before this fix.
        import hashlib as _hashlib

        _bucket = query_time.replace(second=0, microsecond=0).isoformat()
        _hp = f"a={self.alpha}|b={self.beta}|g={self.gamma}" f"|d={self.delta}|e={self.epsilon}"
        _cache_seed = f"{doctor_id}|{patient_id}|{query}|k={k}" f"|img={bool(image_path)}|t={_bucket}|{_hp}"
        _cache_key = "trag:" + _hashlib.sha256(_cache_seed.encode("utf-8")).hexdigest()[:32]
        _cached = await self._cached_retrieve_get(_cache_key)
        if _cached is not None:
            _cached.setdefault("meta", {})["cache"] = "hit"
            return _cached

        # Build base filter: doctor isolation + patient + no future-leak.
        # Qdrant's Range is numeric-only, so we filter on `timestamp_epoch`
        # (populated by qdrant_service.upsert_version alongside the ISO
        # `timestamp`). This is the actual bug that caused every retrieve
        # call to 400-error with "float_parsing" against an ISO string.
        filter_conditions = [
            FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
            FieldCondition(key="timestamp_epoch", range=Range(lte=float(query_time.timestamp()))),
        ]
        base_filter = Filter(must=filter_conditions)
        search_params = SearchParams(hnsw_ef=128, exact=False)
        limit_per_modality = OVERSAMPLE_FACTOR * k

        # ── Step 1: Encode query vectors (PARALLEL — was sequential, saved ~8-12s) ──
        medcpt_vector: List[float] = []
        hybrid_dense: List[float] = []
        sparse_indices: List[int] = []
        sparse_values: List[float] = []
        image_vector: List[float] = []

        # Build task list — all three encoders are independent, so we run them concurrently.
        encode_tasks = [
            embedding_service.encode_medcpt([query]),
            embedding_service.encode_bge_m3([query], return_dense=True, return_sparse=True),
        ]
        if image_path:
            encode_tasks.append(embedding_service.encode_biomedclip_image(image_path))

        encode_results = await asyncio.gather(*encode_tasks, return_exceptions=True)

        # Unpack MedCPT
        medcpt_result = encode_results[0]
        if isinstance(medcpt_result, Exception):
            logger.warning("MedCPT encoding failed: %s", medcpt_result)
        elif medcpt_result is not None and len(medcpt_result) > 0:
            vec = medcpt_result[0]
            medcpt_vector = vec.tolist() if hasattr(vec, "tolist") else vec

        # Unpack BGE-M3 (dense + sparse)
        bge_result = encode_results[1]
        if isinstance(bge_result, Exception):
            logger.warning("BGE-M3 encoding failed: %s", bge_result)
        else:
            if bge_result.get("dense"):
                hybrid_dense = bge_result["dense"][0]
            if bge_result.get("sparse"):
                sp = bge_result["sparse"]
                if isinstance(sp, list) and len(sp) > 0:
                    sp_data = sp[0]
                    if isinstance(sp_data, dict):
                        sparse_indices = sp_data.get("indices", [])
                        sparse_values = sp_data.get("values", [])

        # Unpack BiomedCLIP (only present if image_path was supplied)
        if image_path and len(encode_results) > 2:
            img_result = encode_results[2]
            if isinstance(img_result, Exception):
                logger.warning("BiomedCLIP encoding failed: %s", img_result)
            else:
                image_vector = img_result

        # ── Step 2: Multi-modal search (PARALLEL — was sequential, saves 200-400ms) ──
        # Collect all search coroutines; each maps 1:1 to an appended entry in all_hits.
        search_coros: List[Tuple[str, Any]] = []  # (label, coroutine)

        if medcpt_vector:
            search_coros.append(
                (
                    "medcpt",
                    asyncio.to_thread(
                        qdrant_service._client.search,
                        collection_name=PATIENT_VERSION_COLLECTION,
                        query_vector=("medical_text", medcpt_vector),
                        query_filter=base_filter,
                        limit=limit_per_modality,
                        search_params=search_params,
                        with_payload=True,
                    ),
                )
            )

        if hybrid_dense:
            search_coros.append(
                (
                    "hybrid",
                    asyncio.to_thread(
                        qdrant_service._client.search,
                        collection_name=PATIENT_VERSION_COLLECTION,
                        query_vector=("hybrid", hybrid_dense),
                        query_filter=base_filter,
                        limit=limit_per_modality,
                        search_params=search_params,
                        with_payload=True,
                    ),
                )
            )

        if sparse_indices and sparse_values:
            sparse = SparseVector(indices=sparse_indices, values=sparse_values)
            search_coros.append(
                (
                    "sparse",
                    asyncio.to_thread(
                        qdrant_service._client.search,
                        collection_name=PATIENT_VERSION_COLLECTION,
                        query_vector=sparse,
                        query_filter=base_filter,
                        limit=limit_per_modality,
                        search_params=search_params,
                        with_payload=True,
                    ),
                )
            )

        if image_vector:
            search_coros.append(
                (
                    "image",
                    asyncio.to_thread(
                        qdrant_service._client.search,
                        collection_name=PATIENT_VERSION_COLLECTION,
                        query_vector=("image", image_vector),
                        query_filter=base_filter,
                        limit=limit_per_modality,
                        search_params=search_params,
                        with_payload=True,
                    ),
                )
            )

        all_hits: List[List[ScoredPoint]] = []
        if search_coros:
            search_results = await asyncio.gather(*(c for _, c in search_coros), return_exceptions=True)
            for (label, _), result in zip(search_coros, search_results):
                if isinstance(result, Exception):
                    logger.warning("%s search failed: %s", label, result)
                else:
                    all_hits.append(result)

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
                (1.0 - self.delta - self.epsilon) * rrf_score + self.delta * decay + self.epsilon * sig_score
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
            days_elapsed = (query_time - ts).total_seconds() / 86400 if ts else 0.0
            modality = payload.get("modality", "text")
            tags = payload.get("tags", []) or []
            point_decay = temporal_decay(days_elapsed, modality)
            point_sig = clinical_significance_from_tags(tags)

            result_item = {
                "rank": i + 1,
                "score": round(point.score, 4),
                "version_id": payload.get("version_id", ""),
                "version_number": payload.get("version_number", 0),
                "patient_id": payload.get("patient_id", ""),
                "author": payload.get("author", ""),
                "edit_type": payload.get("edit_type", ""),
                "summary": payload.get("summary", ""),
                "tags": tags,
                "timestamp": ts_str,
                "clinical_significance": point_sig,
                "temporal_decay": round(point_decay, 4),
                "modality": modality,
                "s3_key": payload.get("s3_key", ""),
            }
            results.append(result_item)

            # Build citation for frontend
            version_num = payload.get("version_number", 0)
            date_str = ""
            if ts:
                date_str = ts.strftime("%Y-%m-%d")
            citations.append(
                {
                    "version_number": version_num,
                    "date": date_str,
                    "summary": payload.get("summary", ""),
                    "score": round(point.score, 3),
                    "edit_type": payload.get("edit_type", ""),
                    "modality": modality,
                    "s3_key": payload.get("s3_key", ""),
                }
            )

        elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        logger.info(
            "Temporal RAG: query=%s patient=%s modalities=%d results=%d took=%.0fms",
            query[:50],
            patient_id,
            len([h for h in all_hits if h]),
            len(results),
            elapsed_ms,
        )

        _payload = {
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
                "cache": "miss",
            },
        }
        # P3.31 — populate the Redis cache for repeat queries in the same
        # chat/plan cycle. Fire-and-forget so the caller isn't blocked on the
        # write.
        try:
            await self._cached_retrieve_set(_cache_key, _payload)
        except Exception:
            pass
        return _payload

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
            FieldCondition(key="timestamp_epoch", range=Range(lte=float(query_time.timestamp()))),
        ]
        base_filter = Filter(must=filter_conditions)

        medcpt_result = await embedding_service.encode_medcpt([query])
        query_vector = medcpt_result[0].tolist() if medcpt_result is not None and len(medcpt_result) > 0 else []

        if not query_vector:
            return {"results": [], "citations": [], "meta": {"total_results": 0}}

        hits = await asyncio.to_thread(
            qdrant_service._client.search,
            collection_name=PATIENT_VERSION_COLLECTION,
            query_vector=("medical_text", query_vector),
            query_filter=base_filter,
            limit=k,
            with_payload=True,
        )

        results = []
        for i, point in enumerate(hits):
            payload = point.payload
            results.append(
                {
                    "rank": i + 1,
                    "score": round(point.score, 4),
                    "version_id": payload.get("version_id", ""),
                    "version_number": payload.get("version_number", 0),
                    "summary": payload.get("summary", ""),
                    "timestamp": payload.get("timestamp", ""),
                }
            )

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
