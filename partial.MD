🇮🇳 India Deployment Readiness Assessment

## 💰 Pricing Legend

| Icon | Meaning |
|------|---------|
| 🆓 | **Zero API cost** — needs only dev effort |
| 💵 | **Paid service** — ongoing per-transaction or subscription cost |
| 🟡 | **Sandbox is free**, but production certification has cost |
| ✅ | **Already partially implemented** in codebase |

---

## ⚠️ PARTIAL — Must Complete Before India Launch

---

### 1. Indian Drug Database 🆓
**Status:** ❌ Not started (was marked partial but no code exists)
**Gap:** CDSCO / Jan Aushadhi drug database not integrated
**Cost:** Free — CDSCO drug master data is publicly available. Parse CSV → seed PostgreSQL. Build rule engine in Python.
**Risk:** Prescriptions should use approved Indian drug names and formulations

---

### 2. DPDP Act Compliance 🆓
**Status:** ✅ Partially implemented
**Completed:** PII encryption (pgcrypto), `consent_for_share` field, audit logging, RLS isolation
**Missing:**
- Consent management UI
- Data erasure workflows (anonymization)
- DPO workflows
- Explicit consent records table
**Cost:** Free — pure feature dev on existing infrastructure
**Risk:** Mandatory legal compliance for handling patient data in India

---

### 3. NMC / State Medical Council Verification 🆓
**Status:** ✅ Partially implemented
**Completed:** `registration_number` field, `verification_status` enum, admin approval/rejection endpoints
**Missing:** Auto-verification via Indian Medical Register (publicly accessible)
**Cost:** Free — public register can be checked or scraped
**Risk:** Doctors must have verified registration numbers before practicing

---

### 4. ABDM / ABHA Integration 🟡 — ⏭️ SKIP FOR NOW (not required)
> **Decision (2026-07-25):** Deferred / skipped. ABDM is national health-record *interoperability*, not a
> verifier and not required to operate. The app's own version-controlled records + cross-clinic phone-based
> identity already cover the in-app need. Production also requires being a registered health facility (HFR) +
> a paid CERT-In WASA audit — out of scope. Revisit only post-launch with paying customers, via the free
> sandbox. Prioritise **NMC doctor verification** instead (that is the real verifier that matters).
**Status:** ❌ Not started
**Gap:**
- ABHA linking (create/verify ABHA number)
- Care context discovery & linking
- FHIR bundle generation
- Health record push/pull (HIP + HIU flows)
- Consent management via ABDM gateway
**Cost:**
  - **Sandbox dev & testing:** 🆓 Free (register at sandbox.abdm.gov.in)
  - **Production certification:** 💵 ₹3-8 lakhs one-time (WASA audit + functional testing)
**Python library:** `pip install krama-core`
**Localhost:** Works via `cloudflared tunnel` for bridge URL
**Risk:** Increasingly becoming a national interoperability requirement

---

### 5. UPI Payment Integration 💵
**Status:** ✅ Partially implemented
**Completed:** Invoice model with `status` (paid/cancelled), `payment_method` field, "Mark as Paid" endpoint
**Missing:**
- Real UPI payment gateway
- QR code generation
- Payment confirmation webhook
- Transaction reconciliation
**Cost:** 💵 ~2% per transaction (Razorpay/PhonePe)
**Free MVP workaround:** Generate offline `upi://pay` deep-link QR codes. Patient scans via any UPI app, money goes directly to your UPI ID. No callback — use existing "Mark as Paid" manually
**Risk:** UPI is the default payment method expected in India

---

### 6. Hindi UI Localization 🆓
**Status:** ❌ Not started
**Gap:**
- Hindi translation JSON files
- `react-i18next` framework setup
- Language switcher toggle
**Cost:** Free — `react-i18next` is MIT. Generate translations via Groq Llama-3.2-90B
**Risk:** Major adoption barrier in Tier-2 and Tier-3 cities

---

