import { create } from 'zustand'
import apiClient from '@/services/api'
import type { Doctor, Patient } from '@/types'

interface DoctorState {
  doctor: Doctor | null
  patients: Patient[]
  loading: boolean
  error: string | null

  fetchDoctor: () => Promise<void>
  fetchPatients: () => Promise<void>
  setDoctor: (d: Doctor) => void
}

export const useDoctorStore = create<DoctorState>((set) => ({
  doctor: null,
  patients: [],
  loading: false,
  error: null,

  fetchDoctor: async () => {
    try {
      const res = await apiClient.get('/auth/me')
      set({ doctor: res.data, error: null })
    } catch (e: any) {
      set({ error: e?.response?.data?.detail || 'Failed to fetch doctor' })
    }
  },

  fetchPatients: async () => {
    set({ loading: true, error: null })
    try {
      const res = await apiClient.get('/patients', { params: { limit: 200 } })
      set({ patients: res.data ?? [], loading: false })
    } catch (e: any) {
      set({ loading: false, error: e?.response?.data?.detail || 'Failed to fetch patients' })
    }
  },

  setDoctor: (d) => set({ doctor: d }),
}))
