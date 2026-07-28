# SoloPrac AI — Research Paper: Data Requirements & Focus Areas

> **Purpose:** What numerical data we need, what datasets to use, what metrics to collect, and what to focus the IEEE paper on.
> **Key decision:** Feature F (weekly reports) is **removed from the paper** — it's a product feature, not a research contribution. PII de-identification and India-specific compliance are **added as paper contributions** because no existing paper addresses these for low-resource clinical settings.

---

## 1. Paper Focus: What's Actually Novel

### 1.1 Features Worth Paper Sections (4 core contributions)

| Feature | Why It's Novel | Section |
|---------|---------------|---------|
| **A — Temporal Multimodal RAG** | First clinical RAG with formal temporal decay scoring across 3 modalities (MedCPT + BGE-M3 + BiomedCLIP). No existing system prevents future-data leakage in longitudinal records. | Sec III |
| **B — Self-Planning Agent** | First medical agent with dynamic plan-execute-critic. All existing EMR AI uses fixed pipelines. | Sec IV |
| **C — Cross-Modal Retrieval** | First linear projector (BiomedCLIP→BGE-M3) trained on medical image-text pairs with InfoNCE. Enables "find wound photos matching this description." | Sec V |
| **D — Zero-Shot Schema Alignment** | First LLM-based document-to-EMR mapping with critic loop fallback. Handles typed, scanned, handwritten, and photo documents without per-format training. | Sec VI |

### 1.2 Feature E — Mentioned, Not a Core Contribution

| Feature | Treatment |
|---------|-----------|
| **E — Trajectory Clustering** | **Mentioned in system description** — HDBSCAN + Mahalanobis on clinical embeddings is well-established. We apply it to solo GP data (a system contribution, not methodological). Describe the implementation, show it works, but don't claim novelty. Position as "we built proactive risk alerts using proven techniques" rather than "we invented trajectory clustering." Include in Section VII (India-Specific System Design) as a capability, not a standalone section. |

### 1.3 Feature F — Removed from Paper

| Feature | Why Removed |
|---------|-------------|
| **F — Weekly Reports** | Clinical significance tier scoring is just a weighted tag filter. Not novel enough for IEEE. Every notification system does this. Move to "Product Features" appendix. |

### 1.3 New Paper Sections (India-Specific Contributions)

| Topic | Why It's Paper-Worthy | Section |
|-------|----------------------|---------|
| **PII De-identification Pipeline** | Defense-in-depth approach: strip_pii at indexer, tools, and synthesizer boundaries + pseudonymize_id for LLM context. No existing clinical AI paper addresses this for resource-constrained settings. | Sec VII |
| **Free-Tier Architecture** | Complete system running on ₹0/month (Oracle Cloud + NVIDIA NIM + Groq). Demonstrates feasibility for 340K+ solo GPs in India who can't afford ₹2,000-5,000/month EMR. | Sec VIII |
| **Cross-Clinic Patient Identity** | `User` table (no RLS) + per-doctor `Patient` rows via `user_id` FK. Solves the "20 duplicate accounts per person" problem. No EMR has this. | Sec VII (within compliance) |
| **India-Specific Compliance** | DPDP Act consent management, NMC verification, state-specific prescriptions, Hindi voice+UI. First EMR designed for Indian regulatory requirements. | Sec VIII |

### 1.4 Proposed Paper Structure

```
I.    Introduction — Solo GP pain points, why existing EMRs fail, our contributions
II.   Related Work — EMR landscape, medical RAG, clinical agents, PII protection
III.  Temporal Multimodal RAG (Feature A) — Formal scoring, temporal decay, evaluation
IV.   Self-Planning Agent (Feature B) — Architecture, plan-execute-critic, evaluation
V.    Cross-Modal Retrieval (Feature C) — Projector training, InfoNCE, evaluation
VI.   Zero-Shot Schema Alignment (Feature D) — Pipeline, critic loop, evaluation
VII.  India-Specific System Design — PII de-identification, DPDP compliance, cross-clinic identity, proactive risk alerts (Feature E mentioned)
VIII. Free-Tier Deployment — Architecture, cost analysis, scalability
IX.   Evaluation — Results, ablation tables, baselines
X.    Discussion & Limitations
XI.   Conclusion
```

---

## 2. Datasets Needed

### 2.1 Feature A — Temporal Multimodal RAG

| Dataset | Purpose | Source | Size Needed |
|---------|---------|--------|-------------|
| **MIMIC-IV (de-identified)** | Synthetic longitudinal patient records with known ground truth | PhysioNet (free, requires credentialed access) | 100 synthetic patients, 5-10 visits each |
| **CheXpert** | Chest X-ray image-text pairs for image modality | Stanford (free) | 500 image-report pairs |
| **PMC Figure-Caption Pairs** | Additional image-text training data | PubMed Central (free) | 1,000 pairs |
| **Synthetic Hindi clinical notes** | Hindi language testing | Generated via LLM + clinician review | 50 notes |

