import { useState, useEffect, useCallback } from 'react'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { AppointmentDetail } from '@/components/AppointmentDetail'
import { apiClient } from '@/services/api'
import { Plus, ChevronLeft, ChevronRight, Loader2, AlertCircle, X } from 'lucide-react'
import { format, startOfWeek, endOfWeek, eachDayOfInterval, addWeeks, subWeeks, isToday } from 'date-fns'
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog'
import { toast } from '@/components/ui/Toast'

const TIME_SLOTS = Array.from({ length: 16 }, (_, i) => {
  const h = 8 + i
  return { label: h > 12 ? `${h - 12}:00 PM` : `${h}:00 AM`, value: h * 60 }
})

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

  const weekStart = startOfWeek(currentWeek, { weekStartsOn: 1 })
  const weekEnd = endOfWeek(currentWeek, { weekStartsOn: 1 })
  const weekDays = eachDayOfInterval({ start: weekStart, end: weekEnd })

  const fetchAppointments = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.get('/calendar/appointments', {
        params: {
          date_from: format(weekStart, 'yyyy-MM-dd'),
          date_to: format(weekEnd, 'yyyy-MM-dd'),
        },
      })
      setAppointments(response.data?.appointments || [])
    } catch {
      setError('Failed to load appointments')
      setAppointments([])
    } finally {
      setLoading(false)
    }
  }, [weekStart, weekEnd])

  const fetchSlots = useCallback(async () => {
    setLoadingSlots(true)
    try {
      const response = await apiClient.get('/calendar/slots', {
        params: {
          date_from: format(weekStart, 'yyyy-MM-dd'),
          date_to: format(weekEnd, 'yyyy-MM-dd'),
          duration: 20,
        },
      })
      setAvailableSlots(response.data?.slots || [])
    } catch {
      setAvailableSlots([])
    } finally {
      setLoadingSlots(false)
    }
  }, [weekStart, weekEnd])

  useEffect(() => { fetchAppointments() }, [fetchAppointments])

  const getAppointmentForSlot = (day: string, slotMinutes: number) => {
    const slotTime = day + 'T' + `${String(Math.floor(slotMinutes / 60)).padStart(2, '0')}:${String(slotMinutes % 60).padStart(2, '0')}:00`
    return appointments.find((a: any) => {
      const aStart = a.start_at.slice(0, 16)
      const sStart = slotTime.slice(0, 16)
      return aStart === sStart
    })
  }

  const handleAppointmentClick = (appt: any) => setSelectedAppointment(appt)
  const handleCancel = (appt: any) => setConfirmCancelId(appt.id)

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
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navTo('prev')} size="icon"><ChevronLeft className="h-4 w-4" /></Button>
          <Button variant="outline" onClick={() => navTo('today')} size="sm">Today</Button>
          <Button variant="outline" onClick={() => navTo('next')} size="icon"><ChevronRight className="h-4 w-4" /></Button>
          <Button variant="outline" onClick={() => { fetchSlots(); setShowSlotPicker(!showSlotPicker) }} className={cn(showSlotPicker && 'bg-primary-50 text-primary-700')}>
            <Plus className="h-4 w-4 mr-1" /> Slots
          </Button>
          <Button><Plus className="h-4 w-4 mr-2" /> Book</Button>
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
                  <button key={i} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800">
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
                      return (
                        <td key={day.toISOString()} className="relative h-24 p-1 border-r border-gray-100 dark:border-gray-700">
                          {appt && (
                            <div
                              onClick={() => handleAppointmentClick(appt)}
                              className="absolute inset-0 m-1 rounded bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 p-1.5 text-xs hover:bg-primary-200 dark:hover:bg-primary-900/50 cursor-pointer flex flex-col justify-between"
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

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300 flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}
    </div>
  )
}
