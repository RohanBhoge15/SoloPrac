"""Image Router — Upload, embed, and search patient images via NV-CLIP + Qdrant.

Endpoints:
  POST /patients/{id}/images — Upload one or more images (validated for size/type)
  GET  /patients/{id}/images — List images/comparisons for a patient
  POST /patients/{id}/images/search — Search for similar images by image upload

Validation pipeline:
  1. File type check (JPG, PNG, WEBP only)
  2. File size check (max 25MB each, max 5 per request)
  3. Magic byte verification (extension ≠ content)
  4. NV-CLIP embedding via NIM
  5. Upsert to Qdrant with patient + doctor isolation
"""

from __future__ import annotations

import uuid
import os
import logging
import imghdr
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Patient, ImageComparison
from app.services.embeddings import embedding_service
from app.services.qdrant import qdrant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}/images", tags=["images"])

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Magic bytes for validation
MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",
}

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
MAX_FILES_PER_REQUEST = 5

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "images")


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _check_magic_bytes(content: bytes) -> Optional[str]:
    """Verify file content matches expected magic bytes."""
    for magic, mime in MAGIC_BYTES.items():
        if content.startswith(magic):
            return mime
    return None


async def _validate_image(file: UploadFile) -> bytes:
    """Validate a single uploaded image file."""
    # Check MIME type
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

    # Magic byte verification
    detected_mime = _check_magic_bytes(content)
    if not detected_mime:
        raise HTTPException(status_code=400, detail="File content does not match any allowed image type")

    # Cross-check extension vs content
    ext = os.path.splitext(file.filename or "")[1].lower()
    expected_ext = ALLOWED_MIME_TYPES.get(detected_mime, "")
    if ext and ext != expected_ext:
        logger.warning("Extension mismatch: %s content but %s extension", detected_mime, ext)

    return content


@router.post("/")
async def upload_images(
    patient_id: uuid.UUID,
    files: List[UploadFile] = File(..., description="Image files (max 5)"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more patient images. Validates, embeds, and indexes in Qdrant."""
    # Verify patient ownership
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_REQUEST} files per request")

    _ensure_upload_dir()
    uploaded = []

    for file in files:
        try:
            content = await _validate_image(file)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Validation failed for {file.filename}: {exc}")

        # Save to disk
        image_id = uuid.uuid4()
        ext = ALLOWED_MIME_TYPES.get(file.content_type or "", ".jpg")
        filename = f"{image_id}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(content)

        # Generate NV-CLIP embedding via NIM
        try:
            embedding = await embedding_service.encode_nvclip_image(filepath)
        except Exception as exc:
            logger.warning("NV-CLIP embedding failed for %s: %s (proceeding without)", filename, exc)
            embedding = []

        # Upsert to Qdrant
        point_id = None
        if embedding:
            try:
                point_id = await qdrant_service.upsert_version({
                    "version_id": str(image_id),
                    "patient_id": str(patient_id),
                    "doctor_id": str(doctor.id),
                    "version_number": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "modality": "image",
                    "image_embedding": embedding,
                    "medical_text_embedding": [],
                    "hybrid_embedding": [],
                    "author": f"doctor:{doctor.id}",
                    "edit_type": "manual",
                    "summary": f"Image: {file.filename}",
                    "tags": ["image"],
                    "clinical_significance": 0.3,
                    "version_hash": "",
                })
                logger.info("Indexed image %s to Qdrant (point=%s)", image_id, point_id)
            except Exception as exc:
                logger.error("Qdrant upsert for image %s failed: %s", image_id, exc)

        uploaded.append({
            "image_id": str(image_id),
            "filename": file.filename,
            "size": len(content),
            "mime_type": file.content_type,
            "path": filepath,
            "qdrant_point_id": point_id,
            "had_embedding": len(embedding) > 0,
        })

        # Reset file position for subsequent operations
        await file.seek(0)

    return {
        "status": "ok",
        "patient_id": str(patient_id),
        "uploaded": len(uploaded),
        "images": uploaded,
    }


@router.get("/")
async def list_images(
    patient_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """List all images and comparisons for a patient."""
    # Get comparisons from DB
    result = await db.execute(
        select(ImageComparison)
        .join(Patient, Patient.id == ImageComparison.version_id)
        .where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
        .order_by(ImageComparison.created_at.desc())
    )
    comparisons = result.scalars().all()

    # Get points from Qdrant
    qdrant_versions = []
    try:
        qdrant_versions = await qdrant_service.get_patient_versions(
            patient_id=str(patient_id),
            doctor_id=str(doctor.id),
            limit=50,
        )
    except Exception as exc:
        logger.warning("Qdrant query failed for patient images: %s", exc)

    # Filter to image-modality only
    image_points = [
        p for p in qdrant_versions
        if p.payload.get("modality") == "image"
    ]

    return {
        "patient_id": str(patient_id),
        "comparisons": [
            {
                "id": str(c.id),
                "current_image_path": c.current_image_path,
                "matched_image_path": c.matched_image_path,
                "area_change_pct": c.area_change_pct,
                "edge_convergence_score": c.edge_convergence_score,
                "color_histogram_shift": c.color_histogram_shift,
                "overlay_path": c.overlay_path,
                "clinical_summary": c.clinical_summary,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comparisons
        ],
        "images_from_qdrant": [
            {
                "point_id": str(p.id),
                "version_id": p.payload.get("version_id"),
                "summary": p.payload.get("summary"),
                "timestamp": p.payload.get("timestamp"),
                "score": p.score if hasattr(p, "score") else None,
            }
            for p in image_points
        ],
    }


@router.post("/search")
async def search_similar_images(
    patient_id: uuid.UUID,
    file: UploadFile = File(..., description="Image to search similar matches for"),
    limit: int = Query(10, ge=1, le=50),
    doctor=Depends(get_current_doctor),
):
    """Upload an image and find visually similar images from the patient's history."""
    # Validate and read
    try:
        content = await _validate_image(file)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Validation failed: {exc}")

    # Save temp file for embedding
    _ensure_upload_dir()
    temp_id = uuid.uuid4()
    temp_path = os.path.join(UPLOAD_DIR, f"search_{temp_id}.jpg")
    with open(temp_path, "wb") as f:
        f.write(content)

    # Encode with NV-CLIP
    try:
        query_vector = await embedding_service.encode_nvclip_image(temp_path)
    except Exception as exc:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"NV-CLIP encoding failed: {exc}")

    # Clean up temp file
    os.remove(temp_path)

    if not query_vector:
        raise HTTPException(status_code=500, detail="NV-CLIP produced empty embedding")

    # Search Qdrant
    try:
        results = await qdrant_service.search_image_similar(
            patient_id=str(patient_id),
            doctor_id=str(doctor.id),
            image_vector=query_vector,
            limit=limit,
            score_threshold=0.3,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Similarity search failed: {exc}")

    return {
        "patient_id": str(patient_id),
        "query_image": file.filename,
        "results": [
            {
                "point_id": str(r.id),
                "version_id": r.payload.get("version_id"),
                "summary": r.payload.get("summary"),
                "timestamp": r.payload.get("timestamp"),
                "score": r.score,
            }
            for r in results
        ],
    }
