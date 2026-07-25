# SoloPrac AI v2 — Comprehensive Product + Research Specification

> **Revision date:** 2026-07-18
> **Revision notes:** Scoped for realistic build (team of 4 with AI-assisted code generation). Retains all 6 research features (A–F) for IEEE paper. Adds extras that matter to a real solo GP. DICOM/OHIF deferred to future work. Lightweight patient portal (same app, different login) with real-time notifications and free OpenStreetMap integration.
> **Companion file:** `finalised_techstack.md` (stack reference unchanged — see §Stack for additions)

---

## 0. Project Thesis

**SoloPrac AI** is a multimodal, agentic clinical operating system for solo medical practitioners, built around a **version-controlled patient intelligence layer**.

The differentiating bet: *patient data is a versioned, immutable, time-travelable history* — every consultation mints a new version (like a Git commit), every AI suggestion is auditable, and every retrieval is temporally aware. This unlocks reproducible clinical reasoning, medico-legal traceability, and a research story no existing EMR offers.

**Audience:** Solo GPs, specialists, and small clinics in India and similar markets.
**Constraints:** Free-tier only stack. English + Hindi. RTX 3050 local dev. 4-person BTech final-year capstone → IEEE paper.
**Design principle:** Every feature earns its place by answering _"does a real solo GP need this to do their job better?"_

---

## 1. Architecture at a Glance

```
                    ┌────────────────────────────────────────────────────────────┐
                    │  React 19 + Vite + shadcn/ui + Tailwind                    │
                    │  Doctor app (/dashboard/*) · Patient portal (/patient/*)   │
                    │  Cmd+K · SSE streaming · Framer Motion                     │
                    └────────────────────┬───────────────────────────────────────┘
                                   │ HTTPS (Caddy)
                ┌──────────────────▼───────────────────────────────────────────┐
                │  FastAPI + Pydantic + SQLAlchemy + arq (Redis queue)         │
                │  ┌──────────────────────────────────────────────────────┐   │
                │  │  LangGraph main agent                              │   │
                │  │   ├─ Router (Llama-3.1-8B / NIM)                   │   │
                │  │   ├─ Synth (Llama-4-Maverick / NIM)                │   │
                │  │   ├─ Vision (Llama-3.2-90B / Groq)                 │   │
                │  │   ├─ Local VLM (MedGemma-4B / local)               │   │
                │  │   ├─ Image Reg (ORB + overlay subgraph)             │   │
                │  │   └─ Voice-Scheduling subgraph                      │   │
                │  └──────────────────────────────────────────────────────┘   │
                └──┬─────────┬─────────┬─────────┬─────────┬─────────────────┘
                   │         │         │         │         │
              ┌────▼──┐ ┌───▼───┐ ┌───▼───┐ ┌──▼───────┐ ┌▼─────────┐
              │Postgres│ │Qdrant │ │Redis │ │Langfuse  │ │Playwright│
              │RLS+pgc│ │hybrid │ │arq   │ │self-host │ │PDF render│
              └───────┘ └───────┘ └──────┘ └──────────┘ └──────────┘
```

---

## 2. Core Feature Modules

### Module 1 — Version-Controlled Patient Records ⭐ *core uniqueness*

Every write to a patient record mints a **new immutable version** with a content hash and a pointer to its parent. The current state of a patient is the head of the chain; history is fully reconstructable.

**Mechanics**
- Append-only `patient_versions` table.
- Content-addressed: `version_hash = sha256(canonical_json(patient_state))`.
- Every version stores `parent_version_id`, `author` (`doctor` | `agent:<name>`), `edit_type` (`manual` | `voice` | `ocr` | `ai_suggestion`), `summary`.
- Manual edits go through the same chain with `edit_type='manual'`.
- AI-suggested edits land as a *proposed* version requiring doctor approval before becoming head.

**APIs**
| Verb | Path | Purpose |
|------|------|---------|
| `GET`  | `/patients/{id}` | Current head state |
| `GET`  | `/patients/{id}/timeline` | Ordered list of versions with summaries |
| `GET`  | `/patients/{id}/at_version/{n}` | Reconstruct state at version `n` |
| `GET`  | `/patients/{id}/diff?v1=5&v2=7` | Field-level diff between two versions |
| `POST` | `/patients/{id}/revert/{n}` | Mint new version with state of version `n` |
| `PATCH`| `/patients/{id}/fields` | Field-level inline edit (optimistic locking on `updated_at`) |

**Frontend**
- **Git-like timeline scrubber** at the top of the patient view (Framer Motion).
  - Each version is a node with `author` color: blue = doctor, purple = agent, gray = OCR ingest.
  - Hover = popover with summary; click = body shows that historical state in read-only mode.
- "**Compare**" button → side-by-side diff highlighting added (green), removed (red), modified (yellow) fields.
- Mobile/tablet view collapses scrubber into a vertical accordion.

---

### Module 2 — Dynamic Agentic Router (LangGraph)

A single entry point that classifies user intent and dispatches to the right tool/model.

