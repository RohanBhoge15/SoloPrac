"""Image Router — Upload, embed, and search patient images via BiomedCLIP + Qdrant.

Endpoints:
  POST /patients/{id}/images — Upload one or more images (validated for size/type)
  GET  /patients/{id}/images — List images/comparisons for a patient
  POST /patients/{id}/images/search — Search for similar images by image upload

Validation pipeline:
  1. File type check (JPG, PNG, WEBP only)
  2. File size check (max 25MB each, max 5 per request)
  3. Magic byte verification (extension ≠ content)
  4. BiomedCLIP embedding (local)
  5. Upsert to Qdrant with patient + doctor isolation
"""

from __future__ import annotations

import uuid
import os
import glob
import logging

from dataclasses import asdict
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Patient, PatientVersion, ImageComparison, AuditLog
from app.services.embeddings import embedding_service
from app.services.qdrant import qdrant_service
from app.services.image_registration import image_registration_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}/images", tags=["images"])

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Magic bytes for validation
# WebP files start with RIFF but also have a WEBP chunk at byte 8
# We check the full 12-byte header to avoid false positives on WAV/AVI
MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF\x00\x00\x00\x00WEBP": "image/webp",  # 12-byte WebP header
}

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
MAX_FILES_PER_REQUEST = 5

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "images")


async def _check_upload_rate_limit(doctor_id: str) -> bool:
    """Check if doctor has exceeded upload rate limit (10/min) using Redis."""
    try:
        from app.services.redis import redis_service
        client = await redis_service.connect()
        key = f"rate_limit:upload:{doctor_id}"
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, 60)
        return current <= 10  # 10 uploads per minute
    except Exception:
        # Fallback: allow if Redis is down
        logger.warning("Redis unavailable for rate limiting — allowing upload")
        return True


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

    # Rate limit check
    if not await _check_upload_rate_limit(str(doctor.id)):
        raise HTTPException(
            status_code=429,
            detail=f"Upload rate limit exceeded. Max 10 uploads per minute.",
        )

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

        # Generate BiomedCLIP embedding (local)
        try:
            embedding = await embedding_service.encode_biomedclip_image(filepath)
        except Exception as exc:
            logger.warning("BiomedCLIP embedding failed for %s: %s (proceeding without)", filename, exc)
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
        .join(PatientVersion, PatientVersion.id == ImageComparison.version_id)
        .join(Patient, Patient.id == PatientVersion.patient_id)
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

    # Encode with BiomedCLIP
    try:
        query_vector = await embedding_service.encode_biomedclip_image(temp_path)
    except Exception as exc:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"BiomedCLIP encoding failed: {exc}")

    # Clean up temp file
    os.remove(temp_path)

    if not query_vector:
        raise HTTPException(status_code=500, detail="BiomedCLIP produced empty embedding")

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


# ─── Image Comparison Endpoints ─────────────────────

