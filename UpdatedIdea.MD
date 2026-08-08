# SoloPrac AI — Comprehensive Product + Research Specification

> **Revision date:** 2026-08-07
> **Revision notes:** All core features built and tested. Auth simplified to email+password (Google OAuth removed). Patient portal uses email+password (not OTP). Added: profile photos, voice-to-text, OCR quality alerts, document timeline, patient PDF downloads, state-specific prescriptions, PIN code search, telemedicine consent, DPDP consent management, NMC verification, Hindi UI, offline PWA, Sentry error tracking, backup system, multi-device sessions.
>
> **OCR pipeline swap (2026-08-07):** Surya (commercial-restrictive license) and Nanonets-OCR2 (6.5 GB RAM cost) both removed. Replaced with **RapidOCR** (Apache-2.0) for scanned/photo and **MedGemma-4B via llama-server** for the handwritten fallback — every OCR path is now permissively licensed and small enough to run alongside the rest of the stack. Docling additionally benefits from `g++` in the image so `torch._inductor` can JIT CPU kernels (first-parse confidence 0.70 → 0.95, time 195s → 86s).
>
> **Walk-in ↔ user auto-linking (2026-08-07):** New `services/linking.py` module + `/patient/me/pending-matches` review flow. Two-tier matcher: strong (phone + DOB, or phone + name-token-prefix compare) auto-attaches on signup; weak (phone-only) surfaces a UI banner with Claim / Not-me buttons. Handles families sharing a phone without paid SMS OTP. `UNIQUE` constraint on `users.phone_hash` dropped for family co-existence; `patients.link_rejected_by_user_ids UUID[]` added so rejections stick per user.
>
> **Local model verification:** All 6 local models exercised end-to-end (MedGemma via llama-server, faster-whisper large-v3, MedCPT, BGE-M3 with sparse indices via FlagEmbedding, BiomedCLIP via open_clip_torch, Docling). HuggingFace cache bind-mounted to `D:\models\hf-cache` — one copy on host, shared by `backend` and `arq-worker`, survives rebuilds.
>
> **Test tally: 112 e2e tests across 6 suites** (14 walk-in link + 27 disambiguation + 8 UI pending-matches + 43 API flows + 9 AI flows + 3 PII tripwire + 8 OCR pipeline) — all passing inside the backend container against real Postgres / Qdrant / Redis / MinIO.
>
> Lab alerts removed (intentionally skipped — hardcoded reference ranges are useless for solo doctors). Research section intentionally skipped compared with RAG-Based CDSS project.
> **Companion files:** `finalised_techstack.md` (stack reference), `THIRD_PARTY_LICENSES.md` (attribution + rejected-model rationale).

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
                │  │   ├─ Local VLM (MedGemma-4B GGUF / llama-server)   │   │
                │  │   ├─ OCR Router (Docling → RapidOCR → MedGemma)    │   │
                │  │   ├─ Image Reg (ORB + overlay subgraph)             │   │
                │  │   ├─ Walk-in Linker (services/linking.py)           │   │
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
    ├── parse_document               → Docling (typed) / RapidOCR (scanned) / MedGemma (handwritten)
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

Drop a file → automatically routed. **All three paths are permissively licensed and run locally.**

| Input | Pipeline | License |
|-------|---------|---------|
| Typed PDF | Docling | MIT |
| Scanned PDF / photo (jpg/png) | RapidOCR (ONNX + PaddleOCR models) — kept under the `surya_parse` method name for API stability | Apache-2.0 |
| Handwritten Rx (or low-confidence RapidOCR) | MedGemma-4B GGUF Q4_K_M served by `llama-server` — kept under the `nanonets_ocr_parse` method name | Gemma license |

**Why not Surya / Nanonets any more?**
- **Surya** ships an Apache-2.0 code header but adds a commercial-use clause in its terms — not viable for a project pitched as license-clean. RapidOCR gave equivalent accuracy on our fixture at zero license risk.
- **Nanonets-OCR2** is 6.5 GB in weights and dominated RAM. MedGemma-4B is already in the stack for chat/vision, so reusing it as the handwritten fallback cost 0 additional MB.

