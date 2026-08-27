import { test, expect } from '@playwright/test'
import { newActor, registerDoctor, loginDoctor, registerPatient, loginPatient } from './actors'
import { DOCTORS, PATIENTS } from './fixtures'

test('real doctor signup → logout → login again works', async ({ browser }) => {
  const d = DOCTORS[0]
  const a = await newActor(browser, d.lat, d.lng)
  try {
    await registerDoctor(a, d)
    expect(a.page.url()).toContain('/dashboard')
    a.w.report('doctor-register')
    expect(a.w.pageErrors).toEqual([])

    // Log in a SECOND time — this is what caught the token_jti collision.
    await a.ctx.clearCookies()
    await loginDoctor(a, d)
    expect(a.page.url()).toContain('/dashboard')

    // And a THIRD, to be sure session rows accumulate cleanly.
    await a.ctx.clearCookies()
    await loginDoctor(a, d)
    expect(a.page.url()).toContain('/dashboard')
    a.w.report('doctor-relogin')
    expect(a.w.failed, 'repeat doctor login must not 500').toEqual([])
  } finally {
    await a.close()
  }
})

test('real patient signup → logout → login again works', async ({ browser }) => {
  const p = PATIENTS[1]
  const a = await newActor(browser)
  try {
    await registerPatient(a, p)
    expect(a.page.url()).toContain('/patient/dashboard')
    a.w.report('patient-register')
    expect(a.w.pageErrors).toEqual([])

    await a.ctx.clearCookies()
    await loginPatient(a, p)
    expect(a.page.url()).toContain('/patient/dashboard')
    a.w.report('patient-relogin')
    expect(a.w.failed, 'repeat patient login must not fail').toEqual([])
  } finally {
    await a.close()
  }
})
