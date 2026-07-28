# SoloPrac AI — Comprehensive Product + Research Specification

> **Revision date:** 2026-07-28
> **Revision notes:** All core features built and tested. Auth simplified to email+password (Google OAuth removed). Patient portal uses email+password (not OTP). Added: profile photos, voice-to-text, OCR quality alerts, document timeline, patient PDF downloads, state-specific prescriptions, PIN code search, telemedicine consent, DPDP consent management, NMC verification, Hindi UI, offline PWA, Sentry error tracking, backup system, multi-device sessions. Lab alerts removed (intentionally skipped — hardcoded reference ranges are useless for solo doctors). Research section intentionally skipped compared with RAG-Based CDSS project.
> **Companion file:** `finalised_techstack.md` (stack reference unchanged)

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
                    │  React 19 + Vite + shadcn/ui + Tailwind + i18n + PWA      │
                    │  Doctor app (/dashboard/*) · Patient portal (/patient/*)   │
                    │  Cmd+K · SSE streaming · Framer Motion · Offline Support   │
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
                │  │   ├─ Voice-Scheduling subgraph                      │   │
                │  │   └─ Voice-to-Text (faster-whisper + IndicWhisper)  │   │
                │  └──────────────────────────────────────────────────────┘   │
                └──┬─────────┬─────────┬─────────┬─────────┬─────────────────┘
                   │         │         │         │         │
              ┌────▼──┐ ┌───▼───┐ ┌───▼───┐ ┌──▼───────┐ ┌▼─────────┐
              │Postgres│ │Qdrant │ │Redis │ │MinIO S3  │ │Langfuse  │
              │RLS+pgc│ │hybrid │ │arq   │ │Object    │ │+Sentry   │
              └───────┘ └───────┘ └──────┘ └──────────┘ └──────────┘
```

---

## 2. Auth Model (Revised)

**Google OAuth removed.** Auth is email+password only for both doctors and patients.

### Doctor Auth
- Email + password (bcrypt hashing)
- HttpOnly cookies (`access_token`) — not accessible via JavaScript (XSS-safe)
- JWT with short-lived access tokens + refresh token rotation
- Middleware reads `Authorization` header first, falls back to `access_token` cookie
- Registration at `/register` — requires name, email, phone, clinic_name, clinic_address, password

### Patient Auth
- Email + password (bcrypt hashing) — same as doctor auth
- Separate `patient_token` cookie (isolated from doctor session)
- `get_current_user` reads `patient_token` cookie as fallback
- Walk-in patients (no account) can still be booked by doctor — `user_id=NULL`

### Session Management
- `DoctorSession` model tracks: device_info, ip_address, last_active_at
- `GET /auth/me/sessions` — list active sessions
- `DELETE /auth/me/sessions/{session_id}` — revoke specific session
- Sessions revoked on logout

---

## 3. Core Feature Modules

### Module 1 — Version-Controlled Patient Records ⭐ *core uniqueness*

Every write to a patient record mints a **new immutable version** with a content hash and a pointer to its parent. The current state of a patient is the head of the chain; history is fully reconstructable.

**Mechanics**
- Append-only `patient_versions` table.
- Content-addressed: `version_hash = sha256(canonical_json(patient_state))`.
- Every version stores `parent_version_id`, `author` (`doctor` | `agent:<name>`), `edit_type` (`manual` | `voice` | `ocr` | `ai_suggestion` | `revert`), `summary`.
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
| `GET`  | `/patients/{id}/documents` | Unified document timeline (prescriptions, invoices, certificates, uploads) |

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
- **Voice-to-text mic button** — faster-whisper (English) + IndicWhisper (Hindi) for hands-free input.

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

---

### Module 5 — Document Engine

Drop a file → automatically routed:

| Input | Pipeline |
|-------|---------|
| Typed PDF | Docling |
| Scanned PDF | Surya layout + Docling structure |
| Handwritten Rx | Nanonets-OCR2 → MedGemma fallback |
| Photo (jpg/png) | Surya + MedGemma re-check |

**OCR Quality Alerts** — Before processing, `_check_image_quality()` on `ParserRouter` detects:
- **Blur** (Laplacian variance < 100 severe / < 300 moderate)
- **Low contrast** (std dev < 20 severe / < 35 moderate)
- **Brightness issues** (< 50 too dark / > 230 too bright)
- **Low resolution** (< 500×500 px)

Quality warnings shown as amber alerts in the Scratchpad file list and review dialog.

After parsing, content is converted to a **versioned patient record draft** (or scratchpad) and shown for doctor approval.

---

### Module 6 — Prescription Highlight Box ⭐ *signature print-ready artifact*

After consultation, Maverick generates a **structured Rx card** — print-ready, JSON-validated, rendered as a highlight box. Doctor approves prescription to create new patient version.

**Voice-to-Text Integration:**
- Mic buttons on diagnosis and instructions fields in PrescriptionBox
- Press mic → MediaRecorder records audio → sends to `POST /api/v1/voice/transcribe` → text fills field
- Returns 503 with guidance if ASR model not installed
- Supports Hindi (IndicWhisper) + English (faster-whisper)

**Rendering**
- In-app: colored highlight box (yellow border, white interior) with medications as a table, key warnings in red pill badges.
- Print: Jinja2 → Playwright pipeline, A5 portrait, clinic letterhead, QR code → patient portal link.
- **State-specific:** Doctor's `state` setting controls regulatory header/footer text (24 Indian states supported).
- Always versioned + audit-logged.
- Disclaimer footer: *"AI-assisted draft — validated by Dr. <name>. Not a substitute for clinical judgement."*

---

### Module 7 — Invoice / Billing System

Tracks all patient billing within the system using the same PDF rendering pipeline as prescriptions.

**UI**
- **Invoice list** in the right rail / a dedicated tab per patient.
- **Quick invoice:** doctor adds items (consultation fee, procedure, medicine), system auto-calculates totals.
- **Print:** same Jinja2 → Playwright pipeline. A5 portrait. Clinic letterhead. Invoice number + QR.
- **Status badge:** green (paid), yellow (pending), gray (cancelled).
- **Auto-generate from consultation:** after a consult, doctor can one-click generate an invoice.

**Patient Portal Integration:**
- Patient logs in → sees their invoices.
- Can download PDF via `GET /patient/me/invoices/{id}/pdf`.
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

**Patient Portal Integration:**
- Patient downloads certificates via `GET /patient/me/certificates/{id}/pdf`
- Verification code for authenticity check

---

### Module 9 — Calendar + Voice Scheduling (LangGraph Subgraph)

Full LangGraph subgraph with 9 tools. Voice-driven and text-driven.

**Booking Dialog (Calendar.tsx):**
- Click empty time slot → opens booking modal
- Patient search (debounced `/patients/search`) with photo, name, age, gender, phone
- Date/time pickers, duration selector, reason textarea
- Empty cells are clickable to pre-fill time

**Race Condition Protection:**
- `SELECT FOR UPDATE` on doctor row before conflict check in `create_appointment()`
- Prevents double-booking when two requests hit simultaneously

**Booking Concurrency:**
- `CREATE UNIQUE INDEX idx_unique_active_booking ON appointments (doctor_id, start_at) WHERE status = 'scheduled'`

**Doctor config** (`doctor_settings` table):
- `working_hours_json` — per-weekday windows.
- `buffer_minutes_between_consults` (default 5).
- `default_consult_duration` (default 20).
- `auto_email_on_change` (bool).
- `patient_preference_decay_days` (default 180).
- `state` — controls state-specific prescription regulatory text.

**Five locked voice commands:**
1. *"Book Priya Sharma for Thursday 3 PM, fever follow-up."*
2. *"I'm off Friday and Saturday — handle it."* → blocks calendar, smart-rearranges, drafts emails.
3. *"When am I free 30 minutes next week before lunch?"* → top-3 ranked slots.
4. *"Move all diabetic follow-ups due this month to morning slots."* → NL filter → bulk reschedule.
5. *"Cancel Mrs. Patel's Wednesday appointment, she just called."*

**Scope is voice-only-for-scheduling.** All other voice queries politely redirected.

---

### Module 10 — Patient Web Portal ⭐ *lightweight, same app*

Patients access via `/patient/*` routes in the same React app. Email+password login.

**Patient features:**

| Feature | Details |
|---------|---------|
| **Dashboard** | Upcoming appointments, recent reports, unread notifications |
| **Book appointment** | Search doctors by name/speciality/PIN, see available slots, book with telemedicine consent |
| **Doctor search with map** | OpenStreetMap tiles (free, no API key). PostGIS radius search. PIN code search. Doctor cards show photo, name, speciality, address, years of experience, distance. |
| **Medical reports** | Download prescriptions, invoices, certificates as PDF |
| **Document Timeline** | Unified chronological view with version citations, color-coded icons |
| **Inbox** | Receive notifications, reports, invoices, booking confirmations |
| **Notifications** | AI-generated messages (Maverick drafts content per event type). Real-time via WebSocket. |
| **Consent Management** | DPDP-compliant: view consent, update preferences, request data erasure |

**Telemedicine Consent:**
- Appointment booking includes telemedicine consent checkbox
- `telemedicine_consent` + `telemedicine_consent_at` on Appointment model
- Patient explicitly agrees before booking

**Doctor search with PostGIS:**
- Backend stores doctor clinic lat/lng in `doctors.location` (PostGIS GEOGRAPHY POINT)
- `pincode` column on Doctor model (indexed) for PIN-based search
- `ST_Distance` computes real geographic distance
- `radius_km` parameter (default 10, min 1, max 100)
- Results sorted by distance, showing `distance_km`
- Frontend DoctorSearch shows photo, years experience, distance

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
  "max_future_booking_days": 30,
  "state": "Maharashtra"
}
```

---

### Module 11 — Auth + Multi-Tenancy + Security

**Auth (Revised — no Google OAuth):**
- Doctor: email + password (bcrypt) → HttpOnly cookie
- Patient: email + password (bcrypt) → HttpOnly cookie
- Separate cookies: `access_token` (doctor) vs `patient_token` (patient)
- Middleware reads `Authorization` header first, falls back to cookies

**Doctor Verification:**
- Self-register → upload documents → admin approve/reject → verified badge
- NMC verification: `NMC_API_URL` + `NMC_API_KEY` env vars
  - When set: verifies registration number against NMC API
  - When empty (localhost): verifies directly, marks as `pending_verification`
- `year_of_registration` → `years_experience` computed dynamically (current_year - year_of_registration)

**Admin Endpoints:** `GET/POST /admin/verifications/*` — pending list, approve, reject with reason

**RLS on every patient-bearing table** with `doctor_id` isolation

**users table has NO RLS** — intentionally cross-tenant for multi-clinic identity

**Qdrant isolation:** every query has `must` filter on `doctor_id` at API layer

**PII De-identification (Defense-in-Depth):**
- `strip_pii()` at indexer, tools, and synthesizer boundaries
- `pseudonymize_id()` for LLM context (never send real names to LLM)

**Append-only audit log** — every read/write/AI-suggestion/export logged

**PII encryption:** pgcrypto for phone, email, address columns

**DPDP Compliance:**
- `ConsentRecord` model — tracks consent granted/revoked
- `GET /patient/me/consent` — view current consent
- `PUT /patient/me/consent` — update consent preferences
- `DELETE /patient/me` — data erasure (anonymizes PII, preserves clinical records for medico-legal)

---

## 4. Research Features (A–F) — Paper Contributions

Six features mapped to IEEE paper sections. Feature **A is primary**; B and C are co-equal; D, E, F are supporting.

> **Note:** Features D and F in the evaluation endpoints return `{"status": "requires_manual_evaluation"}` — they require human evaluation (doctor feedback) and cannot be fully automated.

---

### Feature A — Temporal Multimodal RAG ⭐ *primary contribution*

**Problem.** Standard medical RAG retrieves the most semantically similar chunks regardless of *when* the information was true.

**Formal definition.**
Given query `q` at time `t_q`, patient `p`, doctor `d`, retrieve top-`k` versions maximizing:

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

**Evaluation:**
| Metric | Baseline | Target |
|--------|----------|--------|
| Recall@5 (time-correct) | BM25 / vanilla MedCPT | +15 pp |
| Future-leak rate | vanilla dense RAG | < 1 % |
| Latency p95 | — | < 600 ms |
| Answer faithfulness (LLM-judge) | — | > 0.85 |

---

### Feature B — Self-Planning Agent

**Problem.** Fixed agent prompts can't adapt sub-step ordering to query complexity.

**Approach.** LangGraph node `planner` (Maverick) emits a JSON plan; an `executor` runs steps; a `critic` decides re-plan or finish. Plans are logged to Langfuse for paper tables.

**Evaluation:** Steps-to-resolution vs. fixed pipeline; success rate on a held-out 100-query set.

---

### Feature C — Cross-Modal Retrieval with Contrastive Alignment

**Problem.** BiomedCLIP image embeddings (512d) live in a different space from BGE-M3 text embeddings (1024d).

**Approach.** Train a **linear projector** `W: R^512 → R^1024` on image–text pairs with InfoNCE loss.

**Evaluation:** Recall@k on held-out CheXpert + wound photo pairs.

---

### Feature D — Zero-Shot Schema Alignment

**Problem.** Every uploaded document has a different schema.

**Approach.** Maverick with structured output + critic loop. Evaluation requires manual doctor review — endpoint returns `{"status": "requires_manual_evaluation"}`.

**Evaluation:** Field-level F1 across 5 document types (requires clinician labeling).

---

### Feature E — Trajectory Clustering for Proactive Risk Alerts

**Problem.** Solo doctors miss slow deteriorations.

**Approach.** HDBSCAN clustering + Mahalanobis distance on clinical embeddings. Real-time scan runs over patients on arq cron, pushes alerts to doctor dashboard via WebSocket.

**Evaluation:** Precision on injected synthetic deteriorations.

---

### Feature F — Significance-Aware Weekly Reports

**Problem.** Weekly auto-summary is useless if it lists every measurement.

**Approach.** Clinical significance tier scoring. Three PDF layouts (Executive, Clinical, Family-friendly). Evaluation requires doctor Likert ratings — endpoint returns `{"status": "requires_manual_evaluation"}`.

---

## 5. PostgreSQL Schema (canonical)

See `init-schema.sql` and `alembic/versions/001_baseline.py` for the full schema.

**Key tables:**
- `users` — cross-tenant identity (email, password_hash, name, demographics)
- `doctors` — tenants (email, password_hash, clinic info, pincode, location, photo_url, verification, state)
- `patients` — per-doctor medical records (user_id FK for cross-clinic identity)
- `patient_versions` — immutable version chain
- `prescription_boxes` — structured Rx data
- `invoices` — billing
- `certificates` — medical certificates
- `appointments` — scheduling (with telemedicine_consent)
- `patient_time_preferences` — smart scheduling
- `risk_alerts` — Feature E alerts
- `patient_notifications` — AI-generated notifications
- `consent_records` — DPDP consent tracking
- `doctor_sessions` — multi-device session tracking
- `audit_log` — append-only audit trail

**Row-Level Security** enabled on all patient-bearing tables with `doctor_id` isolation.

---

## 6. India-Specific Features

| Feature | Implementation |
|---------|---------------|
| **State-specific prescriptions** | `STATE_PRESCRIPTION_OVERRIDES` dict with 24 states' regulatory header/footer text |
| **PIN code search** | `pincode` column on Doctor (indexed), search endpoint, frontend input |
| **Telemedicine consent** | Checkbox in booking flow, stored on appointment |
| **NMC verification** | `NMC_API_URL` + `NMC_API_KEY` env vars; fallback to admin review |
| **Hindi UI** | react-i18next with `en.json` + `hi.json`; language switcher in UserMenu |
| **Doctor profile photo** | Upload + oval crop with drag/zoom; served via MinIO presigned URL |
| **Years experience** | Computed from `year_of_registration` — zero maintenance |
| **Walk-in patient linking** | Auto-links existing walk-in patients (user_id=NULL) to users by phone |
| **Phone normalization** | `normalize_phone()` strips formatting, takes last 10 digits |
| **Booking race condition** | `SELECT FOR UPDATE` on doctor row prevents double-booking |
| **Offline PWA** | vite-plugin-pwa with Workbox caching (NetworkFirst for API routes) |
| **Sentry error tracking** | Backend + frontend, opt-in via `SENTRY_DSN` env var |
| **Backup system** | `POST /admin/backup` → pg_dump to MinIO; `GET /admin/backups` → list |

---

## 7. What's Implemented vs. Deferred

| Feature | Status | Notes |
|---------|:------:|-------|
| Version-controlled records | **Done** | Immutable chain, diff, revert, timeline |
| LangGraph agent | **Done** | Router + tools + streaming |
| Temporal RAG (Feature A) | **Done** | MedCPT + BGE-M3 + BiomedCLIP + temporal decay |
| Self-Planning Agent (Feature B) | **Done** | Plan-execute-critic loop |
| Cross-Modal Retrieval (Feature C) | **Done** | Linear projector + InfoNCE |
| Schema Alignment (Feature D) | **Done** | Requires manual evaluation |
| Trajectory Clustering (Feature E) | **Done** | HDBSCAN + Mahalanobis + WebSocket alerts |
| Significance Reports (Feature F) | **Done** | Requires manual evaluation |
| Document Engine (OCR) | **Done** | Docling + Surya + Nanonets-OCR2 + quality alerts |
| Voice Scheduling | **Done** | 5 commands Hindi+English |
| Voice-to-Text (PrescriptionBox) | **Done** | Mic buttons on diagnosis + instructions |
| Voice-to-Text (ChatUI) | **Done** | Mic button for chat input |
| Prescription Box | **Done** | AI draft + JSON validation + PDF + state-specific |
| Invoice/Billing | **Done** | Line items + PDF + QR |
| Medical Certificates | **Done** | Templates + PDF + verification |
| Calendar + Booking | **Done** | Weekly view + booking dialog + race protection |
| Patient Portal | **Done** | Search + book + reports + consent + data erasure |
| Doctor Search | **Done** | PostGIS radius + PIN code + photo + years experience |
| Doctor Profile Photo | **Done** | Upload + oval crop + MinIO storage |
| NMC Verification | **Done** | Registration number + state council + year |
| DPDP Consent | **Done** | ConsentRecord + patient endpoints |
| Data Erasure | **Done** | Anonymize PII, preserve clinical records |
| Multi-Device Sessions | **Done** | List + revoke sessions |
| Hindi UI | **Done** | react-i18next + translation files |
| Offline PWA | **Done** | Service worker + Workbox caching |
| Sentry Error Tracking | **Done** | Backend + frontend |
| Backup System | **Done** | pg_dump → MinIO |
| MapPicker (Settings) | **Done** | OpenStreetMap + Nominatim + geolocation |
| Image Registration (ORB) | **Done** | Feature matching + overlay + clinical summary |
| **Lab Alerts** | **Removed** | Hardcoded reference ranges are useless |
| **Indian Drug Database** | **Skipped** | Doctor photographs prescription; OCR+LLM extracts; LLM handles misspellings natively |
| **Research Section** | **Skipped** | Compared with RAG-Based CDSS; solo doctors don't do research |
| **DICOM/OHIF** | **Deferred** | Solo GPs don't use DICOM |
| **Payment Gateway** | **Deferred** | "Mark as paid" suffices |
| **SMS Notifications** | **Deferred** | Email + in-app covers it |

---

## 8. Revised 16-Week Roadmap

| Week | Milestone | Status |
|:----:|-----------|:------:|
| 1 | Repo bootstrap, Docker Compose skeleton | **Done** |
| 2 | Auth (email+password, HttpOnly cookies), RLS, audit log | **Done** |
| 3 | Patient + versioning core | **Done** |
| 4 | Frontend: timeline scrubber, inline edit, Cmd+K | **Done** |
| 5 | LangGraph agent + Maverick synth + SSE streaming | **Done** |
| 6 | Embeddings (MedCPT + BGE-M3 + BiomedCLIP) + Qdrant | **Done** |
| 7 | Feature A — Temporal Multimodal RAG | **Done** |
| 8 | Document engine + OCR quality alerts + Scratchpad | **Done** |
| 9 | Image registration (ORB, overlay, clinical summary) | **Done** |
| 10 | Prescription Box + Invoice + Certificates + state-specific Rx | **Done** |
| 11 | Calendar core + booking dialog + race protection | **Done** |
| 12 | Voice scheduling + voice-to-text (PrescriptionBox + ChatUI) | **Done** |
| 13 | Patient portal + doctor search + PIN + telemedicine consent | **Done** |
| 14 | Profile photos + NMC verification + DPDP + Hindi UI + PWA + Sentry + backup + sessions | **Done** |
| 15 | Integration testing + bug fixes + code audit | **Done** |
| 16 | IEEE paper + demo + deployment | **In Progress** |

---

## 9. Key Design Decisions

1. **Same app, separate routes** — Patient portal lives under `/patient/*` in the same React build.
2. **Email+password only** — Google OAuth removed. Simpler, no third-party dependency.
3. **HttpOnly cookies** — XSS-safe auth. Middleware reads cookies as fallback.
4. **PII de-identification is defense-in-depth** — strip at indexer, tools, synthesizer boundaries.
5. **Doctor photographs prescription** — No Indian drug database. LLM handles misspelled medicine names natively.
6. **State-specific prescriptions** — `STATE_PRESCRIPTION_OVERRIDES` dict with 24 states' regulatory text.
7. **Booking race condition** — `SELECT FOR UPDATE` on doctor row before conflict check.
8. **PIN code search** — Indexed column on Doctor, frontend input, PostGIS fallback.
9. **Telemedicine consent** — Checkbox in booking flow, stored on appointment.
10. **Profile photo with oval crop** — ImageCropModal with drag, zoom, SVG mask, canvas crop.
11. **Years experience computed** — From `year_of_registration`, zero maintenance.
12. **Walk-in patient linking** — Auto-links existing walk-ins to users by phone.
13. **OCR quality alerts** — Blur/contrast/brightness/resolution checks before processing.
14. **Voice-to-text is optional** — Returns 503 with guidance if ASR model not installed.
15. **Lab alerts removed** — Hardcoded reference ranges are useless for solo doctors.
16. **Research section skipped** — Compared with RAG-Based CDSS; not needed for solo doctor workflow.
17. **Offline PWA** — Workbox caching for API routes; doctor can view cached data offline.
18. **Sentry is opt-in** — Only active when `SENTRY_DSN` is set.
19. **Backup to MinIO** — pg_dump uploaded to object storage; list via admin endpoint.
20. **Multi-device sessions** — Track and revoke individual devices.