```
intent_router (Llama-3.1-8B)
    ├── retrieve_patient_context     → Qdrant hybrid
    ├── synthesize_response          → Maverick (NIM)
    ├── analyze_image                → MedGemma-4B local (primary) / Groq fallback
    ├── compare_images               → ORB feature matching subgraph
    ├── parse_document               → Docling / Surya / Nanonets-OCR2
    ├── generate_prescription_box    → Maverick + JSON schema
    ├── schedule_subgraph            → voice scheduling tools
    ├── generate_invoice             → Maverick + Jinja2 + Playwright
    ├── generate_certificate         → Maverick + Jinja2 + Playwright
    ├── propose_record_update        → Maverick → version draft
    └── generate_weekly_report       → Maverick + Jinja2 + ECharts + Playwright
```

All transitions stream to UI as agent-trace events ("Searching records… Analyzing image… Comparing wound photos… Drafting…").

---

### Module 3 — Multimodal RAG Console ⭐ *backbone of Feature A*

The doctor's primary chat surface. Backed by **Feature A** (Temporal Multimodal RAG — see §5).

- Text + image input.
- Streaming SSE response with inline citations to specific patient versions (`[v12 · 2026-03-14]`).
- Citation click = scrubber jumps to that version.
- Answers are *grounded* in retrieved versions + filtered to the active doctor's tenant.

---

### Module 4 — Image Registration for Clinical Comparison ⭐ *image domain requirement*

Patients with wounds, skin conditions, or visible symptoms get photographed at each visit. The system performs **ORB feature matching** between consecutive photos of the same patient to detect visual change over time.

**Pipeline**
```
Visit 1: Photo taken → stored + versioned (image vector embedded via BiomedCLIP)
Visit 2: New photo → ORB feature matching vs all prior photos of that patient
         ↓
Matches scored → best match identified
         ↓
Overlay generated: semi-transparent alignment of old + new image
         ↓
Side-by-side UI: Old | New | Overlay (with edge contours)
         ↓
Maverick generates clinical summary: "Wound area reduced 34% over 14 days.
         Edges approximating. No new inflammation."
         ↓
Summary saved as a versioned entry on the patient record
```

**What it enables for the paper:**
- Feature C (Cross-Modal Retrieval) — image embeddings from wound photos aligned to text descriptions.
- A concrete clinical use case: wound healing trajectory.
- Real image processing (ORB, homography, feature matching) — satisfies the image domain requirement.

**UI:**
- Compare view with 3 panels: Previous photo / Current photo / Overlay.
- Slider control to adjust overlay opacity.
- Automatically computed metrics: % area change, edge convergence score, color histogram shift.
- Button: "Update patient record with comparison note."

---

### Module 5 — Document Engine

Drop a file → automatically routed:

| Input | Pipeline |
|-------|---------|
| Typed PDF | Docling |
| Scanned PDF | Surya layout + Docling structure |
| Handwritten Rx | Nanonets-OCR2 → MedGemma fallback |
| Photo (jpg/png) | Surya + MedGemma re-check |

After parsing, content is converted to a **versioned patient record draft** (or scratchpad) and shown for doctor approval.

---

### Module 6 — Prescription Highlight Box ⭐ *signature print-ready artifact*

After consultation, Maverick generates a **structured Rx card** — print-ready, JSON-validated, rendered as a highlight box.

**JSON schema**

```json
{
  "patient_id": "uuid",
  "issued_at": "ISO-8601",
  "doctor_id": "uuid",
  "diagnosis_short": "string (≤120 chars)",
  "medications": [
    {
      "drug": "Metformin", "strength": "500 mg", "dose": "1 tablet",
      "frequency": "BD (twice daily)", "route": "PO",
      "duration": "30 days", "instructions": "After meals",
      "warnings": ["Avoid in renal impairment"]
    }
  ],
  "investigations": ["HbA1c after 4 weeks"],
  "lifestyle": ["Reduce refined carbs", "30 min brisk walk/day"],
  "follow_up": {"in_days": 30, "mode": "in-person"},
  "doctor_notes": "string",
  "ai_disclaimer_acknowledged": true
}
```

**Rendering**
- In-app: colored highlight box (yellow border, white interior) with medications as a table, key warnings in red pill badges.
- Print: Jinja2 → Playwright pipeline, A5 portrait, clinic letterhead, QR code → patient portal link.
- Always versioned + audit-logged.
- Disclaimer footer: *"AI-assisted draft — validated by Dr. <name>. Not a substitute for clinical judgement."*

---

### Module 7 — Invoice / Billing System

Tracks all patient billing within the system using the same PDF rendering pipeline as prescriptions.

**Data model**
```sql
CREATE TABLE invoices (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    appointment_id UUID REFERENCES appointments(id),
    invoice_number TEXT NOT NULL UNIQUE,  -- auto-generated, e.g. INV-2026-0001
    items JSONB NOT NULL,                 -- [{description, qty, rate, amount}]
    subtotal DECIMAL(10,2) NOT NULL,
    tax DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | paid | cancelled
    payment_method TEXT,                     -- cash | upi | card | insurance
    notes TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    pdf_path TEXT                           -- cached render
);
```

**UI**
- **Invoice list** in the right rail / a dedicated tab per patient.
- **Quick invoice:** doctor adds items (consultation fee, procedure, medicine), system auto-calculates totals.
- **Print:** same Jinja2 → Playwright pipeline. A5 portrait. Clinic letterhead. Invoice number + QR.
- **Status badge:** green (paid), yellow (pending), gray (cancelled).
- **Auto-generate from consultation:** after a consult, doctor can one-click generate an invoice.

