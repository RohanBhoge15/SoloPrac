# Research Features — Evaluation Methodology (A–F)

> How to produce **real, publishable evaluation numbers** for the IEEE paper without real patient data.
> Core principle: you can't use production clinical data (privacy/DPDP), so "real numbers" means
> **methodologically rigorous numbers on defensible datasets** — not hand-waving. Reviewers accept
> synthetic/public data *if you are transparent*; they reject unstated assumptions.

**Current Status:** All 6 features are implemented. Features A, B, C, E have automated evaluation endpoints. Features D and F require manual doctor evaluation.

---

## 0. The Data Foundation

You need a **labeled test set per feature**. Three legitimate sources:

1. **Public de-identified datasets** — MIMIC-IV, CheXpert, PMC figure-caption pairs.
2. **LLM-generated synthetic longitudinal records** — acceptable *if transparent* and validated.
3. **Clinician-reviewed cases** — even 20–30 doctor-labeled cases strengthens credibility.

---

## 1. Every Number Needs a BASELINE

| Feature | Metric | Baseline to beat | Endpoint |
|---|---|---|---|
| **A — Temporal RAG** | Recall@5, future-leak rate, latency p95 | Vanilla dense RAG + BM25 | `POST /api/v1/evaluation/run` |
| **B — Self-Planning** | Success rate, steps-to-resolution | Fixed pipeline (no replan) | `POST /api/v1/evaluation/feature-b` |
| **C — Projector** | Recall@k (image↔text) | Raw cosine without projector | `POST /api/v1/evaluation/feature-c?num_pairs=200` |
| **D — Schema Align** | Field-level F1 | Regex/rule-based extraction | Requires manual evaluation |
| **E — Trajectory** | Precision on injected deteriorations | Threshold-on-single-vital | `POST /api/v1/evaluation/feature-e?num_patients=100` |
| **F — Sig. Reports** | Likert 1–5 usefulness | Unfiltered digest | Requires manual evaluation |

---

## 2. Automated Evaluation Endpoints

| Endpoint | Feature | What It Does |
|----------|---------|--------------|
| `POST /api/v1/evaluation/run` | A | Full eval suite with baselines + ablation tables |
| `POST /api/v1/evaluation/feature-b` | B | Self-planning on 100-query test set |
| `POST /api/v1/evaluation/feature-c?num_pairs=200` | C | Projector training + evaluation |
| `POST /api/v1/evaluation/feature-e?num_patients=100` | E | Trajectory clustering on synthetic cohort |
| `GET /api/v1/weekly-report/likert-study` | F | Study design for doctor feedback |
| `POST /api/v1/documents/parse` | D | Per-document evaluation (manual review needed) |

**Langfuse integration:** All metrics are traced automatically. Pull evaluation results directly from Langfuse dashboards.

---

## 3. Manual Evaluation Required

### Feature D — Schema Alignment
- 5 document types × ~50 documents each
- Hand-label correct field mappings
- Compute field-level F1
- Requires clinician to validate ground truth

### Feature F — Significance Reports
- Doctor rates filtered digest vs unfiltered baseline
- Likert 1–5 scale
- Even n=1 practicing GP feedback is valuable
- Use `GET /api/v1/weekly-report/likert-study` for study design

---

## 4. The Ablation Table (turns a claim into evidence)

For each feature, remove one component at a time and show the metric drop. Example for Feature A:

```
Config                          Recall@5    Future-leak
Full (α+β+γ+δ+ε)                 0.82        0.8%
  − temporal decay (δ)          0.74        —
  − significance (ε)            0.78        —
  − temporal filter             0.79        23%   ← proves the filter works
Vanilla dense RAG               0.67        31%
```

Build one ablation table per feature.

---

## 5. Worth More Than All the Numbers: One Real Doctor

Get one practicing GP to spend ~90 minutes with the system. Even **n = 1**.

> "A practicing physician with 12 years' experience reviewed 20 AI-generated weekly digests and rated them
> 4.2/5 vs 2.1/5 for the unfiltered baseline..."

For Features **D and F**, doctor-rated relevance *is* the metric.

---

## 6. Concrete Sequence

1. **Week 1** — Build labeled test sets (synthetic + public), inject ground truth.
2. **Week 2** — Run all automated eval endpoints at scale, generate ablation tables from Langfuse.
3. **Week 3** — One doctor feedback session (Features D, F + general). Validate LLM-judge against human labels.
4. **Week 4** — Write results sections around the tables. Numbers → figures → prose.

---

## 7. Transparency Clause

State plainly that datasets are synthetic/public, not production clinical data. Suggested wording:

> "Evaluated on synthetic longitudinal records validated against MIMIC-IV distributions; production clinical
> validation is future work."

---

## 8. Targets Recap

| Metric | Baseline | Target |
|---|---|---|
| Recall@5 (time-correct) | BM25 / vanilla MedCPT | +15 pp |
| Future-leak rate | vanilla dense RAG | < 1 % |
| Latency p95 | — | < 600 ms |
| Answer faithfulness (LLM-judge) | — | > 0.85 |
