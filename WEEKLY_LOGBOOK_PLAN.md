# SoloPrac AI — 15-Week Logbook Plan

> **Format:** Each week shows tasks assigned to all 4 members + progress column for mentor review.
> **Team:**
> - **Rohan Bhoge** — Backend, Architecture, RAG, Patient Versioning (lead)
> - **Ranveer Singh Thakur** — Frontend, OCR, Feature Discovery
> - **Nihal Korgaonkar** — Image/AI, Bookings, Voice, Scheduling
> - **Dev Patel** — Security, Planning, Deployment

---

## Week 1 — Foundation & Planning *(mentor-assigned structure)*

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] System Architecture & Design — overall system diagram, module decomposition, API design<br>2] Technology stack finalization with justifications<br>3] Database schema design (ER diagram for patients, versions, appointments)<br>4] Agent architecture design (LangGraph flow, tool tree) | ✅ Complete |
| **Ranveer Singh Thakur** | 1] Literature Survey — study existing EMR systems (OpenEMR, Practo, Tata 1mg)<br>2] Find features — analyze what each competitor lacks<br>3] Feature comparison table — what we do differently (versioning, temporal RAG)<br>4] Document findings for paper introduction | ✅ Complete |
| **Nihal Korgaonkar** | 1] Gap Analysis — identify specific gaps in solo-GP tools<br>2] Feature mapping — map gaps to our research features (A–F)<br>3] Market research — solo GP pain points in India<br>4] Clinical workflow study — how a typical GP day works | ✅ Complete |
| **Dev Patel** | 1] Project Planning & Proposal — scope, objectives, methodology<br>2] Feasibility Study — technical, operational, economic feasibility<br>3] Project Scheduling — 15-week Gantt chart (MS Project or draw.io)<br>4] Hardware/Software Requirements — detailed list with specs | ✅ Complete |

> **Week 1 Deliverables:** Architecture doc (Rohan), Literature survey (Ranveer), Gap analysis (Nihal), Project proposal + Gantt chart (Dev)

---

## Week 2 — Project Bootstrap & Dev Environment

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Docker Compose skeleton — FastAPI + Postgres + Qdrant + Redis + Langfuse + Caddy<br>2] FastAPI project structure — routers, models, dependencies, config<br>3] PostgreSQL schema — `doctors`, `patients`, `patient_versions` tables<br>4] Health check endpoints + Docker layer caching |  |
| **Ranveer Singh Thakur** | 1] React 19 + Vite + TypeScript project scaffold<br>2] shadcn/ui setup + Tailwind config + dark mode default<br>3] Base layout — left rail, center, right rail, top bar<br>4] Framer Motion page transitions + skeleton loaders |  |
| **Nihal Korgaonkar** | 1] Qdrant Docker setup with named vectors config<br>2] Embedding model research — download MedCPT + BGE-M3 locally<br>3] Redis setup for arq queue + caching<br>4] LLM API key setup — NVIDIA NIM account + Groq account |  |
| **Dev Patel** | 1] Auth system — Google OAuth + JWT + fastapi-users<br>2] RLS policies on all initial tables (tenant isolation)<br>3] `.env` template + secrets management (no keys in git)<br>4] Pre-commit hooks (detect-secrets, linting) |  |

> **Week 2 Deliverables:** `docker-compose up` works for all services (Rohan), React app runs + shows layout (Ranveer), Qdrant + Redis connectable (Nihal), Auth flow works (Dev)

---

## Week 3 — Patient Versioning Core + Frontend Setup

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] `patient_versions` — immutable version chain with `version_hash = sha256(canonical_json)`<br>2] Head pointer logic — `patients.head_version_id` tracking<br>3] GET endpoints — `/patients/{id}`, `/patients/{id}/timeline`, `/patients/{id}/at_version/{n}`<br>4] Version minting — POST endpoint for manual version creation |  |
| **Ranveer Singh Thakur** | 1] Patient list component — search-as-you-type, autocomplete<br>2] Cmd+K command palette via `cmdk`<br>3] Basic patient detail view (read-only fields)<br>4] Left rail — patient list with search + new patient button |  |
| **Nihal Korgaonkar** | 1] LangGraph agent skeleton — main graph, nodes, edges<br>2] Intent router node — Llama-3.1-8B via NIM<br>3] Tool registry pattern — how tools register with the agent<br>4] Local model test — verify NIM API connectivity + response format |  |
| **Dev Patel** | 1] Audit log — `audit_log` table + middleware for automatic logging<br>2] CORS strict allowlist per environment<br>3] Rate limiting — `slowapi` per-doctor RPM limits<br>4] Security middleware — request validation, header checks |  |

