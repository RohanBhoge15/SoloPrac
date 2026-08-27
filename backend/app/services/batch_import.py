"""Batch Import — Split multi-page prescription PDF into individual PatientVersions.

When a doctor uploads a PDF containing N prescription pages (oldest → newest),
this service:
  1. Splits the PDF into N individual page files (PyPDF2)
  2. Runs the OCR pipeline on each page independently
  3. Creates a chain of PatientVersions where page[i] → version[i+1],
     linked via parent_version_id so the agent sees a proper timeline
  4. Indexes each version in Qdrant for RAG retrieval

Usage:
    from app.services.batch_import import batch_import_prescription_pdf

    result = await batch_import_prescription_pdf(
        pdf_path="/tmp/upload.pdf",
        doctor_id=uuid,
        patient_id=uuid,
        db=async_session,
    )
    # -> {"pages_processed": 5, "versions": [...], "errors": []}
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import PyPDF2
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Patient
from app.routers.patients import _mint_version
from app.services.document_parser import ParserRouter
from app.services.indexer import index_version
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

# Max pages in a single batch upload (sanity limit)
MAX_PAGES = 50
# Min text length to consider a page "successfully parsed"
MIN_VALID_TEXT_LENGTH = 10


async def batch_import_prescription_pdf(
    pdf_bytes: bytes,
    doctor_id: UUID,
    patient_id: UUID,
    db: AsyncSession,
    filename: str = "prescription.pdf",
) -> Dict[str, Any]:
    """Split a multi-page prescription PDF into a chain of PatientVersions.

    Args:
        pdf_bytes: Raw PDF file content.
        doctor_id: The authenticated doctor's UUID.
        patient_id: The target patient's UUID (must belong to doctor).
        db: Async DB session (caller owns commit).
        filename: Original filename (for audit logging).

    Returns:
        {
            "status": "ok" | "partial" | "error",
            "pages_processed": int,
            "versions": [{"id": str, "version_number": int, "summary": str, "confidence": float}, ...],
            "errors": [str, ...],
            "total_pages": int,
        }
    """
    start = datetime.now(timezone.utc)
    parser = ParserRouter()

    # ── Step 1: Verify patient exists ──
    patient = await db.get(Patient, patient_id)
    if not patient or patient.doctor_id != doctor_id:
        return {
            "status": "error",
            "message": "Patient not found",
            "pages_processed": 0,
            "versions": [],
            "errors": ["Patient not found or not owned by doctor"],
        }

    # ── Step 2: Split PDF into page files ──
    page_paths: List[str] = []
    page_temp_dir: str | None = None
    try:
        page_temp_dir = tempfile.mkdtemp(prefix="batch_import_")
        page_paths = _split_pdf_pages(pdf_bytes, page_temp_dir, filename)
    except Exception as exc:
        logger.error("PDF split failed: %s", exc)
        return {
            "status": "error",
            "message": f"PDF split failed: {exc}",
            "pages_processed": 0,
            "versions": [],
            "errors": [str(exc)],
        }

    total_pages = len(page_paths)
    if total_pages == 0:
        return {
            "status": "error",
            "message": "PDF has no pages",
            "pages_processed": 0,
            "versions": [],
            "errors": ["Empty PDF"],
        }

    if total_pages > MAX_PAGES:
        logger.warning("PDF has %d pages, truncating to %d", total_pages, MAX_PAGES)
        # Clean up excess temp files
        for p in page_paths[MAX_PAGES:]:
            _safe_unlink(p)
        page_paths = page_paths[:MAX_PAGES]

    # ── Step 3: Upload full PDF to S3 for archival ──
    s3_key = f"batch_import/{doctor_id}/{patient_id}/{uuid.uuid4()}.pdf"
    try:
        await storage_service.upload_file(
            file_data=pdf_bytes,
            bucket_type="documents",
            key=s3_key,
            content_type="application/pdf",
        )
    except Exception as exc:
        logger.warning("S3 archival upload failed (non-blocking): %s", exc)
        s3_key = ""

    # ── Step 4: Process each page oldest→newest (page index = chronological order) ──
    versions_created: List[Dict[str, Any]] = []
    errors: List[str] = []
    parent_version_id: Optional[uuid.UUID] = None

    for page_idx, page_path in enumerate(page_paths):
        page_num = page_idx + 1
        try:
            # Parse page via existing OCR pipeline
            parse_result = await parser.parse(page_path, "application/pdf")

            if parse_result.get("status") == "error":
                text = parse_result.get("raw_text", "")
                if len(text.strip()) < MIN_VALID_TEXT_LENGTH:
                    errors.append(f"Page {page_num}: No text extracted")
                    logger.warning("Page %d: no text extracted (%s)", page_num, parse_result.get("message", ""))
                    # Still create a version with what we have (better than skipping)
            else:
                text = parse_result.get("raw_text", "")

            doc_type = parse_result.get("doc_type", "prescription")
            confidence = parse_result.get("confidence", 0.0)
            raw_text = parse_result.get("raw_text", "")
            structured = parse_result.get("structured", {})

            # Build state_jsonb for this page
            state = {
                "demographics": {
                    "source": "batch_import",
                    "import_batch": s3_key or f"batch_{uuid.uuid4().hex[:12]}",
                },
                "clinical": {
                    "documents": [
                        {
                            "page_number": page_num,
                            "doc_type": doc_type,
                            "confidence": confidence,
                            "extracted_text": raw_text[:5000],  # cap to avoid oversized versions
                            "structured": structured,
                            "parsed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                },
            }

            # If this is a prescription with medication data, promote it
            if doc_type == "prescription" and structured.get("medications_found"):
                state["clinical"]["medications"] = [
                    {"drug": m, "source": f"import_page_{page_num}"} for m in structured["medications_found"]
                ]
            if structured.get("dates_mentioned"):
                state["clinical"]["dates_mentioned"] = structured["dates_mentioned"]

            # Mint version with chain linkage
            version = await _mint_version(
                db=db,
                patient=patient,
                doctor_id=doctor_id,
                state=state,
                edit_type="ocr",
                author=f"doctor:{doctor_id}",
                parent_version_id=parent_version_id,
                summary=f"Imported prescription page {page_num}/{total_pages} ({doc_type}, conf={confidence:.2f})",
                tags=["import", "prescription", doc_type, f"page_{page_num}"],
                clinical_significance=max(0.1, confidence * 0.6),  # scale by OCR confidence
            )

            # Update chain pointer for next page
            parent_version_id = version.id

            # Index in Qdrant (fire-and-forget; non-critical path)
            try:
                await index_version(db, version, patient, doctor_id)
            except Exception as exc:
                logger.warning("Qdrant indexing failed for page %d version %s: %s", page_num, version.id, exc)

            versions_created.append(
                {
                    "id": str(version.id),
                    "version_number": version.version_number,
                    "page_number": page_num,
                    "summary": version.summary,
                    "doc_type": doc_type,
                    "confidence": confidence,
                    "parent_version_id": str(parent_version_id) if page_num > 1 else None,
                }
            )

            logger.info(
                "Batch import page %d/%d → version v%d (conf=%.2f, type=%s)",
                page_num,
                total_pages,
                version.version_number,
                confidence,
                doc_type,
            )

        except Exception as exc:
            error_msg = f"Page {page_num}: {exc}"
            errors.append(error_msg)
            logger.error("Batch import failed on page %d: %s", page_num, exc)
            continue
        finally:
            _safe_unlink(page_path)

    # ── Step 5: Cleanup temp directory ──
    if page_temp_dir and os.path.isdir(page_temp_dir):
        try:
            import shutil

            shutil.rmtree(page_temp_dir, ignore_errors=True)
        except Exception:
            pass

    # ── Step 6: Audit log ──
    elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    try:
        audit = AuditLog(
            doctor_id=doctor_id,
            patient_id=patient_id,
            actor=f"doctor:{doctor_id}",
            action="write",
            resource_type="batch_import",
            payload_jsonb={
                "pages_total": total_pages,
                "pages_processed": len(versions_created),
                "errors": errors[:10],  # cap error list
                "took_ms": round(elapsed_ms, 1),
                "s3_key": s3_key,
                "filename": filename,
            },
        )
        db.add(audit)
    except Exception as exc:
        logger.warning("Batch import audit log failed (non-blocking): %s", exc)

    status = "ok" if not errors else "partial"
    return {
        "status": status,
        "pages_processed": len(versions_created),
        "total_pages": total_pages,
        "versions": versions_created,
        "errors": errors[:20],  # cap for response
        "took_ms": round(elapsed_ms, 1),
        "s3_archived": bool(s3_key),
    }


def _split_pdf_pages(pdf_bytes: bytes, output_dir: str, filename: str) -> List[str]:
    """Split a PDF into individual page files using PyPDF2.

    Args:
        pdf_bytes: Raw PDF content.
        output_dir: Directory to write page files.
        filename: Original filename (for naming temp pages).

    Returns:
        List of absolute paths to page PDF files, in page order (page 0 = oldest).
    """
    page_paths: List[str] = []
    base = os.path.splitext(os.path.basename(filename))[0]

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        reader = PyPDF2.PdfReader(tmp_path)
        num_pages = len(reader.pages)

        for i in range(num_pages):
            writer = PyPDF2.PdfWriter()
            writer.add_page(reader.pages[i])
            page_filename = f"{base}_page_{i + 1:03d}.pdf"
            page_path = os.path.join(output_dir, page_filename)

            with open(page_path, "wb") as f:
                writer.write(f)

            page_paths.append(page_path)

        logger.info("Split PDF into %d pages in %s", num_pages, output_dir)
    finally:
        _safe_unlink(tmp_path)

    return page_paths


def _safe_unlink(path: str) -> None:
    """Remove a file, ignoring errors."""
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass
