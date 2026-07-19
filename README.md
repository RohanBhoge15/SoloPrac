# SoloPrac AI

> A multimodal, agentic clinical operating system for solo medical practitioners, built around a **version-controlled patient intelligence layer**.

## 🎯 Vision

Every solo GP deserves clinical intelligence that matches hospital systems — without the cost, complexity, or vendor lock-in. SoloPrac AI makes this possible by combining:

- **Version-controlled patient records** — Immutable, Git-like history for every patient
- **Temporal-aware AI** — RAG that knows *when* information was true
- **Voice-first scheduling** — "I'm off Friday, handle it" in Hindi + English
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
| **Cross-Modal Retrieval (Feature C)** | NV-CLIP → BGE-M3 projector for image↔text search |
| **Zero-Shot Schema Alignment (Feature D)** | LLM maps any document to canonical patient schema |
| **Trajectory Clustering (Feature E)** | HDBSCAN + Mahalanobis for proactive risk alerts |
| **Significance-Aware Reports (Feature F)** | Tiered clinical significance filtering for weekly digests |

### Document & Image Processing
| Feature | Description |
|---------|-------------|
| **Smart Document Engine** | Auto-routes: Docling (typed PDF) → Surya (scanned) → GOT-OCR (handwritten) → MedGemma fallback |
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
| **C — Cross-Modal Retrieval** | Sec V | Linear projector NV-CLIP→BGE-M3 with InfoNCE |
| **D — Schema Alignment** | Sec VI | Zero-shot document-to-EMR mapping with critic loop |
| **E — Trajectory Clustering** | Sec VI | HDBSCAN + Mahalanobis on clinical embeddings |
| **F — Significance Reports** | Sec VI | Tiered clinical significance for automated digests |

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

```bash
# Feature A: Temporal RAG evaluation
python -m evals.temporal_rag

# Feature B: Self-planning agent
python -m evals.self_planning

# Feature C: Cross-modal projector
python -m evals.cross_modal

# Feature D: Schema alignment
python -m evals.schema_alignment

# Feature E: Trajectory clustering
python -m evals.trajectory_clustering

# Feature F: Weekly reports
python -m evals.weekly_reports
```

---

## 📁 Project Structure

```
SoloPrac/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/               # API routes
│   │   ├── core/              # Config, security, database
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # Business logic
│   │   ├── agents/            # LangGraph agents
│   │   ├── workers/           # arq background jobs
│   │   └── main.py            # FastAPI entrypoint
│   ├── tests/
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
│   └── Dockerfile
├── docs/
│   ├── architecture/          # System, DB, Agent architecture
│   ├── research/              # Lit survey, gap analysis, market research
│   ├── planning/              # Proposal, feasibility, Gantt, requirements
│   └── images/                # Mermaid diagrams (PNG + source)
├── docker-compose.yml
├── docker-compose.prod.yml
├── .gitignore
└── README.md
```

---

## 📊 Tech Stack Summary

| Category | Technology |
|----------|------------|
| **Frontend** | React 19, Vite, TypeScript, Tailwind, shadcn/ui, Framer Motion, TanStack Query, Zustand, cmdk, Leaflet |
| **Backend** | FastAPI, Pydantic v2, SQLAlchemy 2.0, arq, LangGraph |
| **Database** | PostgreSQL 16 + PostGIS, Qdrant, Redis |
| **LLMs** | Llama-4 Maverick (NIM), Llama-3.1-8B (NIM), Llama-3.2-90B-V (Groq), MedGemma-4B (local) |
| **AI/ML** | MedCPT, BGE-M3, NV-CLIP, faster-whisper, IndicWhisper, Indic-Parler-TTS, OpenCV ORB |
| **Document** | Docling, Surya, GOT-OCR 2.0 |
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