**OCR Quality Alerts** — Before processing, `_check_image_quality()` on `ParserRouter` detects:
- **Blur** (Laplacian variance < 100 severe / < 300 moderate)
- **Low contrast** (std dev < 20 severe / < 35 moderate)
- **Brightness issues** (< 50 too dark / > 230 too bright)
- **Low resolution** (< 500×500 px)

Quality warnings shown as amber alerts in the Scratchpad file list and review dialog.

**Compile toolchain:** the backend image ships `g++` alongside `gcc` so `torch._inductor` can JIT CPU kernels for Docling — first-parse confidence 0.70 → 0.95, time 195s → 86s.

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

### Module 12 — Walk-in ↔ User Auto-Linking (Free-Tier, Family-Safe)

Solo practitioners frequently add a walk-in patient by phone alone (`user_id = NULL`) before that person has ever signed up. Later — days or months on — the patient signs up as a user. Without linking, the record stays orphaned and every doctor the patient visits creates a fresh chart. Paid SMS OTP would solve it; we don't have a budget for that, and asking doctors to disambiguate slows every consult.

**Design:** every phone-based lookup runs through `backend/app/services/linking.py`, which classifies candidates into **strong** (auto-link on the spot) and **weak** (surface for user review).

**Matcher (`_names_compatible`)** — token-prefix, *not* character-ratio:
- Split each name on non-letters, lowercase.
- Every token in the shorter list must prefix some token in the longer list (one-to-one greedy).
- Handles `"Priya S."` ↔ `"Priya Sharma"` (compatible) while rejecting `"Priya Sharma"` vs `"Rajesh Sharma"` — the pathological case where `SequenceMatcher` scored 0.72 and misfired.

**Two-tier decision:**

| Signal set | Tier | Action |
|------------|------|--------|
| phone + DOB match | strong | auto-attach walk-in `user_id` on signup / walk-in-create |
| phone + name-token-prefix compatible | strong | auto-attach |
| phone only, no DOB, ambiguous name | weak | leave `user_id = NULL`, expose via pending-matches |
| phone but user has previously rejected | — | permanently hidden (see below) |

**API surface (`app/routers/portal.py`):**
| Verb | Path | Purpose |
|------|------|---------|
| `GET`  | `/patient/me/pending-matches` | List candidate walk-in records with clinic + doctor + demographics |
| `POST` | `/patient/me/claim/{patient_id}` | Re-verifies eligibility server-side, then sets `patients.user_id = current_user.id` |
| `POST` | `/patient/me/reject/{patient_id}` | Appends `current_user.id` to `patients.link_rejected_by_user_ids UUID[]` |
| `GET`  | `/patient/me/profile` | Now returns `pending_matches_count` so the banner can show/hide |

**Frontend:**
- `PendingMatchesBanner` — amber card on the patient dashboard; TanStack Query polls `/patient/me/profile` every 60s and hides itself when `pending_matches_count == 0`.
- `PatientPendingMatches` (`/patient/pending-matches`) — full review page; each card shows clinic name, doctor name, DOB, gender, address, and Claim / Not-me buttons wired through TanStack mutations.

**Schema changes:**
- `patients.link_rejected_by_user_ids UUID[] DEFAULT '{}'` — persists rejections across logins, so a wrongly-suggested record never resurfaces for the same user.
- `patients.phone_hash` remains indexed but no longer unique.
- `users.phone_hash` — **UNIQUE constraint dropped** so families sharing a handset can each hold an account. DOB + name-token-compat now carry the disambiguation load the constraint used to mask. `database.py` runs the ALTER TABLE at startup via a `pg_constraint` sweep; `init-schema.sql` matches for fresh boots.

**Doctor-side change (`routers/patients.py::create_patient_manual`):** now accepts optional `dob`, `gender`, and `address`; delegates to `find_user_for_walkin` so a match on manual creation either strong-links (user shows up in patient list immediately) or routes to pending-matches (user sees the banner next login) — no doctor input needed either way.

**Test coverage:** 14 walk-in-link tests + 27 disambiguation tests + 8 Playwright UI tests = 49 tests dedicated to this feature alone (see §7).

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

