-- ═══════════════════════════════════════════════════════════════════════════
-- RLS bootstrap — makes Postgres Row-Level Security ACTUALLY enforce tenant
-- isolation. Executed idempotently by app.database.init_db() as the migration
-- role (table owner / superuser) on every backend boot.
--
-- Why this file exists: the app previously connected as the table-owner
-- superuser, which PostgreSQL silently exempts from RLS — so all the policies
-- below were decorative. This setup creates a dedicated non-owner login role
-- (soloprac_app) for runtime connections and forces RLS on every
-- patient-bearing table.
--
-- Design:
--   * doctors                    → RLS DISABLED  (public directory: login
--                                 lookup, patient search, admin queue).
--   * certificates / report_verifications → RLS DISABLED (public QR-code
--                                 verification by design — anyone with the
--                                 code must be able to look the row up).
--   * patient-bearing tables     → RLS ENABLED + FORCE ROW LEVEL SECURITY
--                                 with two permissive policies (OR'd):
--       tenant_isolation    USING (doctor_id = current_setting('app.current_doctor_id', true)::uuid)
--       patient_self_access USING (patient_id IN (SELECT id FROM patients
--                                 WHERE user_id = current_setting('app.current_user_id', true)::uuid))
--     `true` as missing_ok means an unset variable is NULL (row filtered out),
--     never an error — so anonymous queries simply see nothing.
--   * audit_log                  → doctor-scope policy only (patients never
--                                 read it; admin is itself a doctor row).
--
-- SECURITY DEFINER helpers: a few flows are cross-tenant BY DESIGN and must
-- see rows no RLS policy can show (walk-in discovery for the patient portal,
-- background jobs that only hold a patient/version id). Those go through the
-- narrow functions at the bottom, which run as the table owner and bypass RLS.
-- They are the ONLY sanctioned bypasses; everything else is filtered.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. Runtime role (idempotent) ───────────────────────────────────────────
-- NOTE: the legacy init-schema.sql created soloprac_app as NOLOGIN; if it
-- already exists we must ALTER it to a login role or the app cannot connect.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'soloprac_app') THEN
        CREATE ROLE soloprac_app LOGIN PASSWORD 'soloprac_app_dev_password_change_me';
    ELSE
        ALTER ROLE soloprac_app LOGIN PASSWORD 'soloprac_app_dev_password_change_me';
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO soloprac_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO soloprac_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO soloprac_app;
-- Future tables/sequences created by the migration role (alembic, init_db)
-- are auto-granted so runtime never needs DDL privileges.
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO soloprac_app;
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO soloprac_app;

-- ── 2. Public-by-design tables: RLS off ────────────────────────────────────
ALTER TABLE doctors DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON doctors;

ALTER TABLE certificates DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON certificates;
DROP POLICY IF EXISTS patient_self_access ON certificates;

ALTER TABLE report_verifications DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON report_verifications;
DROP POLICY IF EXISTS patient_self_access ON report_verifications;

-- ── 3. Patient-bearing tables: RLS on + FORCE + dual policies ─────────────
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'patients', 'patient_versions', 'prescription_boxes', 'invoices',
        'appointments', 'risk_alerts', 'patient_notifications',
        'consent_records', 'image_comparisons', 'doctor_notifications'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format('DROP POLICY IF EXISTS patient_self_access ON %I', t);
        IF t = 'patients' THEN
            EXECUTE format(
                'CREATE POLICY tenant_isolation ON %I FOR ALL USING '
                '(doctor_id = NULLIF(current_setting(''app.current_doctor_id'', true), '''')::uuid)',
                t
            );
            EXECUTE format(
                'CREATE POLICY patient_self_access ON %I FOR ALL USING '
                '(user_id = NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid)',
                t
            );
        ELSIF t = 'image_comparisons' THEN
            -- image_comparisons has NO patient_id column — route through
            -- version_id -> patient_versions.patient_id.
            EXECUTE format(
                'CREATE POLICY tenant_isolation ON %I FOR ALL USING '
                '(doctor_id = NULLIF(current_setting(''app.current_doctor_id'', true), '''')::uuid)',
                t
            );
            EXECUTE format(
                'CREATE POLICY patient_self_access ON %I FOR ALL USING '
                '(version_id IN (SELECT id FROM patient_versions WHERE patient_id IN '
                '(SELECT id FROM patients WHERE user_id = NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid)))',
                t
            );
        ELSE
            EXECUTE format(
                'CREATE POLICY tenant_isolation ON %I FOR ALL USING '
                '(doctor_id = NULLIF(current_setting(''app.current_doctor_id'', true), '''')::uuid)',
                t
            );
            EXECUTE format(
                'CREATE POLICY patient_self_access ON %I FOR ALL USING '
                '(patient_id IN (SELECT id FROM patients WHERE '
                'user_id = NULLIF(current_setting(''app.current_user_id'', true), '''')::uuid))',
                t
            );
        END IF;
    END LOOP;
