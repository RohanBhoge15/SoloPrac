"""Embedding Pipeline Orchestrator — connects PatientVersion creation to Qdrant indexing.

When a new PatientVersion is minted, this service:
1. Extracts text from the version's state_jsonb (flattening nested clinical data).
2. Encodes with MedCPT (768d) and BGE-M3 (1024d + sparse).
3. Upserts the vector point into Qdrant's patient_versions collection.
4. Caches the embedding in Redis for quick retrieval.

Two modes:
  - SYNC: Call index_version() directly after minting a version (inline with API response).
  - ASYNC: Enqueue via arq worker for non-blocking indexing (recommended for production).

Usage (sync):
    from app.services.indexer import index_version
    await index_version(db, version, patient, doctor_id)

Usage (async via arq):
    from app.services.indexer import index_version_job
    # In your arq worker:
    await redis.enqueue_job("index_version_job", version_id=str(v.id))
"""

import uuid
import json
import logging
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import PatientVersion, Patient
from app.services.embeddings import embedding_service
from app.services.qdrant import qdrant_service
from app.services.redis import redis_service
from app.services.pii import strip_pii

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 86400  # 24 hours


def _flatten_state(state: dict) -> str:
    """Flatten a patient version state_jsonb into a single text string for embedding.

    Concatenates all field values (demographics, clinical data, etc.) into
    a single searchable text block. Nested dicts are JSON-stringified.
    """
    parts = []
    for key, value in state.items():
        if isinstance(value, dict):
            # Flatten nested dict recursively
            nested = _flatten_state(value)
            if nested:
                parts.append(nested)
        elif isinstance(value, list):
            items = []
            for item in value:
                if isinstance(item, dict):
                    items.append(_flatten_state(item))
                elif item is not None:
                    items.append(str(item))
            if items:
                parts.append(f"{key}: {'; '.join(items)}")
        elif value is not None:
            parts.append(f"{key}: {value}")
    return " | ".join(parts)


def _extract_search_text(version: PatientVersion) -> str:
    """Extract a searchable text string from a PatientVersion for embedding.

    Uses the flattened state text. If the result is empty, falls back
    to the version summary.

    PII (name, phone, email, address, national IDs, ...) is stripped BEFORE
    flattening, so patient identity never enters the embedded text or the
    Qdrant payload — only pseudonymous clinical data is indexed.
    """
    state = strip_pii(version.state_jsonb or {})
    text = _flatten_state(state)
    if not text.strip():
        text = version.summary or f"Patient version {version.version_number}"
    return text


