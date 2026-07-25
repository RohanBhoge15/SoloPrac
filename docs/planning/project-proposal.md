# SoloPrac AI — Project Proposal

## 1. Project Title

**SoloPrac AI: A Multimodal Agentic Clinical Operating System with Version-Controlled Patient Intelligence**

---

## 2. Problem Statement

Solo medical practitioners (GPs, specialists, small clinics) in India face a fundamental contradiction: they need sophisticated clinical intelligence to provide quality care, but existing Electronic Medical Record (EMR) systems are either:

- **Too expensive** (₹2,000-5,000/month per clinic for Practo, KareXpert, etc.)
- **Too complex** (OpenEMR requires server administration, has dated UI)
- **Too limited** (no AI, no voice, no versioning, no temporal awareness)
- **Not localized** (no Hindi support, no Indian drug database, no Indian map integration)

As a result, **85% of solo GPs still use paper records or Excel**, leading to:
- 12+ minutes of administrative overhead per patient
- Inability to search own patient data effectively
- Medico-legal vulnerability from incomplete audit trails
- Missed follow-ups and deteriorating patient trajectories
- No way to digitize decades of paper records

---

## 3. Objectives

### Primary Objective
Build a **free-tier, AI-powered clinical operating system** for solo practitioners that provides:
- **Version-controlled patient records** (immutable, time-travelable, audit-ready)
- **Temporal-aware multimodal RAG** (grounded clinical Q&A with citations)
- **Self-planning AI agent** (dynamic tool selection for clinical workflows)
- **Voice scheduling in Hindi + English** (5 locked voice commands)
- **Document digitization from photos** (OCR pipeline with zero-shot schema alignment)
- **Patient self-booking with map** (OpenStreetMap, zero cost)

### Research Objectives (IEEE Paper Contributions)
1. **Feature A:** Temporal Multimodal RAG — formalize time-aware clinical retrieval
2. **Feature B:** Self-Planning Agent — dynamic plan-execute-critic for medical workflows
3. **Feature C:** Cross-Modal Retrieval — BiomedCLIP to BGE-M3 projector for image↔text search
4. **Feature D:** Zero-Shot Schema Alignment — LLM-based document-to-EMR mapping
5. **Feature E:** Trajectory Clustering — HDBSCAN + Mahalanobis for risk alerts
6. **Feature F:** Significance-Aware Reports — clinical tier filtering for weekly digests

### Secondary Objectives
- Demonstrate full deployment on **Oracle Cloud Free Tier** (zero hosting cost)
- Provide **complete open-source stack** for academic replication
- Publish **5-6 page IEEE conference paper** with evaluation metrics

---

## 4. Scope

### In Scope
| Module | Description |
|--------|-------------|
| Patient Versioning Core | Immutable chain, diff, revert, timeline |
| LangGraph Agent | Router + 9 tools + voice subgraph |
| Temporal Multimodal RAG | 3 vector types + temporal decay + evaluation |
| Document Engine | 4 parsers + schema alignment |
| Image Registration | ORB matching + overlay + clinical summary |
| Calendar + Voice | 9 tools + ASR/TTS + 5 voice commands |
| Patient Portal | Search, book, reports, notifications |
| **User/Patient Separation** | Cross-clinic identity via `users` table + `patient.user_id` FK (NEW) |
| **Doctor Verification** | Tiered trust: unverified → pending_verification → verified → rejected (NEW) |
| **Email/Password Auth** | bcrypt registration + login alongside Google OAuth (NEW) |
| **India DPDP Act** | Consent management, data erasure API, audit trail export (planned) |
| Billing + Certificates | AI-generated PDFs via shared pipeline |
| Security & Observability | RLS, audit, Langfuse, rate limiting |

### Out of Scope
- DICOM/OHIF viewer (radiologist domain, not solo GP)
- Payment gateway integration (demo uses "Mark as Paid")
- SMS notifications (requires paid gateway; email + in-app covered)
- Real-time trajectory WebSocket (Feature E simulated for paper)
- Multi-clinic enterprise features
- NMC API direct integration (admin review used as fallback)

---

## 5. Deliverables

