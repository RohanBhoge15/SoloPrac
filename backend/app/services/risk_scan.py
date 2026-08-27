"""Feature E — Live Risk Scan over real patient data.

Bridges the offline clustering algorithm (feature_e_clustering.py) to
production: pulls a doctor's real patients, builds trajectory embeddings from
their Qdrant version vectors + vitals stored in state_jsonb, runs HDBSCAN +
anomaly detection, persists RiskAlert rows, and pushes new alerts to the
doctor's dashboard over WebSocket.

Previous cluster labels are cached in Redis per doctor so that cross-scan
"trajectory drift" (a patient moving between cohorts) can be detected.

Usage:
    from app.services.risk_scan import scan_doctor, scan_all_doctors
    result = await scan_doctor(doctor_id)          # single tenant
    await scan_all_doctors()                        # cron entrypoint
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Doctor, Patient, RiskAlert
from app.services.feature_e_clustering import (
    AnomalyDetector,
    compute_trajectory_embeddings,
)
from app.services.qdrant import qdrant_service
from app.services.redis import redis_service

logger = logging.getLogger(__name__)

VITALS_KEYS = ["bp_systolic", "bp_diastolic", "heart_rate", "weight"]
PREV_LABELS_KEY = "feature_e:prev_labels:{doctor_id}"
MIN_PATIENTS_FOR_SCAN = 3  # HDBSCAN needs a cohort to cluster against


async def _set_rls(session: AsyncSession, doctor_id: str) -> None:
    """Scope this session to the doctor so RLS lets us read/write their rows."""
    await session.execute(
        text("SELECT set_config('app.current_doctor_id', :did, true)"),
        {"did": doctor_id},
    )


def _extract_vitals(state: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Pull a vitals dict out of a version's state_jsonb, if present."""
    if not isinstance(state, dict):
        return None
    clinical = state.get("clinical") if isinstance(state.get("clinical"), dict) else state
    vitals = clinical.get("vitals") if isinstance(clinical, dict) else None
    if not isinstance(vitals, dict):
        return None
    out = {}
    for k in VITALS_KEYS:
        v = vitals.get(k)
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out or None


async def _gather_cohort(
    session: AsyncSession,
    doctor_id: str,
) -> tuple[Dict[str, List[np.ndarray]], Dict[str, List[Dict[str, float]]], Dict[str, str]]:
    """Build the inputs the clustering algorithm expects from real data.

    Returns (patient_vectors, vitals_history, patient_names) keyed by patient id.
    Vectors come from Qdrant; vitals + names come from Postgres version state.
    """
    result = await session.execute(select(Patient).where(Patient.doctor_id == UUID(doctor_id)))
    patients = result.scalars().all()

    patient_vectors: Dict[str, List[np.ndarray]] = {}
    vitals_history: Dict[str, List[Dict[str, float]]] = {}
    patient_names: Dict[str, str] = {}

    for patient in patients:
        pid = str(patient.id)

        # Vectors from Qdrant (ordered oldest→newest)
        rows = await qdrant_service.get_patient_vectors(pid, doctor_id)
        if not rows:
            continue
        patient_vectors[pid] = [np.asarray(r["vector"], dtype=np.float32) for r in rows]

        # Vitals + display name from the version chain (already time-ordered desc)
        vitals_seq: List[Dict[str, float]] = []
        name = None
        for version in reversed(patient.versions):  # oldest→newest
            state = version.state_jsonb or {}
            v = _extract_vitals(state)
            if v:
                vitals_seq.append(v)
            if name is None:
                demo = state.get("demographics") if isinstance(state, dict) else None
                if isinstance(demo, dict) and demo.get("name"):
                    name = demo["name"]
        vitals_history[pid] = vitals_seq
        patient_names[pid] = name or f"Patient {pid[:8]}"

    return patient_vectors, vitals_history, patient_names


