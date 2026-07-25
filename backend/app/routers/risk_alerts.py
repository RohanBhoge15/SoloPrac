"""Risk Alerts Router — Feature E proactive alerts (doctor-facing).

Endpoints:
  GET  /risk-alerts                 — list active (unacknowledged) alerts
  POST /risk-alerts/scan            — manually trigger a live scan for this doctor
  POST /risk-alerts/{id}/acknowledge — acknowledge an alert
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, Patient, RiskAlert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk-alerts", tags=["risk-alerts"])


@router.get("")
async def list_risk_alerts(
    include_acknowledged: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """List risk alerts for the current doctor, newest first.

    Joins patient display names from the head version state so the UI can
    show a real name instead of a UUID.
    """
    query = select(RiskAlert).where(RiskAlert.doctor_id == doctor.id)
    if not include_acknowledged:
        query = query.where(RiskAlert.acknowledged_at.is_(None))
    query = query.order_by(RiskAlert.triggered_at.desc()).limit(limit)

    result = await db.execute(query)
    alerts = result.scalars().all()

    # Resolve patient names in one pass
    patient_ids = {a.patient_id for a in alerts}
    names: dict[uuid.UUID, str] = {}
    if patient_ids:
        prows = await db.execute(
            select(Patient).where(Patient.id.in_(patient_ids))
        )
        for p in prows.scalars().all():
            head = p.head_version
            demo = (head.state_jsonb or {}).get("demographics") if head else None
            if isinstance(demo, dict) and demo.get("name"):
                names[p.id] = demo["name"]

    return [
        {
            "id": str(a.id),
            "patient_id": str(a.patient_id),
            "patient_name": names.get(a.patient_id, f"Patient {str(a.patient_id)[:8]}"),
            "kind": a.kind,
            "severity": a.severity,
            "message": a.reason,
            "detected_at": a.triggered_at.isoformat() if a.triggered_at else None,
            "acknowledged": a.acknowledged_at is not None,
        }
        for a in alerts
    ]


@router.post("/scan")
async def trigger_scan(
    doctor: Doctor = Depends(get_current_doctor),
):
    """Manually trigger a live risk scan for the current doctor.

    Runs inline (not queued) so the caller gets immediate results; the
    scheduled arq cron covers the periodic case.
    """
    from app.services.risk_scan import scan_doctor
    return await scan_doctor(str(doctor.id))


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: uuid.UUID,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a risk alert (dismisses it from the active list)."""
    result = await db.execute(
        select(RiskAlert).where(
            RiskAlert.id == alert_id,
            RiskAlert.doctor_id == doctor.id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Risk alert not found")

    alert.acknowledged_by = doctor.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": str(alert.id), "acknowledged": True}
