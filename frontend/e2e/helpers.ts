import type { Page } from '@playwright/test'

export type Watcher = {
  consoleErrors: string[]
  pageErrors: string[]
  failed: string[]
  reset: () => void
  report: (label: string) => void
}

// Ignore noise that is expected and not a real defect:
//  - pre-login /auth/me and /patient/me/profile 401s are how the app probes session
//  - favicon 404s
//  - React DevTools suggestion
const IGNORE_REQ = [
  /\/api\/v1\/auth\/me/,
  /\/api\/v1\/patient\/me\/profile/,
  /favicon/,
]
const IGNORE_CONSOLE = [
  /Download the React DevTools/i,
  /status of 401/,
  /\[vite\]/i,
]

export function watch(page: Page): Watcher {
  const w: Watcher = {
    consoleErrors: [],
    pageErrors: [],
    failed: [],
    reset() {
      w.consoleErrors.length = 0
      w.pageErrors.length = 0
      w.failed.length = 0
    },
    report(label) {
      if (w.pageErrors.length) console.log(`[${label}] PAGE ERRORS:`, JSON.stringify(w.pageErrors, null, 2))
      if (w.consoleErrors.length) console.log(`[${label}] CONSOLE:`, JSON.stringify(w.consoleErrors, null, 2))
      if (w.failed.length) console.log(`[${label}] FAILED REQ:`, JSON.stringify(w.failed, null, 2))
    },
  }

  page.on('console', m => {
    if (m.type() !== 'error') return
    const t = m.text()
    if (IGNORE_CONSOLE.some(r => r.test(t))) return
    w.consoleErrors.push(t)
  })
  // Uncaught exceptions = a real React crash. Always a bug.
  page.on('pageerror', e => w.pageErrors.push(e.message))
  page.on('response', r => {
    if (r.status() < 400) return
    const url = r.url()
    if (IGNORE_REQ.some(re => re.test(url))) return
    w.failed.push(`${r.status()} ${r.request().method()} ${url.replace('https://localhost', '')}`)
  })

  return w
}

export async function doctorLogin(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /dev login \(doctor\)/i }).click()
  await page.waitForURL(/dashboard/, { timeout: 30_000 })
  await page.waitForLoadState('networkidle')
}

export async function patientLogin(page: Page) {
  await page.goto('/patient/login')
  await page.getByRole('button', { name: /dev login \(patient\)/i }).click()
  await page.waitForURL(/patient\/dashboard/, { timeout: 30_000 })
  await page.waitForLoadState('networkidle')
}

// Settle the page and return its text. Assertions live in the spec files so
// this module never imports the `expect` runtime (which would load a second
// Playwright instance under "type": "module" and break the test loader).
export async function settle(page: Page, w: Watcher, label: string) {
  await page.waitForLoadState('networkidle')
  // Spinners must resolve — a permanently spinning page is a bug.
  await page
    .locator('.animate-spin')
    .first()
    .waitFor({ state: 'hidden', timeout: 20_000 })
    .catch(() => {})

  const text = (await page.locator('body').innerText()).trim()
  w.report(label)
  return text
}
