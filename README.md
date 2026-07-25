# SoloPrac AI

> A multimodal, agentic clinical operating system for solo medical practitioners in India, built around a **version-controlled patient intelligence layer** with **tiered doctor verification** and **cross-clinic patient identity**.

## 🎯 Vision

Every solo GP in India deserves clinical intelligence that matches hospital systems — without the cost, complexity, or vendor lock-in. SoloPrac AI makes this possible by combining:

- **Version-controlled patient records** — Immutable, Git-like history for every patient
- **Temporal-aware AI** — RAG that knows *when* information was true
- **Voice-first scheduling** — "I'm off Friday, handle it" in Hindi + English
- **Tiered doctor verification** — Self-register instantly, verify for public trust
- **Cross-clinic patient identity** — One person can visit multiple doctors without duplicate accounts
- **Zero-cost deployment** — Runs entirely on free tiers (Oracle Cloud, NVIDIA NIM, Groq)

---

## 🏗️ Architecture

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
│ PG  │  │Qdrant│ │Redis │ │Langfuse  │
│16+  │  │Hybrid│ │arq   │ │Observab. │
│RLS  │  │Vectors│ │Queue │ │+Tracing  │
└─────┘  └──────┘  └──────┘  └──────────┘
```

---

## ✨ Features

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
| **Wound/Skin Comparison** | ORB feature matching + homography overlay + AI clinical summary |
| **Scratchpad** | Drag-drop any PDF/image → extract → "Save to Patient" |

### Scheduling & Voice
| Feature | Description |
|---------|-------------|
| **Semantic Calendar** | 9 LangGraph tools: book, reschedule, cancel, bulk, block, smart-rearrange, NL query |
| **Voice Scheduling** | 5 locked commands in Hindi/English → ASR → intent → tools → TTS confirmation |
| **Doctor-Off Handling** | "I'm off Fri-Sat" → blocks → smart-rearranges → drafts personalized emails → approval screen |

### Patient-Facing
| Feature | Description |
|---------|-------------|
| **Doctor Search + Map** | Leaflet.js + OpenStreetMap (free, no API key) |
| **Self-Booking** | See real availability → book → instant confirmation |
| **Report Inbox** | Prescriptions, invoices, certificates as PDF |
| **AI Notifications** | Maverick generates contextual messages per event type |

### Billing & Documents
| Feature | Description |
|---------|-------------|
| **Prescription Box** | AI draft → JSON schema validated → in-app highlight → print-ready PDF |
| **Invoice/Billing** | Auto from consult, line items, tax, status tracking, QR code |
| **Medical Certificates** | Type-based templates (sick leave, fitness, school) → QR verification |

### Security & Compliance
- **Multi-tenant RLS** on every table via PostgreSQL Row-Level Security
- **PII encryption** (pgcrypto) for phone, email, address
- **Append-only audit log** — every read/write/AI-suggestion/export logged
- **Structured LLM output** — JSON Schema prevents prompt injection
- **Rate limiting** per doctor (protects free-tier quotas)

---

## 📚 Research Contributions (IEEE Paper)

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

## 🚀 Quick Start

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

# Start all services (Postgres, Qdrant, Redis, Langfuse, Caddy, Backend, Frontend)
docker compose up -d

# Backend logs
docker compose logs -f backend

# Frontend dev server (separate terminal)
cd frontend && pnpm dev
```

### Services
| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **Backend API** | http://localhost:8000 |
| **API Docs (OpenAPI)** | http://localhost:8000/docs |
| **Langfuse** | http://localhost:3000 |
| **Qdrant** | http://localhost:6333 |
| **PostgreSQL** | localhost:5432 |

---

## 📦 Deployment (Oracle Cloud Free Tier)

```bash
# 1. Provision Oracle Cloud Free Tier instance (4 OCPU ARM, 24GB RAM)
# 2. Install Docker + Docker Compose
# 3. Clone repo and configure .env
# 4. Deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 5. Caddy auto-provisions HTTPS via Let's Encrypt
```

---

## 🧪 Running Evaluations

> **Methodology:** For how to turn these endpoints into publishable paper numbers (baselines, ablation tables, datasets, doctor study), see [`docs/research/research_features_evaluation_method.md`](docs/research/research_features_evaluation_method.md).

Evaluations run via API endpoints (no separate scripts needed):

