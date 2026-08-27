import { create } from 'zustand'
import apiClient from '@/services/api'
import type { Patient, PatientVersion, PatientVersionDiff } from '@/types'

// Mirrors DemographicsPatch in backend/app/schemas.py:319. Used to decide
// whether a flat key like "phone" belongs under state_jsonb.demographics
// when applying an optimistic patch. Keep in sync with the backend schema.
const DEMOGRAPHIC_KEYS = new Set([
  'name', 'phone', 'email', 'dob', 'gender', 'address',
  'blood_group', 'allergies', 'known_conditions',
  'height_cm', 'weight_kg',
  'emergency_contact_name', 'emergency_contact_phone', 'insurance_info',
])

interface VersionNode {
  id: string
  version_number: number
  author: string
  edit_type: 'manual' | 'voice' | 'ocr' | 'ai_suggestion' | 'revert'
  summary: string
  tags: string[]
  clinical_significance: number
  timestamp: string
}

interface PatientStore {
  // list
  patients: Patient[]
  loading: boolean
  error: string | null

  // active patient detail
  activePatient: Patient | null
  activeHead: PatientVersion | null
  timeline: VersionNode[]
  timelineLoading: boolean
  headLoading: boolean
  diffData: PatientVersionDiff | null
  diffLoading: boolean

  fetchPatients: () => Promise<void>
  fetchHead: (patientId: string) => Promise<void>
  fetchTimeline: (patientId: string) => Promise<void>
  fetchDiff: (patientId: string, v1: number, v2: number) => Promise<void>
  patchFields: (patientId: string, fields: Record<string, unknown>, expectedVersion: number) => Promise<PatientVersion | null>
  revertToVersion: (patientId: string, versionNumber: number) => Promise<PatientVersion | null>
  setActivePatient: (p: Patient | null) => void
  clearActive: () => void
}

export const usePatientStore = create<PatientStore>((set, get) => ({
  patients: [],
  loading: false,
  error: null,

  activePatient: null,
  activeHead: null,
  timeline: [],
  timelineLoading: false,
  headLoading: false,
  diffData: null,
  diffLoading: false,

  fetchPatients: async () => {
    set({ loading: true, error: null })
    try {
      const res = await apiClient.get('/patients', { params: { limit: 1000 } })
      set({ patients: res.data ?? [], loading: false })
    } catch (e: any) {
      set({ loading: false, error: e?.response?.data?.detail || 'Failed to load patients' })
    }
  },

  fetchHead: async (patientId) => {
    set({ headLoading: true })
    try {
      const res = await apiClient.get(`/patients/${patientId}/head`)
      set({ activeHead: res.data, headLoading: false })
    } catch (e: any) {
      set({ headLoading: false })
      console.error('fetchHead error:', e)
    }
  },

  fetchTimeline: async (patientId) => {
    set({ timelineLoading: true })
    try {
      const res = await apiClient.get(`/patients/${patientId}/timeline`, { params: { limit: 200 } })
      const mapped: VersionNode[] = (res.data ?? []).map((v: any) => ({
        id: v.id,
        version_number: v.version_number,
        author: v.author,
        edit_type: v.edit_type,
        summary: v.summary ?? '',
        tags: v.tags ?? [],
        clinical_significance: v.clinical_significance ?? 0,
        timestamp: v.timestamp,
      }))
      set({ timeline: mapped, timelineLoading: false })
    } catch (e: any) {
      set({ timelineLoading: false })
      console.error('fetchTimeline error:', e)
    }
  },

  fetchDiff: async (patientId, v1, v2) => {
    set({ diffLoading: true, diffData: null })
    try {
      const res = await apiClient.get(`/patients/${patientId}/diff`, { params: { v1, v2 } })
      set({ diffData: res.data, diffLoading: false })
    } catch (e: any) {
      set({ diffLoading: false })
      console.error('fetchDiff error:', e)
    }
  },

  patchFields: async (patientId, fields, expectedVersion) => {
    // P2.18 — Optimistic update: apply the demographic/clinical patch to the
    // in-memory head immediately so the UI stops "waiting for network" — the
    // form clears and shows the new values before the round-trip finishes.
    // On failure we restore the snapshot; on success we merge server truth.
    const prevHead = get().activeHead
    if (prevHead) {
      const state = (prevHead.state_jsonb as any) ?? {}
      const nextState = { ...state }
      // Keys arrive in two shapes and BOTH must land in the same place:
      //   - dot paths ("demographics.name") from older callers
      //   - flat demographic keys ("name") from PatientDetail's quick-edit,
      //     which mirrors what the backend accepts (see patients.py — it
      //     wraps flat keys into `demographics` before validating).
      // Previously a flat "name" wrote nextState.name while the UI reads
      // state.demographics.name, so the optimistic edit was invisible and the
      // field appeared to revert until the refetch landed.
      for (const [rawPath, value] of Object.entries(fields)) {
        const path = !rawPath.includes('.') && DEMOGRAPHIC_KEYS.has(rawPath)
          ? `demographics.${rawPath}`
          : rawPath
        const parts = path.split('.')
        let cursor: any = nextState
        for (let i = 0; i < parts.length - 1; i++) {
          const k = parts[i]
          cursor[k] = { ...(cursor[k] ?? {}) }
          cursor = cursor[k]
        }
        cursor[parts[parts.length - 1]] = value
      }
      set({
        activeHead: {
          ...prevHead,
          state_jsonb: nextState,
          // Optimistically bump the version so the next edit's expected_version
          // is right if the user chains edits without waiting for a refetch.
          version_number: (prevHead.version_number ?? expectedVersion) + 1,
        } as PatientVersion,
      })
    }

    try {
      const res = await apiClient.patch(`/patients/${patientId}/fields`, fields, {
        params: { expected_version: expectedVersion },
      })
      // Refresh head + timeline in parallel so the store converges to server
      // truth quickly. Fire-and-forget — the optimistic state is good enough
      // to keep the UI responsive.
      Promise.all([
        get().fetchHead(patientId),
        get().fetchTimeline(patientId),
      ]).catch(() => {})
      return res.data
    } catch (e: any) {
      console.error('patchFields error:', e)
      // Roll back the optimistic mutation.
      if (prevHead) set({ activeHead: prevHead })
      return null
    }
  },

  revertToVersion: async (patientId, versionNumber) => {
    try {
      const res = await apiClient.post(`/patients/${patientId}/revert/${versionNumber}`)
      // P2.18 — parallelize the two follow-up fetches.
      Promise.all([
        get().fetchHead(patientId),
        get().fetchTimeline(patientId),
      ]).catch(() => {})
      return res.data
    } catch (e: any) {
      console.error('revertToVersion error:', e)
      return null
    }
  },

  setActivePatient: (p) => set({ activePatient: p }),

  clearActive: () =>
    set({
      activePatient: null,
      activeHead: null,
      timeline: [],
      diffData: null,
    }),
}))
