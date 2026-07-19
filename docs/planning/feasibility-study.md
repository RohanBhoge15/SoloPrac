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
| Docker Compose | High | Industry standard for local dev |

### 1.2 AI Model Feasibility

| Model | Access | Latency | Quality | Status |
|-------|:------:|:-------:|:-------:|:------:|
| Llama-4 Maverick (NIM) | Free API | ~500ms | SOTA for open weights | ✅ Tested |
| Llama-3.1-8B (NIM) | Free API | ~100ms | Strong for routing | ✅ Tested |
| Llama-3.2-90B-V (Groq) | Free API | ~800ms | Excellent vision | ✅ Tested |
| MedGemma-4B (local) | Local GPU | ~2s | Medical-specialized | ✅ Verified |
| faster-whisper large-v3 | Local GPU | ~1.5s | 4x faster than Whisper | ✅ Tested |
| IndicWhisper | Local GPU | ~2s | Best Hindi ASR | ✅ Tested |
| Indic-Parler-TTS | Local GPU | ~1s | English+Hindi | ✅ Tested |
| MedCPT / BGE-M3 | Local CPU | ~50ms | SOTA embeddings | ✅ Tested |

**GPU Strategy Validated:** RTX 3050 (4-6 GB VRAM) can run one model at a time with Q4 quantization. Model swap orchestrator adds ~500ms overhead — acceptable for async tasks.

### 1.3 Integration Feasibility
All components have well-documented Python/JS APIs:
- FastAPI ↔ LangGraph: native Python integration
- FastAPI ↔ Qdrant: official Python client
- FastAPI ↔ NIM/Groq: OpenAI-compatible API
- React ↔ FastAPI: auto-generated TypeScript from OpenAPI
- OpenCV ORB: pure Python, no GPU dependency

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

**Gap:** None critical. AI-assisted code generation handles boilerplate.

### 2.2 Time Feasibility
15 weeks × 4 people = 60 person-weeks. Detailed task breakdown (see Gantt) shows ~55 person-weeks of work. **5-week buffer** for integration and delays.

### 2.3 Infrastructure Feasibility
| Resource | Requirement | Available |
|----------|:-----------:|:---------:|
| GPU (local) | RTX 3050 (4-6 GB) | ✅ Rohan has |
| Cloud compute | Oracle Free Tier (4 ARM, 24GB) | ✅ Available |
| API quotas | NIM (generous), Groq (14.4K/day) | ✅ Free tier sufficient |
| Storage | ~50 GB for models + data | ✅ Oracle provides |
| Domain/SSL | Free (Caddy auto HTTPS) | ✅ Included |

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

### 3.3 Revenue Potential (Post-Project)
| Model | Conservative | Optimistic |
|:-----:|:------------:|:----------:|
| Free + donation | ₹50K/year | ₹5L/year |
| Freemium (₹499/mo) | ₹20L/year | ₹1Cr/year |
| B2B (clinics) | ₹50L/year | ₹5Cr/year |

**Break-even:** 2-3 paying clinics at ₹1,000/month covers cloud costs.

---

## 4. Legal & Regulatory Feasibility

| Concern | Assessment | Mitigation |
|:--------|:----------:|:----------:|
| Medical device classification | Software as Medical Device (SaMD) risk | Documented as "clinical decision support" not diagnostic |
| HIPAA/HITECH | Not certified | Documented as "HIPAA-pattern aware" in Limitations |
| Data privacy (DPDP Act India) | Applicable | RLS, encryption, consent flags, audit log |
| MedGemma license | Academic free | Use only for thesis; document in paper |
| LLM terms of service | NIM/Groq allow research | Documented; no redistribution of model weights |

---

## 5. Schedule Feasibility

### 5.1 Critical Path
```
Week 1: Docker + Architecture ───┐
Week 2: Auth + Schema            │──► Week 3-4: Versioning + Timeline UI
Week 5: LangGraph + Router       │
Week 6: RAG (Feature A)          │──► Week 7-8: Docs + Image Reg
Week 9: PDF Pipeline             │
Week 10: Calendar                │──► Week 11: Voice
Week 12: Patient Portal          │
Week 13: Feature Evals           │──► Week 14: Integration
Week 15: Paper + Demo            │
```
**Critical dependencies:**
- Week 2 (Auth/Schema) → Week 3 (Versioning)
- Week 5 (LangGraph) → Week 6 (RAG) → Week 13 (Eval)
- Week 10 (Calendar) → Week 11 (Voice) → Week 12 (Portal)

All critical path tasks assigned to strongest team member with buffer.

### 5.2 Float Analysis
- Frontend (Ranveer): 2 weeks float in Phase 1-2
- AI (Nihal): 1 week float in Phase 2-3
- Security (Dev): 1 week float throughout
- Tech Lead (Rohan): Critical path throughout (no float)

---

## 6. Risk Assessment Matrix

| Risk | Probability | Impact | Score | Mitigation |
|:----|:-----------:|:------:|:-----:|------------|
| GPU OOM on RTX 3050 | High | High | 9 | Model swap orchestrator; CPU fallback; quantize Q4 |
| Free LLM rate limits | Medium | Medium | 6 | Aggressive caching; request batching |
| Team member dropout | Medium | High | 6 | Cross-training; AI code gen handles 80% boilerplate |
| Mentor scope change | Low | High | 4 | Weekly tags = immutable milestones |
| Hindi clinical data gap | Medium | Medium | 6 | Synthetic MIMIC-IV + translation; clinician review |
| Integration complexity | High | High | 9 | Interface-first design; contract tests per module |

**Overall Risk Score: Medium-High** — Manageable with fixed scope and weekly checkpoints.

---

## 7. Conclusion

**Technically feasible:** All components tested and validated at prototype level.
**Operationally feasible:** Team has required skills; 15 weeks with buffer.
**Economically feasible:** ₹0 development cost; free-tier deployment.
**Legally feasible:** Documented as academic research tool; compliance patterns implemented.

**Recommendation: PROCEED with 15-week plan as designed.**