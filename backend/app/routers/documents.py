"""Document Router — Upload, parse, and route documents through OCR pipeline.

Endpoints:
  POST /api/v1/documents/parse — Upload + parse a document (auto-detect format)
  GET  /api/v1/documents/types — List supported document types
  POST /api/v1/documents/{id}/save-to-patient — Promote parsed document to patient version
"""

from __future__ import annotations

import uuid
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_doctor
from uuid import UUID
from app.models import Doctor, Patient, PatientVersion, AuditLog
from app.services.document_parser import parser_router, DocType
from app.services.notification_generator import generate_and_dispatch as _dispatch_notification
from app.services.storage import storage_service
from app.routers.patients import _mint_version
from app.services.batch_import import batch_import_prescription_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


async def _background_index_version(version_id: str, patient_id: str, doctor_id: str):
    """Background task: index a PatientVersion into Qdrant after response is sent."""
    try:
        from app.services.indexer import index_version
        from app.database import async_session_maker
        import uuid as _uuid

        async with async_session_maker() as db:
            result = await db.execute(
                select(PatientVersion).where(PatientVersion.id == _uuid.UUID(version_id))
            )
            version = result.scalar_one_or_none()
            if not version:
                return

            result = await db.execute(
                select(Patient).where(Patient.id == _uuid.UUID(patient_id))
            )
            patient = result.scalar_one_or_none()
            if not patient:
                return

            await index_version(db, version, patient, _uuid.UUID(doctor_id))
            logger.info("Background indexing complete for version %s", version_id)
    except Exception as exc:
        logger.warning("Background indexing failed for version %s: %s", version_id, exc)

ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

MAX_UPLOADS_PER_MINUTE = 10


async def _check_upload_rate_limit(doctor_id: str) -> bool:
    """Check if doctor has exceeded upload rate limit (10/min) using Redis."""
    try:
        from app.services.redis import redis_service
        client = await redis_service.connect()
        key = f"rate_limit:upload:{doctor_id}"
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, 60)
        return current <= MAX_UPLOADS_PER_MINUTE
    except Exception:
        # Fallback: allow if Redis is down
        logger.warning("Redis unavailable for rate limiting — allowing upload")
        return True


async def _record_upload(doctor_id: str):
    """Record upload in Redis for rate limiting."""
    try:
        from app.services.redis import redis_service
        client = await redis_service.connect()
        key = f"rate_limit:upload:{doctor_id}"
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, 60)
    except Exception:
        pass


