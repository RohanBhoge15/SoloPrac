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
| **Root Cause** | Standard RDBMS updates data in place. Historical state is lost. |
| **Severity** | High — affects clinical decision quality and medico-legal audits |
| **Our Solution** | **Feature A — Temporal Multimodal RAG** with immutable version chain |
| **Novelty** | First application of temporal decay scoring to clinical RAG |

### Gap 2: No Dynamic AI Agent for Clinical Workflows
| Attribute | Detail |
|-----------|--------|
| **Problem** | Doctors navigate through rigid menus (12+ clicks to book, 8+ to write a prescription). No system adapts to the query complexity. |
| **Root Cause** | All EMRs use fixed form-based interfaces. No agentic orchestration. |
| **Severity** | Medium — causes significant time waste per patient |
| **Our Solution** | **Feature B — Self-Planning Agent** with LangGraph dynamic plan-execute-critic |
| **Novelty** | First self-planning medical agent with dynamic step generation |

### Gap 3: No Cross-Modal Medical Search
| Attribute | Detail |
|-----------|--------|
| **Problem** | Cannot search "find prior wound photos similar to this description" or "show me all patients with x-ray findings matching this report" |
| **Root Cause** | Text and images stored separately. No alignment between embedding spaces. |
| **Severity** | Medium — limits diagnostic pattern matching |
| **Our Solution** | **Feature C — Cross-Modal Retrieval** with linear projector (NV-CLIP → BGE-M3) |
| **Novelty** | First medical cross-modal projector trained on CheXpert + wound pairs |

### Gap 4: No Zero-Shot Document Understanding
| Attribute | Detail |
|-----------|--------|
| **Problem** | A GP receives documents in 10+ formats (typed, handwritten, scanned, lab printouts, referral letters, discharge summaries). Current systems require per-format parsers. |
| **Root Cause** | Rule-based document processing doesn't scale |
| **Severity** | High — digitizing old records is a major barrier to EMR adoption |
| **Our Solution** | **Feature D — Zero-Shot Schema Alignment** with Maverick + structured output |
| **Novelty** | First zero-shot document-to-EMR alignment with critic loop fallback |

### Gap 5: No Proactive Risk Detection for Solo GPs
| Attribute | Detail |
|-----------|--------|
| **Problem** | Solo GPs see patients episodically (every 1-6 months). Slow deteriorations (rising HbA1c, creeping BP) are missed until they become acute. |
| **Root Cause** | No longitudinal trajectory analysis in solo GP tools |
| **Severity** | Medium — late intervention leads to worse outcomes |
| **Our Solution** | **Feature E — Trajectory Clustering** with HDBSCAN + Mahalanobis distance |
| **Novelty** | First application of clinical embedding trajectory clustering for solo GP alerts |

### Gap 6: No Intelligent Information Filtering
| Attribute | Detail |
|-----------|--------|
| **Problem** | Weekly patient summaries are either too long (every BP reading listed) or too short (miss significant changes). |
| **Root Cause** | No clinical significance scoring |
| **Severity** | Low-Medium — information overload |
| **Our Solution** | **Feature F — Significance-Aware Weekly Reports** with tiered scoring |
| **Novelty** | First clinical significance tier applied to automated report generation |

---

## 3. Technology Gaps

| Gap | Current State | Our Solution |
|-----|:-------------|:-------------|
| **Free LLMs for clinical use** | No integrated solution; most systems use no LLMs | Maverick (NIM) + Groq 90B-V + MedGemma-4B |
| **Multilingual voice for Indian clinics** | Practo has partial English; no Hindi ASR/TTS | faster-whisper + IndicWhisper + Indic-Parler-TTS |
| **Free map for patient search** | Google Maps API ($200+/month) | OpenStreetMap + Leaflet.js (zero cost) |
| **Open-source medical RAG stack** | None combines Qdrant + MedCPT + BGE-M3 + NV-CLIP | First integrated pipeline with temporal scoring |
| **Multi-tenant RLS for small clinics** | Enterprise-only in most EMRs | Free PostgreSQL RLS with per-request tenant injection |

---

## 4. Gap Summary — What Makes SoloPrac AI Different

| Dimension | Existing Systems | SoloPrac AI |
|-----------|:----------------|:------------|
| **Data Model** | Mutable (OVERWRITE) | Immutable version chain (GIT-LIKE) |
| **Search** | SQL WHERE + LIKE | Multimodal RAG with temporal decay |
| **AI** | None or basic rules | Self-planning LangGraph agent |
| **Voice** | None | Hindi + English ASR + TTS (scheduling) |
| **Documents** | Manual entry | AI-powered zero-shot OCR → schema alignment |
| **Risk** | None | Trajectory clustering + anomaly detection |
| **Billing** | Separate module | Integrated with agent + AI for auto-generation |
| **Deployment** | $200-5000/month | Free-tier Oracle Cloud |
| **Language** | English only | English + Hindi |