> **Week 3 Deliverables:** Version chain works + timeline API (Rohan), Patient list + Cmd+K (Ranveer), Agent skeleton routes (Nihal), Audit log recording (Dev)

---

## Week 4 — Versioning APIs Complete + Timeline UI

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Diff endpoint — `/patients/{id}/diff?v1=5&v2=7` field-level comparison<br>2] Revert endpoint — `/patients/{id}/revert/{n}` mints new version with old state<br>3] PATCH endpoint — `/patients/{id}/fields` inline edit with optimistic locking<br>4] Author tagging — manual vs agent vs OCR vs voice |  |
| **Ranveer Singh Thakur** | 1] Timeline scrubber component — Framer Motion animated node chain<br>2] Version nodes colored by author (blue=doctor, purple=agent, gray=OCR)<br>3] Hover popover with version summary<br>4] Click version → body shows historical state in read-only |  |
| **Nihal Korgaonkar** | 1] MedCPT embedding pipeline — encode patient text to 768d vectors<br>2] BGE-M3 embedding pipeline — dense + sparse encoding to 1024d<br>3] Qdrant point creation — named vectors `{medical_text, hybrid}` + payload<br>4] Background embedder — arq worker for async embedding jobs |  |
| **Dev Patel** | 1] pgcrypto PII encryption — phone, email, address columns<br>2] Version audit — every version mint logs to `audit_log`<br>3] RLS policy verification — test queries across doctor boundaries<br>4] Optimistic locking enforcement — `updated_at` conflict detection |  |

> **Week 4 Deliverables:** Diff + revert APIs work (Rohan), Timeline scrubber functional (Ranveer), Vectors flowing to Qdrant (Nihal), RLS isolation verified (Dev)

---

## Week 5 — LangGraph Agent + Chat Console

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] LangGraph main agent — router → synthesize → respond flow<br>2] Maverick (Llama-4) synthesis node — NIM integration with structured output<br>3] SSE streaming — `StreamingResponse` with agent-trace events<br>4] Tool integration — connect `retrieve_patient_context` + `synthesize_response` |  |
| **Ranveer Singh Thakur** | 1] Chat UI — message list + input bar + mic button (placeholder)<br>2] SSE consumption — `EventSource` + custom React hook<br>3] Streaming text animation — `useTransition` for smooth token rendering<br>4] Agent trace display — "Searching records… Analyzing… Drafting…" |  |
| **Nihal Korgaonkar** | 1] NV-CLIP embedding pipeline — encode images to 512d via NIM<br>2] Qdrant `image` vector — add to existing named vectors<br>3] Qdrant hybrid search — dense + sparse query with `query_points`<br>4] Image upload endpoint — `/patients/{id}/images` with validation |  |
| **Dev Patel** | 1] Prompt injection defense — sanitize OCR'd text before LLM<br>2] Structured output enforcement — JSON Schema + Pydantic validation<br>3] Doctor identity injection — `SET LOCAL app.current_doctor_id` per request<br>4] Session management — 30-min auto-logout, refresh tokens |  |

> **Week 5 Deliverables:** Agent responds to chat with streaming (Rohan), Chat UI shows streaming text (Ranveer), Images embeddable + searchable (Nihal), No prompt injection possible (Dev)

---

## Week 6 — Temporal Multimodal RAG (Feature A) — Primary Research

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Temporal RAG implementation — `temporal_multimodal_retrieve()` with full scoring<br>2] Reciprocal rank fusion — combine text + hybrid + sparse + image results<br>3] Temporal decay function — `exp(-Δt/τ)` per modality with configurable τ<br>4] Clinical significance scoring — tiered weights integrated into rank |  |
| **Ranveer Singh Thakur** | 1] RAG answer display — citation chips `[v12 · 2026-03-14]`<br>2] Citation click → scrubber jumps to that version<br>3] Right rail — context panel (current vitals, active meds, next appointment)<br>4] Inline edit mode — click field → edit → blur saves to version |  |
| **Nihal Korgaonkar** | 1] MIMIC-IV synthetic data pipeline — generate longitudinal patient records<br>2] Evaluation harness — Recall@5, future-leak rate, latency p95<br>3] Baseline comparisons — BM25, vanilla MedCPT (no temporal), dense-only RAG<br>4] Test dataset — 100 multi-visit query pairs with ground truth |  |
| **Dev Patel** | 1] Qdrant payload filter enforcement — `doctor_id` + `patient_id` + timestamp bounds<br>2] RAG audit logging — every retrieval call logged with query + results summary<br>3] Rate limiting on LLM calls — per-doctor RPM tracking<br>4] Data validation — ensure no future-timestamped versions leak into queries |  |

