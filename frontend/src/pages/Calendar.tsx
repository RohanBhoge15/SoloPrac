import { useState } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Plus, ChevronLeft, ChevronRight, MoreVertical, Calendar as CalendarIcon, Clock } from 'lucide-react'
import { format, startOfWeek, endOfWeek, addWeeks, subWeeks, eachDayOfInterval, isToday } from 'date-fns'

const TIME_SLOTS = Array.from({ length: 14 }, (_, i) => {
  const h = 8 + i
  return `${h > 12 ? h - 12 : h}:00 ${h >= 12 ? 'PM' : 'AM'}`
})

const APPOINTMENTS = [
  { id: '1', patient: 'Priya Sharma', time: '09:00', duration: 30, reason: 'Diabetes follow-up', status: 'scheduled', color: 'bg-blue-500' },
  { id: '2', patient: 'Rajesh Kumar', time: '10:30', duration: 20, reason: 'Hypertension review', status: 'done', color: 'bg-green-500' },
  { id: '3', patient: 'Anita Patel', time: '14:00', duration: 30, reason: 'Wound check', status: 'scheduled', color: 'bg-orange-500' },
  { id: '4', patient: 'Mohammed Ali', time: '16:30', duration: 20, reason: 'New patient intake', status: 'scheduled', color: 'bg-purple-500' },
]

export function Calendar() {
  const [currentWeek, setCurrentWeek] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }))

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
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {format(currentWeek, 'MMM d')} &ndash; {format(endOfWeek(currentWeek, { weekStartsOn: 1 }), 'MMM d, yyyy')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setCurrentWeek(subWeeks(currentWeek, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCurrentWeek(new Date())}>
            Today
          </Button>
          <Button variant="outline" size="icon" onClick={() => setCurrentWeek(addWeeks(currentWeek, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            New Appointment
          </Button>
        </div>
      </div>

      {/* Week Grid */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                <th className="w-20 p-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Time</th>
                {weekDays.map((day) => (
                  <th key={day.toISOString()} className={cn(
                    'p-2 text-sm font-medium',
                    isToday(day) && 'bg-primary-50 dark:bg-primary-900/20'
                  )}>
                    <div className="flex flex-col items-center">
                      <span className="text-xs text-gray-500 dark:text-gray-400">{format(day, 'EEE')}</span>
                      <span className={cn(
                        'text-lg font-semibold',
                        isToday(day) ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-white'
                      )}>
                        {format(day, 'd')}
                      </span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {TIME_SLOTS.map((slot) => (
                <tr key={slot} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="p-2 text-xs text-gray-500 dark:text-gray-400 font-mono">{slot}</td>
                  {weekDays.map((day) => (
                    <td key={`${day}-${slot}`} className="relative p-1 min-h-[60px] border-r border-gray-100 dark:border-gray-800">
                      {APPOINTMENTS
                        .filter(a => a.time === slot.split(' ')[0])
                        .map((apt) => (
                          <div
                            key={apt.id}
                            className={cn(
                              'rounded-lg p-2 text-xs text-white cursor-pointer transition-shadow hover:shadow-md mb-1 last:mb-0',
                              apt.color
                            )}
                          >
                            <div className="font-medium truncate flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {apt.time}
                            </div>
                            <div className="font-medium truncate">{apt.patient}</div>
                            <div className="text-white/80 truncate">{apt.reason}</div>
                          </div>
                        ))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Upcoming List */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <CalendarIcon className="h-5 w-5 text-primary-600" />
            Upcoming This Week
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {APPOINTMENTS.map((apt) => (
              <div key={apt.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                <div className="flex items-center gap-4">
                  <div className={cn('h-10 w-10 rounded-full flex items-center justify-center', apt.color)}>
                    <CalendarIcon className="h-5 w-5 text-white" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{apt.patient}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{apt.reason} &bull; {apt.duration} min</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={cn(
                    'px-2 py-1 rounded-full text-xs font-medium',
                    apt.status === 'scheduled' && 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
                    apt.status === 'done' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
                  )}>
                    {apt.status}
                  </span>
                  <button className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700">
                    <MoreVertical className="h-4 w-4 text-gray-500" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}