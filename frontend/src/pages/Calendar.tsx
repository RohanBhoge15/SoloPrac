'use client'

import { useState } from 'react'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Plus, Mic, ChevronLeft, ChevronRight, MoreVertical, Calendar as CalendarIcon } from 'lucide-react'
import { format, startOfWeek, endOfWeek, eachDayOfInterval, addWeeks, subWeeks, isToday } from 'date-fns'

// Mock appointments
const MOCK_APPOINTMENTS = [
  { id: '1', patientId: '1', patientName: 'Priya Sharma', time: '09:00', duration: 30, reason: 'Diabetes follow-up', status: 'scheduled', color: 'bg-blue-500' },
  { id: '2', patientId: '2', patientName: 'Rajesh Kumar', time: '10:30', duration: 20, reason: 'Hypertension review', status: 'done', color: 'bg-green-500' },
  { id: '3', patientId: '3', patientName: 'Anita Patel', time: '14:00', duration: 30, reason: 'Wound check', status: 'scheduled', color: 'bg-orange-500' },
  { id: '4', patientId: '4', patientName: 'Mohammed Ali', time: '16:30', duration: 20, reason: 'New patient', status: 'scheduled', color: 'bg-purple-500' },
  { id: '5', patientId: '5', patientName: 'Sunita Devi', time: '11:00', duration: 20, reason: 'Follow-up', status: 'cancelled', color: 'bg-red-500' },
]

const TIME_SLOTS = Array.from({ length: 14 }, (_, i) => {
  const h = 8 + i
  return h > 12 ? `${h - 12}:00 PM` : `${h}:00 AM`
})

export function Calendar() {
  const [currentWeek, setCurrentWeek] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }))
  const [view, setView] = useState<'week' | 'day'>('week')
  const [voiceActive, setVoiceActive] = useState(false)

  const weekDays = eachDayOfInterval({
    start: startOfWeek(currentWeek, { weekStartsOn: 1 }),
    end: endOfWeek(currentWeek, { weekStartsOn: 1 }),
  })

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Calendar</h1>
          <p className="text-gray-500 dark:text-gray-400">
            {format(currentWeek, 'MMM d')} - {format(endOfWeek(currentWeek, { weekStartsOn: 1 }), 'MMM d, yyyy')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={view}
            onChange={(e) => setView(e.target.value as 'week' | 'day')}
            className="input w-auto"
          >
            <option value="week">Week</option>
            <option value="day">Day</option>
          </select>
          <Button variant="outline" onClick={() => setCurrentWeek(subWeeks(currentWeek, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" onClick={() => setCurrentWeek(new Date())}>
            Today
          </Button>
          <Button variant="outline" onClick={() => setCurrentWeek(addWeeks(currentWeek, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="outline" onClick={() => setVoiceActive(!voiceActive)} className={voiceActive ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' : ''}>
            <Mic className={cn('h-4 w-4 mr-1', voiceActive && 'animate-pulse text-red-500')} />
            {voiceActive ? 'Listening...' : 'Voice'}
          </Button>
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            New Appointment
          </Button>
        </div>
      </div>

      {/* Week Grid */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px]">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
              <th className="w-24 p-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Time</th>
              {weekDays.map((day) => (
                <th key={day.toISOString()} className={cn(
                  'p-2 text-sm font-medium',
                  isToday(day) && 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                )}>
                  <div className="flex flex-col items-center gap-1">
                    <span>{format(day, 'EEE')}</span>
                    <span className="text-lg font-semibold">{format(day, 'd')}</span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {TIME_SLOTS.map((slot) => (
              <tr key={slot} className="border-b border-gray-100 dark:border-gray-800">
                <td className="w-24 p-1 text-xs text-gray-500 dark:text-gray-400 font-mono">
                  {slot}
                </td>
                {weekDays.map((day) => (
                  <td key={`${day}-${slot}`} className="relative p-1 min-h-[80px] border-r border-gray-100 dark:border-gray-800">
                    {MOCK_APPOINTMENTS
                      .filter(a => a.time === slot.replace(' PM', '').replace(' AM', ''))
                      .map((apt) => (
                        <div
                          key={apt.id}
                          className={cn(
                            'absolute left-1 right-1 m-1 p-2 rounded-lg text-xs cursor-pointer transition-shadow hover:shadow-md',
                            apt.color,
                            apt.status === 'done' && 'opacity-70 line-through',
                            apt.status === 'cancelled' && 'opacity-50 bg-red-100 dark:bg-red-900/20'
                          )}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white truncate">{apt.patientName}</span>
                            <span className="text-white/80 text-[10px]">
                              {apt.status === 'done' ? '✓' : apt.status === 'cancelled' ? '✗' : '○'}
                            </span>
                          </div>
                          <div className="text-white/90 truncate mt-0.5">{apt.reason}</div>
                        </div>
                      ))}
                    <div className="absolute bottom-1 right-1 text-xs text-gray-400">{format(day, 'd')}</div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Upcoming List */}
      <Card className="mt-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Upcoming This Week</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {MOCK_APPOINTMENTS
              .filter(a => a.status !== 'cancelled')
              .slice(0, 5)
              .map((apt) => (
                <div key={apt.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                  <div className="flex items-center gap-4">
                    <div className={cn('h-10 w-10 rounded-full flex items-center justify-center', apt.color)}>
                      <CalendarIcon className="h-5 w-5 text-white" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{apt.patientName}</p>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{apt.reason} • {apt.duration} min</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded-full text-xs font-medium',
                      apt.status === 'scheduled' && 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
                      apt.status === 'done' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
                    )}>
                      {apt.status}
                    </span>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}