> **Week 6 Deliverables:** Feature A works end-to-end (Rohan), Citations clickable in UI (Ranveer), Evaluation scores against baselines (Nihal), Zero future-leak confirmed (Dev)

---

## Week 7 — Document Engine + Schema Alignment (Feature D)

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Docling integration — typed PDF → structured JSON<br>2] Surya OCR integration — scanned PDF → layout → Docling structure<br>3] GOT-OCR 2.0 integration — handwritten Rx → text<br>4] Parser router — auto-detect document type and route |  |
| **Ranveer Singh Thakur** | 1] Upload UI — drag-drop zone with file type validation<br>2] Scratchpad route `/scratchpad` — drag-drop + preview<br>3] "Save to Patient" button — promotes scratchpad to versioned record<br>4] Upload progress indicator + preview thumbnail |  |
| **Nihal Korgaonkar** | 1] Feature D — Maverick schema alignment (free-text → canonical schema)<br>2] Few-shot prompt engineering — 3 examples per document type in prompt<br>3] Validation pipeline — Pydantic → fail → critic → MedGemma fallback<br>4] Test dataset — 50 docs across 5 types (Rx, lab, discharge, referral, report) |  |
| **Dev Patel** | 1] File upload security — magic-byte check (not just extension)<br>2] Upload allowlist — PDF, JPG, PNG, WEBP only<br>3] OCR text sanitization — strip potential injection before LLM<br>4] Rate limiting on document upload — prevent abuse |  |

> **Week 7 Deliverables:** Documents parse + route correctly (Rohan), Drag-drop UI works (Ranveer), Schema alignment F1 > 0.8 (Nihal), Upload security verified (Dev)

---

## Week 8 — Image Registration + Comparison (ORB + Overlay)

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] ORB feature matching pipeline — OpenCV ORB + BFMatcher + Lowe's ratio test<br>2] Homography computation — RANSAC for geometric alignment<br>3] Overlay generation — semi-transparent aligned composite image<br>4] API — POST /patients/{id}/images (upload + auto-match) + comparison retrieval |  |
| **Ranveer Singh Thakur** | 1] Image comparison UI — 3-panel view (Previous / Current / Overlay)<br>2] Opacity slider control for overlay blend<br>3] Metrics display — % area change, edge convergence score, color shift<br>4] "Add to patient record" button → Maverick generates clinical summary |  |
| **Nihal Korgaonkar** | 1] Maverick clinical summary from comparison — wound healing assessment<br>2] Comparison → versioned entry on patient record<br>3] NV-CLIP embedding for comparison images<br>4] Feature C prep — collect (image, doctor summary) training pairs |  |
| **Dev Patel** | 1] Secure image storage — encrypted at rest<br>2] Image validation — size limits, format enforcement<br>3] Audit logging for image access + comparison creation<br>4] RLS for image data — tied to patient + doctor |  |

> **Week 8 Deliverables:** ORB matching finds correct prior photo (Rohan), 3-panel overlay UI works (Ranveer), Clinical summary generated (Nihal), Images securely stored (Dev)

---

## Week 9 — Prescription Box + Invoice + Certificates

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Jinja2 → Playwright PDF pipeline — shared service for all PDF generation<br>2] `prescription_boxes` CRUD — create, get, list, download<br>3] `invoices` CRUD — auto-generate invoice number, calculate totals<br>4] `certificates` CRUD — type-based templates, QR verification codes |  |
| **Ranveer Singh Thakur** | 1] Prescription box UI — colored highlight box with medications table<br>2] Invoice UI — line items, totals, status badge, print button<br>3] Certificate UI — type selector, form fields, preview, download<br>4] All three share "print-ready" button with clinic letterhead |  |
| **Nihal Korgaonkar** | 1] Maverick structured output — Rx JSON schema (diagnosis, medications, instructions)<br>2] Maverick structured output — Invoice line items from consultation<br>3] Maverick structured output — Certificate body from doctor notes<br>4] MedGemma fallback for certificate image analysis if needed |  |
| **Dev Patel** | 1] PDF security — watermark, disclaimer footer enforcement<br>2] QR code generation for certificate verification<br>3] Audit logging — every PDF generate/print/email logged<br>4] Two-step confirmation before any patient-facing PDF |  |

