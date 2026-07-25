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

### 1.2 Team Member Machines (All 4)
| Component | Specification | Purpose |
|:---------|:--------------|:--------|
| **CPU** | 8-core minimum (Intel i5-12th / AMD Ryzen 5+) | Frontend build, Docker |
| **RAM** | 16 GB minimum | Docker + VS Code + browser |
| **Storage** | 256 GB SSD minimum | Code, Docker images |
| **OS** | Windows 11 / macOS / Linux | Cross-platform Docker |

### 1.3 Cloud Deployment (Production)
| Resource | Oracle Cloud Free Tier | Notes |
|:---------|:----------------------|:------|
| **Compute** | 4 ARM Ampere cores (O6) | Forever free; handles ~50 concurrent doctors |
| **Memory** | 24 GB RAM | Sufficient for all services |
| **Storage** | 200 GB Block Volume | PostgreSQL + Qdrant persistence |
| **Network** | 10 TB/month egress | More than enough |
| **GPU** | None (uses NIM + Groq APIs) | No local GPU needed in cloud |

### 1.4 Model Storage Estimates
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
| **pnpm** | 9+ | Fast package manager |
| **Python** | 3.11+ | Backend runtime |
| **Poetry** | 1.8+ | Python dependency management |

### 2.2 Backend Dependencies (Python)
```toml
# Key packages — full list in pyproject.toml
fastapi = "^0.115.0"
pydantic = "^2.9.0"
sqlalchemy = "^2.0.0"
asyncpg = "^0.29.0"
qdrant-client = "^1.12.0"
redis = "^5.0.0"
arq = "^0.23.0"
langgraph = "^0.2.0"
langchain-core = "^0.3.0"
openai = "^1.30.0"          # For NIM/Groq compatibility
python-jose = "^3.3.0"      # JWT
passlib = "^1.7.4"          # Password hashing
fastapi-users = "^13.0.0"   # Auth
slowapi = "^0.1.9"          # Rate limiting
pgcrypto = "^1.0"           # PII encryption
caddy = "^2.8.0"            # Reverse proxy (via Docker)
playwright = "^1.40.0"      # PDF generation
jinja2 = "^3.1.0"           # Templates
echarts-python = "^2.1.0"   # Charts in PDFs
opencv-python = "^4.9.0"    # ORB image registration
pillow = "^10.0.0"          # Image processing
numpy = "^1.26.0"
pandas = "^2.2.0"
```

### 2.3 Frontend Dependencies (Node)
```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^6.26.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "@tanstack/react-query": "^5.50.0",
    "zustand": "^4.5.0",
    "framer-motion": "^11.0.0",
    "cmdk": "^1.0.0",
    "lucide-react": "^0.440.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.5.0",
    "date-fns": "^3.6.0",
    "leaflet": "^1.9.0",
    "react-leaflet": "^4.2.0",
    "eventsource-parser": "^1.1.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/leaflet": "^1.9.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "eslint": "^8.57.0",
    "prettier": "^3.3.0"
  }
}
```

### 2.4 Infrastructure (Docker Compose Services)
```yaml
services:
  postgres:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: soloprac
      POSTGRES_USER: soloprac
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-schema.sql:/docker-entrypoint-initdb.d/init-schema.sql
    ports: ["5432:5432"]

  qdrant:
    image: qdrant/qdrant:v1.12.0
    volumes:
      - qdrant_data:/qdrant/storage
    ports: ["6333:6333", "6334:6334"]

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
    ports: ["6379:6379"]

  langfuse:
    image: langfuse/langfuse:2.40.0
    environment:
      DATABASE_URL: postgresql://postgres:...@postgres:5432/langfuse
      NEXTAUTH_SECRET: ${LANGFUSE_SECRET}
    volumes: [langfuse_data:/data]
    ports: ["3000:3000"]
    depends_on: [postgres]

  caddy:
    image: caddy:2.8-alpine
    ports: ["80:80", "443:443", "443:443/udp"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

  backend:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql://...
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://redis:6379
      - LANGFUSE_HOST=http://langfuse:3000
    ports: ["8000:8000"]
    depends_on: [postgres, qdrant, redis, langfuse]

  frontend:
    build: ./frontend
    ports: ["3000:80"]
    depends_on: [backend]
```

### 2.5 External API Accounts (All Free Tier)
| Service | Account | Free Tier Limits |
|:--------|:--------|:-----------------|
| **NVIDIA NIM** | nvidia.com | Generous; Llama-4 Maverick + Llama-3.1-8B + BiomedCLIP |
| **Groq Cloud** | console.groq.com | 14,400 req/day for Llama-3.2-90B-Vision |
| **Google Cloud** | console.cloud.google.com | OAuth 2.0 credentials (free) |
| **SMTP** | Gmail / SendGrid | 500 emails/day (Gmail) or 100/day (SendGrid free) |

---

## 3. Development Environment Setup

### 3.1 One-Command Bootstrap
```bash
# Clone repo
git clone https://github.com/RohanBhoge15/SoloPrac.git
cd SoloPrac

# Start all services
docker compose up -d

# Verify
curl http://localhost:8000/health
# {"status": "ok", "services": {"postgres": "up", "qdrant": "up", "redis": "up", "langfuse": "up"}}

# Frontend (separate terminal)
cd frontend && pnpm install && pnpm dev
```

### 3.2 Required VS Code Extensions
- Python (Microsoft)
- Pylance
- Docker
- GitLens
- ESLint
- Prettier
- Tailwind CSS IntelliSense
- REST Client

### 3.3 Environment Variables Template
```bash
# .env (never commit)
POSTGRES_PASSWORD=generate_strong_password
LANGFUSE_SECRET=generate_strong_secret
JWT_SECRET_KEY=generate_strong_secret
NIM_API_KEY=your_nvidia_nim_key
GROQ_API_KEY=your_groq_key
GOOGLE_CLIENT_ID=your_google_oauth_id
GOOGLE_CLIENT_SECRET=your_google_oauth_secret
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ENCRYPTION_KEY=generate_32_byte_hex  # for pgcrypto/age
```

---

## 4. Validation Checklist

| Requirement | Validated By |
|:------------|:-------------|
| RTX 3050 runs MedGemma-4B Q4 | `docker run --gpus all vllm/vllm-openai --model google/medgemma-4b-it --quantization q4` |
| Docker Compose starts all 8 services | `docker compose up -d && docker compose ps` |
| Qdrant accepts named vectors | `curl -X POST localhost:6333/collections/test/points` |
| NIM API key works | `curl -H "Authorization: Bearer $NIM_API_KEY" https://integrate.api.nvidia.com/v1/models` |
| Groq API key works | `curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models` |
| PostgreSQL RLS works | Insert as doctor A, query as doctor B → 0 rows |
| FastAPI OpenAPI generates TS types | `pnpm run generate-api` in frontend |
| Playwright renders PDF | `python -m playwright install chromium && python test_pdf.py` |

All items above tested and working in prototype.