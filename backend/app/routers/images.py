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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Patient, PatientVersion, ImageComparison, AuditLog
from app.services.embeddings import embedding_service
from app.services.qdrant import qdrant_service
from app.services.image_registration import image_registration_service
from app.services.storage import storage_service
from app.routers.patients import _mint_version

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}/images", tags=["images"])


async def _background_analyze_image(
    version_id: str, patient_id: str, doctor_id: str,
    s3_key: str, image_type: str,
):
    """Background task: analyze image with MedGemma and update version + Qdrant."""
    try:
        import uuid as _uuid
        from app.database import async_session_maker
        from app.agents.tools import _analyze_with_medgemma, _analyze_with_groq
        from app.services.storage import storage_service

        # Download image from S3 to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            image_bytes = await storage_service.download_file(s3_key)
            if not image_bytes:
                return
            with open(tmp_path, "wb") as f:
                f.write(image_bytes)

            # Generate base64
            import base64
            with open(tmp_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        finally:
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # Analyze with MedGemma (all image types now go local)
        result = await _analyze_with_medgemma(image_b64, image_type)

        if result.get("status") != "ok":
            # Fallback to Groq for non-radiology if MedGemma fails
            result = await _analyze_with_groq(image_b64, image_type)

        analysis = result.get("analysis", "")
        if not analysis:
            return

        # Truncate to crisp 1-2 line summary
        summary_text = analysis.split("\n")[0][:200]

        # Update version state_jsonb
        async with async_session_maker() as db:
            from sqlalchemy import update as sql_update
            from app.models import PatientVersion
            from app.services.qdrant import qdrant_service

            result = await db.execute(
                select(PatientVersion).where(PatientVersion.id == _uuid.UUID(version_id))
            )
            version = result.scalar_one_or_none()
            if not version:
                return

            state = dict(version.state_jsonb or {})
            if "image" not in state:
                state["image"] = {}
            state["image"]["clinical_summary"] = summary_text
            state["image"]["analyzed_by"] = result.get("model", "medgemma")

            version.state_jsonb = state
            version.summary = summary_text[:120]
            await db.commit()

        logger.info("Background image analysis complete for version %s: %s", version_id, summary_text[:50])

    except Exception as exc:
        logger.warning("Background image analysis failed for version %s: %s", version_id, exc)

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
    background_tasks: BackgroundTasks = None,
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

    uploaded = []

    for file in files:
        try:
            content = await _validate_image(file)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Validation failed for {file.filename}: {exc}")

        # Upload to S3
        image_id = uuid.uuid4()
        ext = ALLOWED_MIME_TYPES.get(file.content_type or "", ".jpg")
        s3_key = f"images/{doctor.id}/{patient_id}/{image_id}{ext}"
        
        try:
            await storage_service.upload_file(
                file_data=content,
                bucket_type="images",
                key=s3_key,
                content_type=file.content_type,
            )
        except Exception as exc:
            logger.error("S3 upload failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Image upload failed: {str(exc)[:200]}")

        # Generate BiomedCLIP embedding (local) — use temp file for encoder
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            embedding = await embedding_service.encode_biomedclip_image(tmp_path)
        except Exception as exc:
            logger.warning("BiomedCLIP embedding failed for %s: %s (proceeding without)", file.filename, exc)
            embedding = []
        finally:
            os.unlink(tmp_path)

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
                    "s3_key": s3_key,
                })
                logger.info("Indexed image %s to Qdrant (point=%s)", image_id, point_id)
            except Exception as exc:
                logger.error("Qdrant upsert for image %s failed: %s", image_id, exc)

        # Auto-create PatientVersion for this image
        try:
            version_state = {
                "image": {
                    "image_id": str(image_id),
                    "s3_key": s3_key,
                    "filename": file.filename,
                    "mime_type": file.content_type,
                    "size_bytes": len(content),
                }
            }
            version = await _mint_version(
                db=db,
                patient=patient,
                doctor_id=doctor.id,
                state=version_state,
                edit_type="manual",
                author=f"doctor:{doctor.id}",
                summary=f"Image uploaded: {file.filename}",
                tags=["image"],
                clinical_significance=0.3,
            )
            logger.info("Created PatientVersion %s for image %s", version.id, image_id)

            # Analyze image in background (MedGemma local, non-blocking)
            if background_tasks:
                background_tasks.add_task(
                    _background_analyze_image,
                    str(version.id),
                    str(patient.id),
                    str(doctor.id),
                    s3_key,
                    "xray" if "xray" in (file.content_type or "").lower() else "other",
                )
        except Exception as exc:
            logger.warning("Failed to create PatientVersion for image %s: %s", image_id, exc)

        uploaded.append({
            "image_id": str(image_id),
            "filename": file.filename,
            "size": len(content),
            "mime_type": file.content_type,
            "s3_key": s3_key,
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
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(content)
        temp_path = tmp.name

    # Encode with BiomedCLIP
    try:
        query_vector = await embedding_service.encode_biomedclip_image(temp_path)
    except Exception as exc:
        os.unlink(temp_path)
        raise HTTPException(status_code=500, detail=f"BiomedCLIP encoding failed: {exc}")

    # Clean up temp file
    os.unlink(temp_path)

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

    # Upload to S3
    curr_image_id = uuid.uuid4()
    ext = ALLOWED_MIME_TYPES.get(file.content_type or "", ".jpg")
    curr_s3_key = f"images/{doctor.id}/{patient_id}/{curr_image_id}{ext}"
    
    try:
        await storage_service.upload_file(
            file_data=content,
            bucket_type="images",
            key=curr_s3_key,
            content_type=file.content_type,
        )
    except Exception as exc:
        logger.error("S3 upload failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(exc)[:200]}")

    # Generate BiomedCLIP embedding for the new image (use temp file)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        curr_tmp_path = tmp.name
    
    try:
        curr_embedding = await embedding_service.encode_biomedclip_image(curr_tmp_path)
    except Exception as exc:
        logger.warning("BiomedCLIP embedding failed: %s", exc)
        curr_embedding = []
    finally:
        os.unlink(curr_tmp_path)

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
        # Try to find the prior image in S3
        prior_s3_key = f"images/{doctor.id}/{patient_id}/{prior_version_id}{ext}"
        try:
            if await storage_service.file_exists("images", prior_s3_key):
                # Download prior image to temp file for comparison
                import tempfile
                prior_bytes = await storage_service.download_file("images", prior_s3_key)
                if prior_bytes:
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        tmp.write(prior_bytes)
                        matched_prior_path = tmp.name
        except Exception as exc:
            logger.warning("Failed to download prior image from S3: %s", exc)

    comparison_id = uuid.uuid4()
    reg_result = None
    overlay_path = None
    warped_path = None
    metrics_data = {}

    if matched_prior_path and os.path.exists(matched_prior_path):
        try:
            reg_result = await image_registration_service.compare(
                image_prev_path=matched_prior_path,
                image_curr_path=curr_tmp_path,
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
                    current_image_path=curr_s3_key,
                    matched_version_id=uuid.UUID(prior_version_id) if prior_version_id else None,
                    matched_image_path=prior_s3_key,
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
        finally:
            # Clean up temp files
            if matched_prior_path and os.path.exists(matched_prior_path):
                os.unlink(matched_prior_path)
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


@router.get("/list", response_model=List[dict])
async def list_patient_images(
    patient_id: uuid.UUID,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Return all image versions for a patient with their clinical summaries."""
    result = await db.execute(
        select(PatientVersion)
        .join(Patient, PatientVersion.patient_id == Patient.id)
        .where(
            PatientVersion.patient_id == patient_id,
            Patient.doctor_id == doctor.id,
            PatientVersion.tags.contains(["image"]),
        )
        .order_by(PatientVersion.created_at.desc())
    )
    versions = result.scalars().all()

    images = []
    for v in versions:
        state = v.state_jsonb or {}
        image_data = state.get("image", {})
        images.append({
            "version_id": str(v.id),
            "version_number": v.version_number,
            "filename": image_data.get("filename", ""),
            "s3_key": image_data.get("s3_key", ""),
            "mime_type": image_data.get("mime_type", ""),
            "clinical_summary": image_data.get("clinical_summary", ""),
            "created_at": v.created_at.isoformat() if v.created_at else None,
        })
    return images


@router.patch("/{version_id}/summary")
async def update_image_summary(
    patient_id: uuid.UUID,
    version_id: uuid.UUID,
    body: dict,
    doctor=Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Update clinical_summary on an existing image version (no new version created)."""
    result = await db.execute(
        select(PatientVersion)
        .join(Patient, PatientVersion.patient_id == Patient.id)
        .where(
            PatientVersion.id == version_id,
            PatientVersion.patient_id == patient_id,
            Patient.doctor_id == doctor.id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    summary = body.get("clinical_summary", "")
    state = dict(version.state_jsonb or {})
    if "image" not in state:
        state["image"] = {}
    state["image"]["clinical_summary"] = summary
    version.state_jsonb = state
    version.summary = summary[:120] if summary else version.summary
    await db.commit()

    return {"status": "ok", "version_id": str(version.id), "clinical_summary": summary}


@router.get("/file")
async def get_image_file(
    patient_id: uuid.UUID,
    s3_key: str = Query(..., description="S3 key of the image"),
    doctor=Depends(get_current_doctor),
):
    """Return a presigned URL for viewing an image from S3."""
    url = await storage_service.generate_presigned_url(s3_key, expires_in=3600)
    if not url:
        raise HTTPException(status_code=404, detail="Image not found")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url, status_code=307)