> **Week 9 Deliverables:** All 3 PDF types generate correctly (Rohan), UI shows all 3 with print (Ranveer), Maverick produces valid JSON for all (Nihal), Disclaimers present on all PDFs (Dev)

---

## Week 10 — Calendar Core + Email Queue

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Calendar tools 1–4 — `find_available_slots`, `create_appointment`, `reschedule_appointment`, `cancel_appointment`<br>2] `arq` email queue — send email notifications via SMTP<br>3] Working hours config — `doctor_settings.working_hours_json` parser and validator<br>4] Buffer time enforcement — `buffer_minutes_between_consults` |  |
| **Ranveer Singh Thakur** | 1] Calendar UI — weekly view with appointment blocks<br>2] Slot picker — available time slots highlighted, click to book<br>3] Working hours config UI — per-weekday time windows editor<br>4] Appointment detail card — patient info, reason, status, actions |  |
| **Nihal Korgaonkar** | 1] Patient preference logging — `patient_time_preferences` histogram update on each booking<br>2] Voice scheduling subgraph — router node for scheduling intent<br>3] faster-whisper integration — English ASR, language detection<br>4] IndicWhisper integration — Hindi/Hinglish fallback routing |  |
| **Dev Patel** | 1] Notification preferences schema — doctor-toggleable per event type<br>2] Audit logging for appointment CRUD<br>3] RLS on appointments — doctor isolation<br>4] Rate limiting on calendar API — prevent bulk abuse |  |

> **Week 10 Deliverables:** Book/reschedule/cancel works via API (Rohan), Calendar UI functional (Ranveer), Voice ASR captures and routes (Nihal), Appointments isolated per doctor (Dev)

---

## Week 11 — Voice Scheduling + Smart Rearrange

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Calendar tools 5–9 — `query_calendar_nl`, `bulk_reschedule`, `block_doctor_time`, `smart_rearrange`, `find_optimal_window`<br>2] Smart rearrange ranker — patient preference + risk severity + geographic batching<br>3] Doctor-off scenario — block time → auto-query → smart-rearrange → draft emails → approval card<br>4] LangGraph subgraph — full voice scheduling flow wired |  |
| **Ranveer Singh Thakur** | 1] Approval card UI — shows all proposed moves with accept/reject<br>2] Voice confirmation UI — visual card after TTS playback<br>3] "I'm off" one-click flow — block dates → see affected → approve all<br>4] Mobile-responsive calendar view |  |
| **Nihal Korgaonkar** | 1] Maverick intent classification for scheduling — book/reschedule/cancel/block/query<br>2] Indic-Parler-TTS integration — English + Hindi voice confirmation<br>3] Voice subgraph end-to-end — mic → ASR → intent → tools → TTS<br>4] Five locked voice commands tested end-to-end |  |
| **Dev Patel** | 1] WebSocket security — authenticated connection for voice<br>2] Voice session audit logging — every command logged<br>3] Rate limiting on voice endpoints — prevent abuse<br>4] Two-step confirm for destructive actions (cancel, block) |  |

> **Week 11 Deliverables:** All 9 calendar tools work (Rohan), Approval card UX complete (Ranveer), 5 voice commands work (Nihal), Voice flow secure + audited (Dev)

---

## Week 12 — Patient Web Portal + Real-Time Notifications

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Patient portal APIs — `/api/public/doctors/search` with lat/lng radius query<br>2] Doctor detail + available slots endpoint<br>3] Patient booking endpoint — creates appointment from portal<br>4] WebSocket — `/ws/patient/{patient_id}` for real-time notifications |  |
| **Ranveer Singh Thakur** | 1] Patient portal frontend — `/patient/*` routes in same React app<br>2] Doctor search with Leaflet.js + OpenStreetMap tiles<br>3] Patient dashboard — upcoming appointments, reports, notifications<br>4] Booking flow — search doctor → see slots → book → confirmation |  |
| **Nihal Korgaonkar** | 1] Maverick AI notification generator — per event type with patient context<br>2] `patient_notifications` CRUD — create notification with AI-generated body<br>3] WebSocket notification dispatch — push to patient on new events<br>4] Email notification fallback — via arq queue |  |
| **Dev Patel** | 1] Patient auth — Google OAuth + email/OTP login<br>2] RLS for patient role — patients see only their own data<br>3] Notification preferences — per-doctor toggle enforcement<br>4] Portal security — no cross-patient data access |  |

