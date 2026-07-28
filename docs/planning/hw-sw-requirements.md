# SoloPrac AI — Hardware & Software Requirements

## 1. Hardware Requirements

### 1.1 Development Machine (Primary — Rohan)
| Component | Specification | Purpose |
|:---------|:--------------|:--------|
| **GPU** | NVIDIA RTX 3050 (4-6 GB VRAM) | Local model inference: MedGemma-4B, Whisper, Parler-TTS |
| **CPU** | Intel i7-12th gen / AMD Ryzen 7+ | Embedding models (CPU), compilation, Docker |
| **RAM** | 16 GB minimum, 32 GB recommended | Docker containers + local models + browser |
| **Storage** | 512 GB NVMe SSD minimum | Models (~15 GB), Docker images (~20 GB), databases |
| **OS** | Windows 11 + WSL2 Ubuntu 22.04 | Docker Desktop + Linux environment |

### 1.2 Cloud Deployment (Production)
| Resource | Oracle Cloud Free Tier | Notes |
|:---------|:----------------------|:------|
| **Compute** | 4 ARM Ampere cores (O6) | Forever free; handles ~50 concurrent doctors |
| **Memory** | 24 GB RAM | Sufficient for all services |
| **Storage** | 200 GB Block Volume | PostgreSQL + Qdrant persistence |
| **Network** | 10 TB/month egress | More than enough |
| **GPU** | None (uses NIM + Groq APIs) | No local GPU needed in cloud |

### 1.3 Model Storage Estimates
| Model | Size (Q4) | Storage Location |
|:------|:---------:|:-----------------|
| MedGemma-4B-IT | ~3 GB | Local dev only (not in cloud) |
| faster-whisper large-v3 | ~3 GB | Local dev only |
| IndicWhisper | ~1.5 GB | Local dev only |
| Indic-Parler-TTS | ~1 GB | Local dev only |
| MedCPT (220M) | ~500 MB | Both |
| BGE-M3 (568M) | ~1.2 GB | Both |
| **Total local** | **~9 GB** | Within 512 GB SSD |

---

## 2. Software Requirements

### 2.1 Core Development Stack
| Software | Version | Purpose |
|:---------|:--------|:--------|
| **Docker Desktop** | 4.30+ | Container orchestration |
| **Docker Compose** | v2.25+ | Multi-container apps |
| **Git** | 2.40+ | Version control |
| **VS Code** | 1.85+ | IDE |
| **Node.js** | 20 LTS | Frontend build |
| **npm** | 10+ | Package manager |
| **Python** | 3.11+ | Backend runtime |
| **Poetry** | 1.8+ | Python dependency management |

### 2.2 Backend Dependencies (Python)
Key packages — full list in `pyproject.toml`:
- fastapi, pydantic, sqlalchemy, asyncpg
- qdrant-client, redis, arq
- langgraph, langchain-core
- openai (NIM/Groq compatibility)
- python-jose (JWT), passlib (password hashing)
- slowapi (rate limiting)
- playwright, jinja2 (PDF generation)
- opencv-python (ORB image registration)
- pillow, numpy, pandas
- alembic (database migrations)
- sentry-sdk[fastapi] (error tracking)
- minio (object storage)

### 2.3 Frontend Dependencies (Node)
Key packages — full list in `package.json`:
- react, react-dom, react-router-dom
- typescript, vite
- @tanstack/react-query, zustand
- framer-motion, cmdk, lucide-react
- leaflet, react-leaflet (maps)
- react-i18next, i18next (Hindi UI)
- vite-plugin-pwa (offline support)
- @sentry/react (error tracking)

### 2.4 Infrastructure (Docker Compose Services)
```yaml
services:
  postgres:
    image: postgis/postgis:16-3.4
  qdrant:
    image: qdrant/qdrant:v1.12.0
  redis:
    image: redis:7-alpine
  minio:
    image: minio/minio
  backend:
    build: ./backend
  frontend:
    build: ./frontend
```

### 2.5 External API Accounts (All Free Tier)
| Service | Account | Free Tier Limits |
|:--------|:--------|:-----------------|
| **NVIDIA NIM** | nvidia.com | Generous; Llama-4 Maverick + Llama-3.1-8B + BiomedCLIP |
| **Groq Cloud** | console.groq.com | 14,400 req/day for Llama-3.2-90B-Vision |
| **SMTP** | Gmail / SendGrid | 500 emails/day (Gmail) or 100/day (SendGrid free) |
| **Sentry** | sentry.io | 5K errors/month free |

---

## 3. Environment Variables

```bash
# .env (required)
JWT_SECRET_KEY=generate_strong_secret
ENCRYPTION_KEY=generate_32_byte_hex
POSTGRES_PASSWORD=generate_strong_password
NIM_API_KEY=your_nvidia_nim_key
GROQ_API_KEY=your_groq_key
MINIO_ROOT_USER=generate_strong_password
MINIO_ROOT_PASSWORD=generate_strong_password

# Optional
SENTRY_DSN=your_sentry_dsn
VITE_SENTRY_DSN=your_sentry_dsn
NMC_API_URL=  # empty = localhost direct verify
NMC_API_KEY=  # empty = admin review fallback
WHISPER_PATH=  # custom path to whisper model
INDIC_WHISPER_PATH=  # custom path to indic whisper model
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```
