import { test, expect } from '@playwright/test'
import { watch, doctorLogin, patientLogin, settle } from './helpers'

const DOCTOR_ROUTES = [
  { path: '/dashboard', expect: /Dashboard/ },
  { path: '/calendar', expect: /Calendar|Appointments/i },
  { path: '/scratchpad', expect: /Scratchpad|Paste|note/i },
  { path: '/chat', expect: /Assistant|Chat/i },
  { path: '/settings', expect: /Settings|Profile/i },
  { path: '/weekly-report', expect: /Report/i },
  { path: '/patients/new', expect: /Add new patient/i },
]

const PATIENT_ROUTES = [
  { path: '/patient/dashboard', expect: /My Dashboard/i },
  { path: '/patient/search', expect: /Find a Doctor/i },
  { path: '/patient/appointments', expect: /My Appointments/i },
  { path: '/patient/inbox', expect: /Inbox|notification/i },
  { path: '/patient/reports', expect: /My Reports/i },
  { path: '/patient/profile', expect: /Profile/i },
  // UI copy was renamed to "Records to review" (demo-polish sweep); accept both
  // the old and new headers so the assertion doesn't depend on wording.
  { path: '/patient/pending-matches', expect: /Records to review|match|pending/i },
]

test.describe('doctor portal — every route renders', () => {
  test('all doctor routes load without crashing', async ({ page }) => {
    const w = watch(page)
    await doctorLogin(page)

    const problems: string[] = []

    for (const r of DOCTOR_ROUTES) {
      w.reset()
      await page.goto(r.path)
      let body = ''
      try {
        body = await settle(page, w, r.path)
      } catch (e: any) {
        problems.push(`${r.path}: CRASH — ${e.message.split('\n')[0]}`)
        continue
      }
      if (!r.expect.test(body)) {
        problems.push(`${r.path}: expected content ${r.expect} not found. Got: ${body.slice(0, 200).replace(/\s+/g, ' ')}`)
      }
      if (w.failed.length) problems.push(`${r.path}: failed requests → ${w.failed.join(' | ')}`)
      if (w.consoleErrors.length) problems.push(`${r.path}: console → ${w.consoleErrors.join(' | ')}`)
      // Never leave the user staring at an error boundary.
      if (/Something went wrong|Unexpected Application Error/i.test(body)) {
        problems.push(`${r.path}: rendered an error boundary`)
      }
    }

    console.log('\n=== DOCTOR ROUTE PROBLEMS ===\n' + (problems.join('\n') || 'none'))
    expect(problems, 'doctor route problems').toEqual([])
  })
})

test.describe('patient portal — every route renders', () => {
  test('all patient routes load without crashing', async ({ page }) => {
    const w = watch(page)
    await patientLogin(page)

    const problems: string[] = []

    for (const r of PATIENT_ROUTES) {
      w.reset()
      await page.goto(r.path)
      let body = ''
      try {
        body = await settle(page, w, r.path)
      } catch (e: any) {
        problems.push(`${r.path}: CRASH — ${e.message.split('\n')[0]}`)
        continue
      }
      // "Please login first" means the portal lost its session mid-navigation.
      if (/Please log ?in first|Please log in to view/i.test(body)) {
        problems.push(`${r.path}: session lost — page says "please login" while authenticated`)
      }
      if (!r.expect.test(body)) {
        problems.push(`${r.path}: expected content ${r.expect} not found. Got: ${body.slice(0, 200).replace(/\s+/g, ' ')}`)
      }
      if (w.failed.length) problems.push(`${r.path}: failed requests → ${w.failed.join(' | ')}`)
      if (w.consoleErrors.length) problems.push(`${r.path}: console → ${w.consoleErrors.join(' | ')}`)
      if (/Something went wrong|Unexpected Application Error/i.test(body)) {
        problems.push(`${r.path}: rendered an error boundary`)
      }
    }

    console.log('\n=== PATIENT ROUTE PROBLEMS ===\n' + (problems.join('\n') || 'none'))
    expect(problems, 'patient route problems').toEqual([])
  })
})

test.describe('auth guards', () => {
  test('unauthenticated doctor routes redirect to /login', async ({ page }) => {
    const w = watch(page)
    await page.context().clearCookies()
    await page.goto('/dashboard')
    await page.waitForURL(/login/, { timeout: 20_000 })
    expect(page.url()).toContain('/login')
    w.report('guard-doctor')
  })

  test('unauthenticated patient routes redirect to /patient/login', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/patient/dashboard')
    await page.waitForURL(/patient\/login/, { timeout: 20_000 })
    expect(page.url()).toContain('/patient/login')
  })

  test('unknown route redirects to landing', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/this-route-does-not-exist')
    await page.waitForLoadState('networkidle')
    expect(page.url()).toMatch(/localhost\/(login)?$/)
  })
})
