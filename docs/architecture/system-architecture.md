# SoloPrac AI — System Architecture & Design

## 1. Overview

SoloPrac AI is a **multimodal, agentic clinical operating system** for solo medical practitioners in India. The system is designed around a **version-controlled patient intelligence layer** where every consultation mints a new immutable version (like a Git commit), every AI suggestion is auditable, and every retrieval is temporally aware.

Key architectural innovations:
- **Tiered Doctor Verification** — Self-register for private practice, verify for public trust
- **Cross-Clinic Patient Identity** — One user can be a patient at multiple clinics via `User` → `Patient` relationship
- **India-First Stack** — Hindi voice, OpenStreetMap, DPDP Act compliance, NMC verification, state-specific prescriptions
- **Free-Tier Only** — Zero hosting cost on Oracle Cloud Free Tier + NVIDIA NIM + Groq free tiers
- **Email+Password Auth** — HttpOnly cookies, no Google OAuth dependency
- **PII De-identification** — Defense-in-depth stripping at indexer, tools, and synthesizer boundaries

This document describes the complete system architecture, module decomposition, and API design.

---

## 2. Architectural Philosophy

| Principle | Description |
|-----------|-------------|
| **Versioned Writes Only** | No in-place UPDATE on patient state — always append a new version. |
| **Doctor-in-the-Loop** | Every AI mutation is a proposal until the doctor confirms. |
| **Async-First** | Every I/O path is async; heavy jobs run in arq Redis queue. |
| **Structured Output** | All LLM-driven mutations use JSON Schema + Pydantic validation. |
| **Observability** | Every LLM call, agent step, retrieval is traced in Langfuse + Sentry. |
| **Multi-Tenant Isolation** | Row-Level Security on every table; Qdrant filters enforced at API layer. |
| **PII De-identification** | strip_pii at indexer, tools, synthesizer boundaries; pseudonymize_id for LLM. |
| **Defense-in-Depth** | Multiple layers of security; no single point of failure. |

---

## 3. System Architecture Diagram

### 3.1 Layer Description

| Layer | Components | Responsibility |
|-------|------------|----------------|
| **Client Layer** | React 19 + Vite + shadcn/ui + Tailwind + Framer Motion + i18n + PWA | Doctor-facing app and patient portal (same codebase, different routes) |
| **API Gateway** | Caddy Reverse Proxy | Auto-HTTPS via Let's Encrypt, request routing, static file serving |
| **Backend Layer** | FastAPI + Pydantic + SQLAlchemy + arq | REST API, async task processing, database ORM |
| **Agent Layer** | LangGraph + Multiple LLM Nodes | Intent routing, RAG retrieval, vision analysis, document processing, voice scheduling |
| **Storage Layer** | PostgreSQL 16 + Qdrant + Redis + MinIO + Langfuse | Relational data, vector embeddings, caching, object storage, observability |
| **External Services** | NVIDIA NIM, Groq, OpenStreetMap, SMTP, Sentry | Free-tier LLMs, maps, email, error tracking |

### 3.2 Data Flow

```
User Request (Chat/Image/Voice/Document)
    ↓
Caddy Reverse Proxy (HTTPS termination)
    ↓
FastAPI Router (auth check, tenant isolation via HttpOnly cookies)
    ↓
LangGraph Agent (intent classification)
    ↓
Tool Execution (RAG / Vision / Document / Calendar)
    ↓
Maverick Synthesis (response generation)
    ↓
SSE Stream (real-time tokens to UI)
    ↓
Audit Log (every action recorded)
```

---

## 4. Module Decomposition

### Module 1 — Version-Controlled Patient Records
The core innovation. Every patient write creates an immutable version with content-addressed hash (`sha256(canonical_json(state))`). Versions form a chain via `parent_version_id`, and the patient's current state is simply the head of this chain.

**Key APIs:**
- `GET /patients/{id}` — Current head state
- `GET /patients/{id}/timeline` — Ordered version list with summaries
- `GET /patients/{id}/at_version/{n}` — Historical state reconstruction
- `GET /patients/{id}/diff?v1=5&v2=7` — Field-level comparison
- `POST /patients/{id}/revert/{n}` — New version from historical state
- `PATCH /patients/{id}/fields` — Inline edit with optimistic locking
- `GET /patients/{id}/documents` — Unified document timeline with version citations

### Module 2 — Dynamic Agentic Router (LangGraph)
Single entry point classifying user intent and dispatching to the correct tool/model.

