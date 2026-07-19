"""RAG Audit Logging & LLM Rate Limiting — per-doctor tracking for Feature A.

Provides:
  1. RAG query audit logging — every retrieval call is logged with query, results summary, latency
  2. Per-doctor LLM rate limiting — tracks RPM (requests per minute) per doctor
  3. Future-leak data validation — ensures no timestamp > query_time versions are returned

Usage:
    from app.services.rag_audit import RAGAuditService, LLMRateLimiter
    audit = RAGAuditService()
    await audit.log_retrieval(db, doctor_id=..., patient_id=..., query=..., ...)

    limiter = LLMRateLimiter()
    can_proceed, info = await limiter.check_rate_limit(doctor_id)
"""

from __future__ import annotations

import time
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from collections import defaultdict
from uuid import UUID

from app.models import AuditLog

logger = logging.getLogger(__name__)

# ─── RAG Audit Service ──────────────────────────────

class RAGAuditService:
    """Logs every RAG retrieval call with query details, results, and latency.

    Each call writes an AuditLog entry with:
      - action: "rag:retrieve"
      - resource_type: "rag_query"
      - payload: {query, modalities_used, num_results, latency_ms, score_range, future_leak_check}
    """

    async def log_retrieval(
        self,
        db_session,
        doctor_id: UUID,
        patient_id: str,
        query: str,
        modalities_used: int,
        num_results: int,
        latency_ms: float,
        min_score: float = 0.0,
        max_score: float = 0.0,
        future_leak_count: int = 0,
        citation_ids: Optional[List[str]] = None,
        **extra,
    ) -> None:
        """Log a RAG retrieval call to the audit log.

        Args:
            db_session: SQLAlchemy async session.
            doctor_id: UUID of the doctor.
            patient_id: UUID of the patient.
            query: The original query text (truncated to 500 chars).
            modalities_used: How many search modalities were queried.
            num_results: Number of results returned.
            latency_ms: Retrieval latency in milliseconds.
            min_score: Minimum score among results.
            max_score: Maximum score among results.
            future_leak_count: Number of future-timestamped results detected (should be 0).
            citation_ids: Version IDs of citations returned.
        """
        try:
            entry = AuditLog(
                doctor_id=doctor_id,
                patient_id=UUID(patient_id) if patient_id else None,
                actor=f"doctor:{doctor_id}",
                action="rag:retrieve",
                resource_type="rag_query",
                payload_jsonb={
                    "query": query[:500],
                    "modalities_used": modalities_used,
                    "num_results": num_results,
                    "latency_ms": round(latency_ms, 1),
                    "score_range": {
                        "min": round(min_score, 4),
                        "max": round(max_score, 4),
                    },
                    "future_leak_count": future_leak_count,
                    "citation_count": len(citation_ids) if citation_ids else 0,
                    "citations": citation_ids[:20] if citation_ids else [],
                },
            )
            db_session.add(entry)
            await db_session.commit()
            logger.debug("RAG audit logged: query=%s results=%d leak=%d",
                         query[:60], num_results, future_leak_count)
        except Exception as exc:
            logger.warning("RAG audit log write failed (non-blocking): %s", exc)
            await db_session.rollback()

    async def log_synthesis(
        self,
        db_session,
        doctor_id: UUID,
        patient_id: Optional[str],
        query: str,
        model_used: str,
        response_length: int,
        citations_used: int,
        latency_ms: float,
    ) -> None:
        """Log an LLM synthesis call."""
        try:
            entry = AuditLog(
                doctor_id=doctor_id,
                patient_id=UUID(patient_id) if patient_id else None,
                actor=f"doctor:{doctor_id}",
                action="rag:synthesize",
                resource_type="rag_synthesis",
                payload_jsonb={
                    "query": query[:300],
                    "model": model_used,
                    "response_length": response_length,
                    "citations_used": citations_used,
                    "latency_ms": round(latency_ms, 1),
                },
            )
            db_session.add(entry)
            await db_session.commit()
        except Exception as exc:
            logger.warning("RAG synthesis audit failed (non-blocking): %s", exc)
            await db_session.rollback()


# ─── LLM Rate Limiter ───────────────────────────────

class LLMRateLimiter:
    """Per-doctor rate limiter for LLM API calls.

    Tracks requests per minute (RPM) per doctor in memory.
    Default: 10 RPM per doctor (sustainable for solo GP practice).
    """

    def __init__(self, default_rpm: int = 10):
        self.default_rpm = default_rpm
        self._buckets: Dict[str, List[float]] = defaultdict(list)

    async def check_rate_limit(
        self,
        doctor_id: str,
        rpm_limit: Optional[int] = None,
    ) -> tuple[bool, Dict[str, Any]]:
        """Check if a doctor has exceeded their LLM rate limit.

        Args:
            doctor_id: UUID of the doctor.
            rpm_limit: Max requests per minute (default: 10).

        Returns:
            (allowed: bool, info: dict)
            info contains: current_rpm, limit, reset_after_seconds
        """
        limit = rpm_limit or self.default_rpm
        now = time.time()
        bucket = self._buckets[doctor_id]

        # Prune entries older than 60 seconds
        cutoff = now - 60
        self._buckets[doctor_id] = [t for t in bucket if t > cutoff]

        current_rpm = len(self._buckets[doctor_id])
        allowed = current_rpm < limit

        # Determine reset time
        oldest = min(self._buckets[doctor_id]) if self._buckets[doctor_id] else now
        reset_after = max(0.0, 60.0 - (now - oldest))

        info = {
            "current_rpm": current_rpm,
            "limit": limit,
            "remaining": max(0, limit - current_rpm),
            "reset_after_seconds": round(reset_after, 1),
            "allowed": allowed,
        }

        return allowed, info

    async def record_call(self, doctor_id: str) -> None:
        """Record an LLM API call for rate limiting."""
        self._buckets[doctor_id].append(time.time())

    def get_stats(self, doctor_id: str) -> Dict[str, Any]:
        """Get current rate limit stats for a doctor."""
        now = time.time()
        cutoff = now - 60
        bucket = [t for t in self._buckets.get(doctor_id, []) if t > cutoff]
        return {
            "doctor_id": doctor_id,
            "current_rpm": len(bucket),
            "limit": self.default_rpm,
        }


# ─── Future-Leak Data Validation ────────────────────

def validate_no_future_leak(
    results: List[Dict[str, Any]],
    query_time: datetime,
) -> Dict[str, Any]:
    """Validate that no retrieved version has a timestamp > query_time.

    This is the final safety check before returning results. It should
    always pass since Qdrant's filter already enforces timestamp ≤ query_time,
    but this double-checks in case of clock skew or config error.

    Args:
        results: List of retrieved version dicts with "timestamp" field.
        query_time: The query's timestamp (results must be ≤ this).

    Returns:
        {"passed": bool, "leaked": int, "details": list of leaked version_ids}
    """
    leaked = []
    for r in results:
        ts_str = r.get("timestamp", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts > query_time:
                leaked.append({
                    "version_id": r.get("version_id", ""),
                    "version_number": r.get("version_number", 0),
                    "timestamp": ts_str,
                    "diff_seconds": (ts - query_time).total_seconds(),
                })
        except (ValueError, TypeError):
            pass

    return {
        "passed": len(leaked) == 0,
        "leaked": len(leaked),
        "details": leaked,
    }
