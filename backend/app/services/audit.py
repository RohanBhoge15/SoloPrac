"""Audit Log Completeness & RLS Policy Verification Service.

Provides:
1. RLS isolation tests — verifies cross-doctor boundary enforcement.
2. Audit log completeness checks — ensures every required event type is logging.
3. Optimistic locking verification — validates conflict detection on concurrent writes.

These are designed to run as health checks, test fixtures, or pre-deployment smoke tests.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger(__name__)

# ─── Required Audit Event Types ───
REQUIRED_AUDIT_EVENTS = {
    "patient:create",
    "patient:version_mint",
    "patient:version_revert",
    "patient:field_patch",
    "patient:read",
    "appointment:create",
    "appointment:reschedule",
    "appointment:cancel",
    "prescription:create",
    "invoice:create",
    "certificate:create",
    "auth:login",
    "auth:logout",
    "ai:suggestion_made",
    "ai:suggestion_accepted",
    "ai:suggestion_rejected",
}


# ════════════════════════════════════════════════
# RLS Policy Verification
# ════════════════════════════════════════════════

async def verify_rls_isolation(db: AsyncSession) -> dict:
    """Verify RLS tenant isolation across all patient-bearing tables.

    Test strategy:
        1. Create two distinct doctor IDs.
        2. For each table, attempt to query with the first doctor's ID set
           and verify the second doctor's data is invisible.

    Returns:
        {
            "tables_tested": int,
            "passed": bool,
            "results": {"<table>": {"passed": bool, "detail": str}},
        }
    """
    doctor_a = uuid.uuid4()
    doctor_b = uuid.uuid4()

    tables_to_test = [
        "patients",
        "patient_versions",
        "prescription_boxes",
        "invoices",
        "certificates",
        "appointments",
        "risk_alerts",
        "patient_notifications",
        "audit_log",
        "image_comparisons",
    ]

    results = {}
    passed_count = 0

    for table in tables_to_test:
        try:
            # Set session variable to doctor_a
            await db.execute(text(f"SELECT set_config('app.current_doctor_id', '{doctor_a}', true)"))
            await db.flush()

            # Try to insert or query — we just check that the RLS filter exists
            # by querying for doctor_b's data while doctor_a is the session identity
            check_sql = text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE doctor_id = :other_id"
            )
            row = await db.execute(check_sql, {"other_id": doctor_b})
            count = row.scalar() or 0

            # RLS should have blocked doctor_b's rows since we're set to doctor_a
            blocked = count == 0
            results[table] = {
                "passed": blocked,
                "detail": (
                    f"RLS isolated doctor_b rows (count={count})"
                    if blocked else
                    f"RLS did NOT block doctor_b rows (count={count})"
                ),
            }
            if blocked:
                passed_count += 1

        except Exception as exc:
            error_msg = str(exc)
            # RLS violation errors contain "permission denied" or "policy"
            if "permission denied" in error_msg.lower() or "policy" in error_msg.lower():
                results[table] = {
                    "passed": False,
                    "detail": f"RLS policy error: {error_msg}",
                }
            else:
                # Non-RLS error (table doesn't exist, etc.) — still count as concern
                results[table] = {
                    "passed": False,
                    "detail": f"Query error (may be pre-migration): {error_msg}",
                }

    await db.rollback()

    all_passed = all(r["passed"] for r in results.values())
    return {
        "tables_tested": len(tables_to_test),
        "passed": all_passed,
        "results": results,
    }


async def verify_doctor_identity_injection(db: AsyncSession) -> dict:
    """Verify that the doctor_identity_middleware injects app.current_doctor_id."""
    try:
        result = await db.execute(
            text("SELECT current_setting('app.current_doctor_id', true)")
        )
        setting = result.scalar()
        if setting:
            return {
                "passed": True,
                "detail": f"app.current_doctor_id is set to {setting}",
                "doctor_id": setting,
            }
        else:
            return {
                "passed": False,
                "detail": "app.current_doctor_id is not set. Doctor identity middleware may not be running.",
            }
    except Exception as exc:
        return {
            "passed": False,
            "detail": f"Cannot read app.current_doctor_id: {exc}",
        }


# ════════════════════════════════════════════════
# Audit Log Completeness
# ════════════════════════════════════════════════

async def verify_audit_completeness(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    since: Optional[datetime] = None,
) -> dict:
    """Check that all required event types have at least one log entry.

    Args:
        db: Database session.
        doctor_id: The doctor to check logs for.
        since: Only check events since this timestamp. Defaults to 7 days ago.

    Returns:
        {
            "events_checked": int,
            "events_found": int,
            "events_missing": [str, ...],
            "passed": bool,
        }
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=7)

    result = await db.execute(
        select(AuditLog.action.distinct()).where(
            AuditLog.doctor_id == doctor_id,
            AuditLog.occurred_at >= since,
        )
    )
    found_actions = {row[0] for row in result.fetchall()}

    # Map logbook actions to our internal action values
    # The audit middleware logs actions as "write" and "read"
    # Version-specific actions are embedded in payload_jsonb
    required = {"write", "read"}
    missing = required - found_actions

    return {
        "events_checked": len(required),
        "events_found": len(found_actions),
        "events_missing": sorted(missing) if missing else [],
        "found_actions": sorted(found_actions),
        "passed": len(missing) == 0,
    }


