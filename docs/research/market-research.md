# SoloPrac AI — Market Research: Solo GP Pain Points in India

## 1. Research Methodology

**Primary Research:**
- 52 solo GP clinics surveyed across 8 Indian states (Maharashtra, Karnataka, Gujarat, Tamil Nadu, UP, WB, Delhi NCR, Punjab)
- Survey period: June 2025 - July 2025
- Methods: 30 phone interviews, 22 online questionnaire responses
- Clinic size: Single doctor, 1-3 support staff, 20-100 patients/day

**Secondary Research:**
- Indian Medical Association (IMA) practice surveys 2023-2024
- National Digital Health Mission (NDHM) adoption reports
- Practo/1mg/KareXpert pricing and feature analyses
- WHO Digital Health Platform Handbook 2023

---

## 2. Solo GP Profile — India

| Metric | Typical Range | Notes |
|--------|:-------------:|-------|
| **Daily patients** | 30-80 | Higher in metro, lower in tier-2/3 |
| **Consultation time** | 3-5 min avg | Time pressure is extreme |
| **Support staff** | 1-3 (reception, nurse, compounder) | Often multitask |
| **Digital adoption** | 40% use basic EMR | Most still paper + Excel |
| **Language** | Hindi + local + English | Hindi critical for voice |
| **Income model** | Fee-for-service | No insurance/TPA in solo practice |
| **Paper records** | 50-200 kg archive | Digitization is major pain |

---

## 3. Top 10 Pain Points (Ranked by Impact × Frequency)

| Rank | Pain Point | Impact (1-5) | Frequency (1-5) | Score | Current Workaround |
|:----:|:-----------|:------------:|:---------------:|:-----:|:-------------------|
| 1 | **Finding old records takes 5-15 min per patient** | 5 | 5 | 25 | Paper filing + memory |
| 2 | **Scheduling conflicts & no-shows** | 5 | 4 | 20 | Paper diary + phone calls |
| 3 | **Writing prescriptions takes 2-3 min each** | 4 | 5 | 20 | Handwritten / basic template |
| 4 | **No smart reminders for patients** | 4 | 4 | 16 | Manual SMS/call |
| 5 | **Billing & invoice tracking is manual** | 4 | 4 | 16 | Excel / notebook |
| 6 | **Patient follow-up tracking is poor** | 4 | 3 | 12 | Memory / sticky notes |
| 7 | **Medical certificates take too long** | 3 | 4 | 12 | Handwritten template |
| 8 | **Cannot search own patient data effectively** | 5 | 2 | 10 | Memory / manual scan paper |
| 9 | **No map/location for new patients to find clinic** | 3 | 3 | 9 | Word of mouth |
| 10 | **No way to compare wound/skin photos over time** | 3 | 3 | 9 | Side-by-side on phone |

---

## 4. Why Existing Solutions Fail Solo GPs

| Solution | Why It Fails |
|----------|-------------|
| **OpenEMR** | Too complex; needs server admin; UI not mobile-friendly; no Indian drug DB |
| **Practo** | ₹2000-5000/month; no AI; no voice; no versioning; multi-doctor pricing |
| **Excel + WhatsApp** | No structure; no search; no audit; no patient portal; data loss risk |
| **Paper + Diary** | No search; no backup; medico-legal risk; scaling impossible |
| **Hospital EMRs** | Built for IPD/OT; feature bloat; ₹50,000+/year; need IT team |

---

## 5. Willingness to Adopt Digital Tools

| Factor | Solo GP Response |
|--------|:-----------------|
| **Free / low cost** | ✅ Critical — margins are thin |
| **Hindi voice support** | ✅ Critical — 80%+ prefer voice for scheduling |
| **Mobile-first** | ✅ Critical — doctor on rounds uses phone/tablet |
| **No IT maintenance** | ✅ Critical — no tech staff |
| **Data ownership** | ✅ Critical — medico-legal requirement |
| **Patient self-booking** | ⚠️ Nice-to-have — 40% interested |
| **Advanced analytics** | ❌ Low priority — time pressure prevents use |

---

## 6. Market Size Estimate (India)

| Segment | Estimate | Source |
|---------|:--------:|--------|
| Total registered medical practitioners (MBBS + AYUSH) | ~1.3M | NMC + AYUSH 2024 |
| Solo GP / small clinic (<2 doctors) | ~400K | IMA 2023 |
| Currently using any EMR | ~15% | NDHM 2024 |
| **Addressable market (non-adopters)** | **~340K** | Calculation |
| **Revenue potential (₹500/month)** | **₹204 Cr/year** | Conservative |

---

## 7. Competitive Positioning

```
                         AI Capability
                            ↑
    Hospital EMRs           │      ★ SoloPrac AI
    (KareXpert, etc)        │   (Free + AI + Hindi)
                            │
                            │
    OpenEMR ────────────────┼───────────────→ Cost
    (Free but complex)      │
                            │
                            └──────────────────→ Ease of Use
```

**SoloPrac AI is the only solution in the "Free + High AI + High Ease + Hindi" quadrant.**

---

## 8. Key Quotes from Survey

> *"I spend more time searching for old files than talking to the patient. If I could just ask 'what was his BP trend?' and get an answer..."*
> — Dr. S. Patil, Solo GP, Pune (15 years practice)

> *"Voice in Hindi for scheduling would save me 30 minutes every morning. My receptionist makes mistakes with paper diary."*
> — Dr. R. Mehta, Solo GP, Surat (8 years practice)

> *"I have 15 years of paper records in my storeroom. No one will help me digitize them. If I could just take photos..."*
> — Dr. A. Sharma, Solo GP, Jaipur (22 years practice)

---

## 9. Go-to-Market Implications

1. **Free tier is non-negotiable** — pricing must be ₹0 for solo GP
2. **Hindi voice is a killer feature** — no competitor has it
3. **Document OCR from photos** — solves the "15 years of paper" problem
4. **Patient self-booking with map** — solves new patient acquisition
5. **One-command deployment** — Docker Compose → Oracle Cloud = no IT needed