import { test, expect } from '@playwright/test'

// Collect every console error + failed request so we catch the class of bug
// that curl cannot see: frontend JS crashes and 4xx/5xx from the real browser.
test('smoke: landing loads, dev-login reaches dashboard', async ({ page }) => {
  const consoleErrors: string[] = []
  const failedRequests: string[] = []

  page.on('console', m => {
    if (m.type() === 'error') consoleErrors.push(m.text())
  })
  page.on('response', r => {
    if (r.status() >= 400) failedRequests.push(`${r.status()} ${r.request().method()} ${r.url()}`)
  })

  await page.goto('/')
  await page.waitForLoadState('networkidle')
  console.log('--- LANDING URL:', page.url())
  console.log('--- LANDING TITLE:', await page.title())

  await page.goto('/login')
  await page.waitForLoadState('networkidle')

  const devBtn = page.getByRole('button', { name: /dev login \(doctor\)/i })
  console.log('--- DEV LOGIN BUTTON VISIBLE:', await devBtn.isVisible().catch(() => false))

  await devBtn.click()
  await page.waitForURL(/dashboard/, { timeout: 30_000 }).catch(() => {})
  await page.waitForLoadState('networkidle')

  console.log('--- POST-LOGIN URL:', page.url())
  console.log('--- CONSOLE ERRORS:', JSON.stringify(consoleErrors, null, 2))
  console.log('--- FAILED REQUESTS:', JSON.stringify(failedRequests, null, 2))

  expect(page.url()).toContain('/dashboard')
})
