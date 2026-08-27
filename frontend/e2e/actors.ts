import type { Browser, BrowserContext, Page } from '@playwright/test'
import { Doc, Pat, PASSWORD } from './fixtures'
import { watch, Watcher } from './helpers'

export type Actor = {
  ctx: BrowserContext
  page: Page
  w: Watcher
  close: () => Promise<void>
}

// Each actor gets its OWN browser context = its own cookie jar. This is what
// makes a real concurrent multi-tenant simulation possible: doctor A, doctor B
// and 10 patients are all logged in simultaneously, exactly as in production.
export async function newActor(browser: Browser, lat = 19.076, lng = 72.8777): Promise<Actor> {
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    permissions: ['geolocation'],
    geolocation: { latitude: lat, longitude: lng },
    viewport: { width: 1440, height: 900 },
  })
  const page = await ctx.newPage()
  const w = watch(page)
  return { ctx, page, w, close: () => ctx.close() }
}

export async function registerDoctor(a: Actor, d: Doc) {
  const { page } = a
  await page.goto('/register')
  await page.waitForLoadState('networkidle')

  // Fields have no ids — target by placeholder, which is unique per field.
  await page.getByPlaceholder('Dr. Priya Sharma').fill(d.name)
  await page.getByPlaceholder('doctor@clinic.com').fill(d.email)
  await page.getByPlaceholder('9876543210').fill(d.phone)
  await page.getByPlaceholder('Sharma Clinic').fill(d.clinic)
  await page.getByPlaceholder('123 MG Road, Mumbai 400001').fill(d.address)
  await page.getByPlaceholder('Min 8 characters').fill(PASSWORD)
  await page.getByPlaceholder('Re-enter password').fill(PASSWORD)

  // Geo-pin is REQUIRED by the form. Use the "use my location" crosshair, which
  // resolves from the context geolocation we granted above — deterministic,
  // unlike clicking raw map pixels.
  await page.locator('button[title="Use my current location"]').click()
  await page.locator('text=/✓ Pinned at/').waitFor({ state: 'visible', timeout: 20_000 })

  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL(/dashboard/, { timeout: 45_000 })
  await page.waitForLoadState('networkidle')
}

export async function loginDoctor(a: Actor, d: Doc) {
  const { page } = a
  await page.goto('/login')
  await page.getByPlaceholder('doctor@clinic.com').fill(d.email)
  await page.getByPlaceholder('••••••••').fill(PASSWORD)
  await page.getByRole('button', { name: /^sign in$/i }).click()
  await page.waitForURL(/dashboard/, { timeout: 45_000 })
  await page.waitForLoadState('networkidle')
}

export async function registerPatient(a: Actor, p: Pat) {
  const { page } = a
  await page.goto('/patient/register')
  await page.waitForLoadState('networkidle')

  await page.locator('#name').fill(p.name)
  await page.locator('#email').fill(p.email)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#confirmPassword').fill(PASSWORD)
  await page.locator('#phone').fill(p.phone)
  await page.locator('#dob').fill(p.dob)
  await page.locator('#gender').selectOption(p.gender)
  await page.locator('#address').fill(p.address)

  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL(/patient\/dashboard/, { timeout: 45_000 })
  await page.waitForLoadState('networkidle')
}

export async function loginPatient(a: Actor, p: Pat) {
  const { page } = a
  await page.goto('/patient/login')
  await page.locator('#email').fill(p.email)
  await page.locator('#password').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL(/patient\/dashboard/, { timeout: 45_000 })
  await page.waitForLoadState('networkidle')
}

// Doctor adds a walk-in patient. Returns the patient_id from the resulting URL.
export async function addWalkIn(a: Actor, name: string, phone: string, notes = '') {
  const { page } = a
  await page.goto('/patients/new')
  await page.waitForLoadState('networkidle')
  await page.locator('#name').fill(name)
  await page.locator('#phone').fill(phone)
  if (notes) await page.locator('#notes').fill(notes)
  await page.getByRole('button', { name: /add patient/i }).click()
  await page.waitForURL(/\/patients\/[0-9a-f-]{36}/, { timeout: 45_000 })
  await page.waitForLoadState('networkidle')
  const m = page.url().match(/\/patients\/([0-9a-f-]{36})/)
  return m![1]
}
