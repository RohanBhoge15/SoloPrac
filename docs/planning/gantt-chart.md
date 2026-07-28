# SoloPrac AI — 15-Week Project Schedule & Gantt Chart

## 1. Gantt Chart

### 1.1 Mermaid Source
```mermaid
gantt
    title SoloPrac AI - 15 Week Project Schedule
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d
    tickInterval 1week

    section Phase 1: Planning & Foundation
    Week 1 - Foundation & Planning           :w1, 2026-07-21, 5d
    Week 2 - Bootstrap & Dev Environment     :w2, after w1, 5d
    Week 3 - Patient Versioning Core         :w3, after w2, 5d
    Week 4 - Versioning APIs + Timeline UI   :w4, after w3, 5d

    section Phase 2: Core AI & RAG
    Week 5 - LangGraph Agent + Chat Console  :w5, after w4, 5d
    Week 6 - Temporal Multimodal RAG [A]     :w6, after w5, 5d
    Week 7 - Document Engine + Schema [D]    :w7, after w6, 5d
    Week 8 - Image Registration + ORB        :w8, after w7, 5d

    section Phase 3: Features & Integrations
    Week 9 - Prescription + Invoice + Cert   :w9, after w8, 5d
    Week 10 - Calendar Core + Email Queue    :w10, after w9, 5d
    Week 11 - Voice Scheduling + Smart Rearr :w11, after w10, 5d
    Week 12 - Patient Portal + Notifications :w12, after w11, 5d

    section Phase 4: Research & Polish
    Week 13 - Research Evaluations [B,C,E]   :w13, after w12, 5d
    Week 14 - Integration Testing + Polish   :w14, after w13, 5d
    Week 15 - IEEE Paper + Final Demo        :milestone, w15, after w14, 5d
```

---

## 2. Milestone Status

| Milestone | Week | Deliverable | Status |
|:---------|:----:|:------------|:------:|
| **M1** | 4 | Versioned patient records + timeline UI + auth | **Done** |
| **M2** | 8 | Temporal RAG + Documents + Image Registration | **Done** |
| **M3** | 12 | Full doctor app + Voice + Patient Portal | **Done** |
| **M4** | 15 | Complete system + IEEE Paper + Demo video | **In Progress** |

---

## 3. What Was Built (Weeks 1-14)

| Week | Completed Features |
|:----:|:-------------------|
| **1-2** | Docker Compose, FastAPI skeleton, React scaffold, auth (email+password), RLS, audit log |
| **3-4** | Patient versioning core, hash chain, timeline scrubber, inline edit, diff/revert |
| **5-6** | LangGraph agent, Maverick synth, SSE streaming, MedCPT/BGE-M3/BiomedCLIP embeddings, Qdrant |
| **7-8** | Feature A (Temporal RAG), Document engine (Docling/Surya/Nanonets-OCR2), OCR quality alerts |
| **9-10** | Prescription Box, Invoice, Certificates, state-specific Rx, Calendar core, booking dialog |
| **11-12** | Voice scheduling (5 commands), voice-to-text (PrescriptionBox + ChatUI), Patient portal |
| **13-14** | Doctor search (PostGIS + PIN), profile photos, NMC verification, DPDP consent, Hindi UI, PWA, Sentry, backup, sessions |

---

## 4. What Remains (Week 15)

| Task | Owner | Status |
|------|:-----:|:------:|
| IEEE paper draft | All | In Progress |
| Demo video recording | All | Pending |
| Final integration testing | All | In Progress |
| Oracle Cloud deployment | Dev | Pending |
| Doctor feedback session | Rohan | Pending |
