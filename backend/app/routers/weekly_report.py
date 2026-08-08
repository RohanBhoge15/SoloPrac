"""Weekly Report Router — Feature F endpoint.

Endpoints:
  POST /patients/{id}/weekly-report — Generate weekly report
  GET  /weekly-report/layouts — Available layouts
  GET  /weekly-report/likert-study — Likert study design
  GET  /patients/{id}/weekly-report/pdf — Download weekly report as PDF
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient, ReportVerification
from app.services.email_queue import email_queue
from app.services.pdf_generator import pdf_generator
from app.services.storage import storage_service
from app.services.weekly_report import (
    REPORT_LAYOUTS,
    WeeklyReportService,
    build_likert_study,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["weekly_report"])


@router.post("/patients/{patient_id}/weekly-report")
async def generate_weekly_report(
    patient_id: uuid.UUID,
    layout: str = Query("clinical", description=f"Layout: {REPORT_LAYOUTS}"),
    days: int = Query(7, ge=1, le=90),
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Generate a weekly report for a patient."""
    if layout not in REPORT_LAYOUTS:
        raise HTTPException(status_code=400, detail=f"Invalid layout. Choose from: {REPORT_LAYOUTS}")

    # Verify patient belongs to doctor
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    service = WeeklyReportService()
    report = await service.generate_report(db, patient_id, layout, days)
    return report


@router.get("/weekly-report/layouts")
async def get_available_layouts():
    """Get available report layouts."""
    return {
        "layouts": REPORT_LAYOUTS,
        "descriptions": {
            "executive": "Compact summary — key findings only, for quick review",
            "clinical": "Full clinical detail — all metrics, grouped by significance tier",
            "family_friendly": "Plain language — no jargon, for patient sharing",
        },
    }


@router.get("/weekly-report/likert-study")
async def get_likert_study_design(
    doctors: int = Query(5, ge=1, le=20),
    reports_per_doctor: int = Query(3, ge=1, le=10),
):
    """Get the Likert rating study design for Feature F evaluation."""
    return build_likert_study(doctors=doctors, reports_per_doctor=reports_per_doctor)


@router.post("/weekly-report/{patient_id}/ai-summary")
async def generate_report_ai_summary(
    patient_id: uuid.UUID,
    layout: str = Query("clinical"),
    days: int = Query(7, ge=1, le=90),
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Generate a weekly report with AI narrative summary."""
    # Verify patient belongs to doctor
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    service = WeeklyReportService()
    report = await service.generate_report(db, patient_id, layout, days)
    summary = await service.generate_ai_summary(report)
    return {"report": report, "ai_summary": summary}


@router.get("/patients/{patient_id}/weekly-report/pdf")
async def download_weekly_report_pdf(
    patient_id: uuid.UUID,
    layout: str = Query("clinical", description=f"Layout: {REPORT_LAYOUTS}"),
    days: int = Query(7, ge=1, le=90),
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Download weekly report as PDF."""
    if layout not in REPORT_LAYOUTS:
        raise HTTPException(status_code=400, detail=f"Invalid layout. Choose from: {REPORT_LAYOUTS}")

    # Verify patient belongs to doctor
    result = await db.execute(select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Generate the report
    service = WeeklyReportService()
    report = await service.generate_report(db, patient_id, layout, days)

    if report.get("error"):
        raise HTTPException(status_code=404, detail=report.get("error"))

    # Get patient info for the PDF
    patient_name = report.get("patient_name", f"Patient {str(patient_id)[:8]}")

    # Generate QR verification code
    verification_code = f"WR-{uuid.uuid4().hex[:8].upper()}-{datetime.now(timezone.utc).strftime('%Y%m')}"
    verify_url = f"http://{app_settings.DOMAIN or 'localhost'}:{app_settings.PORT}/api/v1/weekly-report/verify/{verification_code}"

    # Store verification code in DB
    try:
        from app.models import ReportVerification

        rv = ReportVerification(
            id=uuid.uuid4(),
            patient_id=patient_id,
            doctor_id=doctor.id,
            verification_code=verification_code,
            report_type="weekly_report",
        )
        db.add(rv)
        await db.flush()
    except Exception as exc:
        logger.warning("Failed to store report verification code: %s", exc)

    # Attempt to generate a QR code image path
    qr_data_uri = ""
    try:
        from app.services.pdf_security import PDFSecurityService

        pss = PDFSecurityService()
        qr_path = await pss.generate_qr_code(verify_url, size=80)
        # Embed it as a data URI or file path for the Jinja template
        import base64

        with open(qr_path, "rb") as f:
            qr_b64 = base64.b64encode(f.read()).decode()
        qr_data_uri = f"data:image/png;base64,{qr_b64}"
        # Clean up
        import os as _os

        try:
            _os.remove(qr_path)
        except OSError:
            pass
    except Exception as exc:
        logger.warning("QR generation failed (non-blocking): %s", exc)
        # Don't clear verify_url — text link still works even if QR image fails
        qr_data_uri = ""

    # Attach QR + verification to the report data so pdf_generator passes it to template
    report["qr_code"] = qr_data_uri
    report["verify_url"] = verify_url

    # Generate PDF
    filename = f"weekly_report_{patient_id}_{layout}_{uuid.uuid4().hex[:8]}.pdf"

    pdf_path = await pdf_generator.generate_weekly_report(
        report_data=report,
        db=db,
        doctor_id=doctor.id,
    )

    if not pdf_path:
        raise HTTPException(status_code=404, detail="Report PDF could not be generated")

    # Trigger email notification to patient (if patient has email)
    try:
        await email_queue.enqueue(
            email_type="weekly_report_ready",
            doctor_id=str(doctor.id),
            patient_id=str(patient_id),
            layout=layout,
            report_date=datetime.now(timezone.utc).isoformat(),
        )
        logger.info("Enqueued weekly_report_ready email for patient %s", patient_id)
    except Exception as e:
        logger.warning("Failed to enqueue weekly report email: %s", e)

    # Serve the PDF bytes directly so clients (browser/portal) can download it
    try:
        pdf_bytes = await storage_service.download_file("pdfs", pdf_path)
    except Exception as exc:
        logger.error("Failed to fetch weekly report PDF from storage: %s", exc)
        pdf_bytes = None

    if pdf_bytes:
        from fastapi.responses import Response

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    import os

    if os.path.isabs(pdf_path) and os.path.exists(pdf_path):
        from fastapi.responses import FileResponse

        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=filename,
        )

    raise HTTPException(status_code=404, detail="Report PDF file not found on storage")


@router.get("/weekly-report/verify/{verification_code}")
async def verify_weekly_report(
    verification_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to verify a weekly report via QR code scan.

    Returns report metadata if the verification code exists.
    """
    result = await db.execute(
        select(ReportVerification).where(ReportVerification.verification_code == verification_code)
    )
    rv = result.scalar_one_or_none()
    if not rv:
        raise HTTPException(status_code=404, detail="Invalid verification code")

    # Mark as verified
    if not rv.verified_at:
        rv.verified_at = datetime.now(timezone.utc)
        await db.flush()

    return {
        "valid": True,
        "report_type": rv.report_type,
        "generated_at": rv.generated_at.isoformat() if rv.generated_at else None,
        "message": "Report verified — generated by SoloPrac AI",
    }