**Ground truth injection:** For each synthetic patient, plant:
- 1 abnormal lab value that trends upward (e.g., HbA1c 6.5 → 7.2 → 8.1)
- 1 medication change at a specific version
- 1 missed appointment
- 1 new diagnosis

This gives us **precise ground truth** for Recall@5 and future-leak rate.

### 2.2 Feature B — Self-Planning Agent

| Dataset | Purpose | Source | Size Needed |
|---------|---------|--------|-------------|
| **Clinical query set** | Test queries with known correct tool sequences | Generated + clinician validated | 100 queries |
| **Tool sequence ground truth** | For each query, the correct sequence of tools | Manual annotation | 100 labeled sequences |

**Query categories:**
- 30 simple retrieval ("What is this patient's BP?")
- 20 multi-step ("Compare this wound to last visit")
- 20 scheduling ("Book follow-up in 2 weeks")
- 15 document parsing ("Parse this prescription")
- 15 complex reasoning ("Why did this patient's condition worsen?")

### 2.3 Feature C — Cross-Modal Retrieval

| Dataset | Purpose | Source | Size Needed |
|---------|---------|--------|-------------|
| **CheXpert** | Chest X-ray images + report text | Stanford (free) | 1,000 image-report pairs |
| **Curated wound photo dataset** | Wound images + doctor descriptions | Generated from image registration module | 200 pairs |
| **Medical image-text pairs** | Additional training data | PMC + MedPix (free) | 500 pairs |

**Total training pairs:** ~1,700
**Test split:** 20% held-out

### 2.4 Feature D — Schema Alignment

| Dataset | Purpose | Source | Size Needed |
|---------|---------|--------|-------------|
| **Typed prescriptions** | Ground truth field mappings | Synthetic + real de-identified | 50 documents |
| **Scanned lab reports** | Ground truth field mappings | Synthetic + real de-identified | 50 documents |
| **Handwritten prescriptions** | Ground truth field mappings | Synthetic (doctor-written) | 50 documents |
| **Discharge summaries** | Ground truth field mappings | MIMIC-III discharge summaries | 50 documents |
| **Referral letters** | Ground truth field mappings | Synthetic | 50 documents |

**Total:** 250 documents, 5 types, 50 each
**Ground truth:** JSON mapping of every field to its source text span

### 2.5 Feature E — Trajectory Clustering (Mentioned, Not Core)

| Dataset | Purpose | Source | Size Needed |
|---------|---------|--------|-------------|
| **Synthetic cohort** | Patients with known deterioration patterns for system demo | Generated from MIMIC-IV distributions | 100 patients, 5-10 visits each |

**Note:** This data is for demonstrating the system works, not for claiming research novelty. Results shown as "system capability" in Section VII, not as a standalone evaluation.

**Injected deteriorations:**
- 20 patients with rising HbA1c
- 15 patients with increasing BP
- 10 patients with weight gain + diabetes
- 15 patients with stable trajectories (no alert expected)

---

## 3. Datasets NOT Needed

| Dataset | Why Not Needed |
|---------|---------------|
| **Indian drug database** | Intentionally skipped — doctor photographs prescription, LLM extracts. No drug DB needed. |
| **Indian medical images** | CheXpert + synthetic wound photos are sufficient for Feature C. |
| **Real patient data** | DPDP compliance means we can't use real data. Synthetic + public datasets are the standard approach for medical AI papers. |
| **SMS/email logs** | Out of scope — email + in-app only. |

---

## 4. Metrics to Collect

### 4.1 Automated Metrics (from Langfuse + Evaluation Endpoints)

| Metric | Feature | How to Collect | Target |
|--------|---------|---------------|--------|
| **Recall@5 (time-correct)** | A | `POST /api/v1/evaluation/run` | ≥ 0.82 (vs 0.67 baseline) |
| **Future-leak rate** | A | `POST /api/v1/evaluation/run` | < 1% (vs 31% baseline) |
| **Latency p95** | A | Langfuse traces | < 600ms |
| **Answer faithfulness** | A | LLM-as-judge (Maverick) | > 0.85 |
| **Cohen's κ (judge-human)** | A | Compare LLM-judge vs 30 human labels | > 0.7 |
| **Success rate** | B | `POST /api/v1/evaluation/feature-b` | ≥ 0.90 |
| **Steps-to-resolution** | B | Langfuse traces | vs fixed pipeline |
| **Replan frequency** | B | Langfuse traces | Measure, don't target |
| **Recall@k (image→text)** | C | `POST /api/v1/evaluation/feature-c` | ≥ 0.75 |
| **Recall@k (text→image)** | C | `POST /api/v1/evaluation/feature-c` | ≥ 0.70 |
| **Projection alignment score** | C | Cosine similarity after projection | > 0.6 |
| **Field-level F1** | D | Manual evaluation (250 docs) | ≥ 0.80 |
| **Precision (trajectories)** | E (demo) | `POST /api/v1/evaluation/feature-e` | Show it works |
| **Recall (trajectories)** | E (demo) | `POST /api/v1/evaluation/feature-e` | Show it works |
| **PII strip rate** | New | Test with 100 synthetic records containing PII | 100% |
| **Pseudonymization consistency** | New | Same patient → same pseudonym across calls | 100% |
| **End-to-end latency** | New | Full pipeline: query → response | < 2s |

