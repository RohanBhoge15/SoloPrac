import { create } from 'zustand'
import apiClient from '@/services/api'
import type { PrescriptionBox, Invoice, Certificate } from '@/types'

interface NotificationItem {
  id: string
  kind: string
  subject: string
  body: string
  read: boolean
  created_at: string
  meta?: Record<string, unknown>
}

interface AppointmentListItem {
  id: string
  patient_id: string
  patient_name: string
  start_at: string
  end_at: string
  reason?: string
  status: string
  source: string
}

interface NotificationStore {
  // doctor's appointments
  appointments: AppointmentListItem[]
  appointmentsLoading: boolean
  // notifications / inbox
  notifications: NotificationItem[]
  unreadCount: number
  notifLoading: boolean
  // patient reports
  reports: { prescriptions: PrescriptionBox[]; invoices: Invoice[]; certificates: Certificate[] }

  fetchAppointments: (dateFrom?: string, dateTo?: string) => Promise<void>
  fetchNotifications: () => Promise<void>
  markNotificationRead: (notifId: string) => Promise<void>
  pushNotification: (n: NotificationItem) => void
}

export const useNotificationStore = create<NotificationStore>((set, get) => ({
  appointments: [],
  appointmentsLoading: false,
  notifications: [],
  unreadCount: 0,
  notifLoading: false,
  reports: { prescriptions: [], invoices: [], certificates: [] },

  fetchAppointments: async (dateFrom, dateTo) => {
    set({ appointmentsLoading: true })
    try {
      const params: Record<string, string> = {}
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      const res = await apiClient.get('/calendar/appointments', { params })
      set({ appointments: res.data?.appointments ?? [], appointmentsLoading: false })
    } catch (e) {
      set({ appointmentsLoading: false })
    }
  },

  fetchNotifications: async () => {
    set({ notifLoading: true })
    try {
      const res = await apiClient.get(`/patient/me/inbox`, { params: { limit: 50 } })
      const items: NotificationItem[] = res.data ?? []
      set({
        notifications: items,
        unreadCount: items.filter((n) => !n.read).length,
        notifLoading: false,
      })
    } catch (e) {
      set({ notifLoading: false })
    }
  },

  markNotificationRead: async (notifId) => {
    try {
      await apiClient.patch(`/patient/me/inbox/${notifId}/read`)
      get().fetchNotifications()
    } catch (e) {
      console.error('markNotificationRead error:', e)
    }
  },

  pushNotification: (n) => {
    set((s) => {
      const exists = s.notifications.some((x) => x.id === n.id)
      if (exists) return s
      const updated = [n, ...s.notifications]
      return {
        notifications: updated,
        unreadCount: updated.filter((x) => !x.read).length,
      }
    })
  },
}))