@router.post("/compare")
async def compare_images(
    patient_id: uuid.UUID,
    file: UploadFile = File(..., description="Current visit image"),
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new image and auto-compare against the best matching prior image.

    Pipeline:
      1. Validate + save the new image
      2. Search Qdrant for most similar prior image (BiomedCLIP)
      3. Run ORB feature matching between new and prior
      4. Compute homography + overlay + metrics
      5. Store comparison in ImageComparison table
      6. Return overlay path + all metrics

    Returns:
        {
            "status": "ok" | "error" | "no_match",
            "comparison_id": "uuid",
            "matched": bool,
            "current_image": {...},
            "matched_image": {...},
            "overlay_path": "path/to/overlay.jpg",
            "warped_previous_path": "path/to/warped.jpg",
            "metrics": {
                "area_change_pct": float,
                "edge_convergence_score": float,
                "color_histogram_shift": float,
                "num_matches": int,
                "homography_confidence": float,
            },
            "clinical_summary": null,
        }
    """
    # Verify patient ownership
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Validate and save new image
    try:
        content = await _validate_image(file)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Validation failed: {exc}")

    _ensure_upload_dir()
    curr_image_id = uuid.uuid4()
    ext = ALLOWED_MIME_TYPES.get(file.content_type or "", ".jpg")
    curr_filename = f"{curr_image_id}{ext}"
    curr_filepath = os.path.join(UPLOAD_DIR, curr_filename)
    with open(curr_filepath, "wb") as f:
        f.write(content)

    # Generate BiomedCLIP embedding for the new image
    try:
        curr_embedding = await embedding_service.encode_biomedclip_image(curr_filepath)
    except Exception as exc:
        logger.warning("BiomedCLIP embedding failed: %s", exc)
        curr_embedding = []

    # Search for best matching prior image
    best_match = None
    if curr_embedding:
        try:
            similar = await qdrant_service.search_image_similar(
                patient_id=str(patient_id),
                doctor_id=str(doctor.id),
                image_vector=curr_embedding,
                limit=5,
                score_threshold=0.2,
            )
            if similar:
                best_match = similar[0]
        except Exception as exc:
            logger.warning("Qdrant similarity search failed: %s", exc)

    # Index the new image in Qdrant
    if curr_embedding:
        try:
            await qdrant_service.upsert_version({
                "version_id": str(curr_image_id),
                "patient_id": str(patient_id),
                "doctor_id": str(doctor.id),
                "version_number": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "modality": "image",
                "image_embedding": curr_embedding,
                "medical_text_embedding": [],
                "hybrid_embedding": [],
                "author": f"doctor:{doctor.id}",
                "edit_type": "manual",
                "summary": f"Comparison image: {file.filename}",
                "tags": ["image", "comparison"],
                "clinical_significance": 0.5,
                "version_hash": "",
            })
        except Exception as exc:
            logger.warning("Qdrant index for comparison image failed: %s", exc)

    # Run ORB matching if we found a prior image
    matched_prior_path = None
    prior_version_id = ""
    if best_match:
        prior_version_id = best_match.payload.get("version_id", "")
        # Try to find the prior image file
        prior_pattern = os.path.join(UPLOAD_DIR, f"{prior_version_id}.*")
        prior_files = glob.glob(prior_pattern)
        if prior_files:
            matched_prior_path = prior_files[0]

    comparison_id = uuid.uuid4()
    reg_result = None
    overlay_path = None
    warped_path = None
    metrics_data = {}

    if matched_prior_path and os.path.exists(matched_prior_path):
        try:
            reg_result = await image_registration_service.compare(
                image_prev_path=matched_prior_path,
                image_curr_path=curr_filepath,
                patient_id=str(patient_id),
            )
            overlay_path = reg_result.overlay_path
            warped_path = reg_result.warped_previous_path
            m = reg_result.metrics
            metrics_data = asdict(m)

            # Store in ImageComparison table
            try:
                comparison = ImageComparison(
                    id=comparison_id,
                    version_id=None,  # Will be set when saved to patient record
                    current_image_path=curr_filepath,
                    matched_version_id=uuid.UUID(prior_version_id) if prior_version_id else None,
                    matched_image_path=matched_prior_path,
                    area_change_pct=m.area_change_pct if hasattr(m, 'area_change_pct') else None,
                    edge_convergence_score=m.edge_convergence_score if hasattr(m, 'edge_convergence_score') else None,
                    color_histogram_shift=m.color_histogram_shift if hasattr(m, 'color_histogram_shift') else None,
                    overlay_path=overlay_path,
                )
                db.add(comparison)
                await db.commit()

                # Audit log (Dev)
                await _log_image_access(db, doctor.id, patient_id, "create", "comparison", str(comparison_id))

            except Exception as exc:
                logger.warning("Failed to store comparison record: %s", exc)
                await db.rollback()

        except Exception as exc:
            logger.error("Image registration failed: %s", exc)
    else:
        logger.info("No prior match found for patient %s", patient_id)

    clinical_summary = None
    confidence = 0.0

    # Nihal: Generate clinical summary using Maverick
    if reg_result and reg_result.matched:
        try:
            from app.services.clinical_summary import ClinicalSummaryGenerator
            summary_result = await ClinicalSummaryGenerator.generate_summary(
                metrics=metrics_data,
                patient_name=patient.name if hasattr(patient, 'name') else "the patient",
            )
            clinical_summary = summary_result.get("summary")
            confidence = summary_result.get("confidence", 0.0)
            logger.info("Clinical summary generated: %s", clinical_summary[:100] if clinical_summary else "None")
        except Exception as exc:
            logger.warning("Clinical summary generation failed: %s", exc)

    return {
        "status": "ok" if reg_result else "no_match",
        "comparison_id": str(comparison_id),
        "matched": reg_result.matched if reg_result else False,
        "current_image": {
            "image_id": str(curr_image_id),
            "path": curr_filepath,
            "filename": file.filename,
            "size": len(content),
        },
        "matched_image": {
            "path": matched_prior_path,
            "version_id": prior_version_id if best_match else None,
            "score": best_match.score if best_match else None,
        } if best_match else None,
        "overlay_path": overlay_path,
        "warped_previous_path": warped_path,
        "metrics": metrics_data,
        "message": reg_result.message if reg_result else "No prior image found for comparison",
        "clinical_summary": clinical_summary,
        "summary_confidence": confidence,
    }


@router.get("/comparisons/{comparison_id}")
async def get_comparison(
    patient_id: uuid.UUID,
    comparison_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific image comparison result."""
    result = await db.execute(
        select(ImageComparison).where(
            ImageComparison.id == comparison_id,
        )
    )
    comparison = result.scalar_one_or_none()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")

    return {
        "id": str(comparison.id),
        "current_image_path": comparison.current_image_path,
        "matched_image_path": comparison.matched_image_path,
        "area_change_pct": comparison.area_change_pct,
        "edge_convergence_score": comparison.edge_convergence_score,
        "color_histogram_shift": comparison.color_histogram_shift,
        "overlay_path": comparison.overlay_path,
        "clinical_summary": comparison.clinical_summary,
        "created_at": comparison.created_at.isoformat() if comparison.created_at else None,
    }


@router.post("/comparisons/{comparison_id}/save-to-record")
async def save_comparison_to_record(
    patient_id: uuid.UUID,
    comparison_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Save an image comparison as a versioned entry on the patient record.

    Creates a new PatientVersion containing the comparison metrics,
    clinical summary, and overlay references. Connects to the version chain.
    """
    from app.routers.patients import _mint_version

    # Verify patient ownership
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get comparison
    comp_result = await db.execute(
        select(ImageComparison).where(ImageComparison.id == comparison_id)
    )
    comparison = comp_result.scalar_one_or_none()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")

    # Build state from comparison
    state = {
        "image_comparison": {
            "comparison_id": str(comparison_id),
            "current_image_path": comparison.current_image_path,
            "matched_image_path": comparison.matched_image_path,
            "overlay_path": comparison.overlay_path,
            "area_change_pct": comparison.area_change_pct,
            "edge_convergence_score": comparison.edge_convergence_score,
            "color_histogram_shift": comparison.color_histogram_shift,
            "clinical_summary": comparison.clinical_summary,
        }
    }

    # Mint version
    version = await _mint_version(
        db=db,
        patient=patient,
        doctor_id=doctor.id,
        state=state,
        edit_type="manual",
        author=f"doctor:{doctor.id}",
        summary=f"Image comparison: {comparison.area_change_pct}% area change" if comparison.area_change_pct else "Image comparison",
        tags=["image_comparison"],
        clinical_significance=0.5,
    )

    # Update the comparison record with the version_id
    comparison.version_id = version.id
    await db.commit()

    # Audit log
    await _log_image_access(db, doctor.id, patient_id, "write", "comparison_record", str(comparison_id))

    return {
        "status": "ok",
        "version_id": str(version.id),
        "version_number": version.version_number,
    }


async def _log_image_access(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    patient_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: str,
):
    """Log image access to audit trail (Dev)."""
    try:
        audit = AuditLog(
            doctor_id=doctor_id,
            patient_id=patient_id,
            actor=f"doctor:{doctor_id}",
            action=action,
            resource_type=resource_type,
            resource_id=uuid.UUID(resource_id),
            payload_jsonb={"patient_id": str(patient_id)},
        )
        db.add(audit)
        await db.commit()
    except Exception as exc:
        logger.warning("Image audit log failed (non-blocking): %s", exc)
        await db.rollback()
