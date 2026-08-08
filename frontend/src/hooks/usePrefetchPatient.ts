/**
 * P2.20 — Router prefetch on hover.
 *
 * When the doctor hovers a patient row for >120ms, we (a) preload the lazy
 * PatientDetail chunk (P2.19) and (b) prewarm the API cache with head +
 * documents. By the time the click fires and React finishes routing, the
 * response has usually already landed — so the detail page paints in a single
 * frame instead of showing the "Loading…" spinner.
 *
 * Cached-fetch dedup: each patientId is only fetched once per session.
 */

import { useCallback, useRef } from 'react'
import apiClient from '@/services/api'

const HOVER_DELAY_MS = 120

// Module-level dedup so multiple lists that hover the same patient don't
// re-fire the same request.
const prefetched = new Set<string>()

// Kick off the PatientDetail chunk download exactly once, on the first prefetch
// anywhere in the app. It's a static import call so the browser dedups its
// own network request even if we call it multiple times, but skipping it
// keeps devtools clean.
let chunkPrefetched = false
function prefetchChunk() {
  if (chunkPrefetched) return
  chunkPrefetched = true
  // Vite emits a link[rel=modulepreload] for this on the first eval.
  import('@/pages/PatientDetail').catch(() => {
    chunkPrefetched = false // retry next hover
  })
}

async function prefetchPatientData(patientId: string) {
  if (prefetched.has(patientId)) return
  prefetched.add(patientId)
  // Fire the two heaviest reads in parallel; failures are silent (we're just
  // warming caches, not user-facing).
  await Promise.all([
    apiClient.get(`/patients/${patientId}/head`).catch(() => null),
    apiClient.get(`/patients/${patientId}/documents`).catch(() => null),
    apiClient.get(`/patients/${patientId}/timeline`, { params: { limit: 200 } }).catch(() => null),
  ])
}

/**
 * Returns handlers to spread onto a hoverable element (row / card):
 *
 *   const prefetch = usePrefetchPatient()
 *   <div {...prefetch(patient.id)} onClick={...}>...</div>
 */
export function usePrefetchPatient() {
  const timers = useRef<Record<string, number>>({})

  return useCallback((patientId: string | undefined) => {
    if (!patientId) return {}
    return {
      onMouseEnter: () => {
        // Debounce: skip prefetch on quick fly-over.
        window.clearTimeout(timers.current[patientId])
        timers.current[patientId] = window.setTimeout(() => {
          prefetchChunk()
          void prefetchPatientData(patientId)
        }, HOVER_DELAY_MS)
      },
      onMouseLeave: () => {
        window.clearTimeout(timers.current[patientId])
        delete timers.current[patientId]
      },
      // Also fire on focus for keyboard nav.
      onFocus: () => {
        prefetchChunk()
        void prefetchPatientData(patientId)
      },
    }
  }, [])
}
