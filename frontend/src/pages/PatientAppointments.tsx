import { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { CalendarDays, Loader2 } from 'lucide-react'

function cn(...classes: any[]) { return classes.filter(Boolean).join(' ') }

export function PatientAppointments() {
  const [appointments, setAppointments] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const patientId = localStorage.getItem('patient_id') || ''

  useEffect(() => {
    if (!patientId) { setLoading(false); return }
    apiClient.get('/api/patient/me/appointments', { params: { patient_id: patientId } })
      .then(r => setAppointments(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [patientId])

  if (!patientId) return <p className="text-center text-gray-500 py-8">Please login first.</p>
  if (loading) return <div className="text-center py-8"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div>

  const statusColors: Record<string, string> = {
    scheduled: 'bg-yellow-100 text-yellow-800',
    done: 'bg-green-100 text-green-800',
    cancelled: 'bg-red-100 text-red-800',
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Appointments</h1>
      {appointments.length === 0 ? <p className="text-gray-400 text-center py-8">No appointments found.</p> : (
        appointments.map((apt: any) => (
          <Card key={apt.id}>
            <CardContent className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                  <CalendarDays className="h-5 w-5 text-primary-600" />
                </div>
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">{new Date(apt.start_at).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</p>
                  <p className="text-sm text-gray-500">{new Date(apt.start_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })} - {apt.reason || 'Consultation'}</p>
                </div>
              </div>
              <Badge className={cn(statusColors[apt.status] || 'bg-gray-100')}>{apt.status}</Badge>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  )
}