> **Week 12 Deliverables:** Patients can search + book doctors (Rohan), Map shows doctors with details (Ranveer), AI notifications generated and pushed (Nihal), Patient data isolated (Dev)

---

## Week 13 — Features B, C, E (Paper Evaluations)

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] Feature B — Self-Planning Agent (planner → executor → critic loop)<br>2] Feature B evaluation — steps-to-resolution vs fixed pipeline on 100 queries<br>3] Feature F — Weekly report significance scorer + 3 layout templates<br>4] Feature F evaluation — doctor Likert rating study design |  |
| **Ranveer Singh Thakur** | 1] Weekly report UI — 3 layout previews (Executive, Clinical, Family-friendly)<br>2] Report settings per patient — doctor picks layout<br>3] Risk alerts UI — right rail red badge with alert reason<br>4] Report generation + download button in UI |  |
| **Nihal Korgaonkar** | 1] Feature C — Linear projector `W: ℝ^512 → ℝ^1024` training with InfoNCE<br>2] CheXpert dataset prep — image–report pairs for training<br>3] Feature E — Trajectory clustering (HDBSCAN) + anomaly detection on synthetic data<br>4] Feature E evaluation — precision on injected deteriorations |  |
| **Dev Patel** | 1] Feature C — evaluation Recall@k on held-out CheXpert pairs<br>2] Feature E — simulation data security (no real patient data used)<br>3] Research data management — Langfuse metrics export<br>4] Data anonymization checks for paper figures |  |

> **Week 13 Deliverables:** Feature B plans and executes (Rohan), Report UI shows 3 layouts (Ranveer), Projector training loss converges (Nihal), All evaluation data clean + auditable (Dev)

---

## Week 14 — Integration Testing + Polishing

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] End-to-end integration testing — all APIs working together<br>2] Performance optimization — query latency, caching, connection pooling<br>3] Docker Compose finalization — Oracle Cloud Free Tier target config<br>4] Bug fixes from integration testing |  |
| **Ranveer Singh Thakur** | 1] UI polish — consistent spacing, colors, typography<br>2] Dark mode verification — all components tested in both modes<br>3] Mobile/tablet responsiveness — timeline collapses to accordion<br>4] Demo flow — scripted walkthrough of all features |  |
| **Nihal Korgaonkar** | 1] Langfuse dashboard finalization — latency charts, retrieval recall, agent success rate<br>2] Final evaluation runs — all features A–F metrics collected<br>3] GPU optimization — model swapping strategy finalized<br>4] Voice pipeline latency optimization |  |
| **Dev Patel** | 1] Full security audit — RLS, auth, encryption, injection, CORS<br>2] Penetration testing — attempt cross-tenant data access<br>3] Audit log completeness check — every required event logs<br>4] Deployment to Oracle Cloud Free Tier — final working URL |  |

> **Week 14 Deliverables:** Full integration test pass (Rohan), Demo-ready UI (Ranveer), All paper metrics collected (Nihal), Deployed + security verified (Dev)

---

## Week 15 — IEEE Paper + Final Demo

| Student Name | Task Assigned | Progress |
|:---|:---|:---:|
| **Rohan Bhoge** | 1] IEEE paper — Introduction + System Architecture + Feature A (Temporal RAG)<br>2] Feature B (Self-Planning Agent) section<br>3] Architecture diagram (Mermaid → PNG)<br>4] Paper revision + formatting (IEEEtran 2-column) |  |
| **Ranveer Singh Thakur** | 1] Demo video recording — 5-min walkthrough of all features<br>2] Paper figures — latency charts, retrieval precision bars, screenshots<br>3] Feature F (Weekly Reports) section + evaluation results<br>4] Presentation slides for mentor review |  |
| **Nihal Korgaonkar** | 1] IEEE paper — Feature C (Cross-Modal) + Feature D (Schema Alignment)<br>2] Feature E (Trajectory Clustering) section<br>3] Related Work + Bibliography (`references.bib`)<br>4] Ablation studies — contribution of each retrieval modality |  |
| **Dev Patel** | 1] IEEE paper — Security Architecture + Limitations + Ethics sections<br>2] Comparison with existing systems table<br>3] Final deployment verification on Oracle Cloud<br>4] Project submission — all deliverables packaged |  |