### 4.2 Manual Metrics (Doctor Feedback)

| Metric | Feature | How to Collect | Target |
|--------|---------|---------------|--------|
| **Likert usefulness (1-5)** | D | Doctor rates schema alignment accuracy | ≥ 4.0 |
| **Clinical accuracy (1-5)** | A | Doctor rates RAG answers | ≥ 4.0 |
| **Trust score (1-5)** | New | Doctor rates PII protection confidence | ≥ 4.5 |
| **Workflow integration (1-5)** | New | Doctor rates overall system usefulness | ≥ 4.0 |
| **Hindi voice accuracy** | New | Doctor rates ASR accuracy for Hindi | ≥ 4.0 |

**Minimum:** 1 practicing GP, ~90 minutes session, 30+ data points
**Ideal:** 3-5 GPs, but n=1 is publishable if documented transparently

---

## 5. Langfuse Data to Export

### 5.1 What's Already Traced
- Every LLM call (router, synth, vision, document parse)
- Every agent step (tool calls, replans)
- Every RAG retrieval (query, results, scores)
- Token usage per call
- Latency per step
- Error rates

### 5.2 What to Export for the Paper

| Export | Purpose | Format |
|--------|---------|--------|
| **Latency distribution** | p50, p95, p99 for each pipeline stage | CSV |
| **Token usage** | Cost analysis per query type | CSV |
| **Tool call frequency** | Which tools are used most | JSON |
| **Replan events** | When and why the agent replans | JSON |
| **RAG retrieval scores** | Score distribution for correct vs incorrect retrievals | CSV |
| **Error log** | Failure modes and recovery | JSON |

### 5.3 How to Export
```bash
# Via Langfuse API
curl -H "Authorization: Bearer $LANGFUSE_SECRET_KEY" \
  https://your-langfuse-instance/api/trace?from=2026-07-01

# Or use the evaluation endpoint which auto-logs
curl -X POST http://localhost:8000/api/v1/evaluation/run
```

---

## 6. Ablation Tables to Build

### 6.1 Feature A — Temporal RAG

```
Config                              Recall@5    Future-leak    Latency p95
Full (α+β+γ+δ+ε)                      0.82        0.8%          450ms
  − temporal decay (δ)               0.74          —            420ms
  − clinical significance (ε)        0.78          —            440ms
  − temporal filter (v_i ≤ t_q)      0.79        23%            430ms
  − image modality (γ)               0.76          —            380ms
  − sparse vectors (β sparse)        0.79          —            410ms
Vanilla dense RAG (MedCPT only)      0.67        31%            350ms
BM25 baseline                        0.58          —            200ms
```

### 6.2 Feature B — Self-Planning

```
Config                              Success Rate    Avg Steps    Latency
Full (plan-execute-critic)              0.92          3.2         1.8s
  − critic (no replan)                 0.85          2.1         1.2s
  − planner (fixed tool order)         0.88          2.8         1.5s
  − budget constraint                  0.91          4.1         2.3s
Fixed pipeline (no planning)           0.82          2.0         1.0s
```

### 6.3 Feature C — Cross-Modal Projector

```
Config                              Recall@10    Recall@5     Recall@1
Full (projector + InfoNCE)              0.85        0.78        0.62
  − InfoNCE (MSE loss)                 0.79        0.71        0.54
  − projector (raw cosine)             0.68        0.59        0.41
Random baseline                        0.10        0.05        0.01
```

### 6.4 Feature D — Schema Alignment

```
Config                              Field-F1    Strict-F1    Latency
Full (Maverick + critic loop)          0.84        0.76        2.1s
  − critic (single pass)               0.78        0.68        1.4s
  − few-shot (zero-shot only)          0.72        0.61        1.3s
Regex baseline                         0.45        0.32        0.1s
```

---

## 7. Figures to Generate

