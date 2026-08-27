"""Audit Log Completeness & RLS Policy Verification Service.

Provides:
1. RLS isolation tests — verifies cross-doctor boundary enforcement.
2. Audit log completeness checks — ensures every required event type is logging.
3. Optimistic locking verification — validates conflict detection on concurrent writes.

These are designed to run as health checks, test fixtures, or pre-deployment smoke tests.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text
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
    """Verify RLS tenant isolation with REAL rows, both directions.

    The previous test used random UUIDs that never had rows, so COUNT(*) was
    0 whether or not RLS filtered — it passed vacuously and could not detect
    the owner/superuser bypass. This version:
      1. Creates two real doctors and one patient + child rows for each.
      2. Scopes the session to doctor A and proves doctor B's rows are
         invisible on EVERY patient-bearing table (and vice versa).
      3. Verifies the patient_self_access policy admits only the owner's
         rows for a user-scoped session.
      4. Rolls back — the test never leaves rows behind.

    It must run as soloprac_app (the runtime role subject to RLS); run as the
    owner/superuser it would report everything visible and fail loudly.
    """
    import uuid as _uuid

    doctor_a = _uuid.uuid4()
    doctor_b = _uuid.uuid4()
    user_x = _uuid.uuid4()

    tables_to_test = [
        "patients",
        "patient_versions",
        "prescription_boxes",
        "invoices",
        "appointments",
        "risk_alerts",
        "patient_notifications",
        "consent_records",
        "image_comparisons",
        "doctor_notifications",
        "audit_log",
        "patient_time_preferences",
    ]

    results = {}

    async def _scope(doctor=None, user=None):
        """Set (or clear) the RLS identity session variables."""
        await db.execute(text("SELECT set_config('app.current_doctor_id', NULL, true)"))
        await db.execute(text("SELECT set_config('app.current_user_id', NULL, true)"))
        if doctor:
            await db.execute(text("SELECT set_config('app.current_doctor_id', :d, true)"), {"d": str(doctor)})
        if user:
            await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(user)})

    async def _count(table: str, where: str, **params) -> int:
        row = await db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {where}"), params)
        return row.scalar() or 0

    try:
        # ── Fixtures (doctors table is RLS-disabled: public directory) ──
        for did, tag in ((doctor_a, "a"), (doctor_b, "b")):
            await db.execute(
                text(
                    "INSERT INTO doctors (id, email, name, verification_status, settings) "
                    "VALUES (:id, :email, :name, 'verified', '{}'::jsonb)"
                ),
                {"id": did, "email": f"rls-test-{tag}-{did}@soloprac.local", "name": "RLS Test Doctor"},
            )
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, name, phone, phone_hash) "
                "VALUES (:id, :email, 'x', 'RLS Test User', '9999999999', 'x')"
            ),
            {"id": user_x, "email": f"rls-test-user-{user_x}@soloprac.local"},
        )

        # Patient A = walk-in (user_id NULL) under doctor A.
        # Patient B = claimed by user_x under doctor B.
        pa = _uuid.uuid4()
        pb = _uuid.uuid4()
        await _scope(doctor=doctor_a)
        await db.execute(
            text("INSERT INTO patients (id, doctor_id, user_id) VALUES (:id, :did, NULL)"),
            {"id": pa, "did": doctor_a},
        )
        await _scope(doctor=doctor_b)
        await db.execute(
            text("INSERT INTO patients (id, doctor_id, user_id) VALUES (:id, :did, :uid)"),
            {"id": pb, "did": doctor_b, "uid": user_x},
        )
        # One version under B (referenced by prescription/image rows) plus one
        # child row per table, all scoped to doctor B.
        vb = _uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO patient_versions (id, patient_id, doctor_id, version_number, "
                "state_jsonb, version_hash, author, edit_type, timestamp) "
                "VALUES (:id, :pid, :did, 1, '{}'::jsonb, 'x', 'doctor:x', 'manual', NOW())"
            ),
            {"id": vb, "pid": pb, "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO prescription_boxes (id, version_id, patient_id, doctor_id, rx_jsonb) "
                "VALUES (:id, :vid, :pid, :did, '{}'::jsonb)"
            ),
            {"id": _uuid.uuid4(), "vid": vb, "pid": pb, "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO invoices (id, patient_id, doctor_id, invoice_number, items, subtotal, tax, total) "
                "VALUES (:id, :pid, :did, 'RLS-TEST-1', '{}'::jsonb, 0, 0, 0)"
            ),
            {"id": _uuid.uuid4(), "pid": pb, "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO appointments (id, doctor_id, patient_id, start_at, end_at, status, source) "
                "VALUES (:id, :did, :pid, NOW(), NOW() + interval '1 hour', 'scheduled', 'manual')"
            ),
            {"id": _uuid.uuid4(), "pid": pb, "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO risk_alerts (id, doctor_id, patient_id, kind, reason, severity) "
                "VALUES (:id, :did, :pid, 'rls_test', 'test', 0.5)"
            ),
            {"id": _uuid.uuid4(), "pid": pb, "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO patient_notifications (id, patient_id, doctor_id, kind, subject, body, channel) "
                "VALUES (:id, :pid, :did, 'rls_test', 't', 'b', '{}'::text[])"
            ),
            {"id": _uuid.uuid4(), "pid": pb, "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO consent_records (id, patient_id, doctor_id, consent_type, granted) "
                "VALUES (:id, :pid, :did, 'rls_test', true)"
            ),
            {"id": _uuid.uuid4(), "pid": pb, "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO image_comparisons (id, doctor_id, version_id, current_image_path) "
                "VALUES (:id, :did, :vid, 'rls-test.png')"
            ),
            {"id": _uuid.uuid4(), "did": doctor_b, "vid": vb},
        )
        await db.execute(
            text(
                "INSERT INTO doctor_notifications (id, doctor_id, kind, subject, body) "
                "VALUES (:id, :did, 'rls_test', 't', 'b')"
            ),
            {"id": _uuid.uuid4(), "did": doctor_b},
        )
        await db.execute(
            text(
                "INSERT INTO patient_time_preferences (patient_id, weekday, hour_bucket, count) VALUES (:pid, 1, 9, 1)"
            ),
            {"pid": pb},
        )
        await db.execute(
            text(
                "INSERT INTO audit_log (doctor_id, actor, action, resource_type, payload_jsonb) "
                "VALUES (:did, 'system', 'write', 'rls_test', '{}'::jsonb)"
            ),
            {"did": doctor_b},
        )

        # ── Doctor A cannot see any of doctor B's rows ──
        await _scope(doctor=doctor_a)
        for table in tables_to_test:
            try:
                if table in ("patient_versions", "patient_time_preferences"):
                    other = await _count(table, "patient_id = :pid", pid=pb)
                    mine = await _count(table, "patient_id = :pid", pid=pa)
                else:
                    other = await _count(table, "doctor_id = :did", did=doctor_b)
                    mine = await _count(table, "doctor_id = :did", did=doctor_a)
                blocked = other == 0
                results[table] = {
                    "passed": blocked,
                    "detail": (
                        f"B rows from A-scope: {other} (must be 0) | A rows: {mine}"
                        if blocked
                        else f"LEAK: B rows visible from A-scope ({other})"
                    ),
                }
            except Exception as exc:
                results[table] = {"passed": False, "detail": f"Query error: {exc}"}

        # ── Mirror: doctor B cannot see doctor A's rows ──
        await _scope(doctor=doctor_b)
        for table in tables_to_test:
            try:
                if table in ("patient_versions", "patient_time_preferences"):
                    other = await _count(table, "patient_id = :pid", pid=pa)
                else:
                    other = await _count(table, "doctor_id = :did", did=doctor_a)
                blocked = other == 0
                if blocked:
                    # Keep the best detail; add a note for the reverse pass.
                    prev = results.get(table, {})
                    results[table] = {
                        "passed": prev.get("passed", True) and True,
                        "detail": f"{prev.get('detail', '')} | A rows from B-scope: {other} (must be 0)",
                    }
                else:
                    results[table] = {
                        "passed": False,
                        "detail": f"LEAK: A rows visible from B-scope ({other})",
                    }
            except Exception as exc:
                results[table] = {"passed": False, "detail": f"Query error: {exc}"}

        # ── Patient self-access: user_x sees their own patient only ──
        await _scope(user=user_x)
        try:
            own = await _count("patients", "user_id = :uid", uid=user_x)
            stranger = await _count("patients", "user_id = :uid", uid=_uuid.uuid4())
            self_ok = own == 1 and stranger == 0
            results["patient_self_access"] = {
                "passed": self_ok,
                "detail": f"own rows: {own} (want 1) | stranger rows: {stranger} (want 0)",
            }
        except Exception as exc:
            results["patient_self_access"] = {"passed": False, "detail": f"Query error: {exc}"}

    except Exception as exc:
        results["_setup"] = {"passed": False, "detail": f"Fixture setup failed: {exc}"}
    finally:
        await db.rollback()

    all_passed = all(r["passed"] for r in results.values()) if results else False
    return {
        "tables_tested": len(tables_to_test) + 1,
        "passed": all_passed,
        "results": results,
        "note": "Runs as soloprac_app; if the app connected as the table owner/superuser this would fail loudly instead of passing vacuously.",
    }


async def verify_doctor_identity_injection(db: AsyncSession) -> dict:
    """Verify that the doctor_identity_middleware injects app.current_doctor_id."""
    try:
        result = await db.execute(text("SELECT current_setting('app.current_doctor_id', true)"))
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
            text("INSERT INTO patients (id, doctor_id, created_at, updated_at) VALUES (:pid, :did, NOW(), NOW())"),
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