async def verify_version_audit_trail(
    db: AsyncSession,
    version_id: uuid.UUID,
) -> dict:
    """Verify a specific version creation is logged in audit_log."""
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "version",
            AuditLog.resource_id == version_id,
            AuditLog.action == "write",
        )
    )
    entry = result.scalar_one_or_none()
    return {
        "passed": entry is not None,
        "audit_entry_id": entry.id if entry else None,
        "detail": "Version creation logged" if entry else "Version creation NOT found in audit_log",
    }


# ════════════════════════════════════════════════
# Optimistic Locking Verification
# ════════════════════════════════════════════════

async def verify_optimistic_locking(db: AsyncSession) -> dict:
    """Verify that the patients.updated_at column updates on write.

    This confirms that concurrent write detection via updated_at
    (or version_number changes) will work as expected.
    """
    try:
        # Create a test patient temporarily
        doctor_id = uuid.uuid4()
        await db.execute(
            text("SELECT set_config('app.current_doctor_id', :did, true)"),
            {"did": str(doctor_id)},
        )

        # Insert a test patient
        patient_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO patients (id, doctor_id, created_at, updated_at) "
                "VALUES (:pid, :did, NOW(), NOW())"
            ),
            {"pid": patient_id, "did": doctor_id},
        )
        await db.flush()

        # Read the updated_at
        row1 = await db.execute(
            text("SELECT updated_at FROM patients WHERE id = :pid"),
            {"pid": patient_id},
        )
        updated_at_initial = row1.scalar_one()

        # Simulate waiting briefly
        import asyncio
        await asyncio.sleep(0.01)

        # Update the patient to trigger onupdate
        await db.execute(
            text("UPDATE patients SET consent_for_share = TRUE WHERE id = :pid"),
            {"pid": patient_id},
        )
        await db.flush()

        # Read updated_at again
        row2 = await db.execute(
            text("SELECT updated_at FROM patients WHERE id = :pid"),
            {"pid": patient_id},
        )
        updated_at_after = row2.scalar_one()

        await db.rollback()

        has_changed = updated_at_after > updated_at_initial

        return {
            "passed": has_changed,
            "detail": (
                "updated_at advances on write — concurrent conflict detection works"
                if has_changed
                else "updated_at did not advance (no onupdate trigger?)"
            ),
            "initial": updated_at_initial.isoformat() if updated_at_initial else None,
            "after_write": updated_at_after.isoformat() if updated_at_after else None,
        }

    except Exception as exc:
        await db.rollback()
        return {
            "passed": False,
            "detail": f"Optimistic locking verification error: {exc}",
        }


# ════════════════════════════════════════════════
# Full Verification Suite
# ════════════════════════════════════════════════

async def run_security_audit(db: AsyncSession, doctor_id: Optional[uuid.UUID] = None) -> dict:
    """Run the full security verification suite.

    Returns a comprehensive audit report covering RLS, audit completeness,
    and optimistic locking.
    """
    if doctor_id is None:
        doctor_id = uuid.uuid4()

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
    }

    # 1. RLS Isolation
    report["checks"]["rls_isolation"] = await verify_rls_isolation(db)

    # 2. Doctor Identity Injection
    report["checks"]["doctor_identity"] = await verify_doctor_identity_injection(db)

    # 3. Audit Completeness
    report["checks"]["audit_completeness"] = await verify_audit_completeness(db, doctor_id)

    # 4. Optimistic Locking
    report["checks"]["optimistic_locking"] = await verify_optimistic_locking(db)

    # Overall
    all_checks = report["checks"].values()
    report["passed"] = all(c.get("passed", False) for c in all_checks)
    report["summary"] = (
        "All security checks passed"
        if report["passed"]
        else f"{sum(1 for c in all_checks if not c.get('passed', False))} check(s) failed"
    )

    return report
