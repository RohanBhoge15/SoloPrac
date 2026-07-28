# SoloPrac AI — Project Proposal

## 1. Project Title

**SoloPrac AI: A Multimodal Agentic Clinical Operating System with Version-Controlled Patient Intelligence**

---

## 2. Problem Statement

Solo medical practitioners (GPs, specialists, small clinics) in India face a fundamental contradiction: they need sophisticated clinical intelligence to provide quality care, but existing Electronic Medical Record (EMR) systems are either:

- **Too expensive** (₹2,000-5,000/month per clinic for Practo, KareXpert, etc.)
- **Too complex** (OpenEMR requires server administration, has dated UI)
- **Too limited** (no AI, no voice, no versioning, no temporal awareness)
- **Not localized** (no Hindi support, no Indian map integration)

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
| Module | Description | Status |
|--------|-------------|:------:|
| Patient Versioning Core | Immutable chain, diff, revert, timeline | **Done** |
| LangGraph Agent | Router + 9 tools + voice subgraph | **Done** |
| Temporal Multimodal RAG | 3 vector types + temporal decay + evaluation | **Done** |
| Document Engine | 4 parsers + quality alerts + schema alignment | **Done** |
| Image Registration | ORB matching + overlay + clinical summary | **Done** |
| Calendar + Voice | 9 tools + ASR/TTS + 5 voice commands + booking dialog | **Done** |
| Patient Portal | Search, book, reports, notifications, consent, data erasure | **Done** |
| Cross-Clinic Identity | User table + patient.user_id FK | **Done** |
| Doctor Verification | Tiered trust + NMC verification | **Done** |
| Email/Password Auth | bcrypt + HttpOnly cookies | **Done** |
| DPDP Compliance | Consent records, data erasure, audit trail | **Done** |
| State-Specific Prescriptions | 24 Indian states' regulatory text | **Done** |
| Hindi UI | react-i18next + translation files | **Done** |
| Profile Photos | Upload + oval crop + MinIO storage | **Done** |
| Voice-to-Text | Mic buttons on PrescriptionBox + ChatUI | **Done** |
| OCR Quality Alerts | Blur, contrast, brightness, resolution checks | **Done** |
| Patient PDF Downloads | Prescriptions, invoices, certificates from portal | **Done** |
| Document Timeline | Unified chronological view with version citations | **Done** |
| Offline PWA | Service worker + Workbox caching | **Done** |
| Sentry Error Tracking | Backend + frontend (opt-in) | **Done** |
| Backup System | pg_dump to MinIO | **Done** |
| Multi-Device Sessions | Track + revoke sessions | **Done** |
| Billing + Certificates | AI-generated PDFs via shared pipeline | **Done** |
| Security & Observability | RLS, audit, Langfuse, rate limiting | **Done** |

### Out of Scope
| Feature | Decision | Justification |
|---------|:--------:|---------------|
| DICOM/OHIF viewer | Deferred | Solo GPs don't use DICOM |
| Indian drug database | Skipped | LLM handles misspelled medicine names natively |
| Research section in app | Skipped | Compared with RAG-Based CDSS; not needed for solo doctors |
| Lab reference ranges | Removed | Hardcoded ranges are useless |
| Payment gateway | Deferred | "Mark as paid" suffices for demo |
| SMS notifications | Deferred | Email + in-app covers it |
| Google OAuth | Removed | Email+password is simpler; no third-party dependency |

---

## 5. Deliverables

### Software Deliverables
1. **Complete source code** (GitHub repo)
2. **Docker Compose deployment** (8 services, one-command startup)
3. **Oracle Cloud deployment guide** (free tier)
4. **Demo video** (5-minute walkthrough)
5. **User documentation** (setup, usage, API reference)

### Research Deliverables
1. **IEEE paper** (5-6 pages, 2-column, IEEEtran format)
2. **Evaluation metrics** (Recall@5, latency p95, future-leak rate, Likert ratings)
3. **Reproducibility package** (synthetic dataset + evaluation scripts)

### Documentation Deliverables
1. Architecture decision records
2. Database schema with RLS policies
3. API specification (OpenAPI)
4. Security audit report

---

## 6. Team & Responsibilities

| Member | Role | Primary Focus |
|--------|------|---------------|
| Rohan Bhoge | Tech Lead, Backend | Versioning, RAG, LangGraph, Architecture, Auth, Calendar, Patient Portal |
| Ranveer Singh Thakur | Frontend Lead | React UI, Timeline, Chat, Patient Portal, Profile Photos, ImageCropModal |
| Nihal Korgaonkar | AI/ML Engineer | Embeddings, Vision, Voice, Feature Evaluations, Langfuse |
| Dev Patel | Security & DevOps | Auth, RLS, Audit, Deployment, Planning, Alembic, MinIO |

---

## 7. Expected Impact

| Dimension | Target |
|-----------|--------|
| **Time saved per patient** | >10 minutes (17.4 min → ~7 min overhead) |
| **Doctors served (free tier)** | Unlimited — zero marginal cost |
| **Paper records digitized** | Any photo → structured EMR entry |
| **Research contribution** | 6 novel features for IEEE publication |
| **Deployment cost** | ₹0 / month (Oracle Cloud Free Tier) |
| **Language support** | English + Hindi (voice + UI) |
