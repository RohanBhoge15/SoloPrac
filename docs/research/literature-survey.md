# SoloPrac AI — Literature Survey

## 1. Objective

To study existing Electronic Medical Record (EMR) systems, identify their architecture patterns, feature sets, and limitations — specifically for solo medical practitioners in India.

---

## 2. Systems Surveyed

| System | Type | Target Audience | Pricing | Open Source |
|--------|------|----------------|:-------:|:-----------:|
| OpenEMR | Full EMR | Multi-specialty clinics | Free | ✅ Yes (GPL) |
| Practo | Cloud EMR | Indian clinics | Paid | ❌ No |
| Tata 1mg | Health platform | Patients | Free/Paid | ❌ No |
| Dr. Chrono | Cloud EMR | US small practices | Paid | ❌ No |
| EHRBase | EMR backend | Enterprise | Free | ✅ Yes (AGPL) |
| Bahmni | HMIS | Low-resource hospitals | Free | ✅ Yes (AGPL) |
| MedicsCloud | Cloud EMR | Indian clinics | Paid | ❌ No |
| KareXpert | Cloud EMR | Indian hospitals | Paid | ❌ No |

---

## 3. Detailed Analysis

### 3.1 OpenEMR
**Strengths:**
- Most widely deployed open-source EMR globally
- ONC-certified (US meaning)
- Comprehensive features: scheduling, billing, prescriptions, labs, reporting
- SQL database with standard schema

**Weaknesses:**
- **No versioned records** — patient data is overwritten on edit. No audit trail of *what changed when*.
- **No AI integration** — no LLM/RAG pipeline. No intelligent retrieval.
- **No temporal awareness** — queries return current state only. No time-travel.
- UI is functional but dated (PHP-based). Not mobile-optimized for Indian doctors.
- No voice support.
- No patient portal with Indian requirements (Hindi, OTP auth, local maps).

### 3.2 Practo
**Strengths:**
- Market leader in Indian clinic management
- Good patient booking experience
- Integrated medicine database (India-specific)
- Patient engagement features (reminders, reports)

**Weaknesses:**
- **Closed source** — no customization possible
- **Paid subscription** — ₹2,000-5,000/month per clinic
- **No AI features** — basic search, no LLM integration
- **No versioned records** — standard RDBMS updates
- **No temporal retrieval** — can't query "what did we know on date X?"
- **No Hindi voice support**
- **Solo GP pricing is prohibitive** — designed for multi-doctor clinics

### 3.3 Tata 1mg
**Strengths:**
- Strong patient-facing experience
- Medicine delivery integration
- Lab test booking

**Weaknesses:**
- **Patient-facing only** — not a doctor's practice management tool
- **No EMR features** — no clinical notes, no prescriptions from doctor side
- **No AI for doctors**
- Supported by venture funding, not sustainable pricing

### 3.4 Dr. Chrono
**Strengths:**
- Excellent UI/UX
- Good iPad-based intake
- Patient portal with reasonable features

**Weaknesses:**
- **US-focused** — billing codes (CPT/ICD-10-AM) don't match Indian practice
- **No Hindi support**
- **Paid** — $199+/month
- **No AI/LLM features** — basic search only
- **No versioning** — standard audit log, not immutable chain

### 3.5 Bahmni
**Strengths:**
- Designed for low-resource settings
- Offline-capable
- Integrated with OpenMRS

**Weaknesses:**
- **Hospital-focused** — too heavy for solo GP (OT, IPD, nursing)
- **No AI** — no LLM, no retrieval augmentation
- **No voice**
- Patient model is disease-centric, not consultation-centric

---

## 4. Key Findings

### 4.1 Common Gaps Across All Systems

| Gap | OpenEMR | Practo | Dr. Chrono | Bahmni | SoloPrac AI |
|-----|:-------:|:------:|:----------:|:------:|:-----------:|
| Versioned immutable records | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Temporal-aware RAG | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Self-planning AI agent | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Cross-modal retrieval (image↔text) | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Voice scheduling (Hindi+English) | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Zero-shot document schema alignment | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Trajectory-based risk alerts | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| AI-generated weekly significance reports | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Image registration for clinical comparison | ❌ | ❌ | ❌ | ❌ | ✅ **Novel** |
| Free-tier deployment (Oracle Cloud) | ✅ | ❌ | ❌ | ✅ | ✅ |
| Indian languages (Hindi) | ❌ | Partial | ❌ | ❌ | ✅ |
| Solo GP optimized | Partial | Partial | ✅ | ❌ | ✅ **Target** |

### 4.2 No System Has Version-Controlled Patient Records

This is a critical gap. Every existing system either:
- **Overwrites data** on edit (OpenEMR, Practo, Dr. Chrono)
- **Logs audit trails** but doesn't make them queryable as state (Bahmni)
- **Keeps no history** of what changed and why

SoloPrac AI's **versioned immutable chain** is a genuine research contribution — it enables time-travel queries, temporal-aware RAG, and medico-legal traceability that no existing system provides.

---

## 5. Research Paper Positioning

Based on this survey, our paper should highlight:

1. **First EMR with version-controlled patient intelligence** — designing patient records as an immutable git-like chain
2. **First to apply temporal decay to medical RAG** — formalizing "what did we know when" 
3. **First self-planning agent for clinical workflows** — dynamic tool selection vs fixed pipelines
4. **Completely free-tier stack** — accessibility for resource-constrained solo practitioners

---

## 6. References

- OpenEMR. (2024). OpenEMR Project. https://www.open-emr.org
- Practo Technologies. (2024). Practo for Clinics. https://www.practo.com
- Dr. Chrono. (2024). Dr. Chrono EHR. https://www.drchrono.com
- Bahmni. (2024). Bahmni Project. https://www.bahmni.org
- Tata 1mg. (2024). Healthcare Platform. https://www.1mg.com
- World Health Organization. (2023). Digital Health Platform Handbook.
- Ministry of Health and Family Welfare, India. (2024). Ayushman Bharat Digital Mission.
- Price, M. et al. (2023). "Temporal Embeddings for Clinical Data." JAMIA.
- Wu, C. et al. (2024). "MedCPT: Medical Contrastive Pre-Trained Language Model." NAACL.