END $$;

-- patient_time_preferences has no doctor_id column — both scopes via subquery.
ALTER TABLE patient_time_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_time_preferences FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON patient_time_preferences;
DROP POLICY IF EXISTS patient_self_access ON patient_time_preferences;
CREATE POLICY tenant_isolation ON patient_time_preferences FOR ALL USING (
    patient_id IN (SELECT id FROM patients
                   WHERE doctor_id = NULLIF(current_setting('app.current_doctor_id', true), '')::uuid)
);
CREATE POLICY patient_self_access ON patient_time_preferences FOR ALL USING (
    patient_id IN (SELECT id FROM patients
                   WHERE user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
);

-- audit_log: doctor scope only (patients never read it).
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON audit_log;
DROP POLICY IF EXISTS patient_self_access ON audit_log;
CREATE POLICY tenant_isolation ON audit_log FOR ALL USING (
    doctor_id = NULLIF(current_setting('app.current_doctor_id', true), '')::uuid
);

-- ── 4. Sanctioned SECURITY DEFINER bypasses ────────────────────────────────
-- These run as the table owner (bypassing RLS) and are the ONLY sanctioned
-- ways to touch rows the caller cannot prove ownership of up-front. Each is
-- minimal: returns/updates only the fields its flow needs.

-- Background jobs that only hold a patient id resolve the owning doctor here,
-- then scope the rest of their session via app.current_doctor_id.
CREATE OR REPLACE FUNCTION public.patient_doctor_id(pid uuid)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS
$$ SELECT doctor_id FROM public.patients WHERE id = pid $$;

CREATE OR REPLACE FUNCTION public.version_doctor_id(vid uuid)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS
$$ SELECT doctor_id FROM public.patient_versions WHERE id = vid $$;

-- Patient portal: list every unlinked walk-in (phone matching happens in app
-- code after decryption). Cross-clinic BY DESIGN — a user may have records at
-- many clinics, none of which RLS can prove yet.
CREATE OR REPLACE FUNCTION public.list_unlinked_walkins()
RETURNS TABLE(
    id uuid, doctor_id uuid, phone_enc bytea, created_at timestamptz,
    link_rejected_by_user_ids uuid[], head_demo jsonb
)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS
$$
    SELECT p.id, p.doctor_id, p.phone_enc, p.created_at,
           p.link_rejected_by_user_ids,
           (v.state_jsonb->'demographics') AS head_demo
    FROM public.patients p
    LEFT JOIN public.patient_versions v ON v.id = p.head_version_id
    WHERE p.user_id IS NULL
$$;

-- Claim / reject run as owner so the unlinked row (user_id IS NULL) is
-- reachable; eligibility (phone match) is enforced in app code first.
CREATE OR REPLACE FUNCTION public.claim_walkin(pid uuid, uid uuid)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = public AS
$$ UPDATE public.patients SET user_id = uid WHERE id = pid AND user_id IS NULL RETURNING true $$;

CREATE OR REPLACE FUNCTION public.reject_walkin(pid uuid, uid uuid)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = public AS
$$ UPDATE public.patients
   SET link_rejected_by_user_ids =
       array_append(coalesce(link_rejected_by_user_ids, '{}'), uid)
   WHERE id = pid AND user_id IS NULL
     AND NOT (uid = ANY(coalesce(link_rejected_by_user_ids, '{}')))
   RETURNING true $$;

GRANT EXECUTE ON FUNCTION public.patient_doctor_id(uuid) TO soloprac_app;
GRANT EXECUTE ON FUNCTION public.version_doctor_id(uuid) TO soloprac_app;
GRANT EXECUTE ON FUNCTION public.list_unlinked_walkins() TO soloprac_app;
GRANT EXECUTE ON FUNCTION public.claim_walkin(uuid, uuid) TO soloprac_app;
GRANT EXECUTE ON FUNCTION public.reject_walkin(uuid, uuid) TO soloprac_app;
