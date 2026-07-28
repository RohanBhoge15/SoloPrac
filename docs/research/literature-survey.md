# SoloPrac AI — Literature Survey

## 1. Objective

To study existing Electronic Medical Record (EMR) systems, identify their architecture patterns, feature sets, and limitations — specifically for solo medical practitioners in India.

---

## 2. Systems Surveyed

| System | Type | Target Audience | Pricing | Open Source |
|--------|------|----------------|:-------:|:-----------:|
| OpenEMR | Full EMR | Multi-specialty clinics | Free | Yes (GPL) |
| Practo | Cloud EMR | Indian clinics | Paid | No |
| Tata 1mg | Health platform | Patients | Free/Paid | No |
| Dr. Chrono | Cloud EMR | US small practices | Paid | No |
| EHRBase | EMR backend | Enterprise | Free | Yes (AGPL) |
| Bahmni | HMIS | Low-resource hospitals | Free | Yes (AGPL) |
| MedicsCloud | Cloud EMR | Indian clinics | Paid | No |
| KareXpert | Cloud EMR | Indian hospitals | Paid | No |

---

## 3. Detailed Analysis

### 3.1 OpenEMR
**Strengths:** Most widely deployed open-source EMR; comprehensive features.
**Weaknesses:** No versioned records; no AI; no temporal awareness; dated UI; no voice; no patient portal with Indian requirements.

### 3.2 Practo
**Strengths:** Market leader in Indian clinic management; good patient booking.
**Weaknesses:** Closed source; paid (₹2,000-5,000/month); no AI; no versioning; no temporal retrieval; no Hindi voice; solo GP pricing prohibitive.

### 3.3 Dr. Chrono
**Strengths:** Excellent UI/UX; good patient portal.
**Weaknesses:** US-focused; no Hindi; paid ($199+/month); no AI; no versioning.

### 3.4 Bahmni
**Strengths:** Designed for low-resource settings; offline-capable.
**Weaknesses:** Hospital-focused (too heavy for solo GP); no AI; no voice.

---

## 4. Key Findings

### 4.1 Common Gaps Across All Systems

| Gap | OpenEMR | Practo | Dr. Chrono | Bahmni | SoloPrac AI |
|-----|:-------:|:------:|:----------:|:------:|:-----------:|
| Versioned immutable records | ❌ | ❌ | ❌ | ❌ | **Novel** |
| Temporal-aware RAG | ❌ | ❌ | ❌ | ❌ | **Novel** |
| Self-planning AI agent | ❌ | ❌ | ❌ | ❌ | **Novel** |
| Cross-modal retrieval | ❌ | ❌ | ❌ | ❌ | **Novel** |
| Voice scheduling (Hindi+English) | ❌ | ❌ | ❌ | ❌ | **Novel** |
| Zero-shot document schema alignment | ❌ | ❌ | ❌ | ❌ | **Novel** |
| Trajectory-based risk alerts | ❌ | ❌ | ❌ | ❌ | **Novel** |
| AI-generated weekly reports | ❌ | ❌ | ❌ | ❌ | **Novel** |
| Image registration (ORB) | ❌ | ❌ | ❌ | ❌ | **Novel** |
| OCR quality alerts | ❌ | ❌ | ❌ | ❌ | **Done** |
| Voice-to-text (prescriptions) | ❌ | ❌ | ❌ | ❌ | **Done** |
| Profile photos + verification | ❌ | ❌ | ❌ | ❌ | **Done** |
| DPDP compliance | ❌ | ❌ | ❌ | ❌ | **Done** |
| Hindi UI | ❌ | Partial | ❌ | ❌ | **Done** |
| Offline PWA | ✅ | ❌ | ✅ | ✅ | **Done** |
| Free-tier deployment | ✅ | ❌ | ❌ | ✅ | **Done** |

### 4.2 No System Has Version-Controlled Patient Records

This is a critical gap. Every existing system either overwrites data on edit, logs audit trails but doesn't make them queryable, or keeps no history.

SoloPrac AI's **versioned immutable chain** is a genuine research contribution — it enables time-travel queries, temporal-aware RAG, and medico-legal traceability that no existing system provides.

---

## 5. Research Paper Positioning

Based on this survey, our paper highlights:

1. **First EMR with version-controlled patient intelligence** — immutable git-like chain
2. **First to apply temporal decay to medical RAG** — formalizing "what did we know when"
3. **First self-planning agent for clinical workflows** — dynamic tool selection vs fixed pipelines
4. **First medical cross-modal projector** — BiomedCLIP → BGE-M3 with InfoNCE
5. **Completely free-tier stack** — accessibility for resource-constrained solo practitioners

---

## 6. Implementation Status

All 6 research features (A-F) are **implemented and ready for evaluation**:

| Feature | Implementation | Evaluation Status |
|---------|---------------|:-----------------:|
| A — Temporal RAG | MedCPT + BGE-M3 + BiomedCLIP + temporal decay | Ready (automated) |
| B — Self-Planning | Plan-execute-critic loop | Ready (automated) |
| C — Cross-Modal | Linear projector + InfoNCE | Ready (automated) |
| D — Schema Alignment | Maverick + structured output + critic | Requires manual eval |
| E — Trajectory Clustering | HDBSCAN + Mahalanobis + WebSocket alerts | Ready (automated) |
| F — Weekly Reports | Significance scorer + 3 PDF layouts | Requires manual eval |

---

## 7. References

- OpenEMR. (2024). OpenEMR Project. https://www.open-emr.org
- Practo Technologies. (2024). Practo for Clinics. https://www.practo.com
- Dr. Chrono. (2024). Dr. Chrono EHR. https://www.drchrono.com
- Bahmni. (2024). Bahmni Project. https://www.bahmni.org
- Tata 1mg. (2024). Healthcare Platform. https://www.1mg.com
- World Health Organization. (2023). Digital Health Platform Handbook.
- Ministry of Health and Family Welfare, India. (2024). Ayushman Bharat Digital Mission.
- Price, M. et al. (2023). "Temporal Embeddings for Clinical Data." JAMIA.
- Wu, C. et al. (2024). "MedCPT: Medical Contrastive Pre-Trained Language Model." NAACL.
