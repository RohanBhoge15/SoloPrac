# SoloPrac AI — Clinical Workflow Study

## 1. Methodology

Shadow observation of 4 solo GP clinics in Maharashtra (2 urban, 2 semi-urban) over 3 days, plus time-motion analysis of 200+ patient consultations.

---

## 2. Typical Solo GP Workflow

```
                    ┌─────────────────────────┐
                    │  Patient Arrives         │
                    │  (5-15 min wait)         │
                    └──────────┬──────────────┘
                               ▼
              ┌─────────────────────────────────┐
              │  Reception (1-2 min)             │
              │  • Find patient file (paper)     │ ← Pain point #1
              │  • Verify appointment             │
              │  • Collect basic info             │
              └──────────┬──────────────────────┘
                         ▼
              ┌─────────────────────────────────┐
              │  Consultation (3-5 min)          │
              │  • Review past history           │ ← Pain point: 2-5 min searching
              │  • Listen to current complaint   │
              │  • Examination / vitals          │
              │  • Check old records             │ ← Pain point: paper retrieval
              │  • Diagnose                      │
              └──────────┬──────────────────────┘
                         ▼
              ┌─────────────────────────────────┐
              │  Prescription / Advice (1-2 min) │
              │  • Write prescription            │ ← Pain point #3
              │  • Recommend investigations       │
              │  • Explain to patient            │
              └──────────┬──────────────────────┘
                         ▼
              ┌─────────────────────────────────┐
              │  Scheduling / Payment (1-2 min)  │
              │  • Book follow-up                │ ← Pain point #2
              │  • Collect payment               │
              │  • Issue receipt/invoice         │ ← Pain point #5
              └─────────────────────────────────┘
```

**Total face-to-face time:** 3-5 minutes
**Total overhead per patient:** 5-8 minutes (record search, writing, scheduling, billing)

---

## 3. Time-Motion Analysis (200 consultations)

| Activity | Avg Time | % of Cycle | SoloPrac AI Target |
|----------|:--------:|:----------:|:------------------:|
| Patient file retrieval | 4.2 min | 24% | **<10s** |
| Past history review | 2.8 min | 16% | **<30s** |
| Active consultation | 5.0 min | 29% | **5.0 min** (no change) |
| Prescription writing | 2.3 min | 13% | **<20s** |
| Handwriting + verifying | 1.1 min | 6% | **<10s** |
| Appointment scheduling | 1.5 min | 9% | **<5s (voice)** |
| Billing | 0.5 min | 3% | **<5s** |
| **Total Overhead** | **12.4 min** | **71%** | **<1.5 min** |
| **Per-Patient Time** | **17.4 min** | 100% | **~7 min** |

**Potential time savings:** 60% reduction in per-patient overhead
**Additional patients per day:** 15-25 more (with same working hours)

---

## 4. Where SoloPrac AI Intervenes

| Workflow Step | Intervention | Time Saved |
|:-------------|:-------------|:----------:|
| File retrieval | Instant Qdrant search + version timeline | **4 min** |
| History review | Temporal RAG → one-line summary with citations | **2.5 min** |
| Prescription | AI draft → doctor validates (10s) | **2 min** |
| Appointment | Voice: "Book Priya Sharma Thursday 3 PM" (5s) | **1.5 min** |
| Follow-up | AI-generated reminders sent automatically | **1 min** |
| Billing | Auto-invoice from consultation | **0.5 min** |
| Certificate | Template → AI fill → print (10s) | **1 min** |

---

## 5. Key Clinical Workflow Requirements Discovered

### 5.1 Must Be Faster Than Paper
Doctors who use paper can write a prescription in **15-20 seconds** while talking to the patient. Our AI system must be faster — which means:
- **Pre-filled defaults** from version history
- **Auto-complete** drug names (Indian drug database)
- **One-tap prescription** from voice command
- **No typing** during consultation (ideal)

### 5.2 Must Work Offline Occasionally (Compromise)
Many clinics have unreliable internet. We cannot fully support offline, but we can:
- Cache patient lists and basic data in localStorage
- Graceful degradation when API is unreachable
- Retry queue for failed requests

### 5.3 Hindi Is Primary, Not Secondary
In semi-urban clinics observed:
- 100% of consultations in Hindi/local language
- 0% of consultations in English
- Prescriptions: English drug names + Hindi instructions
- Voice: Hindi critical for adoption

### 5.4 Mobile/Tablet First
- 80% of doctors checked their phone during consultations
- Zero doctors used a desktop/laptop during patient interaction
- Desktop used only for billing end-of-day

---

## 6. Proposed Optimized Workflow with SoloPrac

```
                    ┌──────────────────────────────────┐
                    │  Patient checks in via reception   │
                    │  System pre-loads patient context  │
                    └──────────────┬───────────────────┘
                                   ▼
              ┌─────────────────────────────────────────┐
              │  Doctor opens tablet → sees:              │
              │  • Patient name + photo                    │
              │  • Last visit summary (1 line)             │
              │  • Pending tasks (lab results, follow-up)  │
              │  • Suggested next steps (AI)               │
              └──────────────┬──────────────────────────┘
                                   ▼
              ┌─────────────────────────────────────────┐
              │  Consultation (5 min)                     │
              │  • Ask "what changed" → voice query       │
              │  • RAG retrieves: "HbA1c up to 8.2 last   │
              │    month, was 7.0 in March"               │
              │  • Take wound photo → ORB compares        │
              │    to last visit, shows overlay           │
              └──────────────┬──────────────────────────┘
                                   ▼
              ┌─────────────────────────────────────────┐
              │  AI drafts prescription (5s)              │
              │  • Doctor reviews + taps to accept        │
              │  • Medication warnings highlighted        │
              │  • Print / send to patient portal         │
              └──────────────┬──────────────────────────┘
                                   ▼
              ┌─────────────────────────────────────────┐
              │  Voice: "Book follow-up 2 weeks" (3s)     │
              │  • Auto-finds slot, confirms aloud        │
              │  • Patient notified via app/email         │
              │  • Invoice auto-generated                 │
              └─────────────────────────────────────────┘
```

**Total time with SoloPrac AI:** 5.3 minutes (vs 17.4 minutes baseline)

---

## 7. Constraints & Design Implications

| Constraint | Design Decision |
|------------|-----------------|
| 3-5 min per patient | Must be one-screen-does-everything; no multi-step forms |
| Hindi + local language | Voice pipeline must default to Hindi detection |
| Mobile-first | All UI designed for 7" tablet minimum; responsive to phone |
| No IT team | Docker Compose deploy; Oracle Cloud free tier |
| Unreliable internet | Offline cache for patient list; graceful degradation |
| Time pressure | Keyboard shortcuts, Cmd+K command palette, voice shortcuts |
| Medico-legal anxiety | Version chain = full audit trail; doctor validates AI output |
