import { useState, useEffect, useCallback, useRef } from 'react'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { AppointmentDetail } from '@/components/AppointmentDetail'
import { apiClient } from '@/services/api'
import { Plus, ChevronLeft, ChevronRight, Loader2, AlertCircle, X, Search, User, Calendar as CalendarIcon, Clock } from 'lucide-react'
import { format, startOfWeek, endOfWeek, eachDayOfInterval, addWeeks, subWeeks, addDays, subDays, isToday } from 'date-fns'
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog'
import { toast } from '@/components/ui/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useDoctorWebSocket } from '@/hooks/useWebSocket'

// D-5 (AUDIT.md): hour 12 was rendered as "12:00 AM" because the old ternary
// (`h > 12 ? PM : AM`) grouped noon into the AM branch. Use an explicit
// 12-hour clock mapping so 0 → 12 AM, 12 → 12 PM, 13..23 → 1..11 PM.
const TIME_SLOTS = Array.from({ length: 16 }, (_, i) => {
  const h = 8 + i
  const label =
    h === 0 ? '12:00 AM'
    : h < 12 ? `${h}:00 AM`
    : h === 12 ? '12:00 PM'
    : `${h - 12}:00 PM`
  return { label, value: h * 60 }
})

interface PatientResult {
  id: string
  name: string
  initials: string
  age?: number
  gender?: string
  phone?: string
}

