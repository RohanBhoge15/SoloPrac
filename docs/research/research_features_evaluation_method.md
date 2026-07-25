# Research Features — Evaluation Methodology (A–F)

> How to produce **real, publishable evaluation numbers** for the IEEE paper without real patient data.
> Core principle: you can't use production clinical data (privacy/DPDP), so "real numbers" means
> **methodologically rigorous numbers on defensible datasets** — not hand-waving. Reviewers accept
> synthetic/public data *if you are transparent*; they reject unstated assumptions.

---

## 0. The Data Foundation (do this FIRST — everything depends on it)

You need a **labeled test set per feature**. Three legitimate sources, in order of credibility:

1. **Public de-identified datasets** — MIMIC-IV, CheXpert, PMC figure-caption pairs. Gold standard because reviewers can reproduce.
2. **LLM-generated synthetic longitudinal records** — acceptable *if transparent* and a sample is validated. Generate multi-visit histories with **known ground truth**.
3. **Clinician-reviewed cases** — even 20–30 doctor-labeled cases gives a "human ground truth" subset that massively strengthens credibility.

**The key trick that makes synthetic data respectable: inject known ground truth.** If *you* plant the
deterioration / abnormal lab / time-correct answer, you can measure precisely whether the system found it.
That is controlled evaluation, not cheating.

---

## 1. The Non-Negotiable: every number needs a BASELINE

A number alone ("Recall@5 = 0.82") is meaningless. "0.82 vs 0.67 for vanilla RAG, **+15pp**" is a paper.
Every feature must beat a stated baseline.

| Feature | Metric | How to measure | Baseline to beat |
|---|---|---|---|
| **A — Temporal RAG** | Recall@5, **future-leak rate**, latency p95 | ~100 time-stamped queries with known correct version. Future-leak = % retrieved versions with `timestamp > query_time`. | Vanilla dense RAG (no temporal filter) + BM25 |
| **B — Self-Planning** | Success rate, steps-to-resolution | 100-query set; LLM-judge or manual grade of final-answer correctness | Fixed pipeline (no replan loop) |
| **C — Projector** | Recall@k (image↔text) | Held-out CheXpert + wound pairs; project image → search text space | Raw cosine **without** projector |
| **D — Schema Align** | Field-level **F1** | 5 doc types × ~50 docs, hand-label correct field mappings | Regex/rule-based extraction, or LLM without critic loop |
| **E — Trajectory** | Precision, recall on **injected** deteriorations | Synthetic cohort; plant N deteriorating patients; measure detection | Threshold-on-single-vital alerting |
| **F — Sig. Reports** | Likert 1–5 usefulness | Doctor rates filtered digest vs unfiltered | Unfiltered "every measurement" digest |

---

## 2. The Two Highest-Leverage Moves

### 2.1 The Ablation Table (turns a claim into evidence)

For each feature, remove one component at a time and show the metric drop. Example for Feature A:

```
Config                          Recall@5    Future-leak
Full (α+β+γ+δ+ε)                 0.82        0.8%
  − temporal decay (δ)          0.74        —
  − significance (ε)            0.78        —
  − temporal filter             0.79        23%   ← proves the filter works
Vanilla dense RAG               0.67        31%
```

That single table **is** your Section III results — it proves every scoring term earns its place.
Build one ablation table per feature.

### 2.2 LLM-as-Judge, done rigorously

For "answer faithfulness" and plan quality you'll grade with an LLM. Reviewers accept this **only if**:
- You use a strong judge model.
- You publish the grading rubric / prompt.
- **You validate the judge against ~30 human labels** and report judge–human agreement (Cohen's κ).

That validation is what separates rigorous LLM-judge from lazy LLM-judge.

---

## 3. Your Unfair Advantage: Langfuse

Langfuse is already wired, so **every operational metric is already being traced**: latency p95, token counts,
plan steps, replan frequency, tool-call success. Pull these straight from Langfuse instead of re-instrumenting.

The existing evaluation endpoints already exist — run them at scale, log to Langfuse, export the tables:
- `POST /api/v1/evaluation/run` — Feature A full suite + baselines
- `POST /api/v1/evaluation/feature-b` — self-planning (100-query set)
- `POST /api/v1/evaluation/feature-c?num_pairs=200` — projector train + eval
- `POST /api/v1/evaluation/feature-e?num_patients=100` — trajectory clustering
- `GET  /api/v1/weekly-report/likert-study` — Feature F study design
- `POST /api/v1/documents/parse` — Feature D (per-document)

---

## 4. Worth More Than All the Numbers: One Real Doctor

Get one practicing GP to spend ~90 minutes with the system. Even **n = 1**.

> "A practicing physician with 12 years' experience reviewed 20 AI-generated weekly digests and rated them
> 4.2/5 vs 2.1/5 for the unfiltered baseline; qualitative feedback noted…"

That paragraph does more for acceptance than another ablation. For Features **E and F**, doctor-rated relevance
*is* the metric — synthetic data cannot fake clinical usefulness, so this is where a human closes the gap.

---

## 5. Concrete Sequence (remaining weeks)

1. **Week 1 — Build labeled test sets** (synthetic + public), inject ground truth. This is the bottleneck; do it first.
2. **Week 2 — Run all eval endpoints at scale**, generate ablation tables from Langfuse.
3. **Week 3 — One doctor feedback session** (Features E/F + general). Validate LLM-judge against human labels (κ).
4. **Week 4 — Write results sections** around the tables. Numbers → figures → prose.

---

## 6. Transparency Clause (protects the paper)

State plainly that datasets are synthetic/public, not production clinical data. Reviewers forgive **stated**
limitations; they punish **hidden** ones. Suggested wording:

> "Evaluated on synthetic longitudinal records validated against MIMIC-IV distributions; production clinical
> validation is future work."

---

### Targets recap (from UpdatedIdea.MD, Feature A)

| Metric | Baseline | Target |
|---|---|---|
| Recall@5 (time-correct) | BM25 / vanilla MedCPT | +15 pp |
| Future-leak rate | vanilla dense RAG | < 1 % |
| Latency p95 | — | < 600 ms |
| Answer faithfulness (LLM-judge) | — | > 0.85 |
