import { create } from 'zustand'
import apiClient from '@/services/api'
import type { Patient, PatientVersion, PatientVersionDiff } from '@/types'

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
      const res = await apiClient.get('/patients', { params: { limit: 500 } })
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
    try {
      const res = await apiClient.patch(`/patients/${patientId}/fields`, fields, {
        params: { expected_version: expectedVersion },
      })
      // refresh head after patch
      get().fetchHead(patientId)
      get().fetchTimeline(patientId)
      return res.data
    } catch (e: any) {
      console.error('patchFields error:', e)
      return null
    }
  },

  revertToVersion: async (patientId, versionNumber) => {
    try {
      const res = await apiClient.post(`/patients/${patientId}/revert/${versionNumber}`)
      get().fetchHead(patientId)
      get().fetchTimeline(patientId)
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