**Recent schema changes (2026-08-07):**
- `patients.link_rejected_by_user_ids UUID[] DEFAULT '{}'::UUID[]` — added for the walk-in linker's persistent rejections.
- `users.phone_hash` — `UNIQUE` constraint dropped so families sharing a handset can each own an account.
- `patients.phone_hash` — indexed but not unique (walk-in records for family members share phones).

Both changes ship as runtime `ALTER TABLE IF EXISTS` migrations in `app/database.py` and are also reflected in `init-schema.sql` for fresh Postgres containers.

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
| **Walk-in patient linking** | Two-tier matcher (`services/linking.py`) with strong (phone+DOB or phone+name-token) auto-link + weak (phone-only) review flow — see Module 12 |
| **Family-shared phones** | `users.phone_hash` UNIQUE constraint dropped; multiple accounts on one handset disambiguated by DOB / name-tokens |
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
| Document Engine (OCR) | **Done** | Docling (typed) + RapidOCR (scanned/photo) + MedGemma-via-llama-server (handwritten) + quality alerts. Surya + Nanonets-OCR2 removed for license / RAM cost — see revision notes. |
| Walk-in ↔ User Linking | **Done** | `services/linking.py` two-tier matcher + `/patient/me/pending-matches` review flow + `PendingMatchesBanner` + `PatientPendingMatches` page. 49 dedicated tests. |
| Family-Phone Support | **Done** | UNIQUE dropped on `users.phone_hash`; `patients.link_rejected_by_user_ids UUID[]` persists rejections per user. |
| Local Model Verification | **Done** | All 6 models (MedGemma via llama-server, faster-whisper large-v3, MedCPT, BGE-M3 with sparse, BiomedCLIP, Docling) exercised e2e. |
| HF Cache Bind-Mount | **Done** | `D:\models\hf-cache → /hf_cache` shared by backend + arq-worker; survives rebuilds. |
| torch.compile Toolchain | **Done** | `g++` added to backend Dockerfile — Docling first-parse confidence 0.70 → 0.95, time 195s → 86s. |
| THIRD_PARTY_LICENSES.md | **Done** | Full attribution + rejected-model rationale (Surya commercial-restrictive, Nanonets RAM-bound). |
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
| 15+ | OCR license cleanup (Surya→RapidOCR, Nanonets→MedGemma), walk-in linker, family-phone support, license-clean model verification | **Done** |
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
21. **OCR pipeline must be license-clean** — RapidOCR (Apache-2.0) over Surya (commercial-restrictive); MedGemma-4B GGUF (already in stack) over Nanonets-OCR2 (6.5 GB RAM cost). Docling stays for typed PDFs (MIT). Full rationale in `THIRD_PARTY_LICENSES.md`.
22. **Walk-in linking uses token-prefix, not SequenceMatcher** — character-ratio fuzzy match scored 0.72 for `"Priya Sharma"` vs `"Rajesh Sharma"`, a false positive on shared surnames. Token-prefix matching is O(n·m), zero false positives on the test corpus.
23. **No SMS OTP** — free-tier only means paid OTP is off the table. Weak matches route to a UI review flow instead of a "verify by SMS" wall.
24. **`users.phone_hash` UNIQUE dropped** — families share handsets in India; a UNIQUE constraint made co-existence impossible and offered no security anyway (phone alone is not proof of identity). DOB and name-token compatibility now do the disambiguation work.
25. **HF cache on host, not in a Docker volume** — bind-mounted to `D:\models\hf-cache`. Survives rebuilds, inspectable from Windows, shared between backend and arq-worker (removes the ~5 GB duplicate that named volumes forced).
26. **`g++` in backend image** — required by `torch._inductor` for CPU kernel JIT. Docling first-parse: confidence 0.70 → 0.95, time 195s → 86s.
27. **Method names kept for API stability** — the OCR router still exposes `surya_parse` and `nanonets_ocr_parse` on `OCRService`, but they dispatch to RapidOCR and MedGemma respectively. Callers (agents, routers, tests) didn't have to change.
28. **112 e2e tests, all passing** — run inside the backend container against real Postgres/Qdrant/Redis/MinIO. Playwright UI tests included. No mocks for infrastructure.
