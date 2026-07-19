"""Weekly Report Router — Feature F endpoint.

Endpoints:
  POST /patients/{id}/weekly-report — Generate weekly report
  GET  /weekly-report/layouts — Available layouts
  GET  /weekly-report/likert-study — Likert study design
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient
from app.services.weekly_report import (
    WeeklyReportService,
    REPORT_LAYOUTS,
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
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor.id)
    )
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
    service = WeeklyReportService()
    report = await service.generate_report(db, patient_id, layout, days)
    summary = await service.generate_ai_summary(report)
    return {"report": report, "ai_summary": summary}
