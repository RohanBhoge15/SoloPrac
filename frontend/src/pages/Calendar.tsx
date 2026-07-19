'use client'

import { useState, useEffect, useCallback } from 'react'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { AppointmentDetail } from '@/components/AppointmentDetail'
import { apiClient } from '@/services/api'
import { Plus, ChevronLeft, ChevronRight, MoreVertical, Calendar as CalendarIcon, Loader2, AlertCircle, X } from 'lucide-react'
import { format, startOfWeek, endOfWeek, eachDayOfInterval, addWeeks, subWeeks, isToday } from 'date-fns'

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
      const response = await apiClient.get('/api/v1/calendar/appointments', {
        params: {
          date_from: format(weekStart, 'yyyy-MM-dd'),
          date_to: format(weekEnd, 'yyyy-MM-dd'),
        },
      })
      setAppointments(response.data?.appointments || [])
    } catch (err) {
      setError('Failed to load appointments')
      setAppointments([])
    } finally {
      setLoading(false)
    }
  }, [weekStart, weekEnd])

  const fetchSlots = useCallback(async () => {
    setLoadingSlots(true)
    try {
      const response = await apiClient.get('/api/v1/calendar/slots', {
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

  const getAppointmentForSlot = (day: Date, slotMinutes: number) => {
    const slotTime = format(day, 'yyyy-MM-dd') + 'T' + `${String(Math.floor(slotMinutes / 60)).padStart(2, '0')}:${String(slotMinutes % 60).padStart(2, '0')}:00`
    return appointments.find((a: any) => {
      const aStart = a.start_at.slice(0, 16)
      const sStart = slotTime.slice(0, 16)
      return aStart === sStart
    })
  }

  const handleAppointmentClick = (appt: any) => setSelectedAppointment(appt)
  const handleCancel = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/calendar/appointments/${id}/cancel`)
      setSelectedAppointment(null)
      fetchAppointments()
    } catch {}
  }

  const navTo = (direction: 'prev' | 'next' | 'today') => {
    if (direction === 'prev') setCurrentWeek(subWeeks(currentWeek, 1))
    else if (direction === 'next') setCurrentWeek(addWeeks(currentWeek, 1))
    else setCurrentWeek(startOfWeek(new Date(), { weekStartsOn: 1 }))
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header */}
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

      {/* Slot Picker */}
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
              <p className="text-sm text-gray-400">No available slots this week. Check your working hours in Settings.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {availableSlots.slice(0, 20).map((slot, i) => (
                  <button key={i} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800 hover:bg-green-100">
                    {slot.date?.slice(5)} {slot.time} ({slot.duration_minutes}min)
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Week Grid */}
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
                  <tr key={slot.value} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="w-20 p-1 text-[10px] text-gray-500 dark:text-gray-400 font-mono align-top pt-2">{slot.label}</td>
                    {weekDays.map((day) => {
                      const apt = getAppointmentForSlot(day, slot.value)
                      return (
                        <td key={`${day}-${slot.value}`} className="relative p-1 h-16 border-r border-gray-100 dark:border-gray-800 align-top">
                          {apt && (
                            <button onClick={() => handleAppointmentClick(apt)} className={cn(
                              'w-full text-left p-1.5 rounded-md text-[10px] cursor-pointer transition-shadow hover:shadow-md',
                              apt.status === 'scheduled' && 'bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200 border border-blue-200 dark:border-blue-800',
                              apt.status === 'done' && 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-200 opacity-70',
                              apt.status === 'cancelled' && 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200 line-through opacity-60',
                            )}>
                              <div className="flex items-center justify-between">
                                <span className="font-medium truncate max-w-[60px]">{apt.patient_name?.split(' ')[0] || 'Patient'}</span>
                                <span className="text-[8px] opacity-60">{format(new Date(apt.start_at), 'HH:mm')}</span>
                              </div>
                              {apt.reason && <div className="truncate mt-0.5 opacity-70">{apt.reason}</div>}
                            </button>
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

      {/* Upcoming List */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Upcoming This Week</CardTitle>
        </CardHeader>
        <CardContent>
          {appointments.length === 0 && !loading && (
            <p className="text-sm text-gray-400 text-center py-4">No appointments this week</p>
          )}
          <div className="space-y-2">
            {appointments
              .filter((a: any) => a.status !== 'cancelled')
              .slice(0, 8)
              .map((apt: any) => (
                <button key={apt.id} onClick={() => handleAppointmentClick(apt)} className="flex items-center justify-between w-full p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800/50 text-left transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                      <CalendarIcon className="h-5 w-5 text-primary-600" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{apt.patient_name}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {format(new Date(apt.start_at), 'EEEE h:mm a')} &bull; {apt.reason || 'No reason'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'px-2 py-0.5 rounded-full text-[10px] font-medium',
                      apt.status === 'scheduled' && 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
                      apt.status === 'done' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
                    )}>{apt.status}</span>
                    <MoreVertical className="h-4 w-4 text-gray-400" />
                  </div>
                </button>
              ))}
          </div>
        </CardContent>
      </Card>

      {/* Appointment Detail Modal */}
      {selectedAppointment && (
        <AppointmentDetail
          appointment={selectedAppointment}
          onClose={() => setSelectedAppointment(null)}
          onCancel={handleCancel}
        />
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}
    </div>
  )
}
