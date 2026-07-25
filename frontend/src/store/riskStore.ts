import { create } from 'zustand'
import apiClient from '@/services/api'
import type { RiskAlert } from '@/types'

interface RiskStore {
  alerts: RiskAlert[]
  unacknowledgedCount: number
  loading: boolean
  error: string | null

  fetchAlerts: () => Promise<void>
  acknowledgeAlert: (alertId: string) => Promise<void>
  pushAlert: (alert: RiskAlert) => void
}

export const useRiskStore = create<RiskStore>((set, get) => ({
  alerts: [],
  unacknowledgedCount: 0,
  loading: false,
  error: null,

  fetchAlerts: async () => {
    set({ loading: true, error: null })
    try {
      const res = await apiClient.get('/risk-alerts')
      const rawAlerts = res.data ?? []
      // Map backend fields (message/detected_at/acknowledged) to frontend interface
      const alerts: RiskAlert[] = rawAlerts.map((a: any) => ({
        id: a.id,
        patient_id: a.patient_id,
        kind: a.kind,
        severity: a.severity,
        patient_name: a.patient_name,
        message: a.message,
        detected_at: a.detected_at,
        reason: a.message,
        triggered_at: a.detected_at,
        acknowledged_by: a.acknowledged ? 'true' : undefined,
      }))
      set({
        alerts,
        unacknowledgedCount: alerts.filter((a) => !a.acknowledged_by).length,
        loading: false,
      })
    } catch (e: any) {
      set({ loading: false, error: e?.response?.data?.detail || 'Failed to load risk alerts' })
    }
  },

  acknowledgeAlert: async (alertId) => {
    try {
      await apiClient.post(`/risk-alerts/${alertId}/acknowledge`)
      get().fetchAlerts()
    } catch (e: any) {
      console.error('acknowledgeAlert error:', e)
    }
  },

  pushAlert: (alert) => {
    set((s) => {
      const exists = s.alerts.some((a) => a.id === alert.id)
      if (exists) return s
      const updated = [alert, ...s.alerts]
      return {
        alerts: updated,
        unacknowledgedCount: updated.filter((a) => !a.acknowledged_by).length,
      }
    })
  },
}))
