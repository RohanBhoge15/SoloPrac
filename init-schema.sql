-- SoloPrac AI - Database Schema Initialization
-- This runs on first PostgreSQL container startup

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- Set timezone
SET timezone = 'Asia/Kolkata';

-- Doctors table (tenants)
CREATE TABLE doctors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    speciality TEXT DEFAULT 'General Practice',
    location TEXT,  -- Store as "lat,lng" text
    clinic_name TEXT,
    clinic_address TEXT,
    phone TEXT,
    registration_number TEXT,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Patients table (head pointer only)
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    head_version_id UUID,  -- Will FK to patient_versions after creation
    phone_enc BYTEA,
    email_enc BYTEA,
    consent_for_share BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Patient Versions (immutable chain)
CREATE TABLE patient_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    parent_version_id UUID REFERENCES patient_versions(id),
    version_number INT NOT NULL,
    state_jsonb JSONB NOT NULL,
    version_hash TEXT NOT NULL,
    author TEXT NOT NULL,  -- 'doctor:<id>' | 'agent:<name>'
    edit_type TEXT NOT NULL,  -- manual|voice|ocr|ai_suggestion|revert
    summary TEXT,
    tags TEXT[] DEFAULT '{}',
    clinical_significance REAL DEFAULT 0.0,
    image_comparison JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (patient_id, version_number)
);

CREATE INDEX ON patient_versions (patient_id, timestamp DESC);
CREATE INDEX ON patient_versions (doctor_id, timestamp DESC);

-- Prescription Boxes
CREATE TABLE prescription_boxes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version_id UUID NOT NULL REFERENCES patient_versions(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    rx_jsonb JSONB NOT NULL,
    pdf_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Invoices
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    appointment_id UUID REFERENCES appointments(id),
    invoice_number TEXT NOT NULL UNIQUE,
    items JSONB NOT NULL,
    subtotal INTEGER NOT NULL,  -- in paise/cents
    tax INTEGER DEFAULT 0,
    total INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|paid|cancelled
    payment_method TEXT,  -- cash|upi|card|insurance
    notes TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    pdf_path TEXT
);

-- Certificates
CREATE TABLE certificates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    cert_type TEXT NOT NULL,  -- sick_leave|fitness|school|disability|other
    cert_jsonb JSONB NOT NULL,
    pdf_path TEXT,
    verification_code TEXT UNIQUE,
    issued_at TIMESTAMPTZ DEFAULT NOW()
);

-- Appointments
CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled|done|cancelled|moved
    source TEXT NOT NULL DEFAULT 'manual',  -- manual|voice|agent|patient_portal
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON appointments (doctor_id, start_at);
CREATE INDEX ON appointments (patient_id, start_at);

-- Patient Time Preferences (for smart scheduling)
CREATE TABLE patient_time_preferences (
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    weekday INT NOT NULL,  -- 0-6
    hour_bucket INT NOT NULL,  -- 0-23
    count INT NOT NULL DEFAULT 0,
    last_seen TIMESTAMPTZ,
    PRIMARY KEY (patient_id, weekday, hour_bucket)
);

-- Risk Alerts
CREATE TABLE risk_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,  -- trajectory_drift|anomaly
    reason TEXT NOT NULL,
    severity REAL NOT NULL,  -- 0-1
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    acknowledged_by UUID REFERENCES doctors(id),
    acknowledged_at TIMESTAMPTZ
);

-- Patient Notifications
CREATE TABLE patient_notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    channel TEXT[] DEFAULT '{in_app}',
    read BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Log (append-only, medico-legal)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    patient_id UUID REFERENCES patients(id) ON DELETE SET NULL,
    actor TEXT NOT NULL,  -- doctor:<id> | patient:<id> | agent:<name> | system
    action TEXT NOT NULL,  -- read|write|ai_suggest|approve|export|book|cancel
    resource_type TEXT NOT NULL,  -- patient|version|appointment|rx|invoice|certificate|report
    resource_id UUID,
    payload_jsonb JSONB,
    ip_address INET,
    user_agent TEXT,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON audit_log (doctor_id, occurred_at DESC);

-- Image Comparisons
CREATE TABLE image_comparisons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version_id UUID NOT NULL REFERENCES patient_versions(id) ON DELETE CASCADE,
    current_image_path TEXT NOT NULL,
    matched_version_id UUID REFERENCES patient_versions(id),
    matched_image_path TEXT,
    area_change_pct REAL,
    edge_convergence_score REAL,
    color_histogram_shift REAL,
    overlay_path TEXT,
    clinical_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row-Level Security on all patient-bearing tables
ALTER TABLE doctors ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescription_boxes ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE image_comparisons ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Tenant Isolation
-- All queries must have app.current_doctor_id set
CREATE POLICY tenant_isolation ON doctors
  USING (id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON patients
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON patient_versions
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON prescription_boxes
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON invoices
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON certificates
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON appointments
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON risk_alerts
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON patient_notifications
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON audit_log
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

CREATE POLICY tenant_isolation ON image_comparisons
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);

-- Grant permissions for application role
CREATE ROLE soloprac_app NOLOGIN;
GRANT USAGE ON SCHEMA public TO soloprac_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO soloprac_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO soloprac_app;

-- For audit_log: revoke DELETE to make it append-only
REVOKE DELETE ON audit_log FROM soloprac_app;

-- Function to compute version hash
CREATE OR REPLACE FUNCTION compute_version_hash(state JSONB)
RETURNS TEXT AS $$
BEGIN
    RETURN encode(digest(state::text, 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function to update patient.updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create langfuse database and user
CREATE DATABASE langfuse;
CREATE USER langfuse WITH ENCRYPTED PASSWORD 'langfuse_dev_password';
GRANT ALL PRIVILEGES ON DATABASE langfuse TO langfuse;