**Integration with patient portal:**
- Patient logs in → sees their invoices.
- Can download PDF.
- Status shown: paid/pending.
- (Actual payment processing is out of scope — demo shows "Mark as paid".)

---

### Module 8 — Medical Certificate Generator

Doctor provides a template category → model extracts structure → generates PDF.

**Certificate types**
- Sick leave certificate (with diagnosis code, duration, recommended rest)
- Fitness certificate (post-illness return-to-work)
- Medical certificate for school/college
- Disability certificate support note

**Pipeline**
```
Doctor picks certificate type (or types free-text)
    ↓
Maverick with structured output + JSON Schema
    ↓
Validates against Pydantic model for the certificate type
    ↓
Jinja2 template → Playwright PDF (same pipeline as prescriptions)
    ↓
Versioned + audit-logged
    ↓
Delivered to patient portal inbox + downloadable
```

**UI controls per doctor setting:**
- Doctor can configure default templates (via `doctor_settings.certificate_templates`)
- Default signature, clinic stamp, registration number auto-populated
- QR code linking to verification URL on patient portal

---

### Module 9 — Calendar + Voice Scheduling (LangGraph Subgraph)

Full LangGraph subgraph with 9 tools. Voice-driven and text-driven.

**Tools**
```python
TOOLS = [
    find_available_slots(date_range, duration, prefer_morning=False),
    create_appointment(patient_id, slot, reason, send_notification=True),
    reschedule_appointment(appointment_id, new_slot, reason),
    cancel_appointment(appointment_id, reason, notify_patient=True),
    query_calendar_nl(natural_language_filter),
    bulk_reschedule(appointment_ids, new_window, notify_template),
    block_doctor_time(date_range, reason),
    smart_rearrange(date_range, optimization='minimize_patient_disruption'),
    find_optimal_window(constraints),
]
```

**Doctor config** (`doctor_settings` table):
- `working_hours_json` — per-weekday windows (e.g., `{"mon": [["09:00","13:00"], ["16:00","20:00"]]}`).
- `buffer_minutes_between_consults` (default 5).
- `default_consult_duration` (default 20).
- `auto_email_on_change` (bool).
- `patient_preference_decay_days` (default 180).

**Patient preference learning:** every confirmed appointment logs `(patient_id, weekday, hour_bucket)`. Histogram drives the `smart_rearrange` ranker.

**Five locked voice commands:**
1. *"Book Priya Sharma for Thursday 3 PM, fever follow-up."*
2. *"I'm off Friday and Saturday — handle it."* → blocks calendar, smart-rearranges, drafts emails.
3. *"When am I free 30 minutes next week before lunch?"* → top-3 ranked slots.
4. *"Move all diabetic follow-ups due this month to morning slots."* → NL filter → bulk reschedule.
5. *"Cancel Mrs. Patel's Wednesday appointment, she just called."*

**Scope is voice-only-for-scheduling.** All other voice queries politely redirected.

---

### Module 10 — Patient Web Portal ⭐ *lightweight, same app*

Patients access via `/patient/*` routes in the same React app. Separate login flow (Google OAuth for patients too, or email+OTP).

**Patient features:**

| Feature | Details |
|---------|---------|
| **Dashboard** | Upcoming appointments, recent reports, unread notifications |
| **Book appointment** | Search doctors by name/speciality, see available slots, book |
| **Doctor search with map** | OpenStreetMap tiles (free, no API key). Lat/lng radius query. Doctor cards show name, speciality, address, timings, rating. |
| **Medical reports** | Download prescriptions, invoices, certificates as PDF |
| **Inbox** | Receive notifications, reports, invoices, booking confirmations |
| **Notifications** | AI-generated messages (Maverick drafts content per event type). Real-time via WebSocket. |

**Notification system:**
- **Events:** appointment reminder (configurable n-hours before), new report available, invoice generated, certificate issued, booking confirmed, reschedule notification.
- **Content:** Maverick generates the natural-language message for each event. Nothing hardcoded.
- **Delivery:** In-app (WebSocket) + email (arq queue) + SMS (if doctor has Twilio or free SMS gateway — optional).
- **Doctor-controlled toggles:** Each notification type can be enabled/disabled per doctor via `doctor_settings.notification_preferences`.

```sql
CREATE TABLE patient_notifications (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    kind TEXT NOT NULL,              -- appointment_reminder | report_available | invoice_generated | booking_confirmed | rescheduled | certificate_issued
    subject TEXT NOT NULL,           -- AI-generated short subject line
    body TEXT NOT NULL,              -- AI-generated message body
    channel TEXT[] DEFAULT '{in_app}',  -- in_app | email | sms
    read BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Doctor search with OpenStreetMap:**
- Uses **Leaflet.js** (free, MIT license) with OpenStreetMap tile layer.
- No API key required. No cost.
- Backend stores doctor clinic lat/lng in `doctors.location` (PostGIS or plain `POINT`).
- Patient searches → backend queries nearby doctors within radius → results marked on map.
- Doctor cards below the map with details, click to book.

**Doctor settings for notification/booking toggles:**
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
  "max_future_booking_days": 30
}
```

