# SoloPrac AI — Technology Stack Finalization

## 1. Stack Selection Criteria

Every technology choice was evaluated against:
1. **Free-tier availability** — Zero cost for development and deployment
2. **Production readiness** — Used in real medical/enterprise systems
3. **Community & documentation** — Active maintenance, strong ecosystem
4. **Research alignment** — Must produce paper-worthy results
5. **Resource efficiency** — Must run on RTX 3050 (4-6 GB VRAM)

---

## 2. Finalized Technology Stack

| Layer | Technology | Version | License | Selection Rationale |
|-------|-----------|:-------:|:-------:|---------------------|
| **Frontend Framework** | React | 19 | MIT | Industry standard; huge ecosystem; shadcn/ui compatibility |
| **Build Tool** | Vite | 6+ | MIT | 10x faster than CRA; native ESM; HMR out of the box |
| **UI Components** | shadcn/ui | Latest | MIT | Copy-paste components; full Tailwind customization; accessible |
| **CSS** | Tailwind CSS | 4 | MIT | Utility-first; consistent design system; small bundle size |
| **State Management** | Zustand + TanStack Query | Latest | MIT | Zustand for UI state; TanStack Query for server state caching |
| **Animation** | Framer Motion | 11 | MIT | Production-grade animations for timeline scrubber |
| **Command Palette** | cmdk | Latest | MIT | Accessible command menu for power users |
| **Icons** | Lucide React | Latest | ISC | Clean, consistent icon set |
| **i18n** | react-i18next | Latest | MIT | Hindi + English UI translation with language switcher |
| **PWA** | vite-plugin-pwa | Latest | MIT | Offline support via Workbox service worker |
| **Backend Framework** | FastAPI | 0.115+ | MIT | Async-native; auto OpenAPI docs; Pydantic validation |
| **ORM** | SQLAlchemy | 2.0+ | MIT | Most mature Python ORM; async support |
| **Migrations** | Alembic | Latest | MIT | Database schema versioning with baseline migration |
| **Data Validation** | Pydantic | 2+ | MIT | Type-safe; JSON Schema generation; FastAPI integration |
| **Task Queue** | arq | Latest | MIT | Redis-based; async-native; lightweight |
| **Agent Framework** | LangGraph | Latest | MIT | Graph-based agent orchestration; built-in streaming |
| **LLM (Heavy)** | Llama-4 Maverick 17B-128E | NIM | Free tier | MoE architecture; strong reasoning; free via NVIDIA NIM |
| **LLM (Router)** | Llama-3.1-8B | NIM | Free tier | Fast; sufficient for intent classification |
| **Vision (General)** | Llama-3.2-90B-V | Groq | Free tier | ~14,400 req/day free; excellent at general medical images |
| **Vision (Medical)** | MedGemma-4B-IT | Local | Research | Free for academic use; specialized for radiology/dermatology |
| **ASR (English)** | faster-whisper large-v3 | CTranslate2 | MIT | 4x faster than Whisper; multilingual |
| **ASR (Hindi)** | AI4Bharat IndicWhisper | Latest | Apache 2.0 | Fine-tuned on 10K+ hours Indic speech |
| **TTS** | Indic-Parler-TTS | Latest | Apache 2.0 | English + Hindi in one model; 880MB on GPU |
| **Medical Embeddings** | MedCPT (ncbi) | 768d | MIT | Purpose-built for clinical text retrieval |
| **Hybrid Embeddings** | BGE-M3 (BAAI) | 1024d | MIT | Dense + sparse + multi-vector; Hindi support |
| **Image Embeddings** | BiomedCLIP | 512d | MIT | Runs locally; free, no API needed; SOTA medical image-text |
| **Vector Database** | Qdrant | 1.12+ | Apache 2.0 | Named vectors; hybrid dense+sparse; payload filtering |
| **Relational Database** | PostgreSQL | 16 | PostgreSQL | RLS, pgcrypto, PostGIS; mature and reliable |
| **Cache/Queue** | Redis | 7+ | BSD | arq queue + caching + rate limiting tracking |
| **Object Storage** | MinIO | Latest | AGPL | S3-compatible; stores avatars, PDFs, documents |
| **Observability** | Langfuse | Self-hosted | MIT | LLM tracing + evaluation dashboards; free self-hosted |
| **Error Tracking** | Sentry | Latest | BSL | Opt-in via DSN; backend + frontend |
| **Reverse Proxy** | Caddy | 2+ | Apache 2.0 | Auto HTTPS; simple config; Let's Encrypt integration |
| **OCR (Typed)** | Docling (IBM) | Latest | Apache 2.0 | Table preservation; reading order; Hindi support |
| **OCR (Scanned)** | Surya | Latest | MIT | Multilingual; layout-aware |
| **OCR (Handwritten)** | Nanonets-OCR2-1.5B-exp | Latest | Apache 2.0 | SOTA handwritten/printed OCR; free; better than GOT-OCR |
| **PDF Generation** | Jinja2 + Playwright | Latest | MIT | HTML→PDF with full CSS support; ECharts SVGs |
| **Image Processing** | OpenCV (ORB) | 4.9+ | Apache 2.0 | Feature matching; homography; free |
| **Free Maps** | Leaflet.js + OpenStreetMap | Latest | BSD | No API key required; free tile layer |
| **Authentication** | Email/Password (bcrypt) + JWT + HttpOnly Cookies | — | — | XSS-safe; no third-party dependency |
| **Deployment** | Docker Compose | Latest | Apache 2.0 | Reproducible; Oracle Cloud Free Tier compatible |

