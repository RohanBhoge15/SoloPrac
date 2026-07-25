# Demo Flow — SoloPrac AI Walkthrough

## Overview
5-minute scripted walkthrough covering all 12 weeks of features.
Suitable for mentor review, capstone presentation, and demo video.

---

## 1. Login & Verification (60s)
1. Open `http://localhost:5173`
2. Click "Register with Email" → enter email + password + name → new doctor created (`verification_status: unverified`)
3. Show you can access dashboard immediately as unverified doctor (private practice works)
4. Click "Upload License" → submit registration number + license PDF → status becomes `pending_verification`
5. Login as admin → `GET /admin/verifications/pending` → see pending doctor
6. Click "Approve" → doctor becomes `verified`
7. Logout, login as the verified doctor → profile shows "Verified Practice" badge
8. (Alt: Click "Login with Google" to use OAuth flow)

## 2. Patient Timeline + Versioning (45s)
1. Click any patient → Timeline view loads
2. Show version chain with dates and summaries
3. Click a specific version → state displayed
4. Click "Diff" between two versions → changes highlighted
5. Make an inline edit → new version created (show in sidebar)
6. Click "Revert" → version rolled back

## 3. AI Chat + Agent (45s)
1. Go to Chat page (`/chat`)
2. Type: "What is this patient's BP trend?"
3. Show SSE streaming: Router → Plan → Execute → Synthesize → Respond
4. Click a citation chip `[v3 · Jan 15]` → jumps to that version
5. Type: "Generate a prescription for Metformin 500mg"
6. Show AI-assisted prescription created

## 4. Document Parsing + OCR (30s)
1. Go to Scratchpad (`/scratchpad`)
2. Upload a prescription PDF/image
3. Show: parsing → schema alignment → extracted fields (Nanonets-OCR2 for handwritten)
4. Click "Save to Patient" → document linked to patient

## 5. Image Registration + Comparison (45s)
1. Go to a patient → Images tab
2. Upload a wound photo
3. Upload a follow-up photo
4. Click "Compare" → 3-panel view (Previous/Current/Overlay)
5. Drag opacity slider → overlay blends
6. Show metrics: area change %, edge convergence, color shift
7. Click "Generate Clinical Summary" → Maverick summary appears
8. Click "Save to Record" → summary saved

## 6. Prescriptions / Invoices / Certificates (30s)
1. Go to Prescription Box → add medications table
2. Generate PDF → show preview with clinic letterhead + watermark
3. Go to Invoices → add line items with auto-calculate
4. Generate Invoice PDF with QR code
5. Go to Certificates → select type → generate with verification code

## 7. Calendar + Scheduling (45s)
1. Go to Calendar (`/calendar`)
2. Show weekly view with appointment blocks (colored by status)
3. Click a free slot → booking modal
4. Schedule appointment → confirmed
5. Click existing appointment → detail modal
6. Reschedule → appointment moved
7. Cancel → two-step confirmation
8. Go to Settings → Calendar tab → modify working hours

## 8. Smart Scheduling + Voice (30s)
1. Show "Find Optimal Window" → suggests best slot based on patient preference
2. Demo "Doctor Off" scenario → affected appointments listed
3. Smart Rearrange → proposed moves with accept/reject

## 9. Patient Portal (30s)
1. Open `/patient/login` in new tab/incognito
2. Enter phone → receive OTP → SHA256 phone_hash lookup → login (cross-tenant User)
3. Show Patient Dashboard with appointment count + notifications
4. Search for a doctor → Leaflet map with doctor locations (**only verified doctors shown**)
5. Click doctor → see profile with `verification_status` badge ("Verified Practice" / "Practice Account")
6. See available slots → book appointment (creates Patient row under that doctor with user_id)
7. Show Inbox with real-time notifications via WebSocket

## 10. Weekly Reports + Risk Alerts (30s)
1. Go to Weekly Report page
2. Select patient, choose layout (Executive/Clinical/Family-friendly)
3. Generate report → significance-scored sections
4. Show AI summary of the week
5. Show Risk Alerts panel (Feature E) — trajectory drifts detected

## Total: ~7 minutes

---

## Tips for Smooth Demo
- Have test data pre-loaded (synthetic patients with 6+ visits each)
- Keep API keys functional (NVIDIA NIM, Groq)
- Open DevTools Network tab to show SSE streaming in Chat
- Pre-generate a PDF for faster display
- Use incognito window for patient portal demo
- Mute microphone if voice features are unstable
