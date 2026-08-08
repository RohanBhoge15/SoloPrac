"""Background job dispatcher — offloads heavy work to the arq worker so the
API request path stays fast and the uvicorn event loop is never held hostage.

Every function here has TWO surfaces:

1. `enqueue_<name>(...)` — called from FastAPI request handlers. Pushes a job
   onto the arq queue and returns a job id. Non-blocking.
2. `<name>_job(ctx, ...)` — the actual work, executed inside the arq-worker
   container. Registered in `email_queue.WorkerSettings.functions`.

Job status can be polled via `GET /api/v1/jobs/{job_id}` (see routers/jobs.py).

Fixes covered:
  * P0.7  — OCR pipeline (`/documents/parse`) enqueues here instead of awaiting
  * P1.9  — Vector indexing on version create enqueues here instead of using
             FastAPI BackgroundTasks (which is in-process, non-persistent)
  * P2.23 — Weekly report generation
  * P2.24 — ORB image comparison
  * P2.25 — pg_dump backup
  * P2.27 — Batched flush of Redis-buffered audit-log entries (cron)

Never import heavy ML libs at module top-level here — they only need to load
inside the arq worker, not in the API process.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ── Shared arq pool (lazy) ──────────────────────────────────────────────────

_arq_pool = None
_pool_broken = False


async def get_arq_pool():
    """Return a shared ArqRedis pool, creating it once on first use.

    Returns None if arq/Redis isn't reachable — callers must handle that
    gracefully (do the work inline as a last resort, or return 503).
    """
    global _arq_pool, _pool_broken
    if _pool_broken:
        return None
    if _arq_pool is not None:
        return _arq_pool
    try:
        from arq.connections import RedisSettings, create_pool

        _arq_pool = await create_pool(
            RedisSettings(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                database=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
            )
        )
        logger.info("background_jobs: arq pool ready")
        return _arq_pool
    except Exception as exc:
        logger.warning("background_jobs: failed to build arq pool (%s) — falling back", exc)
        _pool_broken = True
        return None


async def preload_arq_pool() -> None:
    """Called from FastAPI startup lifespan so the first request doesn't pay
    the ~100-200ms pool-creation cost."""
    await get_arq_pool()


# ═══════════════════════════════════════════════════════════════════════════
#  P0.7 — Document parsing (OCR router: Docling / RapidOCR / MedGemma)
# ═══════════════════════════════════════════════════════════════════════════


async def enqueue_parse_document(
    doc_id: str,
    s3_key: str,
    content_type: str,
    doctor_id: str,
    patient_id: Optional[str],
    filename: str,
    size_bytes: int,
) -> Optional[str]:
    """Enqueue OCR + indexing. Returns arq job id or None on failure.

    Called from POST /documents/parse. The endpoint returns 202 with this
    job_id; the frontend polls GET /api/v1/jobs/{job_id} to know when to
    fetch the parsed result from /documents/{doc_id}.
    """
    pool = await get_arq_pool()
    if pool is None:
        return None
    try:
        job = await pool.enqueue_job(
            "parse_document_job",
            doc_id=doc_id,
            s3_key=s3_key,
            content_type=content_type,
            doctor_id=doctor_id,
            patient_id=patient_id,
            filename=filename,
            size_bytes=size_bytes,
        )
        return job.job_id if job else None
    except Exception as exc:
        logger.warning("enqueue_parse_document failed: %s", exc)
        return None


async def parse_document_job(
    ctx,
    doc_id: str,
    s3_key: str,
    content_type: str,
    doctor_id: str,
    patient_id: Optional[str],
    filename: str,
    size_bytes: int,
) -> Dict[str, Any]:
    """Worker: download from S3, run the OCR router, mint a PatientVersion
    (if patient_id was supplied), and dispatch a report_available
    notification. All the work that used to block /documents/parse for
    5-30s now runs here instead."""
    import os
    import tempfile

    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models import AuditLog, Patient
    from app.routers.documents import _dispatch_notification, _mint_version  # reuse
    from app.services.document_parser import parser_router
    from app.services.storage import storage_service

    # 1. Pull the file back down from S3 to a local temp path (parser needs
    #    a real filesystem path for RapidOCR / Docling / MedGemma).
    ext = os.path.splitext(s3_key)[1] or ".bin"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        content = await storage_service.download_file(bucket_type="documents", key=s3_key)
        with open(tmp_path, "wb") as f:
            f.write(content)

        # 2. Route through Docling / RapidOCR / MedGemma.
        result = await parser_router.parse(tmp_path, content_type or "application/octet-stream")
    except Exception as exc:
        logger.error("parse_document_job: parse failed (doc_id=%s): %s", doc_id, exc)
        return {"status": "error", "doc_id": doc_id, "error": str(exc)[:400]}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # 3. Attach to a patient version if requested.
    version_id: Optional[str] = None
    if patient_id:
        try:
            async with async_session_maker() as db:
                pat_row = await db.execute(
                    select(Patient).where(
                        Patient.id == uuid.UUID(patient_id),
                        Patient.doctor_id == uuid.UUID(doctor_id),
                    )
                )
                patient = pat_row.scalar_one_or_none()
                if patient:
                    version_state = {
                        "document": {
                            "doc_id": doc_id,
                            "s3_key": s3_key,
                            "filename": filename,
                            "mime_type": content_type,
                            "size_bytes": size_bytes,
                            "doc_type": result.get("doc_type"),
                            "doc_format": result.get("doc_format"),
                            "extracted_text": result.get("raw_text", ""),
                            "confidence": result.get("confidence", 0.0),
                        }
                    }
                    version = await _mint_version(
                        db=db,
                        patient=patient,
                        doctor_id=uuid.UUID(doctor_id),
                        state=version_state,
                        edit_type="ocr",
                        author=f"doctor:{doctor_id}",
                        summary=f"Document uploaded: {filename} ({result.get('doc_type', 'unknown')})",
                        tags=["document", result.get("doc_type", "general")],
                        clinical_significance=0.5,
                    )
                    version_id = str(version.id)

                    # Fire-and-forget: notify patient + queue vector indexing.
                    try:
                        patient_name = "Patient"
                        if patient.head_version and patient.head_version.state_jsonb:
                            patient_name = patient.head_version.state_jsonb.get("demographics", {}).get(
                                "name", "Patient"
                            )
                        await _dispatch_notification(
                            db,
                            event_type="report_available",
                            patient_id=patient.id,
                            doctor_id=uuid.UUID(doctor_id),
                            meta={"resource_type": "document", "resource_id": version_id},
                            patient_name=patient_name,
                            report_type=result.get("doc_type", "document").replace("_", " ").title(),
                        )
                    except Exception as exc:
                        logger.warning("parse_document_job: notify failed: %s", exc)

                    # Enqueue P1.9 indexing (runs after this job finishes).
                    try:
                        await enqueue_index_version(
                            version_id=version_id,
                            patient_id=str(patient.id),
                            doctor_id=doctor_id,
                        )
                    except Exception as exc:
                        logger.warning("parse_document_job: index enqueue failed: %s", exc)

                    # Audit entry (batched via Redis, see P2.27).
                    try:
                        audit = AuditLog(
                            doctor_id=uuid.UUID(doctor_id),
                            patient_id=patient.id,
                            actor=f"doctor:{doctor_id}",
                            action="write",
                            resource_type="document",
                            payload_jsonb={
                                "doc_id": doc_id,
                                "filename": filename,
                                "size": size_bytes,
                                "mime_type": content_type,
                                "doc_type": result.get("doc_type"),
                                "confidence": result.get("confidence"),
                            },
                        )
                        db.add(audit)
                        await db.commit()
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("parse_document_job: attach to patient failed: %s", exc)

    return {
        "status": "done",
        "doc_id": doc_id,
        "version_id": version_id,
        "doc_type": result.get("doc_type"),
        "doc_format": result.get("doc_format"),
        "confidence": result.get("confidence"),
        "text_length": len(result.get("raw_text", "")),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  P1.9 — Vector indexing (was FastAPI BackgroundTasks — non-persistent)
# ═══════════════════════════════════════════════════════════════════════════


async def enqueue_index_version(version_id: str, patient_id: str, doctor_id: str) -> Optional[str]:
    pool = await get_arq_pool()
    if pool is None:
        return None
    try:
        job = await pool.enqueue_job(
            "index_version_job",
            version_id=version_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
        )
        return job.job_id if job else None
    except Exception as exc:
        logger.warning("enqueue_index_version failed: %s", exc)
        return None


async def index_version_job(ctx, version_id: str, patient_id: str, doctor_id: str) -> Dict[str, Any]:
    """Worker: run MedCPT + BGE-M3 + BiomedCLIP embeddings and upsert to
    Qdrant. Runs in the arq worker so the doctor's PATCH /patients/{id}/fields
    returns immediately."""
    from app.database import async_session_maker
    from app.models import Patient, PatientVersion
    from app.services.indexer import index_version

    try:
        async with async_session_maker() as db:
            v_row = await db.execute(
                __import__("sqlalchemy").select(PatientVersion).where(PatientVersion.id == uuid.UUID(version_id))
            )
            version = v_row.scalar_one_or_none()
            if not version:
                return {"status": "error", "error": "version_not_found"}

            p_row = await db.execute(
                __import__("sqlalchemy").select(Patient).where(Patient.id == uuid.UUID(patient_id))
            )
            patient = p_row.scalar_one_or_none()
            if not patient:
                return {"status": "error", "error": "patient_not_found"}

            await index_version(db, version, patient, uuid.UUID(doctor_id))
            return {"status": "indexed", "version_id": version_id}
    except Exception as exc:
        logger.error("index_version_job failed: %s", exc)
        return {"status": "error", "error": str(exc)[:400]}


# ═══════════════════════════════════════════════════════════════════════════
#  P2.23 — Weekly report generation
# ═══════════════════════════════════════════════════════════════════════════


async def enqueue_weekly_report(
    patient_id: str,
    layout: str,
    days: int,
    doctor_id: str,
    include_ai_summary: bool = False,
) -> Optional[str]:
    pool = await get_arq_pool()
    if pool is None:
        return None
    try:
        job = await pool.enqueue_job(
            "generate_weekly_report_job",
            patient_id=patient_id,
            layout=layout,
            days=days,
            doctor_id=doctor_id,
            include_ai_summary=include_ai_summary,
        )
        return job.job_id if job else None
    except Exception as exc:
        logger.warning("enqueue_weekly_report failed: %s", exc)
        return None


async def generate_weekly_report_job(
    ctx,
    patient_id: str,
    layout: str,
    days: int,
    doctor_id: str,
    include_ai_summary: bool,
) -> Dict[str, Any]:
    from app.database import async_session_maker
    from app.services.weekly_report import WeeklyReportService

    try:
        svc = WeeklyReportService()
        async with async_session_maker() as db:
            report = await svc.generate_report(db, uuid.UUID(patient_id), layout, days)
            if include_ai_summary:
                summary = await svc.generate_ai_summary(report)
                report["ai_summary"] = summary
            return {"status": "done", "report": report}
    except Exception as exc:
        logger.error("generate_weekly_report_job failed: %s", exc)
        return {"status": "error", "error": str(exc)[:400]}


# ═══════════════════════════════════════════════════════════════════════════
#  P2.24 — ORB image comparison
# ═══════════════════════════════════════════════════════════════════════════


async def enqueue_compare_images(
    doctor_id: str,
    patient_id: str,
    image_prev_path: str,
    image_curr_path: str,
) -> Optional[str]:
    pool = await get_arq_pool()
    if pool is None:
        return None
    try:
        job = await pool.enqueue_job(
            "compare_images_job",
            doctor_id=doctor_id,
            patient_id=patient_id,
            image_prev_path=image_prev_path,
            image_curr_path=image_curr_path,
        )
        return job.job_id if job else None
    except Exception as exc:
        logger.warning("enqueue_compare_images failed: %s", exc)
        return None


async def compare_images_job(
    ctx,
    doctor_id: str,
    patient_id: str,
    image_prev_path: str,
    image_curr_path: str,
) -> Dict[str, Any]:
    from app.services.image_registration import image_registration_service

    try:
        result = await image_registration_service.compare(
            image_prev_path=image_prev_path,
            image_curr_path=image_curr_path,
            patient_id=patient_id,
        )
        return {"status": "done", "result": result}
    except Exception as exc:
        logger.error("compare_images_job failed: %s", exc)
        return {"status": "error", "error": str(exc)[:400]}


# ═══════════════════════════════════════════════════════════════════════════
#  P2.25 — pg_dump backup (blocking subprocess wrapped in to_thread)
# ═══════════════════════════════════════════════════════════════════════════


async def enqueue_backup(doctor_id: str) -> Optional[str]:
    pool = await get_arq_pool()
    if pool is None:
        return None
    try:
        job = await pool.enqueue_job("backup_database_job", doctor_id=doctor_id)
        return job.job_id if job else None
    except Exception as exc:
        logger.warning("enqueue_backup failed: %s", exc)
        return None


async def backup_database_job(ctx, doctor_id: str) -> Dict[str, Any]:
    """Runs pg_dump inside asyncio.to_thread so the worker's event loop isn't
    frozen for the 5-30 min the dump takes."""
    import asyncio as _asyncio

    from app.routers.backup import _run_pg_dump_and_upload  # sync helper (see backup.py)

    try:
        result = await _asyncio.to_thread(_run_pg_dump_and_upload, doctor_id)
        return {"status": "done", **result}
    except Exception as exc:
        logger.error("backup_database_job failed: %s", exc)
        return {"status": "error", "error": str(exc)[:400]}


# ═══════════════════════════════════════════════════════════════════════════
#  P2.27 — Audit-log flush (batched from Redis)
# ═══════════════════════════════════════════════════════════════════════════

AUDIT_LOG_REDIS_KEY = "audit_log_queue"


async def flush_audit_log_job(ctx) -> Dict[str, Any]:
    """Cron job — drains the audit_log_queue Redis list and batch-inserts
    into audit_log. Runs every 5s. The middleware `RPUSH`es entries during
    request handling; here we `LPOP` and INSERT in a single transaction so
    per-request latency isn't hit by the audit write."""
    import json as _json

    from app.database import async_session_maker
    from app.models import AuditLog
    from app.services.redis import redis_service

    try:
        client = await redis_service.connect()
        # Pop up to 500 entries per tick to bound memory + Postgres batch size.
        entries: list[dict] = []
        for _ in range(500):
            raw = await client.lpop(AUDIT_LOG_REDIS_KEY)
            if raw is None:
                break
            try:
                entries.append(_json.loads(raw))
            except Exception:
                continue

        if not entries:
            return {"status": "empty"}

        async with async_session_maker() as db:
            for e in entries:
                try:
                    row = AuditLog(
                        doctor_id=uuid.UUID(e["doctor_id"]) if e.get("doctor_id") else None,
                        patient_id=uuid.UUID(e["patient_id"]) if e.get("patient_id") else None,
                        actor=e.get("actor"),
                        action=e.get("action"),
                        resource_type=e.get("resource_type"),
                        resource_id=uuid.UUID(e["resource_id"]) if e.get("resource_id") else None,
                        payload_jsonb=e.get("payload_jsonb") or {},
                    )
                    db.add(row)
                except Exception:
                    continue
            await db.commit()
        return {"status": "flushed", "n": len(entries)}
    except Exception as exc:
        logger.error("flush_audit_log_job failed: %s", exc)
        return {"status": "error", "error": str(exc)[:400]}


# ═══════════════════════════════════════════════════════════════════════════
#  Registered worker functions — imported by email_queue.WorkerSettings
# ═══════════════════════════════════════════════════════════════════════════

ALL_JOB_FUNCTIONS = [
    parse_document_job,
    index_version_job,
    generate_weekly_report_job,
    compare_images_job,
    backup_database_job,
    flush_audit_log_job,
]
