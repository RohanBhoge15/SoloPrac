import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { usePatientWebSocket } from '@/hooks/useWebSocket'
import { CalendarDays, Loader2, X, CalendarClock } from 'lucide-react'

function cn(...classes: any[]) { return classes.filter(Boolean).join(' ') }

const statusColors: Record<string, string> = {
  scheduled: 'bg-yellow-100 text-yellow-800',
  done: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
}
function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

export function PatientAppointments() {
  const [appointments, setAppointments] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [patientId, setPatientId] = useState<string>('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [rescheduleFor, setRescheduleFor] = useState<any | null>(null)
  const [slots, setSlots] = useState<any[]>([])
  const [slotsLoading, setSlotsLoading] = useState(false)

  const { lastEvent } = usePatientWebSocket(patientId || null)

  const load = useCallback(async () => {
    if (!patientId) return
    try {
      const r = await apiClient.get('/patient/me/appointments')
      setAppointments(r.data || [])
    } catch {
      /* keep previous list on transient error */
    } finally {
      setLoading(false)
    }
  }, [patientId])

  useEffect(() => {
    apiClient
      .get('/patient/me/profile')
      .then((res) => { if (res.data?.user_id) setPatientId(res.data.user_id) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  // Live refresh when the doctor cancels/reschedules this patient's appointment
  // (incoming patient notification) — no manual refresh needed.
  useEffect(() => {
    if (lastEvent && (lastEvent as any).type === 'notification') {
      load()
    }
  }, [lastEvent, load])

  const cancel = async (id: string) => {
    if (!window.confirm('Cancel this appointment?')) return
    setBusyId(id)
    try {
      await apiClient.post(`/patient/me/appointments/${id}/cancel`, {})
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to cancel appointment')
    } finally {
      setBusyId(null)
    }
  }

  const openReschedule = async (apt: any) => {
    setRescheduleFor(apt)
    setSlotsLoading(true)
    setSlots([])
    try {
      const today = new Date()
      const to = new Date()
      to.setDate(to.getDate() + 14)
      const df = today.toISOString().slice(0, 10)
      const dt = to.toISOString().slice(0, 10)
      const r = await apiClient.get(
        `/public/doctors/${apt.doctor_id}?date_from=${df}&date_to=${dt}`,
      )
      setSlots(r.data?.available_slots || [])
    } catch {
      setSlots([])
    } finally {
      setSlotsLoading(false)
    }
  }

  const doReschedule = async (slot: any) => {
    if (!rescheduleFor) return
    setBusyId(rescheduleFor.id)
    try {
      await apiClient.post(`/patient/me/appointments/${rescheduleFor.id}/reschedule`, {
        start_at: slot.start,
        end_at: slot.end,
      })
      setRescheduleFor(null)
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to reschedule appointment')
    } finally {
      setBusyId(null)
    }
  }

  const slotsByDate: Record<string, any[]> = {}
  for (const s of slots) {
    const d = (s.start || '').slice(0, 10)
    if (!slotsByDate[d]) slotsByDate[d] = []
    slotsByDate[d].push(s)
  }
  const slotDates = Object.keys(slotsByDate).sort()

  if (!patientId)
    return <p className="text-center text-gray-500 py-8">Please login first.</p>
  if (loading)
    return (
      <div className="text-center py-8">
        <Loader2 className="h-6 w-6 animate-spin mx-auto" />
      </div>
    )

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <h1 className="text-2xl font-bold text-strong-fg">My Appointments</h1>

      {appointments.length === 0 ? (
        <p className="text-gray-400 text-center py-8">No appointments found.</p>
      ) : (
        appointments.map((apt: any) => (
          <Card key={apt.id}>
            <CardContent className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                  <CalendarDays className="h-5 w-5 text-primary-600" />
                </div>
                <div>
                  <p className="font-medium text-strong-fg">{fmtDate(apt.start_at)}</p>
                  <p className="text-sm text-gray-500">
                    {fmtTime(apt.start_at)} - {apt.reason || 'Consultation'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge className={cn(statusColors[apt.status] || 'bg-gray-100')}>{apt.status}</Badge>
                {apt.status !== 'cancelled' && (
                  <div className="flex flex-col gap-1">
                    <button
                      onClick={() => openReschedule(apt)}
                      disabled={busyId === apt.id}
                      className="text-xs px-2 py-1 rounded bg-primary-50 text-primary-700 hover:bg-primary-100 disabled:opacity-50"
                    >
                      {busyId === apt.id ? '…' : 'Reschedule'}
                    </button>
                    <button
                      onClick={() => cancel(apt.id)}
                      disabled={busyId === apt.id}
                      className="text-xs px-2 py-1 rounded bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))
      )}

      {rescheduleFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-surface-2 shadow-xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h2 className="font-semibold text-strong-fg flex items-center gap-2">
                <CalendarClock className="h-5 w-5" /> Pick a new time
              </h2>
              <button onClick={() => setRescheduleFor(null)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              {slotsLoading ? (
                <div className="text-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin mx-auto" />
                </div>
              ) : slotDates.length === 0 ? (
                <p className="text-center text-gray-400 py-8">No open slots in the next 14 days.</p>
              ) : (
                slotDates.map((d) => (
                  <div key={d}>
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                      {fmtDate(d + 'T00:00:00')}
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                      {slotsByDate[d].map((s, i) => (
                        <button
                          key={i}
                          onClick={() => doReschedule(s)}
                          disabled={busyId === rescheduleFor.id}
                          className="text-xs px-2 py-2 rounded border border-primary-200 text-primary-700 hover:bg-primary-50 disabled:opacity-50"
                        >
                          {fmtTime(s.start)}
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