> **Week 15 Deliverables:** Complete IEEE paper submitted (All), Demo video ready (Ranveer), System deployed and accessible (Dev), Mentor presentation prepared (All)

---

## Gantt Chart Overview

```
Week    1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
        ────Planning──── ────────Build──────── ──Paper─
Rohan   ▓░ ▓░ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓
        Ar  Dk  VC  DA  LA  RA  DE  IR  PX  CA  VZ  PP  BE  IN  PA
        ch  oc  or  PI  ng  G_  ng  eg  In  le  Sl  or  va  te  pe
Ranveer ▓░ ▓░ ▓░ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓
        Li  Re  Pa  Ti  Ch  RA  Up  Im  Rx  Ca  Vc  Po  Rr  UI  Dm
        t   ac  tL  me  at  G_  lo  ag  UI  le  on  rt  ep  Po  o
Nihal   ▓░ ▓░ ▓░ ▓░ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓
        Ga  Em  La  Em  Im  Ev  Sc  Fe  Mv  AS  Vc  AI  Pr  La  Pa
        p   bd  ng  be  gE  al  h   at  er  R   T   Nt  oj  ng  p
Dev     ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓
        Pl  Au  Au  RL  Se  Qd  Fi  Im  PD  No  Au  Pt  Ev  Se  Pa
        an  th  dit  S   c   R   le  gS  F   t   dit  Au  al  c   p
```

**Legend:**
- Ar = Architecture | Dk = Docker | VC = Version Chain | DA = Diff APIs | LA = LangGraph Agent | RAG = Temporal RAG | DE = Doc Engine | IR = Image Reg | PX = Prescriptions | CA = Calendar | VZ = Voice | PP = Patient Portal | BE = B+E+Eval | IN = Integration | PA = Paper
- Lit = Literature | PatL = Patient List | Tim = Timeline | Chat = Chat UI | RAG UI = RAG Citations | Up = Upload | Img = Image UI | Rx = Presc UI | Cal = Calendar | Vc = Voice | Por = Portal | Rr = Reports | UI = Polish | Dm = Demo
- Gap = Gap Analysis | Emb = Embeddings | Lang = LangGraph | Emb = Embed Qdrant | ImgE = Image Embed | Eval = Eval Harness | Sch = Schema Alignment | Fe = Feature C | ASR = Whisper | VcT = TTS | AIN = AI Notif | Proj = Projector | Lang = Langfuse | Pap = Paper
- Plan = Planning | Auth = Auth System | Audit = Audit Log | RLS = RLS Policies | Sec = Security Middleware | QdR = Qdrant Security | File = File Upload | ImgS = Image Security | PDF = PDF Security | Not = Notification Prefs | Audit = Voice Audit | PtAu = Patient Auth | Eval = Eval Security | Sec = Security Audit | Pap = Paper Security

---

## Key Milestones for Mentor Reviews

| Review | Week | What to Show |
|:------:|:----:|-------------|
| **Review 1** | 4 | Patient version chain working, timeline scrubber, auth + RLS |
| **Review 2** | 8 | RAG answering questions, documents parse, image comparison works |
| **Review 3** | 12 | Full doctor app (Rx, calendar, voice), patient portal with map |
| **Final** | 15 | Working system deployed, IEEE paper draft, demo video |

---

## Logbook Entry Format (per week, per student)

```
┌─────────────────────────────────────────────────────────────────┐
│ Week N: [Week Title]                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Student Name: [Name]                                             │
│                                                                  │
│ Tasks Assigned:                                                  │
│ 1] [Task 1 description]                                          │
│ 2] [Task 2 description]                                          │
│ 3] [Task 3 description]                                          │
│ 4] [Task 4 description]                                          │
│                                                                  │
│ Progress:                                                        │
│ [✔ / ⚠ / ❌] Task 1 — [Status note, e.g., "Completed. Detail..."] │
│ [✔ / ⚠ / ❌] Task 2 — [Status note]                              │
│ [✔ / ⚠ / ❌] Task 3 — [Status note]                              │
│ [✔ / ⚠ / ❌] Task 4 — [Status note]                              │
│                                                                  │
│ Learning / Issues:                                               │
│ • [Key learning or blocker for this week]                        │
│                                                                  │
│ Mentor Signature: _______________  Date: _______                 │
└─────────────────────────────────────────────────────────────────┘
```
