'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { User, CalendarDays, X, RotateCcw, AlertTriangle } from 'lucide-react'

interface AppointmentDetailProps {
  appointment: {
    id: string
    patient_name: string
    start_at: string
    end_at: string
    reason: string
    status: string
    source: string
  }
  onClose: () => void
  onReschedule?: (id: string) => void
  onCancel?: (id: string) => void
}

export function AppointmentDetail({ appointment, onClose, onReschedule, onCancel }: AppointmentDetailProps) {
  const [confirmCancel, setConfirmCancel] = useState(false)

  const startDate = new Date(appointment.start_at)
  const endDate = new Date(appointment.end_at)
  const duration = Math.round((endDate.getTime() - startDate.getTime()) / 60000)

  const statusColor = {
    scheduled: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    done: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    cancelled: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  }[appointment.status] || 'bg-gray-100 text-gray-800'

  return (
    <Card className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <Card className="w-full max-w-md mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <CalendarDays className="h-5 w-5 text-primary-600" />
            Appointment Details
          </CardTitle>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                <User className="h-6 w-6 text-primary-600" />
              </div>
              <div>
                <p className="text-lg font-semibold text-gray-900 dark:text-white">{appointment.patient_name}</p>
                <Badge variant="outline" className={statusColor}>{appointment.status}</Badge>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500">Date</p>
              <p className="font-medium text-gray-900 dark:text-white">{startDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</p>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500">Time</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {startDate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })} - {endDate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500">Duration</p>
              <p className="font-medium text-gray-900 dark:text-white">{duration} min</p>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500">Source</p>
              <p className="font-medium text-gray-900 dark:text-white capitalize">{appointment.source}</p>
            </div>
          </div>

          {appointment.reason && (
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500 mb-1">Reason</p>
              <p className="text-sm text-gray-900 dark:text-white">{appointment.reason}</p>
            </div>
          )}

          <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-2">
              {onReschedule && appointment.status === 'scheduled' && (
                <Button variant="outline" size="sm" onClick={() => { onReschedule(appointment.id) }}>
                  <RotateCcw className="h-3.5 w-3.5 mr-1" /> Reschedule
                </Button>
              )}
              {onCancel && appointment.status === 'scheduled' && !confirmCancel && (
                <Button variant="outline" size="sm" className="text-red-600 border-red-300 hover:bg-red-50 dark:hover:bg-red-900/20" onClick={() => setConfirmCancel(true)}>
                  <AlertTriangle className="h-3.5 w-3.5 mr-1" /> Cancel
                </Button>
              )}
              {confirmCancel && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-red-600">Confirm?</span>
                  <Button size="sm" variant="destructive" onClick={() => { onCancel?.(appointment.id); setConfirmCancel(false) }}>Yes, Cancel</Button>
                  <Button size="sm" variant="outline" onClick={() => setConfirmCancel(false)}>No</Button>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </Card>
  )
}
