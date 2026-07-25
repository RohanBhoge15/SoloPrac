import { create } from 'zustand'
import apiClient from '@/services/api'

interface SearchResult {
  id: string
  name: string
  age: number
  gender: string
  phone?: string
  email?: string
  last_visit?: string
  head_version_id?: string
}

interface SearchStore {
  results: SearchResult[]
  loading: boolean
  query: string

  search: (q: string) => Promise<void>
  clear: () => void
}

export const useSearchStore = create<SearchStore>((set) => ({
  results: [],
  loading: false,
  query: '',

  search: async (q) => {
    set({ loading: true, query: q })
    try {
      const res = await apiClient.get('/patients/search', { params: { q, limit: 20 } })
      set({ results: res.data ?? [], loading: false })
    } catch (e) {
      set({ results: [], loading: false })
    }
  },

  clear: () => set({ results: [], query: '', loading: false }),
}))