# SoloPrac AI

> A multimodal, agentic clinical operating system for solo medical practitioners in India, built around a **version-controlled patient intelligence layer** with **tiered doctor verification** and **cross-clinic patient identity**.

## Vision

Every solo GP in India deserves clinical intelligence that matches hospital systems — without the cost, complexity, or vendor lock-in. SoloPrac AI makes this possible by combining:

- **Version-controlled patient records** — Immutable, Git-like history for every patient
- **Temporal-aware AI** — RAG that knows *when* information was true
- **Voice-first scheduling** — "I'm off Friday, handle it" in Hindi + English
- **Tiered doctor verification** — Self-register instantly, verify for public trust
- **Cross-clinic patient identity** — One person can visit multiple doctors without duplicate accounts
- **Zero-cost deployment** — Runs entirely on free tiers (Oracle Cloud, NVIDIA NIM, Groq)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    React 19 + Vite + Tailwind                   │
│  Doctor App (/dashboard/*)  │  Patient Portal (/patient/*)      │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS (Caddy)
┌──────────────────────▼──────────────────────────────────────────┐
│              FastAPI + Pydantic + SQLAlchemy + arq              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  LangGraph Agent                                         │  │
│  │  ├─ Router (Llama-3.1-8B)  ├─ Synthesizer (Maverick)    │  │
│  │  ├─ Vision (90B-V / MedGemma) ├─ Doc Processor           │  │
│  │  ├─ Image Registration (ORB)    ├─ Voice Scheduling      │  │
│  └──────────────────────────────────────────────────────────┘  │
└──┬─────────┬─────────┬─────────┬───────────────────────────────┘
   │         │         │         │
┌──▼──┐  ┌──▼──┐  ┌──▼──┐  ┌──▼───────┐
│ PG  │  │Qdrant│ │Redis │ │MinIO S3  │
│16+  │  │Hybrid│ │arq   │ │Object    │
│RLS  │  │Vectors│ │Queue │ │Storage   │
└─────┘  └──────┘  └──────┘  └──────────┘
```

---

## Features

### Core Clinical Workflow
| Feature | Description |
|---------|-------------|
| **Versioned Patient Records** | Every change mints a new immutable version with content hash, parent pointer, author, and edit type |
| **Timeline Scrubber** | Git-like visual timeline with Framer Motion animations — click any version to time-travel |
| **Diff & Revert** | Field-level diff between any two versions; one-click revert to historical state |
| **Inline Editing** | Click any field → edit → blur to save (optimistic locking) |

### AI Intelligence
| Feature | Description |
|---------|-------------|
| **Temporal Multimodal RAG (Feature A)** | Retrieves with temporal decay, clinical significance, and cross-modal fusion |
| **Self-Planning Agent (Feature B)** | Dynamic plan-execute-critic loop for clinical queries |
| **Cross-Modal Retrieval (Feature C)** | BiomedCLIP → BGE-M3 projector for image↔text search |
| **Zero-Shot Schema Alignment (Feature D)** | LLM maps any document to canonical patient schema |
| **Trajectory Clustering (Feature E)** | HDBSCAN + Mahalanobis for proactive risk alerts |
| **Significance-Aware Reports (Feature F)** | Tiered clinical significance filtering for weekly digests |

### Document & Image Processing
| Feature | Description |
|---------|-------------|
| **Smart Document Engine** | Auto-routes: Docling (typed PDF) → Surya (scanned) → Nanonets-OCR2 (handwritten) → MedGemma fallback |
| **OCR Quality Alerts** | Detects blur, low contrast, bad brightness, low resolution — warns doctor before processing |
| **Wound/Skin Comparison** | ORB feature matching + homography overlay + AI clinical summary |
| **Scratchpad** | Drag-drop any PDF/image → extract → "Save to Patient" |
| **Voice-to-Text** | Mic buttons on PrescriptionBox and ChatUI — faster-whisper + IndicWhisper for Hindi |

### Scheduling & Voice
| Feature | Description |
|---------|-------------|
| **Semantic Calendar** | 9 LangGraph tools: book, reschedule, cancel, bulk, block, smart-rearrange, NL query |
| **Booking Dialog** | Click empty slot → patient search → date/time → reason → book (with race condition protection) |
| **Voice Scheduling** | 5 locked commands in Hindi/English → ASR → intent → tools → TTS confirmation |
| **Doctor-Off Handling** | "I'm off Fri-Sat" → blocks → smart-rearranges → drafts personalized emails → approval screen |

### Patient-Facing
| Feature | Description |
|---------|-------------|
| **Doctor Search + Map** | OpenStreetMap (free, no API key) with PostGIS radius search + PIN code search |
| **Self-Booking** | See real availability → book → instant confirmation with telemedicine consent |
| **Report Inbox** | Prescriptions, invoices, certificates as PDF — downloadable from patient portal |
| **Document Timeline** | Unified chronological view of all patient documents with version citations |
| **AI Notifications** | Maverick generates contextual messages per event type via WebSocket |
| **Patient Profile** | Auto-populated demographics from registration — fills booking form automatically |
| **Consent Management** | DPDP-compliant consent tracking + data erasure (anonymize PII, preserve clinical records) |

### Billing & Documents
| Feature | Description |
|---------|-------------|
| **Prescription Box** | AI draft → JSON schema validated → doctor approves → version created → print-ready PDF |
| **Invoice/Billing** | Auto from consult, line items, tax, status tracking, QR code |
| **Medical Certificates** | Type-based templates (sick leave, fitness, school) → QR verification |
| **State-Specific Prescriptions** | 24 Indian states' regulatory header/footer text applied automatically |

### Security & Compliance
| Feature | Description |
|---------|-------------|
| **Multi-tenant RLS** | PostgreSQL Row-Level Security on every patient-bearing table |
| **PII Encryption** | pgcrypto for phone, email, address columns |
| **PII De-identification** | Strip pseudonyms at indexer, tools, and synthesizer boundaries |
| **Append-only Audit Log** | Every read/write/AI-suggestion/export logged |
| **Rate Limiting** | Per-doctor RPM limits via slowapi |
| **Sentry Error Tracking** | Backend + frontend error monitoring (opt-in via DSN) |
| **Offline PWA** | Service worker with Workbox caching for offline access |
| **Permissions-Policy** | Browser geolocation API enabled for map features |

### Doctor Profile
| Feature | Description |
|---------|-------------|
| **Profile Photo** | Upload + oval crop with drag-to-position and zoom control |
| **NMC Verification** | Registration number + state medical council + year — verified via NMC API or admin review |
| **Years of Experience** | Computed from year_of_registration — zero maintenance, auto-updates yearly |
| **Profile Completion Banner** | Amber prompt when verification is incomplete — drives search visibility |
| **Multi-Device Sessions** | Track active sessions, revoke individual devices |
| **State Selection** | Doctor's state controls which prescription regulatory header is applied |

### Developer Experience
| Feature | Description |
|---------|-------------|
| **Alembic Migrations** | Database schema versioning with baseline migration |
| **Hindi UI** | react-i18next with full translation files — language switcher in user menu |
| **Sentry DSN** | Environment-variable-driven error tracking |
| **Backup System** | pg_dump to MinIO with restore capability |

---

## Quick Start

### Prerequisites
- Docker Desktop 4.30+
- Node.js 20+ (for frontend dev)
- Python 3.11+ (for backend dev)
- NVIDIA RTX 3050+ (for local models) — optional for cloud deployment

### Development

```bash
# Clone
git clone https://github.com/RohanBhoge15/SoloPrac.git
cd SoloPrac

# Start all services (Postgres, Qdrant, Redis, MinIO, Backend)
docker compose up -d

# Backend logs
docker compose logs -f backend

# Run migrations
cd backend && alembic upgrade head

# Frontend dev server (separate terminal)
cd frontend && npm run dev
```

### Services
| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **Backend API** | http://localhost:8000 |
| **API Docs (OpenAPI)** | http://localhost:8000/docs |
| **Qdrant** | http://localhost:6333 |
| **PostgreSQL** | localhost:5432 |
| **MinIO Console** | http://localhost:9001 |
| **Redis** | localhost:6379 |

### Environment Variables
```bash
# .env (required)
JWT_SECRET_KEY=generate_strong_secret
ENCRYPTION_KEY=generate_32_byte_hex
POSTGRES_PASSWORD=generate_strong_password
NIM_API_KEY=your_nvidia_nim_key
GROQ_API_KEY=your_groq_key

# Optional
SENTRY_DSN=your_sentry_dsn
VITE_SENTRY_DSN=your_sentry_dsn
NMC_API_URL=  # empty = localhost direct verify
NMC_API_KEY=  # empty = admin review fallback
```

---

## Deployment (Oracle Cloud Free Tier)

```bash
# 1. Provision Oracle Cloud Free Tier instance (4 OCPU ARM, 24GB RAM)
# 2. Install Docker + Docker Compose
# 3. Clone repo and configure .env
# 4. Deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 5. Caddy auto-provisions HTTPS via Let's Encrypt
```

---

## Project Structure

```
SoloPrac/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── routers/            # API route handlers
│   │   ├── services/           # Business logic + research features
│   │   ├── agents/             # LangGraph agent (planner, router, tools)
│   │   ├── middleware/         # Audit log, RLS identity middleware
│   │   ├── utils/              # Phone normalization, helpers
│   │   ├── uploads/            # Uploaded documents, images
│   │   ├── config.py           # Settings via pydantic-settings
│   │   ├── database.py         # Async SQLAlchemy + init_db
│   │   ├── dependencies.py     # FastAPI deps (get_current_doctor, rate limit)
│   │   ├── models.py           # SQLAlchemy models (User, Doctor, Patient, etc.)
│   │   ├── schemas.py          # Pydantic schemas
│   │   └── main.py             # FastAPI entrypoint
│   ├── alembic/                # Database migrations
│   │   └── versions/
│   │       └── 001_baseline.py
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                   # React 19 + Vite
│   ├── src/
│   │   ├── components/        # shadcn/ui components
│   │   │   ├── ImageCropModal.tsx   # Profile photo crop
│   │   │   ├── MapPicker.tsx        # OpenStreetMap location picker
│   │   │   ├── PrescriptionBox.tsx  # Rx with voice mic
│   │   │   └── ChatUI.tsx          # Chat with voice mic
│   │   ├── pages/             # Page components
│   │   │   ├── Landing.tsx          # Professional landing page
│   │   │   ├── Register.tsx         # Doctor registration
│   │   │   ├── Login.tsx           # Login page
│   │   │   ├── Calendar.tsx        # Calendar with booking dialog
│   │   │   ├── Settings.tsx        # Profile photo, verification banner
│   │   │   ├── DoctorSearch.tsx    # Patient doctor search
│   │   │   ├── Scratchpad.tsx      # OCR with quality alerts
│   │   │   └── PatientDetail.tsx   # Document timeline
│   │   ├── hooks/             # Custom React hooks
│   │   ├── services/          # API clients
│   │   ├── store/             # Zustand stores
│   │   ├── locales/           # i18n translation files
│   │   │   ├── en.json
│   │   │   └── hi.json
│   │   └── main.tsx
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── Dockerfile
├── docs/
│   ├── architecture/          # System, DB, Agent architecture
│   ├── research/              # Lit survey, gap analysis, market research
│   ├── planning/              # Proposal, feasibility, Gantt, requirements
│   └── demo-flow.md
├── docker-compose.yml
├── Caddyfile
├── init-schema.sql
├── UpdatedIdea.MD
└── README.md
```

---

## Tech Stack Summary

| Category | Technology |
|----------|------------|
| **Frontend** | React 19, Vite, TypeScript, Tailwind, shadcn/ui, Framer Motion, TanStack Query, Zustand, cmdk, Leaflet, react-i18next, vite-plugin-pwa |
| **Backend** | FastAPI, Pydantic v2, SQLAlchemy 2.0, arq, LangGraph, Alembic |
| **Database** | PostgreSQL 16 + PostGIS, Qdrant, Redis |
| **Object Storage** | MinIO S3 (avatars, documents, PDFs) |
| **LLMs** | Llama-4 Maverick (NIM), Llama-3.1-8B (NIM), MedGemma-4B (local) |
| **AI/ML** | MedCPT, BGE-M3, BiomedCLIP, faster-whisper, IndicWhisper, OpenCV ORB |
| **Document** | Docling, Surya, Nanonets-OCR2-1.5B-exp |
| **PDF** | Jinja2, Playwright, ECharts |
| **Observability** | Langfuse (self-hosted), Sentry (opt-in) |
| **Infrastructure** | Docker Compose, Caddy, Oracle Cloud Free Tier |
| **Maps** | Leaflet.js + OpenStreetMap (zero cost) |
| **Auth** | Email + password (bcrypt), HttpOnly cookies, JWT |
| **Compliance** | DPDP Act (consent records, data erasure), NMC verification |

---

## Research Contributions (IEEE Paper)

| Feature | Section | Contribution |
|---------|---------|--------------|
| **A — Temporal Multimodal RAG** | Sec III | Time-aware clinical retrieval with formal scoring |
| **B — Self-Planning Agent** | Sec IV | Dynamic plan-execute-critic for medical workflows |
| **C — Cross-Modal Retrieval** | Sec V | Linear projector BiomedCLIP→BGE-M3 with InfoNCE |
| **D — Schema Alignment** | Sec VI | Zero-shot document-to-EMR mapping with critic loop |
| **E — Trajectory Clustering** | Sec VI | HDBSCAN + Mahalanobis on clinical embeddings |
| **F — Significance Reports** | Sec VI | Tiered clinical significance for automated digests |

> **Evaluation methodology:** See [`docs/research/research_features_evaluation_method.md`](docs/research/research_features_evaluation_method.md) for how to produce real, publishable numbers (baselines, ablation tables, LLM-as-judge, datasets) for each feature.

---

## Team

| Member | Role | GitHub |
|--------|------|--------|
| **Rohan Bhoge** | Tech Lead, Backend, RAG, Architecture | [@RohanBhoge15](https://github.com/RohanBhoge15) |
| **Ranveer Singh Thakur** | Frontend Lead, OCR Integration | [@ranveerst33](https://github.com/ranveerst33) |
| **Nihal Korgaonkar** | AI/ML Lead, Vision, Voice, Evaluations | [@nihalkorgaonkar](https://github.com/nihalkorgaonkar) |
| **Dev Patel** | Security Lead, DevOps, Planning | [@devptl3660-cloud](https://github.com/devptl3660-cloud) |

---

## Acknowledgments

- **NVIDIA NIM** for free-tier Llama 4 Maverick access
- **Groq** for free-tier Llama 3.2 90B Vision
- **Google** for MedGemma (academic license)
- **AI4Bharat** for IndicWhisper and Indic-Parler-TTS
- **Oracle Cloud** for Forever Free Tier infrastructure
- **Langfuse** for self-hosted observability
- **OpenStreetMap** for free map tiles
- **Sentry** for error tracking

---

## Citation

If you use SoloPrac AI in your research, please cite:

```bibtex
@inproceedings{soloprac2025,
  title={SoloPrac AI: A Multimodal Agentic Clinical Operating System with Version-Controlled Patient Intelligence},
  author={Bhoge, Rohan and Thakur, Ranveer Singh and Korgaonkar, Nihal and Patel, Dev},
  booktitle={IEEE Conference Proceedings},
  year={2025}
}
```

---

## License

MIT License — Free for academic and research use.
