# SoloPrac AI — Feasibility Study

## 1. Technical Feasibility

### 1.1 Architecture Feasibility
All proposed technologies are production-ready with active communities:

| Component | Maturity | Evidence |
|-----------|:--------:|----------|
| FastAPI | High | Used by Microsoft, Uber, Netflix |
| React 19 + Vite | High | Meta, Vercel, 1M+ weekly downloads |
| LangGraph | High | LangChain ecosystem; used by multiple LLM apps |
| PostgreSQL 16 + RLS | High | Decades of production use |
| Qdrant | High | Used by Redis, Snowflake, Cursor; 15K+ stars |
| NVIDIA NIM | High | Enterprise-grade inference; free tier available |
| Groq API | High | 14,400 req/day free; sub-second latency |
| MinIO | High | S3-compatible; production-grade object storage |

### 1.2 AI Model Feasibility

| Model | Access | Latency | Quality | Status |
|-------|:------:|:-------:|:-------:|:------:|
| Llama-4 Maverick (NIM) | Free API | ~500ms | SOTA for open weights | **Tested** |
| Llama-3.1-8B (NIM) | Free API | ~100ms | Strong for routing | **Tested** |
| Llama-3.2-90B-V (Groq) | Free API | ~800ms | Excellent vision | **Tested** |
| MedGemma-4B (local) | Local GPU | ~2s | Medical-specialized | **Verified** |
| faster-whisper large-v3 | Local GPU | ~1.5s | 4x faster than Whisper | **Tested** |
| IndicWhisper | Local GPU | ~2s | Best Hindi ASR | **Tested** |
| Indic-Parler-TTS | Local GPU | ~1s | English+Hindi | **Tested** |
| MedCPT / BGE-M3 | Local CPU | ~50ms | SOTA embeddings | **Tested** |

### 1.3 Integration Feasibility
All components have well-documented Python/JS APIs:
- FastAPI ↔ LangGraph: native Python integration
- FastAPI ↔ Qdrant: official Python client
- FastAPI ↔ NIM/Groq: OpenAI-compatible API
- React ↔ FastAPI: auto-generated TypeScript from OpenAPI
- OpenCV ORB: pure Python, no GPU dependency
- MinIO ↔ FastAPI: official Python client
- Alembic ↔ SQLAlchemy: native integration

---

## 2. Operational Feasibility

### 2.1 Team Capabilities
| Skill | Team Coverage | Risk |
|-------|:-------------:|:----:|
| Python/FastAPI | Rohan (lead) + Nihal | Low |
| React/TypeScript | Ranveer (lead) | Low |
| ML/AI (embeddings, training) | Nihal (lead) | Medium |
| Security/DevOps | Dev (lead) | Low |
| Clinical domain knowledge | Mentor + 1 practicing GP | Low |

### 2.2 Time Feasibility
15 weeks × 4 people = 60 person-weeks. All core features built and tested. Paper and deployment in progress.

### 2.3 Infrastructure Feasibility
| Resource | Requirement | Status |
|----------|:-----------:|:------:|
| GPU (local) | RTX 3050 (4-6 GB) | Available |
| Cloud compute | Oracle Free Tier (4 ARM, 24GB) | Available |
| API quotas | NIM (generous), Groq (14.4K/day) | Free tier sufficient |
| Storage | ~50 GB for models + data | Oracle provides |
| Domain/SSL | Free (Caddy auto HTTPS) | Included |

---

## 3. Economic Feasibility

### 3.1 Development Cost
| Item | Cost | Notes |
|------|:----:|-------|
| Hardware (already owned) | ₹0 | RTX 3050 + laptops |
| Cloud hosting | ₹0 | Oracle Free Tier forever |
| API calls | ₹0 | Free tiers generous |
| Domain/SSL | ₹0 | Caddy + Let's Encrypt |
| Team stipends | N/A | Academic project |

**Total development cost: ₹0**

### 3.2 Operational Cost (Post-Development)
| Scale | Monthly Cost | Basis |
|:-----:|:------------:|-------|
| 1 doctor (demo) | ₹0 | Oracle Free Tier |
| 10 doctors | ₹0 | Oracle Free Tier (4 ARM cores handle ~50 concurrent) |
| 100 doctors | ~$200 | Need paid cloud; within budget for small SaaS |

---

## 4. Risk Assessment Matrix

| Risk | Probability | Impact | Score | Mitigation |
|:----|:-----------:|:------:|:-----:|------------|
| GPU OOM on RTX 3050 | High | High | 9 | Model swap orchestrator; CPU fallback; quantize Q4 |
| Free LLM rate limits | Medium | Medium | 6 | Aggressive caching; request batching; graceful degradation |
| Team member dropout | Medium | High | 6 | Cross-training; AI code gen handles 80% boilerplate |
| Integration complexity | High | High | 9 | Interface-first design; contract tests per module |

**Overall Risk Score: Medium-High** — Manageable with fixed scope and weekly checkpoints.

---

## 5. Conclusion

**Technically feasible:** All components tested and validated.
**Operationally feasible:** Team has required skills; 15 weeks with buffer.
**Economically feasible:** ₹0 development cost; free-tier deployment.
**Legally feasible:** Documented as academic research tool; DPDP compliance implemented.

**Status: All core features built and tested. Paper and deployment in progress.**
