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

| Rank | Pain Point | Score | SoloPrac AI Solution | Status |
|:----:|:-----------|:-----:|:---------------------|:------:|
| 1 | Finding old records takes 5-15 min | 25 | Version timeline + RAG search | **Done** |
| 2 | Scheduling conflicts & no-shows | 20 | Calendar + booking dialog + race protection | **Done** |
| 3 | Writing prescriptions takes 2-3 min | 20 | AI draft + voice-to-text + approval | **Done** |
| 4 | No smart reminders for patients | 16 | AI-generated notifications via WebSocket | **Done** |
| 5 | Billing & invoice tracking is manual | 16 | Auto-invoice + PDF + QR | **Done** |
| 6 | Patient follow-up tracking is poor | 12 | Risk alerts (Feature E) + weekly reports | **Done** |
| 7 | Medical certificates take too long | 12 | Template → AI fill → print (10s) | **Done** |
| 8 | Cannot search own patient data effectively | 10 | Temporal RAG with citations | **Done** |
| 9 | No map/location for new patients | 9 | OpenStreetMap + PostGIS radius + PIN search | **Done** |
| 10 | No way to compare wound photos | 9 | ORB matching + overlay + clinical summary | **Done** |

**All 10 pain points addressed.**

---

## 4. Why Existing Solutions Fail Solo GPs

| Solution | Why It Fails | SoloPrac AI Advantage |
|----------|-------------|----------------------|
| **OpenEMR** | Too complex; needs server admin; no AI; no Hindi | One-command Docker deploy; AI-powered; Hindi UI |
| **Practo** | ₹2000-5000/month; no AI; no voice; no versioning | Free tier; self-planning agent; voice scheduling |
| **Excel + WhatsApp** | No structure; no search; no audit; data loss risk | Version chain; RLS; audit log; offline PWA |
| **Paper + Diary** | No search; no backup; medico-legal risk | Temporal RAG; immutable versions; full audit trail |
| **Hospital EMRs** | Feature bloat; ₹50,000+/year; need IT team | Solo-GP focused; zero cost; Docker Compose deploy |

---

## 5. Willingness to Adopt Digital Tools

| Factor | Solo GP Response | SoloPrac AI Coverage |
|--------|:-----------------|:--------------------:|
| **Free / low cost** | Critical | ₹0 (Oracle Free Tier) |
| **Hindi voice support** | Critical | IndicWhisper + Indic-Parler-TTS |
| **Mobile-first** | Critical | Responsive Tailwind + touch-friendly |
| **No IT maintenance** | Critical | Docker Compose one-command deploy |
| **Data ownership** | Critical | Version chain + RLS + audit log |
| **Patient self-booking** | Nice-to-have | Patient portal with PostGIS search |
| **Offline capability** | Important | PWA with Workbox caching |

---

## 6. Market Size Estimate (India)

| Segment | Estimate | Source |
|---------|:--------:|--------|
| Total registered medical practitioners | ~1.3M | NMC + AYUSH 2024 |
| Solo GP / small clinic (<2 doctors) | ~400K | IMA 2023 |
| Currently using any EMR | ~15% | NDHM 2024 |
| **Addressable market (non-adopters)** | **~340K** | Calculation |
| **Revenue potential (₹500/month)** | **₹204 Cr/year** | Conservative |

---

## 7. Key Quotes from Survey

> *"I spend more time searching for old files than talking to the patient. If I could just ask 'what was his BP trend?' and get an answer..."*
> — Dr. S. Patil, Solo GP, Pune

> *"Voice in Hindi for scheduling would save me 30 minutes every morning."*
> — Dr. R. Mehta, Solo GP, Surat

> *"I have 15 years of paper records. If I could just take photos and have them organized..."*
> — Dr. A. Sharma, Solo GP, Jaipur

---

## 8. Go-to-Market Implications

1. **Free tier is non-negotiable** — pricing must be ₹0 for solo GP
2. **Hindi voice is a killer feature** — no competitor has it
3. **Document OCR from photos** — solves the "15 years of paper" problem
4. **Patient self-booking with map** — solves new patient acquisition
5. **One-command deployment** — Docker Compose → Oracle Cloud = no IT needed
6. **Profile photos + verification** — builds patient trust
7. **Offline PWA** — works in areas with poor connectivity
8. **DPDP compliance** — legally safe for Indian market