### 7. CDSCO / State Prescription Compliance 🆓
**Status:** ✅ Partially implemented
**Completed:** PDF prescription generation with clinic branding (Jinja2 + Playwright)
**Missing:**
- State-compliant prescription layouts (extend Jinja2 templates)
- CDSCO-compliant drug naming (use imported drug DB)
- Required regulatory fields (doctor reg. number, clinic license)
**Cost:** Free — extends existing PDF generator
**Risk:** Non-compliant prescriptions may not satisfy state regulations

---

### 8. Telemedicine Practice Guidelines (2020) 🆓
**Status:** ✅ Partially implemented
**Completed:** Appointment system with `source` tracking, calendar, slot finding
**Missing:**
- Telemedicine consent flow (checkbox + timestamp)
- RMP verification before online consultation
- Guideline-compliant consultation workflow
**Cost:** Free — extends existing appointment system
**Risk:** Required for legal teleconsultation services

---

## ❌ MISSING — Must Build Before Production Deployment

### 1. Regulatory Compliance 🔴 Critical

| Feature | Cost | ETA |
|---------|------|-----|
| DPDP consent management | 🆓 | 1 week |
| Data erasure workflows | 🆓 | 1 week |
| NMC auto-verification | 🆓 | 2 weeks |
| ABDM integration | 🟡 Free sandbox / 💵 Paid production | 6-8 weeks |
| Telemedicine consent flow | 🆓 | 1 week |

### 2. India Localization 🔴 Critical

| Feature | Cost | ETA |
|---------|------|-----|
| Full Hindi UI (i18n) | 🆓 | 2-3 weeks |
| CDSCO drug database | 🆓 | 2-4 weeks |
| State-specific prescription formats | 🆓 | 1 week |
| UPI payments | 💵 ~2% per txn | 1-2 weeks |
| PIN code-based doctor search | 🆓 | 1 day |

### 3. Clinical Safety 🔴 Critical

| Feature | Cost | ETA |
|---------|------|-----|
| Drug interaction checker (Indian formulary) | 🆓 | 1-2 weeks |
| Allergy cross-check | 🆓 | 3 days |
| Duplicate prescription prevention | 🆓 | 2 days |
| Critical laboratory value alerts | 🆓 | 1 week |

### 4. Operational Readiness 🟡 High

| Feature | Cost | ETA |
|---------|------|-----|
| Offline-first synchronization (PWA) | 🆓 | 1-2 weeks |
| SMS fallback (NIC / MSG91) | 💵 ~₹0.12/SMS | 1 week |
| Backup and restore | 🆓 | 3 days |
| Multi-device session management | 🆓 | 1 week |

### 5. Observability 🟡 High

| Feature | Cost | ETA |
|---------|------|-----|
| Structured audit logging | ✅ Already done | — |
| Error tracking (Sentry) | 🆓 Free tier (5k/mo) | 1 day |
| Health checks | ✅ Already done | — |
| Migration scripts (Alembic) | 🆓 | 1 day |

### 6. Testing & Quality Assurance 🟡 High

| Feature | Cost | ETA |
|---------|------|-----|
| Playwright end-to-end tests | 🆓 | 2-3 weeks |
| Contract/API tests (Pytest) | 🆓 | 1-2 weeks |
| Load testing (~50 concurrent) | 🆓 Locust | 1 week |
| Chaos testing | 🆓 | 1 week |

---

## 💳 Summary: What Actually Costs Money

| Feature | Estimated Cost | Can Skip for MVP? |
|---------|---------------|-------------------|
| **UPI Payment Gateway** | ~2% per transaction | ✅ Yes — use offline QR + manual "Mark as Paid" |
| **SMS (MSG91/NIC)** | ~₹0.12/SMS | ✅ Yes — use email (already built) + WhatsApp Cloud free tier |
| **ABDM Production Certification** | ₹3-8 lakhs one-time | ✅ Yes — use sandbox for dev; certify only with paying customers |
| **All other features** | **₹0** | — |

**16 out of 18 missing features need zero ongoing API costs.** Build everything except UPI gateway and SMS on free tools.