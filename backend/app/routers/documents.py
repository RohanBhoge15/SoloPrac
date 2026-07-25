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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_doctor
from uuid import UUID
from app.models import Doctor, Patient, PatientVersion, AuditLog
from app.services.document_parser import parser_router, DocType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "documents")

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


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/parse")
async def parse_document(
    file: UploadFile = File(..., description="Document to parse (PDF, JPG, PNG, WebP)"),
    patient_id: Optional[str] = Form(None, description="Optional patient ID to associate"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
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

    # Save file
    _ensure_upload_dir()
    doc_id = uuid.uuid4()
    ext = ALLOWED_MIME_TYPES.get(file.content_type or "", ".bin")
    filename = f"{doc_id}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    _record_upload(doctor_id_str)

    # Parse document
    try:
        result = await parser_router.parse(filepath, file.content_type or "application/octet-stream")
    except Exception as exc:
        logger.error("Document parsing failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Document parsing failed: {str(exc)[:200]}")

    # If patient_id provided, check ownership
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
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
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

    # Check if the parsed document file exists
    # In a real app, the parsed content would be stored and retrievable by doc_id
    filepath = os.path.join(UPLOAD_DIR, f"{doc_id}.*")
    import glob
    matches = glob.glob(filepath)
    if not matches:
        raise HTTPException(status_code=404, detail="Document not found")

    # For now, create a version with a note about the document
    # Full implementation will replay the parsed content
    from app.routers.patients import _mint_version

    state = {
        "document_reference": {
            "doc_id": doc_id,
            "note": "Document processed and associated with patient record",
        }
    }

    version = await _mint_version(
        db=db,
        patient=patient,
        doctor_id=doctor.id,
        state=state,
        edit_type="ocr",
        author=f"doctor:{doctor.id}",
        summary=f"Document {doc_id[:8]}... added to patient record",
        tags=["document", "ocr"],
        clinical_significance=0.5,
    )

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


