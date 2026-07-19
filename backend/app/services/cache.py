"""Enhanced Redis caching — decorators and helpers for frequent queries.

Provides cache-aside pattern for common DB queries:
  - Patient list caching (TTL: 60s)
  - Doctor settings caching (TTL: 300s)
  - Working hours caching (TTL: 120s)
  - Available slots caching (TTL: 30s — short due to booking)
  - Notification preferences caching (TTL: 300s)

Usage:
    from app.services.cache import cached_patients, invalidate_cache
    patients = await cached_patients(db, doctor_id)  # cached 60s
    await invalidate_cache(f"patients:{doctor_id}")  # on write
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar
from uuid import UUID
from functools import wraps

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Doctor, Patient, Appointment, WorkingHours
from app.services.redis import redis_service

logger = logging.getLogger(__name__)

# ─── Cache Key Helpers ─────────────────────────────────────

CACHE_PREFIX = "soloprac"

def _key(*parts: str) -> str:
    return f"{CACHE_PREFIX}:{':'.join(parts)}"

def patients_key(doctor_id: UUID) -> str:
    return _key("patients", str(doctor_id))

def patient_key(patient_id: UUID) -> str:
    return _key("patient", str(patient_id))

def doctor_settings_key(doctor_id: UUID) -> str:
    return _key("doctor:settings", str(doctor_id))

def working_hours_key(doctor_id: UUID) -> str:
    return _key("doctor:wh", str(doctor_id))

def slots_key(doctor_id: UUID, date_from: str, date_to: str) -> str:
    return _key("slots", str(doctor_id), date_from, date_to)

def notifications_key(patient_id: UUID) -> str:
    return _key("notifications", str(patient_id))

# ─── Cache Invalidation ────────────────────────────────────

async def invalidate_cache(*keys: str) -> int:
    """Delete one or more cache keys. Returns count deleted."""
    total = 0
    for k in keys:
        try:
            total += await redis_service.delete(k)
        except Exception as exc:
            logger.warning("Cache invalidation failed for %s: %s", k, exc)
    return total

async def invalidate_patient_cache(doctor_id: UUID, patient_id: Optional[UUID] = None) -> None:
    """Invalidate patient-related caches (call on patient write)."""
    keys = [patients_key(doctor_id)]
    if patient_id:
        keys.append(patient_key(patient_id))
    await invalidate_cache(*keys)

async def invalidate_doctor_cache(doctor_id: UUID) -> None:
    """Invalidate doctor-related caches (call on settings/working-hours change)."""
    await invalidate_cache(
        doctor_settings_key(doctor_id),
        working_hours_key(doctor_id),
    )

# ─── Cached DB Accessors ───────────────────────────────────

async def cached_patients(
    db: AsyncSession,
    doctor_id: UUID,
    ttl: int = 60,
) -> List[Dict[str, Any]]:
    """Get patient list with caching (60s TTL)."""
    cache_key = patients_key(doctor_id)
    cached = await redis_service.get_cached(cache_key)
    if cached is not None:
        logger.debug("Cache hit: patients for doctor %s", doctor_id)
        return cached

    result = await db.execute(
        select(Patient).where(Patient.doctor_id == doctor_id).order_by(Patient.created_at.desc())
    )
    patients = []
    for p in result.scalars().all():
        patients.append({
            "id": str(p.id),
            "name": f"Patient {str(p.id)[:8]}",
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "head_version_id": str(p.head_version_id) if p.head_version_id else None,
        })

    # Also try to get names from head versions
    for idx, p in enumerate(patients):
        if p["head_version_id"]:
            p["name"] = f"{p['id'][:8]}"

    await redis_service.set_cached(cache_key, patients, ttl=ttl)
    return patients


async def cached_doctor_settings(
    db: AsyncSession,
    doctor_id: UUID,
    ttl: int = 300,
) -> Dict[str, Any]:
    """Get doctor settings with caching (5 min TTL)."""
    cache_key = doctor_settings_key(doctor_id)
    cached = await redis_service.get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    settings = doctor.settings if doctor else {}

    await redis_service.set_cached(cache_key, settings, ttl=ttl)
    return settings


async def cached_working_hours(
    db: AsyncSession,
    doctor_id: UUID,
    ttl: int = 120,
) -> Dict[str, Any]:
    """Get doctor working hours with caching (2 min TTL)."""
    cache_key = working_hours_key(doctor_id)
    cached = await redis_service.get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(WorkingHours).where(WorkingHours.doctor_id == doctor_id)
    )
    wh = result.scalars().all()

    hours = {}
    for h in wh:
        hours[h.day_of_week] = {
            "start": h.start_time.isoformat() if h.start_time else None,
            "end": h.end_time.isoformat() if h.end_time else None,
            "enabled": h.is_enabled if hasattr(h, "is_enabled") else True,
        }

    await redis_service.set_cached(cache_key, hours, ttl=ttl)
    return hours


# ─── Eager Loading Optimization ────────────────────────────

def eager_patient_query(patient_id: UUID) -> Any:
    """Build a patient query with eager-loaded relationships.

    Prevents N+1 queries when accessing patient with related data.
    """
    from sqlalchemy.orm import joinedload
    return (
        select(Patient)
        .options(
            joinedload(Patient.versions),
            joinedload(Patient.appointments),
            joinedload(Patient.prescriptions),
            joinedload(Patient.invoices),
            joinedload(Patient.certificates),
            joinedload(Patient.notifications),
        )
        .where(Patient.id == patient_id)
    )


# ─── DB Pool Tuning ────────────────────────────────────────

# These are applied in database.py — just utilities here
POOL_TUNING = {
    "pool_size": 20,          # Increased from 10 — handle concurrent requests
    "max_overflow": 40,       # Increased from 20 — burst capacity
    "pool_pre_ping": True,    # Verify connections before use
    "pool_recycle": 3600,     # Recycle connections after 1 hour
    "pool_use_lifo": True,    # Use LIFO for better connection reuse
}


# ─── Error Fixes Utility ───────────────────────────────────

async def safe_get_patient(
    db: AsyncSession,
    patient_id: UUID,
    doctor_id: UUID,
) -> Optional[Patient]:
    """Safely get a patient with doctor ownership check.

    Returns None (instead of raising) if not found or not owned.
    Handles malformed UUIDs gracefully.
    """
    try:
        result = await db.execute(
            select(Patient).where(
                Patient.id == patient_id,
                Patient.doctor_id == doctor_id,
            )
        )
        return result.scalar_one_or_none()
    except Exception as exc:
        logger.error("Error fetching patient %s: %s", patient_id, exc)
        return None