---

### Module 11 — Auth + Multi-Tenancy + Security

Same layered approach from the original spec. See `finalised_techstack.md` §13 for full detail. Key points:

- **Dual auth:** Doctor login (Google OAuth + **Email/Password bcrypt**) + Patient login (Google OAuth or **phone OTP with SHA256 lookup**)
- **Doctor Verification:** Self-register → upload documents → admin approve/reject → verified badge
- **Admin Endpoints:** `GET/POST /admin/verifications/*` — pending list, approve, reject with reason
- **RLS on every patient-bearing table** with `doctor_id` isolation
- **users table has NO RLS** — intentionally cross-tenant for multi-clinic identity
- **Qdrant isolation:** every query has `must` filter on `doctor_id` at API layer
- **Append-only audit log** — every read/write/AI-suggestion/export logged
- **PII encryption:** pgcrypto for phone, email, address columns

---

## 3. Research Features (A–F) — Paper Contributions

Six features mapped to IEEE paper sections. Feature **A is primary**; B and C are co-equal; D, E, F are supporting.

---

### Feature A — Temporal Multimodal RAG ⭐ *primary contribution*

**Problem.** Standard medical RAG retrieves the most semantically similar chunks regardless of *when* the information was true. In a longitudinal record, this leaks future knowledge into past-state queries and underweights recent vitals.

**Formal definition.**
Given query `q` at time `t_q`, patient `p`, doctor `d`, retrieve top-`k` versions `V = {v_i}` from `patient_versions(p, d)` maximizing:

```
score(v_i, q, t_q) =
      α · cos(MedCPT(q), v_i.medical_text)
    + β · hybrid_bm25_dense(BGE-M3(q), v_i.hybrid, v_i.sparse)
    + γ · cos(NVCLIP(q_image), v_i.image)             [if query has image]
    + δ · temporal_decay(t_q − v_i.timestamp)
    + ε · clinical_significance(v_i)
subject to:  v_i.timestamp ≤ t_q
             v_i.doctor_id == d
```

with `temporal_decay(Δt) = exp(−Δt / τ)` (τ tuned per modality — vitals decay fast, family history slowly).

**Qdrant point layout:**
```json
{
  "id": "version_id",
  "vectors": {
    "medical_text": "float[768]",   # MedCPT
    "hybrid":       "float[1024]",  # BGE-M3 dense
    "image":        "float[512]"    # BiomedCLIP
  },
  "sparse": "bge_m3_sparse",
  "payload": {"patient_id", "doctor_id", "timestamp", "modality", "version_number",
              "clinical_significance", "version_hash"}
}
```

**Retrieval algorithm:**
```python
def temporal_multimodal_retrieve(q, t_q, patient_id, doctor_id, k=8):
    filt = Filter(must=[
        FieldCondition(key="patient_id", match=patient_id),
        FieldCondition(key="doctor_id", match=doctor_id),
        FieldCondition(key="timestamp", range=Range(lte=t_q)),
    ])
    text_hits   = qdrant.query("medical_text", MedCPT(q),    filter=filt, limit=4*k)
    hybrid_hits = qdrant.query("hybrid",       BGEM3(q),     filter=filt, limit=4*k)
    sparse_hits = qdrant.query_sparse(BGEM3_sparse(q),       filter=filt, limit=4*k)
    image_hits  = qdrant.query("image", NVCLIP(q_img),       filter=filt, limit=4*k) if q_img else []
    fused = reciprocal_rank_fusion([text_hits, hybrid_hits, sparse_hits, image_hits])
    for v in fused:
        v.score += DELTA * exp(-(t_q - v.timestamp).days / TAU[v.modality])
        v.score += EPS   * v.clinical_significance
    return sorted(fused, key=lambda v: -v.score)[:k]
```

**Evaluation:**
| Metric | Baseline | Target |
|--------|----------|--------|
| Recall@5 (time-correct) | BM25 / vanilla MedCPT | +15 pp |
| Future-leak rate | vanilla dense RAG | < 1 % |
| Latency p95 | — | < 600 ms |
| Answer faithfulness (LLM-judge) | — | > 0.85 |

**Datasets:** Synthetic longitudinal records generated from MIMIC-IV (de-identified) + curated multi-visit cases. Hindi cases via translation + clinician review.

---

### Feature B — Self-Planning Agent

**Problem.** Fixed agent prompts can't adapt sub-step ordering to query complexity.

**Approach.** LangGraph node `planner` (Maverick) emits a JSON plan; an `executor` runs steps; a `critic` decides re-plan or finish. Plans are logged to Langfuse for paper tables.

```json
{
  "goal": "answer doctor's question about Mrs. Sharma's BP trend",
  "steps": [
    {"id": 1, "tool": "retrieve_patient_context", "args": {...}},
    {"id": 2, "tool": "summarize_trend", "depends_on": [1]},
    {"id": 3, "tool": "draft_response", "depends_on": [2]}
  ],
  "budget_tokens": 4000
}
```

**Evaluation:** Steps-to-resolution vs. fixed pipeline; success rate on a held-out 100-query set.

---

