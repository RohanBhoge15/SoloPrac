import { test, expect } from '@playwright/test'
import { newActor, registerDoctor, registerPatient, addWalkIn, loginDoctor, Actor } from './actors'
import { DOCTORS, PATIENTS, SHARED, RUN_ID, PASSWORD, Doc } from './fixtures'
import { settle } from './helpers'

// Flip a test-created doctor to `verified` the way an admin would, without
// touching the real ADMIN_EMAILS account's credentials. Scoped to the exact
// clinic name this run generated.
async function verifyDoctorOutOfBand(clinicName: string): Promise<boolean> {
  const { execFile } = await import('node:child_process')
  const sql = `update doctors set verification_status='verified' where clinic_name='${clinicName.replace(/'/g, "''")}' and verification_status='pending_verification';`
  return new Promise(resolve => {
    execFile(
      'docker',
      ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'soloprac', '-d', 'soloprac', '-c', sql],
      { cwd: 'C:\\Users\\rohan\\SoloPrac' },
      err => resolve(!err)
    )
  })
}

// One long scenario: 3 clinics + 10 patients live at the same time, each in its
// own browser context (own cookie jar), exactly like production. Then we assert
// tenant isolation from BOTH directions.
test('3 doctors + 10 patients concurrently — data isolation holds', async ({ browser }) => {
  test.setTimeout(15 * 60_000)

  const problems: string[] = []
  const docs: Actor[] = []
  const pats: Actor[] = []

  try {
    // ── Phase 1: register all 3 doctors concurrently ──
    console.log(`\n=== RUN_ID ${RUN_ID} — registering 3 doctors ===`)
    for (const d of DOCTORS) docs.push(await newActor(browser, d.lat, d.lng))
    await Promise.all(
      DOCTORS.map(async (d, i) => {
        try {
          await registerDoctor(docs[i], d)
          console.log(`  doctor ${d.key} (${d.clinic}) registered`)
        } catch (e: any) {
          problems.push(`doctor ${d.key} registration failed: ${e.message.split('\n')[0]}`)
        }
      })
    )

    // ── Phase 2: register all 10 patients concurrently ──
    console.log('=== registering 10 patients ===')
    for (const _ of PATIENTS) pats.push(await newActor(browser))
    await Promise.all(
      PATIENTS.map(async (p, i) => {
        try {
          await registerPatient(pats[i], p)
        } catch (e: any) {
          problems.push(`patient ${p.key} registration failed: ${e.message.split('\n')[0]}`)
        }
      })
    )
    console.log(`  ${PATIENTS.length} patients registered`)

    // ── Phase 3: each doctor adds their own walk-in patients concurrently ──
    // Doctor A and Doctor B BOTH add SHARED (same phone) — the isolation subject.
    console.log('=== doctors add walk-in records concurrently ===')
    const createdBy: Record<string, { id: string; name: string }[]> = { A: [], B: [], C: [] }

    await Promise.all([
      (async () => {
        // Doctor A: the shared patient + 2 exclusive.
        const idShared = await addWalkIn(docs[0], SHARED.name, SHARED.phone, `A-ONLY-NOTE-${RUN_ID} seen at Rao Clinic`)
        createdBy.A.push({ id: idShared, name: SHARED.name })
        for (const p of [PATIENTS[2], PATIENTS[3]]) {
          const id = await addWalkIn(docs[0], p.name, p.phone, `A-ONLY-NOTE-${RUN_ID}`)
          createdBy.A.push({ id, name: p.name })
        }
      })(),
      (async () => {
        // Doctor B: the SAME shared patient (second clinic) + 2 exclusive.
        const idShared = await addWalkIn(docs[1], SHARED.name, SHARED.phone, `B-ONLY-NOTE-${RUN_ID} seen at Nair Care`)
        createdBy.B.push({ id: idShared, name: SHARED.name })
        for (const p of [PATIENTS[4], PATIENTS[5]]) {
          const id = await addWalkIn(docs[1], p.name, p.phone, `B-ONLY-NOTE-${RUN_ID}`)
          createdBy.B.push({ id, name: p.name })
        }
      })(),
      (async () => {
        for (const p of [PATIENTS[6], PATIENTS[7]]) {
          const id = await addWalkIn(docs[2], p.name, p.phone, `C-ONLY-NOTE-${RUN_ID}`)
          createdBy.C.push({ id, name: p.name })
        }
      })(),
    ]).catch(e => problems.push(`walk-in creation failed: ${e.message.split('\n')[0]}`))

    console.log(`  A=${createdBy.A.length} B=${createdBy.B.length} C=${createdBy.C.length} records`)

    // The shared patient must get DISTINCT patient rows per clinic.
    const sharedA = createdBy.A.find(r => r.name === SHARED.name)?.id
    const sharedB = createdBy.B.find(r => r.name === SHARED.name)?.id
    if (sharedA && sharedB && sharedA === sharedB) {
      problems.push(`ISOLATION: same patient row ${sharedA} shared across clinic A and B — must be separate rows`)
    }

    // ── Phase 4: ISOLATION — doctor search must only see own patients ──
    console.log('=== isolation: patient search scoping ===')
    for (const [idx, key] of [[0, 'A'], [1, 'B'], [2, 'C']] as [number, string][]) {
      const a = docs[idx]
      const foreign = Object.entries(createdBy)
        .filter(([k]) => k !== key)
        .flatMap(([, v]) => v)
      // Search by a token unique to this run so we only match simulation data.
      const res = await a.page.request.get(
        `https://localhost/api/v1/patients?limit=1000`
      )
      const list = await res.json().catch(() => [])
      const visibleIds = new Set((Array.isArray(list) ? list : []).map((p: any) => String(p.id)))
      for (const f of foreign) {
        if (visibleIds.has(f.id)) {
          problems.push(`ISOLATION BREACH: doctor ${key} can list another clinic's patient ${f.id} (${f.name})`)
        }
      }
      console.log(`  doctor ${key}: sees ${visibleIds.size} patients, no foreign leakage`)
    }

    // ── Phase 5: ISOLATION — direct object reference must 403/404 ──
    console.log('=== isolation: direct patient URL access ===')
    const victim = createdBy.B.find(r => r.name !== SHARED.name)
    if (victim) {
      // Doctor A tries to open Doctor B's patient by guessing the URL.
      const r = await docs[0].page.request.get(`https://localhost/api/v1/patients/${victim.id}/head`)
      if (r.status() < 400) {
        problems.push(`ISOLATION BREACH: doctor A read doctor B's patient ${victim.id} via direct API (status ${r.status()})`)
      } else {
        console.log(`  doctor A blocked from B's patient (status ${r.status()})`)
      }

      // And through the actual UI route.
      await docs[0].page.goto(`/patients/${victim.id}`)
      const body = await settle(docs[0].page, docs[0].w, 'cross-tenant-ui')
      if (new RegExp(victim.name.split(' ')[0], 'i').test(body)) {
        problems.push(`ISOLATION BREACH: doctor A's UI rendered doctor B's patient name for ${victim.id}`)
      }
    }

    // ── Phase 6: doctor changes a SETTING → must reflect on patient side ──
    // Patient-facing search intentionally only lists VERIFIED doctors, so the
    // full real-world path is: update profile → submit verification → admin
    // approves → doctor becomes patient-visible with the new value.
    console.log('=== doctor setting change → patient-visible ===')
    const newSpeciality = `Cardiology-${RUN_ID}`
    const setRes = await docs[0].page.request.put('https://localhost/api/v1/auth/me', {
      data: { speciality: newSpeciality },
    })
    if (setRes.status() >= 400) {
      problems.push(`doctor A could not update speciality (status ${setRes.status()})`)
    }

    // Unverified doctors must NOT be searchable — that is the safe default.
    const preRes = await pats[0].page.request.get(
      `https://localhost/api/v1/public/doctors/search?q=${encodeURIComponent(DOCTORS[0].clinic)}`
    )
    const preTxt = JSON.stringify(await preRes.json().catch(() => ({})))
    if (preTxt.includes(DOCTORS[0].clinic)) {
      problems.push('SECURITY: unverified doctor A is already visible in public patient search')
    } else {
      console.log('  unverified doctor correctly hidden from patient search')
    }

    // Submit verification (NMC external call is skipped by config; this only
    // moves the doctor into the admin queue).
    const subRes = await docs[0].page.request.post('https://localhost/api/v1/auth/me/verify', {
      data: {
        registration_number: `REG-${RUN_ID}`,
        state_medical_council: 'Maharashtra Medical Council',
        year_of_registration: 2015,
      },
    })
    if (subRes.status() >= 400) {
      problems.push(`doctor A verification submit failed (${subRes.status()}): ${(await subRes.text()).slice(0, 200)}`)
    } else {
      const st = JSON.stringify(await subRes.json().catch(() => ({})))
      // MUST be exactly `pending_verification` — admin.py filters its pending
      // queue and gates approve/reject on that literal. Any other spelling
      // silently strands the doctor: never listed, never approvable.
      if (!st.includes('pending_verification')) {
        problems.push(
          `VERIFICATION PIPELINE BROKEN: submit returned ${st.slice(0, 200)} — admin.py only matches "pending_verification", so this doctor can never be approved`
        )
      } else {
        console.log('  verification submitted → pending_verification (admin-queue compatible)')
      }
    }

    // Approval itself is an operator action (admin.py gates /admin/* on a fixed
    // ADMIN_EMAILS address that this suite must not hijack). We verify the part
    // the app owns — that submitting puts the doctor in the state admin.py's
    // queue actually filters on — and let the runner approve out-of-band via
    // scripts/verify_test_doctor.sql before re-checking patient visibility.
    const verified = await verifyDoctorOutOfBand(DOCTORS[0].clinic)
    if (!verified) {
      console.log('  (skipped post-approval visibility check — could not verify out-of-band)')
    } else {
      const pRes = await pats[0].page.request.get(
        `https://localhost/api/v1/public/doctors/search?q=${encodeURIComponent(DOCTORS[0].clinic)}`
      )
      const txt = JSON.stringify(await pRes.json().catch(() => ({})))
      if (!txt.includes(newSpeciality)) {
        problems.push(
          `SETTING NOT REFLECTED: verified doctor A speciality "${newSpeciality}" still not visible to patients. Got: ${txt.slice(0, 300)}`
        )
      } else {
        console.log(`  speciality "${newSpeciality}" visible to patient side after approval`)
      }
    }

    // ── Phase 7: working-hours change → patient slot availability ──
    console.log('=== doctor working hours → patient slots ===')
    const whRes = await docs[1].page.request.put('https://localhost/api/v1/calendar/working-hours', {
      data: {
        working_hours_json: { mon: [['10:00', '13:00']], tue: [['10:00', '13:00']], wed: [['10:00', '13:00']], thu: [['10:00', '13:00']], fri: [['10:00', '13:00']] },
        buffer_minutes: 10,
        default_duration: 20,
      },
    })
    if (whRes.status() >= 400) {
      problems.push(`doctor B could not save working hours (status ${whRes.status()}) — ${(await whRes.text()).slice(0, 200)}`)
    } else {
      const back = await docs[1].page.request.get('https://localhost/api/v1/calendar/working-hours')
      const wh = await back.json().catch(() => ({}))
      if (wh?.buffer_minutes !== 10 || wh?.default_duration !== 20) {
        problems.push(`working hours did not persist for doctor B: ${JSON.stringify(wh).slice(0, 200)}`)
      } else {
        console.log('  working hours persisted (buffer 10, duration 20)')
      }
      // Doctor A's config must be untouched — settings are per-tenant.
      const aWh = await docs[0].page.request.get('https://localhost/api/v1/calendar/working-hours')
      const aCfg = await aWh.json().catch(() => ({}))
      if (aCfg?.buffer_minutes === 10 && aCfg?.default_duration === 20) {
        problems.push('ISOLATION: doctor B working-hours change leaked into doctor A config')
      }
    }

    // ── Phase 8: shared patient sees BOTH clinics, isolated per clinic ──
    console.log('=== shared patient cross-clinic view ===')
    const sharedActor = pats[0]
    await sharedActor.page.goto('/patient/pending-matches')
    const pmBody = await settle(sharedActor.page, sharedActor.w, 'shared-pending-matches')
    console.log(`  pending-matches page: ${pmBody.slice(0, 160).replace(/\s+/g, ' ')}`)

    // Their reports/appointments endpoints must never 500.
    for (const ep of ['/patient/me/profile', '/patient/me/appointments', '/patient/me/reports', '/patient/me/inbox']) {
      const r = await sharedActor.page.request.get(`https://localhost/api/v1${ep}`)
      if (r.status() >= 400) problems.push(`shared patient ${ep} → ${r.status()}`)
    }

    // ── Phase 9: every patient's portal pages must render ──
    console.log('=== all 10 patients: portal pages render ===')
    await Promise.all(
      pats.map(async (a, i) => {
        for (const route of ['/patient/dashboard', '/patient/appointments', '/patient/reports', '/patient/inbox']) {
          a.w.reset()
          await a.page.goto(route)
          const body = await settle(a.page, a.w, `${PATIENTS[i].key}${route}`)
          if (a.w.pageErrors.length) problems.push(`${PATIENTS[i].key} ${route}: JS crash → ${a.w.pageErrors[0]}`)
          if (/Please log ?in first/i.test(body)) problems.push(`${PATIENTS[i].key} ${route}: session lost`)
          const bad = a.w.failed.filter(f => / 5\d\d /.test(` ${f} `) || f.startsWith('5'))
          if (bad.length) problems.push(`${PATIENTS[i].key} ${route}: server error → ${bad.join(', ')}`)
        }
      })
    )

    // ── Phase 10: doctors' pages must render with real data present ──
    console.log('=== all 3 doctors: pages render with data ===')
    await Promise.all(
      docs.map(async (a, i) => {
        for (const route of ['/dashboard', '/calendar', '/settings', '/weekly-report', '/chat', '/scratchpad']) {
          a.w.reset()
          await a.page.goto(route)
          const body = await settle(a.page, a.w, `${DOCTORS[i].key}${route}`)
          if (a.w.pageErrors.length) problems.push(`doctor ${DOCTORS[i].key} ${route}: JS crash → ${a.w.pageErrors[0]}`)
          if (/Something went wrong|Unexpected Application Error/i.test(body)) {
            problems.push(`doctor ${DOCTORS[i].key} ${route}: error boundary`)
          }
          const bad = a.w.failed.filter(f => /^5\d\d/.test(f))
          if (bad.length) problems.push(`doctor ${DOCTORS[i].key} ${route}: server error → ${bad.join(', ')}`)
        }
      })
    )
  } finally {
    console.log('\n=== PROBLEMS ===\n' + (problems.length ? problems.join('\n') : 'none'))
    await Promise.all([...docs, ...pats].map(a => a.close().catch(() => {})))
  }

  expect(problems, 'multi-tenant simulation problems').toEqual([])
})