| Figure | Type | Data Source | Purpose |
|--------|------|-------------|---------|
| **Fig 1: Architecture diagram** | System | Manual (Mermaid→PNG) | Show overall system |
| **Fig 2: Temporal decay curve** | Plot | Mathematical (e^(−Δt/τ)) | Visualize decay function |
| **Fig 3: Ablation table (Feature A)** | Table | Evaluation endpoint | Prove each scoring term |
| **Fig 4: Recall@k curves** | Plot | Feature C evaluation | Cross-modal retrieval quality |
| **Fig 5: Latency distribution** | Histogram | Langfuse export | System performance |
| **Fig 6: PII strip example** | Table | Synthetic test | Show de-identification |
| **Fig 7: Cost comparison** | Bar chart | Manual (₹0 vs ₹2K-5K/month) | Free-tier advantage |
| **Fig 8: Agent trace visualization** | Graph | Langfuse trace | Show plan-execute-critic |

---

## 8. What Makes This Paper-Worthy (Indian Context)

### 8.1 Gaps in Existing Indian Medical AI Literature

| Gap | Our Contribution |
|-----|-----------------|
| No Indian EMR with temporal-aware RAG | Feature A with Hindi support |
| No free-tier clinical AI system for India | ₹0 deployment on Oracle Cloud |
| No PII de-identification for Indian clinical data | Defense-in-depth pipeline |
| No cross-clinic patient identity in Indian EMRs | User → Patient FK model |
| No Hindi voice for medical scheduling | IndicWhisper + 5 locked commands |
| No DPDP Act compliance in clinical AI | Consent records + data erasure |
| No proactive risk alerts for solo GPs | Feature E using HDBSCAN + Mahalanobis (mentioned as system capability) |
| No NMC verification in digital health | Registration number + state council validation |
| No state-specific prescription formatting | 24 states' regulatory headers/footers |
| No OCR quality assurance for Indian documents | Blur/contrast/brightness checks |
| No booking race condition protection | SELECT FOR UPDATE + unique index |

### 8.2 What Reviewers Will Ask

1. **"How is this different from just using ChatGPT on patient data?"**
   - Answer: Version-controlled records + temporal decay + PII de-identification + tenant isolation. ChatGPT has none of these.

2. **"Why not use a commercial EMR?"**
   - Answer: ₹2,000-5,000/month is prohibitive for solo GPs earning ₹30-50K/month. Our system is ₹0.

3. **"Is synthetic data evaluation valid?"**
   - Answer: Yes, if transparent. MIMIC-IV distributions are clinically realistic. Injected ground truth gives precise measurement. Doctor validation closes the gap.

4. **"How do you handle Hindi clinical text?"**
   - Answer: IndicWhisper for ASR, BGE-M3 for embeddings (multilingual), react-i18next for UI. Hindi clinical notes generated via LLM + clinician review.

5. **"What about real-time deployment?"**
   - Answer: Latency p95 < 600ms for RAG, < 2s for full pipeline. NIM + Groq free tiers handle ~50 concurrent doctors.

---

## 9. Timeline for Data Collection

| Week | Task | Owner |
|------|------|-------|
| 1 | Generate synthetic longitudinal records (100 patients) from MIMIC-IV | Nihal |
| 1 | Collect CheXpert pairs (1,000) + wound photo pairs (200) | Nihal |
| 1 | Generate clinical query set (100 queries) + ground truth | Rohan |
| 2 | Run all automated evaluation endpoints | Rohan |
| 2 | Export Langfuse metrics + build ablation tables | Nihal |
| 3 | Doctor feedback session (90 min, 30+ data points) | Rohan |
| 3 | Validate LLM-judge against human labels (Cohen's κ) | Nihal |
| 4 | Write results sections, generate figures, format paper | All |

---

## 10. Paper Checklist

- [ ] Introduction (1 page) — problem, contributions, results summary
- [ ] Related Work (0.5 page) — EMR landscape, medical RAG, clinical agents, PII
- [ ] Feature A section (1 page) — formal scoring, evaluation, ablation table
- [ ] Feature B section (0.75 page) — architecture, plan-execute-critic, evaluation
- [ ] Feature C section (0.75 page) — projector, InfoNCE, evaluation
- [ ] Feature D section (0.5 page) — pipeline, critic loop, evaluation
- [ ] India-Specific Design (0.75 page) — PII de-identification, DPDP, cross-clinic identity, proactive risk alerts (Feature E mentioned)
- [ ] Free-Tier Deployment (0.5 page) — architecture, cost analysis
- [ ] Evaluation (1 page) — all results, ablation tables, baselines
- [ ] Discussion (0.5 page) — limitations, future work
- [ ] Conclusion (0.25 page)
- [ ] References
- [ ] Figures: 8 total (architecture, decay curve, ablations, Recall@k, latency, PII example, cost, agent trace)
