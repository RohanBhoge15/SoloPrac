# SoloPrac AI — Database Schema Design

## 1. Schema Philosophy

### Versioned Immutable Records
The core architectural bet: patient data is **never updated in place**. Every change mints a new version, forming an immutable chain. This enables time-travel queries, medico-legal audit trails, and temporal-aware RAG.

### Multi-Tenant by Design
Every patient-bearing table includes `doctor_id` with PostgreSQL Row-Level Security (RLS) ensuring that even a buggy query cannot leak data across doctors.

### PII Encryption
Personally Identifiable Information (phone, email, address) is encrypted at rest using pgcrypto with application-layer key management.

### Cross-Clinic Patient Identity
A `users` table (no RLS) stores cross-tenant user identity. Each clinic visit creates a `patient` row scoped to that doctor with `patient.user_id` FK to the shared `user`. Walk-in patients have `user_id = NULL`.

### Doctor Verification & Trust
Doctors register with email/password, start as `unverified`. Upload registration number + license document → `pending_verification`. Admin approves → `verified` (appears in public search). Admin rejects → `rejected` with reason.

---

## 2. Table Definitions

### 2.1 Users (Cross-Tenant, No RLS)
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    date_of_birth DATE,
    gender TEXT,
    blood_group TEXT,
    allergies TEXT[],
    chronic_conditions TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.2 Doctors (Tenants)
```sql
CREATE TABLE doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    speciality TEXT DEFAULT 'General Practice',
    location GEOGRAPHY(POINT),              -- PostGIS for patient map search
    clinic_name TEXT NOT NULL,
    clinic_address TEXT NOT NULL,
    phone TEXT NOT NULL,
    pincode TEXT,                            -- indexed for PIN-based search
    registration_number TEXT,
    state_medical_council TEXT,
    year_of_registration INTEGER,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    license_document_path TEXT,
    rejection_reason TEXT,
    verified_at TIMESTAMPTZ,
    photo_url TEXT,                          -- MinIO avatar path
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_doctors_pincode ON doctors(pincode);
CREATE INDEX idx_doctors_location ON doctors USING GIST(location);
```

**Settings JSONB Structure:**
```json
{
  "notification_preferences": {
    "appointment_reminder": {"enabled": true, "hours_before": 2, "channels": ["in_app", "email"]},
    "new_report": {"enabled": true, "channels": ["in_app", "email"]},
    "invoice_generated": {"enabled": true, "channels": ["in_app"]},
    "booking_confirmation": {"enabled": true, "channels": ["in_app", "email"]},
    "reschedule_notification": {"enabled": true, "channels": ["in_app", "email"]},
    "certificate_issued": {"enabled": true, "channels": ["in_app"]}
  },
  "patient_booking_enabled": true,
  "auto_confirm_booking": false,
  "max_future_booking_days": 30,
  "certificate_templates": {},
  "state": "Maharashtra"
}
```

### 2.3 Patients (Per-Doctor Medical Record)
```sql
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    head_version_id UUID REFERENCES patient_versions(id),
    phone_enc BYTEA, email_enc BYTEA,
    consent_for_share BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_patients_doctor_id ON patients(doctor_id);
CREATE INDEX idx_patients_user_id ON patients(user_id);
```

### 2.4 Patient Versions (Immutable Chain)
```sql
CREATE TABLE patient_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    parent_version_id UUID REFERENCES patient_versions(id),
    version_number INT NOT NULL,
    state_jsonb JSONB NOT NULL,
    version_hash TEXT NOT NULL,
    author TEXT NOT NULL,
    edit_type TEXT NOT NULL,
    summary TEXT,
    tags TEXT[] DEFAULT '{}',
    clinical_significance REAL DEFAULT 0.0,
    image_comparison JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (patient_id, version_number)
);

CREATE INDEX idx_pv_patient_ts ON patient_versions (patient_id, timestamp DESC);
CREATE INDEX idx_pv_doctor_ts ON patient_versions (doctor_id, timestamp DESC);
```