### Software Deliverables
1. **Complete source code** (GitHub repo with per-week tags)
2. **Docker Compose deployment** (8 services, one-command startup)
3. **Oracle Cloud deployment guide** (free tier)
4. **Demo video** (5-minute walkthrough)
5. **User documentation** (setup, usage, API reference)

### Research Deliverables
1. **IEEE paper** (5-6 pages, 2-column, IEEEtran format)
2. **Evaluation metrics** (Recall@5, latency p95, future-leak rate, Likert ratings)
3. **Reproducibility package** (synthetic MIMIC-IV dataset + evaluation scripts)

### Documentation Deliverables
1. Architecture decision records
3. Database schema with RLS policies
4. API specification (OpenAPI)
5. Security audit report

---

## 6. Methodology

### Development Approach
- **15-week incremental delivery** — each week produces demonstrable feature set
- **Research-first** — evaluation harness built before feature implementation
- **Doctor-in-the-loop** — all AI mutations require approval; feedback from practicing GP at weeks 4, 8, 12
- **Observability-driven** — Langfuse traces every LLM call and agent step

### Evaluation Strategy
| Feature | Primary Metric | Dataset |
|---------|---------------|---------|
| A — Temporal RAG | Recall@5 (time-correct) + future-leak rate | Synthetic MIMIC-IV longitudinal |
| B — Self-Planning | Steps-to-resolution vs fixed pipeline | 100 clinical queries held-out |
| C — Cross-Modal | Recall@k on CheXpert + wound pairs | CheXpert + curated wound dataset |
| D — Schema Alignment | Field-level F1 (5 doc types × 50) | Real documents + clinician review |
| E — Trajectory Clustering | Precision on injected deteriorations | Synthetic trajectories |
| F — Weekly Reports | Doctor Likert (1-5) vs unfiltered baseline | 30-day simulated study |

---

## 7. Team & Responsibilities

| Member | Role | Primary Focus |
|--------|------|---------------|
| Rohan Bhoge | Tech Lead, Backend | Versioning, RAG, LangGraph, Architecture |
| Ranveer Singh Thakur | Frontend Lead | React UI, Timeline, Chat, Patient Portal |
| Nihal Korgaonkar | AI/ML Engineer | Embeddings, Vision, Voice, Feature Evaluations |
| Dev Patel | Security & DevOps | Auth, RLS, Audit, Deployment, Planning |

---

## 8. Timeline Overview

| Phase | Weeks | Focus |
|-------|:-----:|-------|
| **Phase 1: Foundation** | 1-4 | Architecture, Docker, Auth, Versioning, Timeline UI, Embeddings |
| **Phase 2: Core AI** | 5-8 | Agent, Chat, RAG (Feature A), Documents, Image Registration |
| **Phase 3: Features** | 9-12 | Prescriptions, Billing, Certificates, Calendar, Voice, Patient Portal |
| **Phase 4: Research** | 13-15 | Feature Evaluations, Integration, Paper, Demo, Deploy |

---

## 8. Expected Impact

| Dimension | Target |
|-----------|--------|
| **Time saved per patient** | >10 minutes (17.4 min → ~7 min overhead) |
| **Doctors served (free tier)** | Unlimited — zero marginal cost |
| **Paper records digitized** | Any photo → structured EMR entry |
| **Research contribution** | 6 novel features for IEEE publication |
| **Deployment cost** | ₹0 / month (Oracle Cloud Free Tier) |
| **Language support** | English + Hindi (voice + UI) |

---

## 9. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| GPU memory (RTX 3050) | High | High | Model swapping orchestrator; CPU embeddings |
| Free LLM rate limits | Medium | Medium | Caching; local fallback; graceful degradation |
| Team bandwidth (4 students) | High | High | Clear task ownership; AI-assisted code gen; scope fixed |
| Hindi clinical data scarcity | Medium | Medium | Synthetic generation from MIMIC-IV + translation |
| Mentor scope changes | Low | High | Weekly tags allow rollback; fixed deliverables |

---

## 10. Ethics & Compliance

- **AI Disclaimer** on every generated surface: "AI Suggestion — Requires Doctor Validation"
- **No autonomous outbound** messages without doctor approval
- **Patient consent** required before external sharing
- **Right to be forgotten** implemented as tombstone version
- **HIPAA-pattern aware** (not certified — documented in Limitations)
- **MedGemma license** — academic use only (free for thesis)