**Tools:**
- `retrieve_patient_context` — Qdrant hybrid search with temporal decay
- `synthesize_response` — Llama-4 Maverick response generation
- `analyze_image` — Groq 90B-V / MedGemma-4B vision analysis
- `compare_images` — ORB feature matching + overlay generation
- `parse_document` — Docling / Surya / Nanonets-OCR2 pipeline with quality alerts
- `generate_prescription_box` — Structured JSON Rx → PDF (state-specific)
- `generate_invoice` — Line item billing → PDF
- `generate_certificate` — Medical certificate → PDF with QR verification
- `schedule_subgraph` — 9 calendar tools (voice + text)
- `generate_weekly_report` — Significance-filtered digest → PDF

### Module 3 — Multimodal RAG Console
Primary chat interface with temporal-aware retrieval. Supports text and image input with inline citations to specific patient versions. Voice-to-text mic button for hands-free input.

### Module 4 — Image Registration for Clinical Comparison
ORB feature matching between consecutive patient photos (wounds, skin conditions). Produces overlay images with clinical summary using BiomedCLIP for similarity search.

### Module 5 — Document Engine
Intelligent document parsing pipeline with auto-routing and quality alerts: typed PDF → Docling, scanned PDF → Surya + Docling, handwritten Rx → Nanonets-OCR2, photos → Surya + MedGemma. Quality checks for blur, contrast, brightness, resolution.

### Module 6 — Prescription Highlight Box
AI-generated, JSON-validated prescription cards rendered in-app and as print-ready PDFs via Jinja2 + Playwright. State-specific regulatory headers/footers. Voice-to-text mic buttons. Doctor approves prescription to create new patient version.

### Module 7 — Invoice/Billing System
Track patient billing with auto-generated invoice numbers, line items, tax calculations, and PDF output (same pipeline as prescriptions).

### Module 8 — Medical Certificate Generator
Type-based certificate templates (sick leave, fitness, school) with QR verification codes. Same PDF pipeline.

### Module 9 — Calendar + Voice Scheduling
LangGraph subgraph with 9 tools covering booking, rescheduling, cancellation, bulk operations, doctor-off handling, and smart rearrangement with patient preference learning. Booking dialog with patient search. Race condition protection via SELECT FOR UPDATE.

### Module 10 — Patient Web Portal
Lightweight patient interface in the same React app (`/patient/*` routes). Features include doctor search with PostGIS radius + PIN code, appointment booking with telemedicine consent, report download (prescriptions, invoices, certificates as PDF), document timeline, DPDP consent management, data erasure, and AI-generated notifications via WebSocket.

### Module 11 — Doctor Profile & Verification
Profile photo upload with oval crop (ImageCropModal), NMC verification (registration number + state council + year), years experience computed from year_of_registration, profile completion banner, multi-device session management.

---

## 5. Security Architecture

| Layer | Mechanism |
|-------|-----------|
| **Auth** | Email + password (bcrypt) → HttpOnly cookies (access_token for doctors, patient_token for patients) |
| **Tenant Isolation** | `doctor_id` on every table + PostgreSQL Row-Level Security |
| **Vector DB** | Every Qdrant query has `must` filter on `doctor_id` at API layer |
| **Encryption at Rest** | pgcrypto for PII columns; MinIO server-side encryption |
| **Encryption in Transit** | Caddy auto-HTTPS (Let's Encrypt) |
| **PII De-identification** | strip_pii at indexer, tools, synthesizer; pseudonymize_id for LLM context |
| **Audit Log** | Append-only `audit_log` table for every read/write |
| **Rate Limiting** | slowapi per-doctor RPM limits |
| **Input Validation** | Pydantic everywhere; file upload allowlist + magic-byte check |
| **Prompt Injection Defense** | Sanitized OCR text; structured output (JSON Schema); PII stripped before LLM |
| **Session Management** | DoctorSession model tracks devices; revoke individual sessions |
| **Sentry** | Opt-in error tracking via SENTRY_DSN env var |

---

## 6. Deployment Architecture

Development: Docker Compose on local RTX 3050 machine.
Production: Docker Compose → Oracle Cloud Free Tier (4 ARM cores + 24 GB RAM).

**Services (8 Docker containers):**
1. FastAPI backend
2. PostgreSQL 16 + PostGIS
3. Qdrant vector database
4. Redis (cache + arq queue)
5. MinIO (object storage for avatars, PDFs, documents)
6. Caddy (reverse proxy)
7. Playwright (PDF generation)
8. Frontend (React, served via Caddy or standalone)

---

## 7. Scalability Considerations

- **Horizontal scaling:** Each doctor = isolated tenant; can scale by adding compute
- **Async processing:** Embeddings, PDF generation, and email send via arq queue
- **Caching:** Patient lists (60s), doctor settings (300s), working hours (120s), available slots (30s)
- **Content-hash caching:** Embeddings cached by content hash (same text → same vector, no cross-user leakage)
- **GPU strategy:** Only one local model on RTX 3050 at a time; swap on demand via orchestrator
- **Offline support:** PWA service worker caches API routes for offline viewing