### Feature C — Cross-Modal Retrieval with Contrastive Alignment

**Problem.** BiomedCLIP image embeddings (512d) live in a different space from BGE-M3 text embeddings (1024d), so true cross-modal search ("find prior wound photos similar to this symptom description") is weak.

**Approach.** Train a **linear projector** `W: ℝ^512 → ℝ^1024` on image–text pairs (CheXpert + curated wound photo dataset) with InfoNCE:

```
L = -log [ exp(sim(W·img, txt)/τ) / Σ_j exp(sim(W·img, txt_j)/τ) ]
```

At query time, project BiomedCLIP image embeddings into BGE-M3 space and search the `hybrid` vector — no second collection needed.

**Connection to Module 4:** Wound photos from the image registration feature feed this training pipeline. Every comparison generates a paired (image, doctor's summary text) sample.

**Evaluation:** Recall@k on held-out CheXpert + wound photo pairs; qualitative panel of 20 clinical cases.

---

### Feature D — Zero-Shot Schema Alignment

**Problem.** Every uploaded document (prescription, lab report, discharge summary) has a different schema.

**Approach.** Maverick with **structured output (JSON Schema)** receives raw OCR text + the canonical schema + 3 few-shot examples; emits a mapping. Validation: Pydantic. On validation failure → critic re-prompt → escalate to MedGemma if image-bearing.

**Evaluation:** Field-level F1 across 5 document types (Rx, lab, discharge, referral, imaging report), n ≥ 50 each.

---

### Feature E — Trajectory Clustering for Proactive Risk Alerts *(paper-simulated)*

**Problem.** Solo doctors miss slow deteriorations because they see patients episodically.

**Approach:**
1. **Trajectory embedding.** For each patient, compute a temporal embedding by mean-pooling `medical_text` vectors of the last `N` versions, concatenated with delta-vitals over a sliding window.
2. **Clustering.** HDBSCAN over the doctor's patient population → cohort labels.
3. **Anomaly detection.** When a patient's trajectory drifts > Mahalanobis distance `d_thresh` from their cluster centroid → alert.

**Implementation note:** Evaluated on synthetic data + simulation. Real-time alert WebSocket is stubbed for the paper — the algorithm is implemented and metrics are collected offline. UI shows a "Risk Alerts" panel but populated from simulated runs.

**Evaluation:** Precision of alerts (doctor-rated relevance, blinded); targeted recall on injected synthetic deteriorations.

---

### Feature F — Significance-Aware Weekly Reports

**Problem.** A weekly auto-summary email is useless if it lists every BP measurement. Doctors need a *clinically significant* digest.

**Significance scorer:**
```python
TIER_WEIGHTS = {
    "new_diagnosis"      : 1.0,
    "medication_change"  : 0.9,
    "abnormal_lab"       : 0.8,
    "ai_risk_alert"      : 0.75,
    "missed_appointment" : 0.5,
    "routine_visit"      : 0.2,
    "vitals_in_range"    : 0.05,
}
def clinical_significance(version):
    return max(TIER_WEIGHTS[tag] for tag in version.tags)
```

Versions below `0.3` are skipped in the weekly digest; above `0.75` get a colored callout.

**Three PDF layouts** (doctor picks per patient in settings):
1. **Executive** — 1 page, headline + top 3 changes + next-step suggestion.
2. **Clinical** — 2 pages, trend charts (ECharts SVG) + medication table + risk alerts.
3. **Family-friendly** — 1 page, plain-language summary + lifestyle tips + next appointment.

**Opt-out intelligence.** Patients who replied "stop" → automatically muted; doctor sees the muted list in dashboard.

**Evaluation:** Doctor rating of digest usefulness (Likert 1–5) vs. unfiltered baseline.

---

## 4. PostgreSQL Schema (canonical)

```sql
-- Users (cross-tenant identity, no RLS)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone TEXT NOT NULL,
    phone_hash CHAR(64) NOT NULL UNIQUE,  -- sha256(phone) for O(1) lookup
    name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON users(phone_hash);

-- Doctors (tenants)
CREATE TABLE doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name  TEXT NOT NULL,
    speciality TEXT DEFAULT 'General Practice',
    location GEOGRAPHY(POINT),                    -- for patient search/map
    clinic_name TEXT,
    clinic_address TEXT,
    phone TEXT,
    registration_number TEXT,
    password_hash TEXT,                            -- bcrypt for email/password auth
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    license_document_path TEXT,
    rejection_reason TEXT,
    verified_at TIMESTAMPTZ,
    settings JSONB NOT NULL DEFAULT '{}',         -- working_hours, buffers, notification_prefs, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Patients (head pointer only; state lives in versions)
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,  -- cross-clinic identity
    head_version_id UUID,                         -- current state pointer
    phone_enc BYTEA, email_enc BYTEA,             -- pgcrypto
    consent_for_share BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON patients(doctor_id);
CREATE INDEX ON patients(user_id);

-- Immutable version chain
CREATE TABLE patient_versions (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id  UUID NOT NULL REFERENCES doctors(id),
    parent_version_id UUID REFERENCES patient_versions(id),
    version_number INT NOT NULL,
    state_jsonb JSONB NOT NULL,                   -- full patient state at this version
    version_hash TEXT NOT NULL,                   -- sha256
    author TEXT NOT NULL,                         -- 'doctor:<id>' or 'agent:<name>'
    edit_type TEXT NOT NULL,                      -- manual|voice|ocr|ai_suggestion|revert
    summary TEXT,
    tags TEXT[] DEFAULT '{}',
    clinical_significance REAL,
    image_comparison JSONB,                       -- {matched_version_id, area_change_pct, overlay_path} — Module 4
    timestamp TIMESTAMPTZ NOT NULL,
    UNIQUE (patient_id, version_number)
);
CREATE INDEX ON patient_versions (patient_id, timestamp DESC);
CREATE INDEX ON patient_versions (doctor_id, timestamp DESC);

-- Prescription highlight boxes
CREATE TABLE prescription_boxes (
    id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES patient_versions(id),
    doctor_id  UUID NOT NULL REFERENCES doctors(id),
    rx_jsonb   JSONB NOT NULL,
    pdf_path   TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Invoices
CREATE TABLE invoices (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
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

-- Certificates
CREATE TABLE certificates (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    cert_type TEXT NOT NULL,                       -- sick_leave | fitness | school | disability | other
    cert_jsonb JSONB NOT NULL,                     -- structured certificate data
    pdf_path TEXT,
    verification_code TEXT UNIQUE,                 -- QR code payload
    issued_at TIMESTAMPTZ DEFAULT NOW()
);

-- Appointments
CREATE TABLE appointments (
    id UUID PRIMARY KEY,
    doctor_id  UUID NOT NULL REFERENCES doctors(id),
    patient_id UUID NOT NULL REFERENCES patients(id),
    start_at TIMESTAMPTZ NOT NULL,
    end_at   TIMESTAMPTZ NOT NULL,
    reason   TEXT,
    status   TEXT NOT NULL DEFAULT 'scheduled',    -- scheduled|done|cancelled|moved
    source   TEXT NOT NULL DEFAULT 'manual',       -- manual|voice|agent|patient_portal
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON appointments (doctor_id, start_at);
CREATE INDEX ON appointments (patient_id, start_at);

-- Patient time preferences (for smart schedule)
CREATE TABLE patient_time_preferences (
    patient_id UUID NOT NULL REFERENCES patients(id),
    weekday INT NOT NULL,                          -- 0–6
    hour_bucket INT NOT NULL,                      -- 0–23
    count INT NOT NULL DEFAULT 0,
    last_seen TIMESTAMPTZ,
    PRIMARY KEY (patient_id, weekday, hour_bucket)
);

-- Risk alerts (Feature E — simulated)
CREATE TABLE risk_alerts (
    id UUID PRIMARY KEY,
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    patient_id UUID NOT NULL REFERENCES patients(id),
    kind TEXT NOT NULL,                            -- trajectory_drift|anomaly
    reason TEXT NOT NULL,
    severity REAL NOT NULL,                        -- 0–1
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    acknowledged_by UUID,
    acknowledged_at TIMESTAMPTZ
);

-- Patient notifications (Module 10)
CREATE TABLE patient_notifications (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    doctor_id UUID NOT NULL REFERENCES doctors(id),
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    channel TEXT[] DEFAULT '{in_app}',
    read BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

    -- Append-only audit log (medico-legal)
    CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    doctor_id UUID NOT NULL,
    patient_id UUID,
    actor TEXT NOT NULL,                           -- doctor:<id> | patient:<id> | agent:<name> | system
    action TEXT NOT NULL,                          -- read|write|ai_suggest|approve|export|book|cancel
    resource_type TEXT NOT NULL,                   -- patient|version|appointment|rx|invoice|certificate|report
    resource_id UUID,
    payload_jsonb JSONB,
    ip_address INET,
    user_agent TEXT,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON audit_log (doctor_id, occurred_at DESC);

-- Row-Level Security
ALTER TABLE patients            ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_versions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescription_boxes  ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices            ENABLE ROW LEVEL SECURITY;
ALTER TABLE certificates        ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_alerts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_notifications ENABLE ROW LEVEL SECURITY;

-- Policy template
CREATE POLICY tenant_isolation ON patients
  USING (doctor_id = current_setting('app.current_doctor_id')::uuid);
-- Same policy applied to all other tenant-scoped tables.
```

---

## 5. Revised 16-Week Roadmap

| Week | Milestone | Owner |
|:----:|-----------|:-----:|
| 1 | Repo bootstrap, Docker Compose skeleton (FastAPI + Postgres + Qdrant + Redis + Langfuse + Caddy + Playwright) | **All** |
| 2 | Auth (Google OAuth + Email/Password + JWT + OTP), RLS policies, audit log scaffolding. Patient seed data. | **A** (backend) |
| 3 | Patient + versioning core (`patient_versions`, hash chain, head pointer, diff endpoint, revert) | **A** |
| 4 | Frontend: patient list + timeline scrubber (read-only first) + inline-edit + Cmd+K shell | **C** (frontend) |
| 5 | LangGraph main agent + Llama-3.1-8B router + Maverick synth (NIM wired). Streaming SSE. | **B** (AI/ML) |
| 6 | Embeddings (MedCPT + BGE-M3 + BiomedCLIP) + Qdrant named-vector ingest + hybrid search | **B** |
| 7 | **Feature A** — Temporal Multimodal RAG (search, fusion, decay, evaluation harness) | **B** |
| 8 | Document engine (Docling + Surya + Nanonets-OCR2 + MedGemma fallback) + Scratchpad chatbot | **D** (integrations) |
| 9 | **Module 4** — Image registration (ORB feature matching, overlay UI, clinical summary). Connect to version chain. | **B + D** |
| 10 | Prescription Highlight Box + Invoice/Billing + Medical Certificates (shared Jinja2 → Playwright pipeline) | **C + D** |
| 11 | Calendar core (tools 1–4) + email queue + working-hours config + patient preference logging | **A + D** |
| 12 | Voice scheduling subgraph (ASR + intent + tools 5–9 + TTS confirmation) | **D** (with B) |
| 13 | Patient web portal (search doctors with OSM map, book, view reports, inbox + real-time notifications) | **C** (with A) |
| 14 | **Feature B** eval (100-query set), **Feature C** projector training (CheXpert + wound pairs), **Feature E** simulation | **B** (with D) |
| 15 | **Feature D** eval (5 doc types × 50 each), **Feature F** weekly report evaluation. IEEE paper draft started. | **All** |
| 16 | IEEE paper final + Langfuse-pulled metrics + figures. Demo recording. Doctor feedback session. Deployment. | **All** |

---

## 6. Updated Consolidated Tech Stack

| Layer | Choice | Free? | Notes |
|-------|--------|:-----:|-------|
| **Frontend** | React 19 + Vite + TS + shadcn/ui + Tailwind + Framer Motion + TanStack Query + Zustand + cmdk | ✅ | — |
| **Maps** | Leaflet.js + OpenStreetMap tiles | ✅ | No API key needed. MIT license. |
| **Backend** | FastAPI + Pydantic + SQLAlchemy + arq (Redis queue) | ✅ | — |
| **Agent** | LangGraph (main graph + voice-scheduling subgraph + image-reg subgraph) | ✅ | MIT license |
| **Relational DB** | PostgreSQL 16 + PostGIS + Row-Level Security + pgcrypto | ✅ | — |
| **Vector DB** | Qdrant (named vectors, hybrid dense+sparse) | ✅ | Docker, free tier |
| **Queue/Cache** | Redis | ✅ | — |
| **Observability** | Langfuse (self-hosted Docker) | ✅ | — |
| **Reverse proxy** | Caddy (auto-HTTPS) | ✅ | — |
| **LLM (heavy)** | Llama-4-Maverick-17B-128E via NVIDIA NIM | ✅ | Free tier |
| **LLM (router)** | Llama-3.1-8B via NIM | ✅ | — |
| **VLM (general)** | MedGemma-4B-IT local (primary) / Groq fallback | ✅ | Medical VLM; Rad/Derm routed local, general routed to Groq |
| **VLM (medical)** | MedGemma-4B-IT local (RTX 3050) | ✅ | Research/academic free |
| **ASR** | faster-whisper large-v3 + AI4Bharat IndicWhisper | ✅ | Apache 2.0 |
| **TTS** | AI4Bharat Indic-Parler-TTS | ✅ | Apache 2.0 |
| **Embeddings (medical)** | MedCPT (ncbi) | ✅ | 768d |
| **Embeddings (hybrid)** | BGE-M3 (BAAI) | ✅ | 1024d dense + sparse |
| **Embeddings (image)** | BiomedCLIP (Microsoft) | ✅ | 512d; MIT license, SOTA medical retrieval |
| **OCR (typed)** | Docling (IBM) | ✅ | Apache 2.0 |
| **OCR (scanned)** | Surya | ✅ | — |
| **OCR (handwritten)** | Nanonets-OCR2-1.5B-exp | ✅ | Apache 2.0; free, better than GOT-OCR |
| **PDF output** | Jinja2 + Tailwind (inlined) + ECharts SVG + Playwright | ✅ | — |
| **Image registration** | ORB (OpenCV) + homography + overlay | ✅ | BSD license |
| **Auth** | Google OAuth + JWT + Email/Password (bcrypt) + OTP | ✅ | Dual auth for doctors + patients |
| **Deploy** | Docker Compose → Oracle Cloud Free Tier (4 ARM + 24GB) | ✅ | — |
| **Research paper** | LaTeX IEEEtran | ✅ | — |

---

## 7. Team Division

| Person | Primary | Secondary | Also helps with |
|--------|---------|-----------|----------------|
| **A** | Backend core (FastAPI, Postgres schema, version chain, auth, RLS, audit log) | Docker + deployment | Calendar backend, patient portal APIs |
| **B** | AI/ML (LangGraph, LLM routing, RAG pipeline, embeddings, MedGemma, Feature C projector) | Image processing pipeline | Evaluation harness, Langfuse metrics |
| **C** | Frontend — Doctor app (React, timeline scrubber, chat UI, Cmd+K, prescription/invoice/certificate UI) | Patient portal frontend | Connecting APIs to backend |
| **D** | Integrations (OCR pipeline, voice ASR+TTS, PDF generation pipeline, notifications, Leaflet map) | Calendar backend | Image registration pipeline |

---

## 8. New/Revised API Endpoints

Beyond the Module 1 patient endpoints, the following are added:

### Invoices
| Verb | Path | Purpose |
|------|------|---------|
| `GET` | `/patients/{id}/invoices` | List invoices for a patient |
| `POST` | `/patients/{id}/invoices` | Generate new invoice |
| `GET` | `/invoices/{id}` | Get invoice detail |
| `GET` | `/invoices/{id}/pdf` | Download invoice PDF |
| `PATCH`| `/invoices/{id}/status` | Mark paid/cancelled |

### Certificates
| Verb | Path | Purpose |
|------|------|---------|
| `POST` | `/patients/{id}/certificates` | Generate certificate |
| `GET` | `/patients/{id}/certificates` | List certificates |
| `GET` | `/certificates/{id}` | Get certificate detail |
| `GET` | `/certificates/{id}/pdf` | Download certificate PDF |
| `GET` | `/certificates/verify/{code}` | Public verification endpoint |

### Image Registration
| Verb | Path | Purpose |
|------|------|---------|
| `POST` | `/patients/{id}/images` | Upload image (triggers ORB matching + overlay) |
| `GET` | `/patients/{id}/images/comparisons` | List all image comparisons |
| `GET` | `/patients/{id}/images/{image_id}/overlay` | Get overlay image for comparison |
| `GET` | `/patients/{id}/images/comparison/{comparison_id}` | Get comparison detail |

### Patient Portal (Public)
| Verb | Path | Purpose |
|------|------|---------|
| `GET` | `/api/public/doctors?lat={}&lng={}&radius={}` | Search doctors by location |
| `GET` | `/api/public/doctors/{id}` | Doctor detail + available slots |
| `POST` | `/api/public/appointments` | Patient books appointment |
| `GET` | `/api/patient/me/inbox` | Patient notifications |
| `GET` | `/api/patient/me/reports` | Patient reports (Rx, invoices, certificates) |
| `GET` | `/api/patient/me/appointments` | Patient's appointments |

### Real-Time Notifications
| Verb | Path | Purpose |
|------|------|---------|
| `WS` | `/ws/patient/{patient_id}` | WebSocket for patient real-time notifications |
| `WS` | `/ws/doctor/{doctor_id}` | WebSocket for doctor real-time alerts |

---

## 9. Ethics & Disclaimer Layer (unchanged from original)

- **Persistent banner** on every AI-generated surface: *"AI Suggestion — Requires Doctor Validation."*
- **Two-step confirm** before any patient-facing email, prescription print, or external share.
- **Disclaimer footer** on every prescription, invoice, certificate, and weekly report PDF.
- **Patient consent flag** stored on the patient record before any external share.
- **No autonomous outbound messages** without a doctor-approved template.
- **Right-to-be-forgotten:** patient deletion is a tombstone version + Qdrant payload purge.

---

## 10. What's Deferred / Cut vs. Original

| Original Feature | Decision | Justification |
|-----------------|:--------:|---------------|
| DICOM integration (pydicom + Orthanc) | **Deferred** | Solo GPs don't use DICOM. Refer to radiologist. |
| OHIF Viewer | **Deferred** | Would add 50K+ lines of code for zero GP benefit. |
| Trajectory clustering real-time WebSocket (Feature E) | **Implemented** | Algorithm + offline eval for the paper; live scan runs over real patients on an arq cron and pushes alerts to the doctor dashboard via WebSocket. |
| Cross-modal projector full training pipeline (Feature C) | **Partial** | Linear projector trained + evaluated. Production integration deferred. |
| SMS notifications | **Deferred** | Requires paid gateway. Email + in-app covers it. |
| Payment processing integration | **Deferred** | In-app "mark as paid" suffices for demo. |
| Everything else from v1 | **Kept** | Version chain, RAG, agent, voice, calendar, docs, images, Rx, portal, billing, certificates |

---

## 11. Key Design Decisions (v2)

1. **Same app, separate routes** — Patient portal lives under `/patient/*` in the same React build. Shared components. No separate deployment.
2. **Leaflet.js + OpenStreetMap** — Zero cost, no API key, MIT license. Tile layers from OpenStreetMap's free CDN. Backend uses PostGIS geography queries for radius search.
3. **WebSocket for real-time** — Simple WebSocket server in FastAPI (no external service needed). Patients subscribe via `/ws/patient/{patient_id}`. Doctor gets `/ws/doctor/{doctor_id}` for risk alerts.
4. **AI-generated notifications** — Maverick drafts each notification message per event type with patient context. Nothing is hardcoded. Doctor can toggle each notification type.
5. **ORB-based image registration** — OpenCV's ORB (Oriented FAST and Rotated BRIEF) is free, fast, and runs CPU. Feature matching via BFMatcher + Lowe's ratio test. Homography computed via RANSAC.
6. **Shared PDF pipeline** — Prescriptions, invoices, certificates all use the same Jinja2 → Playwright → PDF pipeline. Reduces code duplication. Doctor controls templates via settings.
7. **Shared agent infrastructure** — All tools (RAG, image compare, document parse, PDF generate) are nodes on the same LangGraph. The router dispatches based on intent classification.