async def index_version(
    db: AsyncSession,
    version: PatientVersion,
    patient: Patient,
    doctor_id: uuid.UUID,
) -> str:
    """Index a single PatientVersion into Qdrant with all vector representations.

    Steps:
        1. Extract text from state_jsonb.
        2. Generate MedCPT (768d), BGE-M3 dense (1024d), and BGE-M3 sparse vectors.
        3. Upsert point to Qdrant.
        4. Cache the result in Redis.

    Returns:
        The Qdrant point ID (same as version_id).

    This function is designed to be called from an arq worker or directly
    after version minting. It catches embedding errors gracefully so the
    API response is not blocked by a model load failure.
    """
    version_id = str(version.id)
    search_text = _extract_search_text(version)

    try:
        # Step 1: Generate MedCPT embedding (768d, clinical text)
        logger.info("Encoding MedCPT for version %s (patient %s)", version_id, patient.id)
        medcpt_vectors = await embedding_service.encode_medcpt([search_text])
        medcpt_embedding = medcpt_vectors[0].tolist() if hasattr(medcpt_vectors[0], 'tolist') else medcpt_vectors[0]
    except Exception as exc:
        logger.warning("MedCPT encoding failed for version %s: %s (proceeding without)", version_id, exc)
        medcpt_embedding = []

    try:
        # Step 2: Generate BGE-M3 dense + sparse embeddings (1024d)
        logger.info("Encoding BGE-M3 for version %s", version_id)
        bge_result = await embedding_service.encode_bge_m3([search_text], return_dense=True, return_sparse=True)
        hybrid_embedding = bge_result["dense"][0] if bge_result.get("dense") else []
        sparse_indices = []
        sparse_values = []
        if bge_result.get("sparse"):
            sparse_data = bge_result["sparse"][0] if isinstance(bge_result["sparse"], list) else bge_result["sparse"]
            if isinstance(sparse_data, dict):
                sparse_indices = sparse_data.get("indices", [])
                sparse_values = sparse_data.get("values", [])
    except Exception as exc:
        logger.warning("BGE-M3 encoding failed for version %s: %s (proceeding without)", version_id, exc)
        hybrid_embedding = []
        sparse_indices = []
        sparse_values = []

    try:
        # Step 3: Upsert to Qdrant
        logger.info("Indexing version %s to Qdrant", version_id)
        point_id = await qdrant_service.upsert_version({
            "version_id": version_id,
            "patient_id": str(patient.id),
            "doctor_id": str(doctor_id),
            "version_number": version.version_number,
            "timestamp": version.timestamp.isoformat() if version.timestamp else None,
            "modality": "text",
            "version_hash": version.version_hash,
            "author": version.author,
            "edit_type": version.edit_type,
            "summary": version.summary,
            "tags": version.tags or [],
            "clinical_significance": version.clinical_significance or 0.0,
            "medical_text_embedding": medcpt_embedding,
            "hybrid_embedding": hybrid_embedding,
            "sparse_indices": sparse_indices,
            "sparse_values": sparse_values,
            "image_embedding": [],  # No image data at version creation
        })
    except Exception as exc:
        logger.error("Qdrant upsert failed for version %s: %s", version_id, exc)
        raise

    try:
        # Step 4: Cache the embedding reference in Redis
        cache_key = f"embedding_pending:{version_id}"
        await redis_service.set_cached(
            cache_key,
            {
                "version_id": version_id,
                "patient_id": str(patient.id),
                "version_number": version.version_number,
                "qdrant_point_id": point_id,
                "modality": "text",
            },
            ttl=CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("Redis cache write failed for version %s: %s", version_id, exc)

    logger.info(
        "Indexed version %s v%d to Qdrant (point=%s, medcpt=%d dims, hybrid=%d dims)",
        version_id, version.version_number, point_id,
        len(medcpt_embedding), len(hybrid_embedding),
    )
    return point_id


# ─── Arq Job Functions ────────────────────────────

async def index_version_job(ctx, version_id: str):
    """Arq job: index a version by ID.

    Called by the arq worker when a version needs background indexing.
    The context provides a Redis connection; we create a fresh DB session
    since arq workers don't share the app's request-scoped sessions.

    Usage:
        await redis.enqueue_job("index_version_job", version_id=str(version.id))
    """
    from app.database import async_session_maker

    async with async_session_maker() as db:
        result = await db.execute(
            select(PatientVersion).where(PatientVersion.id == uuid.UUID(version_id))
        )
        version = result.scalar_one_or_none()
        if not version:
            logger.error("index_version_job: version %s not found", version_id)
            return {"status": "error", "detail": "version not found"}

        result = await db.execute(
            select(Patient).where(Patient.id == version.patient_id)
        )
        patient = result.scalar_one_or_none()
        if not patient:
            logger.error("index_version_job: patient %s not found", version.patient_id)
            return {"status": "error", "detail": "patient not found"}

        point_id = await index_version(db, version, patient, version.doctor_id)
        return {"status": "ok", "version_id": version_id, "qdrant_point_id": point_id}


async def reindex_patient_job(ctx, patient_id: str):
    """Arq job: reindex all versions for a patient (for backfill or recovery)."""
    from app.database import async_session_maker

    async with async_session_maker() as db:
        result = await db.execute(
            select(Patient).where(Patient.id == uuid.UUID(patient_id))
        )
        patient = result.scalar_one_or_none()
        if not patient:
            return {"status": "error", "detail": "patient not found"}

        versions = await db.execute(
            select(PatientVersion)
            .where(PatientVersion.patient_id == patient.id)
            .order_by(PatientVersion.version_number)
        )
        # Use yield_per to avoid loading all versions into memory at once
        version_list = []
        for v in versions.yield_per(50):
            version_list.append(v)

        results = []
        for version in version_list:
            try:
                point_id = await index_version(db, version, patient, patient.doctor_id)
                results.append({"version_id": str(version.id), "status": "ok", "point_id": point_id})
            except Exception as exc:
                results.append({"version_id": str(version.id), "status": "error", "detail": str(exc)})
                logger.error("Reindex failed for version %s: %s", version.id, exc)

        return {
            "status": "ok",
            "patient_id": patient_id,
            "total": len(version_list),
            "indexed": sum(1 for r in results if r["status"] == "ok"),
            "failed": sum(1 for r in results if r["status"] == "error"),
            "results": results,
        }


# ─── Arq Worker Settings ──────────────────────────

class WorkerSettings:
    """Arq worker configuration for embedding/indexing jobs."""
    functions = [index_version_job, reindex_patient_job]
    max_burst_jobs = 10
    keep_result_seconds = 3600
    poll_delay = 1.0
    burst = False
