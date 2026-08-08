-- P1.14 + P1.15 — index hygiene pass.
--
-- Executed at startup by `init_db()` (see database.py). All statements are
-- idempotent (IF NOT EXISTS) so this can be re-applied on every boot.
--
-- P1.14 — FK columns without indexes that show up in JOIN/WHERE hot paths.
-- Postgres does NOT auto-index the "child" side of a FK; every one of these
-- causes a seq scan on the referenced table when the parent is deleted or
-- when the child is filtered by the FK value.
--
-- P1.15 — GIN on state_jsonb->'demographics' so patient search by name /
-- phone-fragment / dob doesn't full-table-scan the JSONB blob.

BEGIN;

-- ── patient_versions.parent_version_id (versioned history walks) ──
CREATE INDEX IF NOT EXISTS ix_patient_versions_parent
    ON patient_versions (parent_version_id)
    WHERE parent_version_id IS NOT NULL;

-- ── patients.head_version_id (patient list → head-version dereference) ──
CREATE INDEX IF NOT EXISTS ix_patients_head_version
    ON patients (head_version_id)
    WHERE head_version_id IS NOT NULL;

-- ── patient_notes / images / consents (patient timeline queries) ──
CREATE INDEX IF NOT EXISTS ix_patient_notes_patient
    ON patient_notes (patient_id);
CREATE INDEX IF NOT EXISTS ix_patient_notes_doctor
    ON patient_notes (doctor_id);
CREATE INDEX IF NOT EXISTS ix_patient_images_patient
    ON patient_images (patient_id);
CREATE INDEX IF NOT EXISTS ix_patient_images_doctor
    ON patient_images (doctor_id);

-- ── prescription_boxes (P1.12 timeline fan-out & agent citations) ──
CREATE INDEX IF NOT EXISTS ix_prescription_boxes_patient_created
    ON prescription_boxes (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_prescription_boxes_doctor_created
    ON prescription_boxes (doctor_id, created_at DESC);

-- ── invoices (P1.12 timeline fan-out) ──
CREATE INDEX IF NOT EXISTS ix_invoices_patient_generated
    ON invoices (patient_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS ix_invoices_doctor_generated
    ON invoices (doctor_id, generated_at DESC);

-- ── certificates (P1.12 timeline fan-out) ──
CREATE INDEX IF NOT EXISTS ix_certificates_patient_created
    ON certificates (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_certificates_doctor_created
    ON certificates (doctor_id, created_at DESC);

-- ── risk_alerts (Feature E hot path) ──
CREATE INDEX IF NOT EXISTS ix_risk_alerts_patient
    ON risk_alerts (patient_id);

-- ── pending_links (linking + walk-in disambiguation) ──
CREATE INDEX IF NOT EXISTS ix_pending_links_version
    ON pending_links (version_id);
CREATE INDEX IF NOT EXISTS ix_pending_links_matched
    ON pending_links (matched_version_id)
    WHERE matched_version_id IS NOT NULL;

-- ── consents ──
CREATE INDEX IF NOT EXISTS ix_consents_patient
    ON consents (patient_id);
CREATE INDEX IF NOT EXISTS ix_consents_doctor
    ON consents (doctor_id);

-- ── audit_log.patient_id (compliance queries) ──
CREATE INDEX IF NOT EXISTS ix_audit_log_patient_occurred
    ON audit_log (patient_id, occurred_at DESC)
    WHERE patient_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────
-- P1.15 — GIN on demographics for fast patient search
-- ─────────────────────────────────────────────────────────────
-- Query patterns that hit this: LIKE '%name%', @> '{"demographics":{"phone":"..."}}',
-- and the doctor UI's patient search bar. Without this, every keystroke
-- triggers a full-table scan on patient_versions.
--
-- We index only the head-version rows (via a partial index) so it stays small
-- even after many edits per patient.

CREATE INDEX IF NOT EXISTS ix_patient_versions_demographics_gin
    ON patient_versions
    USING GIN ((state_jsonb -> 'demographics') jsonb_path_ops);

-- Trigram index on the flattened name — used by ILIKE '%foo%' during search.
-- pg_trgm is enabled in init-schema.sql; safe to reference here.
CREATE INDEX IF NOT EXISTS ix_patient_versions_name_trgm
    ON patient_versions
    USING GIN ((state_jsonb #>> '{demographics,name}') gin_trgm_ops);

COMMIT;