async def _load_prev_labels(doctor_id: str) -> Optional[Dict[str, int]]:
    """Load previous cluster labels from Redis using shared connection pool."""
    try:
        redis = await redis_service.connect()
        raw = await redis.get(PREV_LABELS_KEY.format(doctor_id=doctor_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def _save_labels(doctor_id: str, labels: Dict[str, int]) -> None:
    """Save current cluster labels to Redis using shared connection pool."""
    try:
        redis = await redis_service.connect()
        await redis.set(
            PREV_LABELS_KEY.format(doctor_id=doctor_id),
            json.dumps(labels),
            ex=60 * 60 * 24 * 30,  # 30 days
        )
    except Exception:
        pass


async def scan_doctor(doctor_id: str) -> Dict[str, Any]:
    """Run a live risk scan for one doctor. Persists alerts and pushes them.

    Returns a summary dict (also used by the manual-trigger endpoint).
    """
    doctor_id = str(doctor_id)
    async with async_session_maker() as session:
        await _set_rls(session, doctor_id)
        patient_vectors, vitals_history, patient_names = await _gather_cohort(session, doctor_id)

        n = len(patient_vectors)
        if n < MIN_PATIENTS_FOR_SCAN:
            logger.info("Risk scan skipped for doctor %s: only %d patients with vectors", doctor_id, n)
            return {"doctor_id": doctor_id, "scanned": n, "alerts": [], "skipped": "insufficient_cohort"}

        patient_ids = list(patient_vectors.keys())

        # Build trajectory embeddings and detect anomalies/drift
        embeddings = compute_trajectory_embeddings(patient_vectors, vitals_history)
        prev_map = await _load_prev_labels(doctor_id)
        prev_labels = None
        if prev_map:
            prev_labels = np.array([prev_map.get(pid, -1) for pid in patient_ids])

        detector = AnomalyDetector()
        alerts = detector.detect_anomalies(embeddings, patient_ids, previous_labels=prev_labels)

        # Persist current labels for next-scan drift comparison
        labels = detector.clusterer.labels_
        if labels is not None:
            await _save_labels(doctor_id, {pid: int(labels[i]) for i, pid in enumerate(patient_ids)})

        # Persist alerts + collect for push
        persisted = []
        for a in alerts:
            row = RiskAlert(
                doctor_id=UUID(doctor_id),
                patient_id=UUID(a.patient_id),
                kind=a.kind,
                reason=a.message,
                severity=a.severity,
            )
            session.add(row)
            await session.flush()  # get row.id
            persisted.append(
                {
                    "id": str(row.id),
                    "patient_id": a.patient_id,
                    "patient_name": patient_names.get(a.patient_id),
                    "kind": a.kind,
                    "severity": a.severity,
                    "message": a.message,
                    "detected_at": a.detected_at,
                }
            )
        await session.commit()

    # Push new alerts to the doctor's live dashboard (outside the DB txn)
    if persisted:
        from app.routers.portal import ws_manager

        for alert in persisted:
            await ws_manager.notify_doctor(doctor_id, {"type": "risk_alert", "data": alert})
        logger.info("Risk scan for doctor %s: %d alerts pushed", doctor_id, len(persisted))

    return {"doctor_id": doctor_id, "scanned": n, "alerts": persisted}


async def scan_all_doctors() -> Dict[str, Any]:
    """Scan every doctor's cohort. Cron entrypoint (runs in the arq worker)."""
    async with async_session_maker() as session:
        result = await session.execute(select(Doctor.id))
        doctor_ids = [str(row[0]) for row in result.all()]

    total_alerts = 0
    for did in doctor_ids:
        try:
            res = await scan_doctor(did)
            total_alerts += len(res.get("alerts", []))
        except Exception as exc:
            logger.warning("Risk scan failed for doctor %s: %s", did, exc)

    logger.info("Risk scan complete: %d doctors, %d total alerts", len(doctor_ids), total_alerts)
    return {"doctors_scanned": len(doctor_ids), "total_alerts": total_alerts}
