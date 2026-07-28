# Demo Flow — SoloPrac AI Walkthrough

## Overview
5-minute scripted walkthrough covering all features.
Suitable for mentor review, capstone presentation, and demo video.

---

## 1. Landing Page & Registration (45s)
1. Open `http://localhost:5173` — professional landing page with hero, features, how-it-works
2. Click "Register" → `/register` page
3. Fill form: name, email, phone, clinic name, clinic address, password
4. Submit → new doctor created (`verification_status: unverified`)
5. Show you can access dashboard immediately as unverified doctor

## 2. Doctor Verification (30s)
1. Go to Settings → Profile tab
2. Show amber "Complete your profile" banner
3. Fill: registration number, state medical council, year of registration
4. Upload profile photo → oval crop modal with drag + zoom
5. Submit → status becomes `pending_verification`
6. Login as admin → `GET /admin/verifications/pending` → approve
7. Doctor becomes `verified` — badge appears

## 3. Patient Timeline + Versioning (45s)
1. Click any patient → Timeline view loads
2. Show version chain with dates and summaries
3. Click a specific version → state displayed
4. Click "Diff" between two versions → changes highlighted
5. Make an inline edit → new version created (show in sidebar)
6. Click "Revert" → version rolled back

## 4. AI Chat + Voice Input (45s)
1. Go to Chat page (`/chat`)
2. Type: "What is this patient's BP trend?"
3. Show SSE streaming: Router → Plan → Execute → Synthesize → Respond
4. Click a citation chip `[v3 · Jan 15]` → jumps to that version
5. Click mic button → speak a question → text appears in input
6. Type: "Generate a prescription for Metformin 500mg"
7. Show AI-assisted prescription created + approval popup

## 5. Document Parsing + OCR Quality Alerts (30s)
1. Go to Scratchpad (`/scratchpad`)
2. Upload a blurry photo → amber quality warning appears
3. Upload a clear prescription PDF/image
4. Show: parsing → schema alignment → extracted fields
5. Click "Save to Patient" → document linked to patient

## 6. Prescriptions / Invoices / Certificates (30s)
1. Go to Prescription Box → add medications table
2. Click mic on diagnosis field → speak → text fills
3. Generate PDF → show preview with state-specific regulatory header
4. Approval popup → "Approve to Record" → version created
5. Go to Invoices → add line items with auto-calculate
6. Generate Invoice PDF with QR code
7. Go to Certificates → select type → generate with verification code

## 7. Calendar + Booking (45s)
1. Go to Calendar (`/calendar`)
2. Show weekly view with appointment blocks (colored by status)
3. Click a free slot → booking dialog opens
4. Search patient by name → shows photo, age, gender
5. Select date/time, add reason → book
6. Show real-time update via WebSocket (no refresh needed)
7. Click existing appointment → detail modal
8. Reschedule → appointment moved
9. Cancel → two-step confirmation

## 8. Patient Portal (45s)
1. Open `/patient/login` in new tab
2. Login with email + password
3. Show Patient Dashboard with appointment count + notifications
4. Search for a doctor → PostGIS radius search + PIN code input
5. Doctor cards show photo, name, years experience, distance
6. Click doctor → see profile
7. See available slots → book appointment (with telemedicine consent checkbox)
8. Show Inbox with real-time notifications via WebSocket
9. Show Reports → download prescription PDF
10. Show Documents → unified timeline with version citations
11. Show Consent → DPDP consent management
12. Click "Delete Account" → data erasure confirmation

## 9. Settings & Profile (30s)
1. Go to Settings → Profile tab
2. Show profile photo with change-on-hover
3. Show years of experience (computed from year_of_registration)
4. Show state selector (controls prescription regulatory text)
5. Show map picker (OpenStreetMap + Nominatim search + geolocation)
6. Show multi-device sessions → revoke a session
7. Switch language to Hindi → UI updates

## 10. Offline + Error Tracking (15s)
1. Show service worker registration in DevTools
2. Disconnect network → page still loads cached content
3. Show Sentry DSN configuration (opt-in)

## Total: ~5.5 minutes

---

## Tips for Smooth Demo
- Have test data pre-loaded (synthetic patients with 6+ visits each)
- Keep API keys functional (NVIDIA NIM, Groq)
- Open DevTools Network tab to show SSE streaming in Chat
- Pre-generate a PDF for faster display
- Use incognito window for patient portal demo
- Test voice features with quiet microphone
- Show Hindi UI switch in user menu
- Show OCR quality alert with a deliberately blurry image
