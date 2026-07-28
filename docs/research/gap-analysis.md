# SoloPrac AI — Gap Analysis

## 1. Research Methodology

Gaps were identified through:
1. **Literature survey findings** — Features absent from 5 major EMR systems
2. **Clinical workflow analysis** — Pain points in a typical solo GP's day
3. **Market research** — Survey of 50+ solo GP clinics in India (online + phone)
4. **Technology landscape** — What free-tier AI can now enable that wasn't possible before

---

## 2. Identified Gaps — Mapped to Research Features

### Gap 1: No Temporal Awareness in Medical Retrieval
| Attribute | Detail |
|-----------|--------|
| **Problem** | When a doctor asks "what was this patient's HbA1c trend?", current EMRs return the latest value. They cannot answer "what did we know on March 14?" or show how information evolved. |
| **Our Solution** | **Feature A — Temporal Multimodal RAG** with immutable version chain |
| **Status** | **Implemented** — MedCPT + BGE-M3 + BiomedCLIP + temporal decay scoring |

### Gap 2: No Dynamic AI Agent for Clinical Workflows
| Attribute | Detail |
|-----------|--------|
| **Problem** | Doctors navigate through rigid menus (12+ clicks to book, 8+ to write a prescription). No system adapts to the query complexity. |
| **Our Solution** | **Feature B — Self-Planning Agent** with LangGraph dynamic plan-execute-critic |
| **Status** | **Implemented** — Plan-execute-critic loop with Langfuse tracing |

### Gap 3: No Cross-Modal Medical Search
| Attribute | Detail |
|-----------|--------|
| **Problem** | Cannot search "find prior wound photos similar to this description" |
| **Our Solution** | **Feature C — Cross-Modal Retrieval** with linear projector (BiomedCLIP → BGE-M3) |
| **Status** | **Implemented** — Linear projector + InfoNCE training |

### Gap 4: No Zero-Shot Document Understanding
| Attribute | Detail |
|-----------|--------|
| **Problem** | A GP receives documents in 10+ formats. Current systems require per-format parsers. |
| **Our Solution** | **Feature D — Zero-Shot Schema Alignment** with Maverick + structured output |
| **Status** | **Implemented** — Requires manual evaluation |

### Gap 5: No Proactive Risk Detection for Solo GPs
| Attribute | Detail |
|-----------|--------|
| **Problem** | Solo GPs see patients episodically. Slow deteriorations are missed until they become acute. |
| **Our Solution** | **Feature E — Trajectory Clustering** with HDBSCAN + Mahalanobis distance |
| **Status** | **Implemented** — Real-time scan via arq cron + WebSocket alerts |

### Gap 6: No Intelligent Information Filtering
| Attribute | Detail |
|-----------|--------|
| **Problem** | Weekly patient summaries are either too long or too short. |
| **Our Solution** | **Feature F — Significance-Aware Weekly Reports** with tiered scoring |
| **Status** | **Implemented** — Requires manual evaluation (doctor Likert ratings) |

---

## 3. Technology Gaps (All Addressed)

| Gap | Our Solution | Status |
|-----|:-------------|:------:|
| Free LLMs for clinical use | Maverick (NIM) + Groq 90B-V + MedGemma-4B | **Done** |
| Multilingual voice for Indian clinics | faster-whisper + IndicWhisper + Indic-Parler-TTS | **Done** |
| Free map for patient search | OpenStreetMap + Leaflet.js + PostGIS | **Done** |
| Multi-tenant RLS for small clinics | Free PostgreSQL RLS with per-request tenant injection | **Done** |
| Cross-clinic patient identity | `User` table + `Patient.user_id` FK | **Done** |
| Doctor verification & trust | Tiered trust model + NMC verification | **Done** |
| DPDP Act compliance | Consent records + data erasure + audit trail | **Done** |
| Hindi UI | react-i18next with translation files | **Done** |
| Doctor profile photos | Upload + oval crop + MinIO storage | **Done** |
| OCR quality assurance | Blur/contrast/brightness/resolution checks | **Done** |
| Booking race conditions | SELECT FOR UPDATE + unique index | **Done** |

---

## 4. Gap Summary — What Makes SoloPrac AI Different

| Dimension | Existing Systems | SoloPrac AI |
|-----------|:----------------|:------------|
| **Data Model** | Mutable (OVERWRITE) | Immutable version chain (GIT-LIKE) |
| **Search** | SQL WHERE + LIKE | Multimodal RAG with temporal decay |
| **AI** | None or basic rules | Self-planning LangGraph agent |
| **Voice** | None | Hindi + English ASR + TTS (scheduling + voice-to-text) |
| **Documents** | Manual entry | AI-powered zero-shot OCR → schema alignment with quality alerts |
| **Risk** | None | Trajectory clustering + anomaly detection |
| **Billing** | Separate module | Integrated with agent + AI for auto-generation |
| **Deployment** | $200-5000/month | Free-tier Oracle Cloud |
| **Language** | English only | English + Hindi (UI + voice) |
| **Auth** | Varies | Email+password + HttpOnly cookies (XSS-safe) |
| **Compliance** | Minimal | DPDP consent + data erasure + NMC verification |
| **Offline** | Rare | PWA with Workbox caching |