@router.post("/parse")
async def parse_document(
    file: UploadFile = File(..., description="Document to parse (PDF, JPG, PNG, WebP)"),
    patient_id: Optional[str] = Form(None, description="Optional patient ID to associate"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Upload and parse a medical document through the OCR pipeline.

    Auto-detects document format (typed PDF, scanned PDF, handwritten, photo)
    and routes to the correct parser (Docling, Surya, Nanonets-OCR2, MedGemma).
    Also classifies document type (prescription, lab report, etc.).
    """
    doctor_id_str = str(doctor.id)

    # Rate limit check (Dev)
    if not await _check_upload_rate_limit(doctor_id_str):
        raise HTTPException(
            status_code=429,
            detail=f"Upload rate limit exceeded. Max {MAX_UPLOADS_PER_MINUTE} uploads per minute.",
        )

    # Validate MIME type (Dev)
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    # Read content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE})",
        )

    # Check magic bytes (Dev: not just extension)
    magic_match = _check_magic_bytes(content, file.content_type)
    if not magic_match:
        raise HTTPException(
            status_code=400,
            detail="File content does not match expected format (magic byte check failed)",
        )

    # Upload to S3
    doc_id = uuid.uuid4()
    ext = ALLOWED_MIME_TYPES.get(file.content_type or "", ".bin")
    s3_key = f"documents/{doctor_id_str}/{doc_id}{ext}"
    
    try:
        await storage_service.upload_file(
            file_data=content,
            bucket_type="documents",
            key=s3_key,
            content_type=file.content_type,
        )
    except Exception as exc:
        logger.error("S3 upload failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(exc)[:200]}")

    _record_upload(doctor_id_str)

    # Parse document — download from S3 to temp file for parser
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        result = await parser_router.parse(tmp_path, file.content_type or "application/octet-stream")
    except Exception as exc:
        logger.error("Document parsing failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Document parsing failed: {str(exc)[:200]}")
    finally:
        os.unlink(tmp_path)

    # If patient_id provided, check ownership and auto-create version
    patient = None
    if patient_id:
        try:
            pid = uuid.UUID(patient_id)
            pat_result = await db.execute(
                select(Patient).where(Patient.id == pid, Patient.doctor_id == doctor.id)
            )
            patient = pat_result.scalar_one_or_none()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")

    # Auto-create PatientVersion with actual parsed content
    if patient:
        try:
            version_state = {
                "document": {
                    "doc_id": str(doc_id),
                    "s3_key": s3_key,
                    "filename": file.filename,
                    "mime_type": file.content_type,
                    "size_bytes": len(content),
                    "doc_type": result.get("doc_type"),
                    "doc_format": result.get("doc_format"),
                    "extracted_text": result.get("raw_text", ""),
                    "confidence": result.get("confidence", 0.0),
                }
            }
            version = await _mint_version(
                db=db,
                patient=patient,
                doctor_id=doctor.id,
                state=version_state,
                edit_type="ocr",
                author=f"doctor:{doctor.id}",
                summary=f"Document uploaded: {file.filename} ({result.get('doc_type', 'unknown')})",
                tags=["document", result.get("doc_type", "general")],
                clinical_significance=0.5,
            )
            logger.info("Created PatientVersion %s for document %s", version.id, doc_id)

            # Index in background (non-blocking)
            if background_tasks:
                background_tasks.add_task(
                    _background_index_version,
                    str(version.id),
                    str(patient.id),
                    str(doctor.id),
                )

            # ── Dispatch "report_available" notification ──
            try:
                patient_name = "Patient"
                if patient.head_version and patient.head_version.state_jsonb:
                    patient_name = patient.head_version.state_jsonb.get(
                        "demographics", {}
                    ).get("name", "Patient")
                await _dispatch_notification(
                    db,
                    event_type="report_available",
                    patient_id=patient.id,
                    doctor_id=doctor.id,
                    meta={"resource_type": "document", "resource_id": str(version.id)},
                    patient_name=patient_name,
                    report_type=result.get("doc_type", "document").replace("_", " ").title(),
                )
            except Exception as exc:
                logger.warning("Failed to dispatch report_available notification: %s", exc)

        except Exception as exc:
            logger.warning("Failed to create PatientVersion for document %s: %s", doc_id, exc)

    # Log to audit (Dev)
    try:
        audit = AuditLog(
            doctor_id=doctor.id,
            patient_id=UUID(patient_id) if patient_id else None,
            actor=f"doctor:{doctor.id}",
            action="write",
            resource_type="document",
            payload_jsonb={
                "doc_id": str(doc_id),
                "filename": file.filename,
                "size": len(content),
                "mime_type": file.content_type,
                "doc_type": result.get("doc_type"),
                "doc_format": result.get("doc_format"),
                "confidence": result.get("confidence"),
                "text_length": len(result.get("raw_text", "")),
            },
        )
        db.add(audit)
        await db.commit()
    except Exception as exc:
        logger.warning("Document audit log failed (non-blocking): %s", exc)
        await db.rollback()

    response = {
        "status": "ok",
        "doc_id": str(doc_id),
        "filename": file.filename,
        "size": len(content),
    }
    response.update(result)
    return response


@router.post("/{doc_id}/save-to-patient")
async def save_document_to_patient(
    doc_id: str,
    patient_id: str = Form(...),
    edited_text: Optional[str] = Form(None),
    doctor_notes: Optional[str] = Form(None),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Promote a parsed document to a versioned patient record entry."""
    # Verify patient ownership
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid patient_id")

    pat_result = await db.execute(
        select(Patient).where(Patient.id == pid, Patient.doctor_id == doctor.id)
    )
    patient = pat_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Check if the parsed document file exists in S3
    try:
        files = await storage_service.list_files("documents", f"documents/{doctor.id}/{doc_id}")
        if not files:
            raise HTTPException(status_code=404, detail="Document not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("S3 list failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve document")

    # Get the S3 key for the document
    doc_s3_key = files[0] if files else f"documents/{doctor.id}/{doc_id}"

    # Build version state with edited text and doctor notes
    state = {
        "document": {
            "doc_id": doc_id,
            "s3_key": doc_s3_key,
            "filename": doc_id,
            "doc_type": "uploaded_document",
        }
    }
    if edited_text:
        state["document"]["extracted_text"] = edited_text
    if doctor_notes:
        state["document"]["doctor_notes"] = doctor_notes

    summary = f"Document {doc_id[:8]}... added to patient record"
    if doctor_notes:
        summary = doctor_notes[:120]

    version = await _mint_version(
        db=db,
        patient=patient,
        doctor_id=doctor.id,
        state=state,
        edit_type="ocr",
        author=f"doctor:{doctor.id}",
        summary=summary,
        tags=["document", "uploaded"],
        clinical_significance=0.5,
    )

    # Index in background (non-blocking)
    if background_tasks:
        background_tasks.add_task(
            _background_index_version,
            str(version.id),
            str(patient.id),
            str(doctor.id),
        )

    # ── Dispatch "report_available" notification ──
    try:
        patient_name = "Patient"
        if patient.head_version and patient.head_version.state_jsonb:
            patient_name = patient.head_version.state_jsonb.get(
                "demographics", {}
            ).get("name", "Patient")
        await _dispatch_notification(
            db,
            event_type="report_available",
            patient_id=patient.id,
            doctor_id=doctor.id,
            meta={"resource_type": "document", "resource_id": str(version.id)},
            patient_name=patient_name,
            report_type="Document",
        )
    except Exception as exc:
        logger.warning("Failed to dispatch report_available notification: %s", exc)

    return {
        "status": "ok",
        "version_id": str(version.id),
        "version_number": version.version_number,
        "patient_id": patient_id,
    }


@router.get("/types")
async def list_document_types():
    """List supported document types for the parser."""
    return {
        "document_types": [
            {"id": "prescription", "name": "Prescription", "formats": ["typed_pdf", "scanned_pdf", "handwritten"]},
            {"id": "lab_report", "name": "Lab Report", "formats": ["typed_pdf", "scanned_pdf"]},
            {"id": "discharge_summary", "name": "Discharge Summary", "formats": ["typed_pdf", "scanned_pdf"]},
            {"id": "referral_letter", "name": "Referral Letter", "formats": ["typed_pdf", "scanned_pdf", "handwritten"]},
            {"id": "imaging_report", "name": "Imaging Report", "formats": ["typed_pdf", "scanned_pdf"]},
            {"id": "general_document", "name": "General Document", "formats": ["typed_pdf", "scanned_pdf", "photo"]},
        ],
        "accepted_mime_types": list(ALLOWED_MIME_TYPES.keys()),
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "rate_limit_per_minute": MAX_UPLOADS_PER_MINUTE,
    }


@router.get("/{doc_id}/file")
async def get_document_file(
    doc_id: str,
    doctor=Depends(get_current_doctor),
):
    """Get a presigned URL for a document file in S3."""
    try:
        files = await storage_service.list_files("documents", f"documents/{doctor.id}/{doc_id}")
        if not files:
            raise HTTPException(status_code=404, detail="Document not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("S3 list failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve document")

    s3_key = files[0]
    presigned_url = await storage_service.get_presigned_url(s3_key, expires_in=3600)
    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate URL")

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=presigned_url)


@router.get("/avatar/{doctor_id}")
async def get_doctor_avatar(
    doctor_id: str,
):
    """Get a presigned URL for a doctor's profile photo.

    Public endpoint — no auth required (used in patient search results).
    """
    try:
        import uuid as _uuid
        _uuid.UUID(doctor_id)  # validate
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid doctor ID")

    # Try common extensions
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        s3_key = f"avatars/{doctor_id}{ext}"
        try:
            files = await storage_service.list_files("documents", s3_key)
            if files:
                presigned_url = await storage_service.get_presigned_url(files[0], expires_in=3600)
                if presigned_url:
                    return RedirectResponse(url=presigned_url)
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="No profile photo")


# ════════════════════════════════════════════════════════════
# Batch Import — multi-page prescription PDF → version chain
# ════════════════════════════════════════════════════════════

@router.post("/batch-import", status_code=status.HTTP_201_CREATED)
async def batch_import_prescriptions(
    file: UploadFile = File(..., description="Multi-page prescription PDF (oldest→newest)"),
    patient_id: str = Form(..., description="Patient UUID to import into"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Upload a multi-page prescription PDF — each page becomes a version.

    The doctor uploads a single PDF where pages are in chronological order
    (oldest prescription first, newest last). This endpoint:
      1. Splits the PDF into individual pages
      2. OCRs each page through the document parsing pipeline
      3. Creates an immutable PatientVersion chain with proper ordering
      4. Indexes each version in Qdrant for AI retrieval

    Args:
        file: PDF file with prescription pages (oldest → newest order).
        patient_id: UUID of the target patient.

    Returns:
        {
            "status": "ok" | "partial" | "error",
            "total_pages": int,
            "pages_processed": int,
            "versions": [{id, version_number, page_number, summary, doc_type, confidence}],
            "errors": [str, ...],
            "took_ms": float,
        }
    """
    # ── Validate: PDF only ──
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported for batch import")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Magic byte check
    if not content.startswith(b"\x25\x50\x44\x46"):
        raise HTTPException(status_code=400, detail="File content is not a valid PDF")

    # ── Validate patient_id ──
    try:
        pid = UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")

    # Verify patient ownership
    pat_result = await db.execute(
        select(Patient).where(Patient.id == pid, Patient.doctor_id == doctor.id)
    )
    patient = pat_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # ── Run batch import ──
    result = await batch_import_prescription_pdf(
        pdf_bytes=content,
        doctor_id=doctor.id,
        patient_id=pid,
        db=db,
        filename=file.filename or "prescription.pdf",
    )

    if result["status"] == "error" and result["pages_processed"] == 0:
        raise HTTPException(status_code=400, detail=result.get("message", "Import failed"))

    # ── Refresh patient to ensure version chain is visible ──
    await db.refresh(patient)

    return result


# ─── Magic Byte Check (Dev) ─────────────────────────

MAGIC_BYTE_MAP = {
    b"\x25\x50\x44\x46": "application/pdf",  # %PDF
    b"\xff\xd8\xff": "image/jpeg",            # JPEG
    b"\x89\x50\x4e\x47": "image/png",         # PNG
    b"\x52\x49\x46\x46": "image/webp",        # RIFF (WebP)
}


def _check_magic_bytes(content: bytes, declared_mime: str) -> bool:
    """Verify file content matches the declared MIME type using magic bytes."""
    for magic, mime in MAGIC_BYTE_MAP.items():
        if content.startswith(magic):
            return mime == declared_mime
    return False