```bash
# Feature A: Full eval suite (Temporal RAG + baselines)
curl -X POST http://localhost:8000/api/v1/evaluation/run

# Feature B: Self-planning (100-query test set)
curl -X POST http://localhost:8000/api/v1/evaluation/feature-b

# Feature C: Cross-modal projector (trains + evaluates)
curl -X POST "http://localhost:8000/api/v1/evaluation/feature-c?num_pairs=200"

# Feature E: Trajectory clustering (synthetic cohort)
curl -X POST "http://localhost:8000/api/v1/evaluation/feature-e?num_patients=100"

# Feature F: Likert study design
curl -X GET http://localhost:8000/api/v1/weekly-report/likert-study

# Feature D: Schema alignment (via document upload)
curl -X POST -F "file=@prescription.pdf" http://localhost:8000/api/v1/documents/parse
```

---

## 📁 Project Structure

```
SoloPrac/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── routers/            # API route handlers
│   │   ├── services/           # Business logic + research features
│   │   ├── agents/             # LangGraph agent (planner, router, tools)
│   │   ├── middleware/         # Audit log, RLS identity middleware
│   │   ├── uploads/            # Uploaded documents, images
│   │   ├── config.py           # Settings via pydantic-settings
│   │   ├── database.py         # Async SQLAlchemy + init_db
│   │   ├── dependencies.py     # FastAPI deps (get_current_doctor, rate limit)
│   │   ├── models.py           # SQLAlchemy models (User, Doctor, Patient, etc.)
│   │   ├── schemas.py          # Pydantic schemas
│   │   └── main.py             # FastAPI entrypoint
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                   # React 19 + Vite
│   ├── src/
│   │   ├── components/        # shadcn/ui components
│   │   ├── pages/             # Page components
│   │   ├── hooks/             # Custom React hooks
│   │   ├── services/          # API clients
│   │   ├── store/             # Zustand stores
│   │   └── main.tsx
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── Dockerfile
├── docs/
│   ├── architecture/          # System, DB, Agent architecture
│   ├── research/              # Lit survey, gap analysis, market research
│   ├── planning/              # Proposal, feasibility, Gantt, requirements
│   └── images/                # Mermaid diagrams (PNG + source)
├── docker-compose.yml
├── Caddyfile
├── init-schema.sql
└── README.md
```

---

## 📊 Tech Stack Summary

| Category | Technology |
|----------|------------|
| **Frontend** | React 19, Vite, TypeScript, Tailwind, shadcn/ui, Framer Motion, TanStack Query, Zustand, cmdk, Leaflet |
| **Backend** | FastAPI, Pydantic v2, SQLAlchemy 2.0, arq, LangGraph |
| **Database** | PostgreSQL 16 + PostGIS, Qdrant, Redis |
| **LLMs** | Llama-4 Maverick (NIM), Llama-3.1-8B (NIM), MedGemma-4B (local) |
| **AI/ML** | MedCPT, BGE-M3, BiomedCLIP, faster-whisper, IndicWhisper, Indic-Parler-TTS, OpenCV ORB |
| **Document** | Docling, Surya, Nanonets-OCR2-1.5B-exp |
| **PDF** | Jinja2, Playwright, ECharts |
| **Observability** | Langfuse (self-hosted) |
| **Infrastructure** | Docker Compose, Caddy, Oracle Cloud Free Tier |
| **Maps** | Leaflet.js + OpenStreetMap (zero cost) |

---

## 📝 License

MIT License — Free for academic and research use.

---

## 🤝 Team

| Member | Role | GitHub |
|--------|------|--------|
| **Rohan Bhoge** | Tech Lead, Backend, RAG, Architecture | [@RohanBhoge15](https://github.com/RohanBhoge15) |
| **Ranveer Singh Thakur** | Frontend Lead, OCR Integration | [@ranveerst33](https://github.com/ranveerst33) |
| **Nihal Korgaonkar** | AI/ML Lead, Vision, Voice, Evaluations | [@nihalkorgaonkar](https://github.com/nihalkorgaonkar) |
| **Dev Patel** | Security Lead, DevOps, Planning | [@devptl3660-cloud](https://github.com/devptl3660-cloud) |

---

## 🙏 Acknowledgments

- **NVIDIA NIM** for free-tier Llama 4 Maverick access
- **Groq** for free-tier Llama 3.2 90B Vision
- **Google** for MedGemma (academic license)
- **AI4Bharat** for IndicWhisper and Indic-Parler-TTS
- **Oracle Cloud** for Forever Free Tier infrastructure
- **Langfuse** for self-hosted observability
- **OpenStreetMap** for free map tiles

---

## 📄 Citation

If you use SoloPrac AI in your research, please cite:

```bibtex
@inproceedings{soloprac2025,
  title={SoloPrac AI: A Multimodal Agentic Clinical Operating System with Version-Controlled Patient Intelligence},
  author={Bhoge, Rohan and Thakur, Ranveer Singh and Korgaonkar, Nihal and Patel, Dev},
  booktitle={IEEE Conference Proceedings},
  year={2025}
}
```