### 2.5 Prescription Boxes
```sql
CREATE TABLE prescription_boxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES patient_versions(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    rx_jsonb JSONB NOT NULL,
    pdf_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.6 Invoices
```sql
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    appointment_id UUID REFERENCES appointments(id),
    invoice_number TEXT NOT NULL UNIQUE,
    items JSONB NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    tax DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payment_method TEXT,
    notes TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    pdf_path TEXT
);
```

### 2.7 Certificates
```sql
CREATE TABLE certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    cert_type TEXT NOT NULL,
    cert_jsonb JSONB NOT NULL,
    pdf_path TEXT,
    verification_code TEXT UNIQUE,
    issued_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.8 Appointments
```sql
CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    source TEXT NOT NULL DEFAULT 'manual',
    notified BOOLEAN DEFAULT FALSE,
    telemedicine_consent BOOLEAN DEFAULT FALSE,
    telemedicine_consent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_appt_doctor_start ON appointments (doctor_id, start_at);
CREATE INDEX idx_appt_patient_start ON appointments (patient_id, start_at);
```

### 2.9 Patient Time Preferences (Smart Scheduling)
```sql
CREATE TABLE patient_time_preferences (
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    weekday INT NOT NULL,
    hour_bucket INT NOT NULL,
    count INT NOT NULL DEFAULT 0,
    last_seen TIMESTAMPTZ,
    PRIMARY KEY (patient_id, weekday, hour_bucket)
);
```

### 2.10 Risk Alerts
```sql
CREATE TABLE risk_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    reason TEXT NOT NULL,
    severity REAL NOT NULL,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    acknowledged_by UUID REFERENCES doctors(id),
    acknowledged_at TIMESTAMPTZ
);
```

### 2.11 Patient Notifications
```sql
CREATE TABLE patient_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    channel TEXT[] DEFAULT '{in_app}',
    meta JSONB,
    read BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.12 Consent Records (DPDP)
```sql
CREATE TABLE consent_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    consent_type TEXT NOT NULL,
    granted BOOLEAN NOT NULL,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    ip_address INET,
    user_agent TEXT
);
```

### 2.13 Doctor Sessions
```sql
CREATE TABLE doctor_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    token_jti TEXT NOT NULL UNIQUE,
    device_info TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMPTZ
);
```

### 2.14 Audit Log (Append-Only)
```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    doctor_id UUID NOT NULL,
    patient_id UUID,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id UUID,
    payload_jsonb JSONB,
    ip_address INET,
    user_agent TEXT,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_doctor_time ON audit_log (doctor_id, occurred_at DESC);
```

---

## 3. Row-Level Security Policies

Every patient-bearing table has RLS enabled with the same policy pattern:

```sql
-- Enable RLS
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescription_boxes ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;

-- Policy: tenant isolation via app.current_doctor_id
CREATE POLICY tenant_isolation ON patients
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);
-- Same policy applied to all other tenant-scoped tables.
```

**How it works:**
- FastAPI middleware sets `SET LOCAL app.current_doctor_id = '<uuid>'` after JWT auth
- Even if an ORM query forgets a WHERE clause, RLS enforces isolation
- Backup restoration cannot leak data across tenants
- `users` table has NO RLS (cross-tenant by design)

---

## 4. Data Integrity & Performance

| Feature | Implementation | Benefit |
|---------|---------------|---------|
| Version Hash | `sha256(canonical_json(state))` | Content-addressable; tamper-evident |
| Unique Constraint | `UNIQUE(patient_id, version_number)` | Prevents version gaps/duplicates |
| Foreign Keys | All relationships enforced | Referential integrity |
| Composite Indexes | Time-bound queries covered | <50ms timeline queries |
| JSONB Columns | Flexible patient state schemas | Schema-less per version |
| Pincode Index | `doctors.pincode` indexed | Fast PIN-based search |
| PostGIS GiST | `doctors.location` GiST index | Fast radius queries |
| Phone Hash Index | `users.phone_hash` SHA256 | O(1) user lookup |

---

## 5. Migration Notes

The canonical schema is in `init-schema.sql` at repo root. Alembic manages incremental migrations:

```bash
# Run all migrations
cd backend && alembic upgrade head

# Check current version
alembic current

# Rollback one step
alembic downgrade -1
```

Baseline migration: `alembic/versions/001_baseline.py`
