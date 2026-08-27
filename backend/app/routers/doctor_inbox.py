"""C-9: Doctor-side inbox HTTP endpoints.

Mirror of the /patient/me/inbox endpoints but keyed on the current
doctor via get_current_doctor. Live updates arrive over the doctor
WebSocket (see routers/portal.py :: doctor_websocket); these HTTP
endpoints back the bell popover fetches.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor, DoctorNotification

logger = logging.getLogger(__name__)

router = APIRouter(tags=["doctor-inbox"])


@router.get("/doctor/me/inbox")
async def doctor_inbox(
    doctor: Doctor = Depends(get_current_doctor),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """C-9: Return the doctor's most recent notifications."""
    result = await db.execute(
        select(DoctorNotification)
        .where(DoctorNotification.doctor_id == doctor.id)
        .order_by(DoctorNotification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    return [
        {
            "id": str(n.id),
            "kind": n.kind,
            "subject": n.subject,
            "body": n.body,
            "meta": n.meta,
            "read": n.read,
            "patient_id": str(n.patient_id) if n.patient_id else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


@router.get("/doctor/me/inbox/unread-count")
async def doctor_inbox_unread_count(
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """C-9: Cheap count for the bell red-dot."""
    result = await db.execute(
        select(func.count(DoctorNotification.id)).where(
            DoctorNotification.doctor_id == doctor.id,
            DoctorNotification.read.is_(False),
        )
    )
    count = result.scalar() or 0
    return {"count": int(count)}


@router.patch("/doctor/me/inbox/{notification_id}/read")
async def mark_doctor_notification_read(
    notification_id: uuid.UUID,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """C-9: Mark a notification read (only if it belongs to this doctor)."""
    result = await db.execute(
        select(DoctorNotification).where(
            DoctorNotification.id == notification_id,
            DoctorNotification.doctor_id == doctor.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.read = True
    await db.commit()
    return {"ok": True, "read": True}