export function Calendar() {
  const [currentWeek, setCurrentWeek] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }))
  const [appointments, setAppointments] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedAppointment, setSelectedAppointment] = useState<any>(null)
  const [confirmCancelId, setConfirmCancelId] = useState<string | null>(null)
  const [showSlotPicker, setShowSlotPicker] = useState(false)
  const [availableSlots, setAvailableSlots] = useState<any[]>([])
  const [loadingSlots, setLoadingSlots] = useState(false)

  // ── Booking dialog state ──
  const [showBooking, setShowBooking] = useState(false)
  const [bookingPatient, setBookingPatient] = useState<PatientResult | null>(null)
  const [bookingDate, setBookingDate] = useState('')
  const [bookingTime, setBookingTime] = useState('09:00')
  const [bookingDuration, setBookingDuration] = useState(20)
  const [bookingReason, setBookingReason] = useState('')
  const [bookingLoading, setBookingLoading] = useState(false)
  const [bookingError, setBookingError] = useState<string | null>(null)
  // Patient search
  const [patientQuery, setPatientQuery] = useState('')
  const [patientResults, setPatientResults] = useState<PatientResult[]>([])
  const [patientSearching, setPatientSearching] = useState(false)
  const [showPatientDropdown, setShowPatientDropdown] = useState(false)
  const patientSearchRef = useRef<HTMLDivElement>(null)

  const weekStart = startOfWeek(currentWeek, { weekStartsOn: 1 })
  const weekEnd = endOfWeek(currentWeek, { weekStartsOn: 1 })
  const weekDays = eachDayOfInterval({ start: weekStart, end: weekEnd })

  // Depend on the FORMATTED strings, not the Date objects. `weekStart`/`weekEnd`
  // are recomputed as fresh Date instances on every render (new reference each
  // time), so listing them as deps to useCallback made the callback identity
  // change every render → the useEffect below re-fired → setAppointments →
  // re-render → new Dates → infinite "Loading appointments…" loop.
  const weekFromStr = format(weekStart, 'yyyy-MM-dd')
  const weekToStr = format(weekEnd, 'yyyy-MM-dd')

  // The backend treats date_from/date_to as UTC day boundaries, but this grid
  // reasons in LOCAL time. For any non-UTC timezone (IST is UTC+5:30) the local
  // week spills past those boundaries, so a strict range clips appointments at
  // the edges. Pad one day either side to guarantee a superset — the grid then
  // filters exactly via getAppointmentForSlot's local-time comparison.
  const fetchFromStr = format(subDays(weekStart, 1), 'yyyy-MM-dd')
  const fetchToStr = format(addDays(weekEnd, 1), 'yyyy-MM-dd')

  const fetchAppointments = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.get('/calendar/appointments', {
        params: { date_from: fetchFromStr, date_to: fetchToStr },
      })
      setAppointments(response.data?.appointments || [])
    } catch {
      setError('Failed to load appointments')
      setAppointments([])
    } finally {
      setLoading(false)
    }
  }, [fetchFromStr, fetchToStr])

  // ── Live updates ──
  // Subscribe to the doctor WebSocket so patient bookings / cancels / reschedules
  // appear on the calendar instantly instead of requiring a manual refresh.
  const { user } = useAuth()
  const { lastEvent } = useDoctorWebSocket(user?.id ?? null)
  useEffect(() => {
    if (!lastEvent) return
    const kind = lastEvent.data?.kind ?? lastEvent.type ?? ''
    if (typeof kind === 'string' && kind.toLowerCase().includes('appointment')) {
      fetchAppointments()
    }
  }, [lastEvent, fetchAppointments])

  const fetchSlots = useCallback(async () => {
    setLoadingSlots(true)
    try {
      const response = await apiClient.get('/calendar/slots', {
        params: { date_from: weekFromStr, date_to: weekToStr, duration: 20 },
      })
      setAvailableSlots(response.data?.slots || [])
    } catch {
      setAvailableSlots([])
    } finally {
      setLoadingSlots(false)
    }
  }, [weekFromStr, weekToStr])

  useEffect(() => { fetchAppointments() }, [fetchAppointments])

  // ── Patient search with debounce ──
  useEffect(() => {
    if (patientQuery.length < 2) {
      setPatientResults([])
      return
    }
    const timer = setTimeout(async () => {
      setPatientSearching(true)
      try {
        const res = await apiClient.get('/patients/search', { params: { q: patientQuery, limit: 10 } })
        setPatientResults(res.data?.patients || res.data || [])
        setShowPatientDropdown(true)
      } catch {
        setPatientResults([])
      } finally {
        setPatientSearching(false)
      }
    }, 200)
    return () => clearTimeout(timer)
  }, [patientQuery])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (patientSearchRef.current && !patientSearchRef.current.contains(e.target as Node)) {
        setShowPatientDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // D-6 (AUDIT.md): TIME_SLOTS only produces hour buckets (multiples of 60),
  // but appointments can start at :15 / :30 / :45. The old exact-match against
  // `HH:MM` dropped those appointments off the grid. Match by (date + hour
  // bucket) instead. Original start_at is preserved untouched on the object
  // so downstream display still shows the true minute (e.g. "10:15").
  const getAppointmentForSlot = (day: string, slotMinutes: number) => {
    const slotHour = Math.floor(slotMinutes / 60)
    return appointments.find((a: any) => {
      if (!a?.start_at) return false
      // Cancelled appointments should not occupy the grid as active bookings.
      if (a.status === 'cancelled') return false
      // Compare in LOCAL time. `start_at` comes back as UTC (…Z), but the grid's
      // row labels ("9 AM") and its `day` columns are local. String-slicing the
      // UTC hour out of the ISO text meant a 9 AM IST booking (stored 03:30Z)
      // was hunted for in the 3 AM row — which isn't rendered at all, so the
      // appointment silently vanished right after being created.
      const d = new Date(a.start_at)
      if (Number.isNaN(d.getTime())) return false
      return format(d, 'yyyy-MM-dd') === day && d.getHours() === slotHour
    })
  }

  const handleAppointmentClick = (appt: any) => setSelectedAppointment(appt)
  const handleCancel = (appt: any) => setConfirmCancelId(appt.id)

  // ── Drag-to-reschedule ──
  // We use plain HTML5 drag-and-drop (no extra deps). The dragged appointment's
  // full JSON is stashed in dataTransfer so the drop handler can rebuild an
  // updated PATCH body — start_at moved to the drop cell, end_at moved by the
  // same delta so the appointment keeps its original duration.
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  const handleDragStart = (e: React.DragEvent, appt: any) => {
    setDraggingId(appt.id)
    e.dataTransfer.effectAllowed = 'move'
    try { e.dataTransfer.setData('application/json', JSON.stringify(appt)) } catch { /* Firefox is fine without */ }
    // Fallback: also stash on window in case dataTransfer.getData is empty on drop (Safari).
    ;(window as any).__dragAppt = appt
  }

  const handleDragEnd = () => {
    setDraggingId(null)
    setDropTarget(null)
    ;(window as any).__dragAppt = null
  }

  const handleCellDragOver = (e: React.DragEvent, cellKey: string) => {
    // Only accept if there's no appointment already in this cell.
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDropTarget(cellKey)
  }

  const handleCellDrop = async (e: React.DragEvent, day: Date, slotMinutes: number) => {
    e.preventDefault()
    setDropTarget(null)

    let dragged: any = null
    try {
      const raw = e.dataTransfer.getData('application/json')
      if (raw) dragged = JSON.parse(raw)
    } catch { /* ignore */ }
    if (!dragged) dragged = (window as any).__dragAppt
    if (!dragged) return

    // Compute new start / end. Preserve original duration.
    const originalStart = new Date(dragged.start_at)
    const originalEnd = new Date(dragged.end_at)
    const durationMs = originalEnd.getTime() - originalStart.getTime()

    const hh = Math.floor(slotMinutes / 60)
    const mm = slotMinutes % 60
    const newStart = new Date(day)
    // Preserve original minute offset so a 09:15 apt dropped on the "9 AM" row stays at 09:15,
    // but if the source cell was aligned to :00 we get :00.
    const originalMinuteOffset = originalStart.getMinutes()
    newStart.setHours(hh, originalMinuteOffset || mm, 0, 0)
    const newEnd = new Date(newStart.getTime() + durationMs)

    // No-op if the user dropped it on its current cell.
    if (newStart.getTime() === originalStart.getTime()) return

    // Optimistic update
    const previousAppointments = appointments
    setAppointments(prev => prev.map(a => a.id === dragged.id
      ? { ...a, start_at: newStart.toISOString(), end_at: newEnd.toISOString() }
      : a
    ))

    try {
      await apiClient.patch(`/calendar/appointments/${dragged.id}/reschedule`, {
        start_at: newStart.toISOString(),
        end_at: newEnd.toISOString(),
        reason: 'Rescheduled via drag',
      })
      toast.success('Appointment rescheduled')
      // Refetch to reconcile with any server-side normalisation (e.g. buffer merges).
      fetchAppointments()
    } catch (err: any) {
      // Roll back on failure.
      setAppointments(previousAppointments)
      const detail = err?.response?.data?.detail || 'Failed to reschedule'
      toast.error(String(detail))
    }
  }

  const confirmCancelAppointment = async () => {
    if (!confirmCancelId) return
    try {
      await apiClient.post(`/calendar/appointments/${confirmCancelId}/cancel`)
      toast.success('Appointment cancelled')
      setSelectedAppointment(null)
      fetchAppointments()
    } catch {
      toast.error('Failed to cancel appointment')
    } finally {
      setConfirmCancelId(null)
    }
  }

  // ── Click empty calendar cell to pre-fill booking time ──
  const handleEmptyCellClick = (day: Date, slotMinutes: number) => {
    const hh = String(Math.floor(slotMinutes / 60)).padStart(2, '0')
    const mm = String(slotMinutes % 60).padStart(2, '0')
    setBookingDate(format(day, 'yyyy-MM-dd'))
    setBookingTime(`${hh}:${mm}`)
    setShowBooking(true)
  }

  // ── Submit booking ──
  const handleBook = async () => {
    if (!bookingPatient || !bookingDate || !bookingTime) return
    setBookingLoading(true)
    setBookingError(null)
    try {
      const startISO = `${bookingDate}T${bookingTime}:00`
      const startDate = new Date(startISO)
      const endDate = new Date(startDate.getTime() + bookingDuration * 60000)
      await apiClient.post('/calendar/appointments', {
        patient_id: bookingPatient.id,
        start_at: startDate.toISOString(),
        end_at: endDate.toISOString(),
        reason: bookingReason || 'Consultation',
      })
      toast.success('Appointment booked')
      resetBooking()
      fetchAppointments()
    } catch (err: any) {
      setBookingError(err?.response?.data?.detail || 'Failed to book appointment')
    } finally {
      setBookingLoading(false)
    }
  }

  const resetBooking = () => {
    setShowBooking(false)
    setBookingPatient(null)
    setPatientQuery('')
    setPatientResults([])
    setBookingDate('')
    setBookingTime('09:00')
    setBookingDuration(20)
    setBookingReason('')
    setBookingError(null)
  }

  const navTo = (direction: 'prev' | 'next' | 'today') => {
    if (direction === 'prev') setCurrentWeek(subWeeks(currentWeek, 1))
    else if (direction === 'next') setCurrentWeek(addWeeks(currentWeek, 1))
    else setCurrentWeek(startOfWeek(new Date(), { weekStartsOn: 1 }))
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Calendar</h1>
          <p className="text-gray-500 dark:text-gray-400">
            {format(weekStart, 'MMM d')} - {format(weekEnd, 'MMM d, yyyy')}
            <span className="hidden sm:inline text-xs text-gray-400 ml-2">· Drag an appointment to a new time to reschedule</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navTo('prev')} size="icon"><ChevronLeft className="h-4 w-4" /></Button>
          <Button variant="outline" onClick={() => navTo('today')} size="sm">Today</Button>
          <Button variant="outline" onClick={() => navTo('next')} size="icon"><ChevronRight className="h-4 w-4" /></Button>
          <Button variant="outline" onClick={() => { fetchSlots(); setShowSlotPicker(!showSlotPicker) }} className={cn(showSlotPicker && 'bg-primary-50 text-primary-700')}>
            <Plus className="h-4 w-4 mr-1" /> Slots
          </Button>
          <Button onClick={() => { setBookingDate(format(new Date(), 'yyyy-MM-dd')); setShowBooking(true) }}>
            <Plus className="h-4 w-4 mr-2" /> Book
          </Button>
        </div>
      </div>

      {showSlotPicker && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between py-3">
            <CardTitle className="text-sm">Available This Week</CardTitle>
            <Button variant="ghost" size="icon" onClick={() => setShowSlotPicker(false)}><X className="h-4 w-4" /></Button>
          </CardHeader>
          <CardContent className="py-2">
            {loadingSlots ? (
              <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading slots...</div>
            ) : availableSlots.length === 0 ? (
              <p className="text-sm text-gray-400">No available slots this week.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {availableSlots.slice(0, 20).map((slot: any, i: number) => (
                  // D-2 (AUDIT.md): slot buttons were inert. Clicking a slot
                  // should pre-fill the booking dialog with its date/time/
                  // duration and close the picker so the doctor can pick a
                  // patient and confirm.
                  <button
                    key={i}
                    onClick={() => {
                      if (slot.date) setBookingDate(slot.date)
                      if (slot.time) setBookingTime(String(slot.time).slice(0, 5))
                      if (slot.duration_minutes) setBookingDuration(Number(slot.duration_minutes))
                      setShowSlotPicker(false)
                      setShowBooking(true)
                    }}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-900/40 transition-colors"
                  >
                    {slot.date?.slice(5)} {slot.time} ({slot.duration_minutes}min)
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                <th className="w-20 p-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Time</th>
                {weekDays.map((day) => (
                  <th key={day.toISOString()} className={cn('p-2 text-sm font-medium', isToday(day) && 'bg-primary-50 dark:bg-primary-900/20 text-primary-700')}>
                    <div className="flex flex-col items-center gap-1">
                      <span>{format(day, 'EEE')}</span>
                      <span className="text-lg font-semibold">{format(day, 'd')}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="p-8 text-center text-gray-500"><Loader2 className="h-5 w-5 animate-spin mx-auto mb-2" />Loading appointments...</td></tr>
              ) : (
                TIME_SLOTS.map((slot) => (
                  <tr key={slot.value} className="border-b border-gray-100 dark:border-gray-700">
                    <td className="w-20 p-2 text-xs text-gray-500 dark:text-gray-400 font-mono">{slot.label}</td>
                    {weekDays.map((day) => {
                      const appt = getAppointmentForSlot(format(day, 'yyyy-MM-dd'), slot.value)
                      const cellKey = `${format(day, 'yyyy-MM-dd')}-${slot.value}`
                      const isDropTarget = dropTarget === cellKey && !appt
                      return (
                        <td
                          key={day.toISOString()}
                          className={cn(
                            "relative h-24 p-1 border-r border-gray-100 dark:border-gray-700",
                            !appt && "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50",
                            isDropTarget && "bg-primary-100 dark:bg-primary-900/40 ring-2 ring-primary-400 ring-inset"
                          )}
                          onClick={() => !appt && handleEmptyCellClick(day, slot.value)}
                          onDragOver={!appt ? (e) => handleCellDragOver(e, cellKey) : undefined}
                          onDragLeave={!appt ? () => setDropTarget(prev => prev === cellKey ? null : prev) : undefined}
                          onDrop={!appt ? (e) => handleCellDrop(e, day, slot.value) : undefined}
                        >
                          {appt && (
                            <div
                              draggable
                              onDragStart={(e) => handleDragStart(e, appt)}
                              onDragEnd={handleDragEnd}
                              onClick={(e) => { e.stopPropagation(); handleAppointmentClick(appt) }}
                              className={cn(
                                "absolute inset-0 m-1 rounded bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 p-1.5 text-xs hover:bg-primary-200 dark:hover:bg-primary-900/50 cursor-move flex flex-col justify-between",
                                draggingId === appt.id && "opacity-40"
                              )}
                              title="Drag to reschedule · click to view"
                            >
                              <span className="truncate font-medium">{appt.patient_name || `Patient ${appt.patient_id?.slice(0, 6)}`}</span>
                              <span className="text-[10px] opacity-80">{appt.reason || 'Consultation'}</span>
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {selectedAppointment && (
        <AppointmentDetail
          appointment={selectedAppointment}
          onClose={() => setSelectedAppointment(null)}
          onCancel={handleCancel}
        />
      )}

      {confirmCancelId && (
        <ConfirmationDialog
          open={true}
          onOpenChange={() => setConfirmCancelId(null)}
          title="Cancel Appointment"
          description="Are you sure you want to cancel this appointment? The patient will be notified."
          variant="danger"
          confirmLabel="Cancel Appointment"
          onConfirm={confirmCancelAppointment}
        />
      )}

      {/* ── Booking Dialog ── */}
      {showBooking && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={resetBooking}>
          <div
            className="bg-white dark:bg-gray-900 rounded-xl p-6 max-w-lg w-full mx-4 shadow-2xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Book Appointment</h2>
              <button onClick={resetBooking} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800">
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Step 1: Patient */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  <User className="inline h-3.5 w-3.5 mr-1" />
                  Patient
                </label>
                <div ref={patientSearchRef} className="relative">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input
                      type="text"
                      value={bookingPatient ? bookingPatient.name : patientQuery}
                      onChange={(e) => {
                        if (bookingPatient) setBookingPatient(null)
                        setPatientQuery(e.target.value)
                      }}
                      onFocus={() => patientResults.length > 0 && setShowPatientDropdown(true)}
                      placeholder="Search patient by name or phone..."
                      className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      disabled={!!bookingPatient}
                    />
                    {bookingPatient && (
                      <button
                        onClick={() => { setBookingPatient(null); setPatientQuery('') }}
                        className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                  {showPatientDropdown && !bookingPatient && (
                    <div className="absolute z-10 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                      {patientSearching ? (
                        <div className="p-3 text-sm text-gray-500 flex items-center gap-2">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Searching...
                        </div>
                      ) : patientResults.length === 0 ? (
                        <div className="p-3 text-sm text-gray-400">No patients found</div>
                      ) : (
                        patientResults.map((p) => (
                          <button
                            key={p.id}
                            onClick={() => { setBookingPatient(p); setShowPatientDropdown(false); setPatientQuery('') }}
                            className="w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-3"
                          >
                            <div className="h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 flex items-center justify-center text-xs font-bold">
                              {p.initials}
                            </div>
                            <div>
                              <div className="font-medium text-gray-900 dark:text-white">{p.name}</div>
                              <div className="text-xs text-gray-500">
                                {[p.age && `${p.age}y`, p.gender, p.phone].filter(Boolean).join(' · ')}
                              </div>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Step 2: Date & Time */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <CalendarIcon className="inline h-3.5 w-3.5 mr-1" />
                    Date
                  </label>
                  <input
                    type="date"
                    value={bookingDate}
                    onChange={(e) => setBookingDate(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <Clock className="inline h-3.5 w-3.5 mr-1" />
                    Time
                  </label>
                  <input
                    type="time"
                    value={bookingTime}
                    onChange={(e) => setBookingTime(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Duration */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Duration (minutes)</label>
                <select
                  value={bookingDuration}
                  onChange={(e) => setBookingDuration(Number(e.target.value))}
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value={10}>10 min</option>
                  <option value={15}>15 min</option>
                  <option value={20}>20 min</option>
                  <option value={30}>30 min</option>
                  <option value={45}>45 min</option>
                  <option value={60}>60 min</option>
                </select>
              </div>

              {/* Reason */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Reason</label>
                <input
                  type="text"
                  value={bookingReason}
                  onChange={(e) => setBookingReason(e.target.value)}
                  placeholder="Consultation"
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
              </div>
            </div>

            {bookingError && (
              <div className="mt-3 p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-sm text-red-700 dark:text-red-300">{bookingError}</div>
            )}

            <div className="flex justify-end gap-2 mt-5">
              <Button variant="outline" onClick={resetBooking} disabled={bookingLoading}>Cancel</Button>
              <Button
                onClick={handleBook}
                disabled={bookingLoading || !bookingPatient || !bookingDate || !bookingTime}
              >
                {bookingLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
                Book Appointment
              </Button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300 flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}
    </div>
  )
}