---

## 3. GPU Memory Budget

| Model | VRAM | Strategy |
|-------|:----:|----------|
| MedGemma-4B-IT (Q4) | ~3 GB | GPU; loaded on demand |
| faster-whisper large-v3 | ~2 GB | GPU; swapped with MedGemma |
| Indic-Parler-TTS | ~2 GB | GPU; swapped with Whisper |
| BiomedCLIP | ~1 GB | GPU; small, can stay loaded |
| MedCPT + BGE-M3 | ~0 GB | CPU only (sufficient) |

**Total RTX 3050 VRAM:** 4-6 GB
**Strategy:** Only one large model on GPU at a time. Orchestrator swaps based on incoming request type. BiomedCLIP is small enough to co-reside.

---

## 4. Why NOT alternatives considered

| Technology | Alternative | Why Not |
|------------|-------------|---------|
| Next.js | React + Vite | More complexity than needed; no SSR requirement |
| Django | FastAPI | Heavy; not async-first by default |
| Pinecone | Qdrant | Paid; no self-hosting; no named vectors |
| AWS/GCP | Oracle Cloud | Free tier ends; Oracle is forever-free |
| Kokoro TTS | Indic-Parler-TTS | Kokoro is English-only; Parler has Hindi |
| Redis Queue (RQ) | arq | arq is async-native |
| LangChain | LangGraph | LangGraph gives graph-based agent control |
| traditional RAG | Temporal RAG | No temporal awareness; future data leaks |
| Google Maps API | OpenStreetMap + Leaflet.js | Google Maps costs $200+/month; OSM is free |
| Practo (paid) | SoloPrac (free) | Practo charges ₹2000-5000/month; SoloPrac is free + open source |
| Google OAuth | Email/Password | Removed to simplify auth; no third-party dependency |
| OTP (patient auth) | Email/Password | Email+password is simpler; no SMS gateway needed |
| Hardcoded drug DB | LLM extraction | Doctor photographs prescription; LLM handles misspellings natively |
| Local file storage | MinIO S3 | S3-compatible; scalable; avatars served via presigned URLs |
| Lab reference ranges | Removed | Hardcoded ranges are useless for solo doctors |
