import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { CalendarDays, Bell, FileText, Loader2 } from 'lucide-react'
import { usePatientWebSocket } from '@/hooks/useWebSocket'
import { PendingMatchesBanner } from '@/components/PendingMatchesBanner'

function cn(...classes: any[]) { return classes.filter(Boolean).join(' ') }

export function PatientDashboard() {
  const [appointments, setAppointments] = useState<any[]>([])
  const [notifications, setNotifications] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [patientId, setPatientId] = useState<string>('')
  const { isConnected: wsConnected, lastEvent } = usePatientWebSocket(patientId)

  // P2.17 — Fire all three /patient/me/* requests in parallel on mount.
  //
  // Old flow: profile → (appointments, inbox). The chain existed only because
  // patientId gated the second useEffect, but the appointments/inbox endpoints
  // authenticate via the HttpOnly cookie — they don't need patientId either.
  // Combining them into one Promise.all cuts dashboard TTFB by ~one RTT.
  useEffect(() => {
    let cancelled = false
    setLoading(true)

    Promise.all([
      apiClient.get('/patient/me/profile').catch(() => null),
      apiClient.get('/patient/me/appointments').catch(() => null),
      apiClient.get('/patient/me/inbox', { params: { limit: 5 } }).catch(() => null),
    ]).then(([profileRes, aptRes, notifRes]) => {
      if (cancelled) return
      const uid = profileRes?.data?.id ?? profileRes?.data?.user_id
      if (uid) setPatientId(uid)
      setAppointments(aptRes?.data || [])
      setNotifications(notifRes?.data || [])
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })

    return () => { cancelled = true }
  }, [])

  // Handle real-time notifications from WebSocket
  useEffect(() => {
    if (lastEvent?.type === 'notification' && lastEvent.data) {
      setNotifications(prev => [lastEvent.data, ...prev.slice(0, 19)])
    }
  }, [lastEvent])

  if (!patientId) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Please log in to view your dashboard.</p>
        <Button className="mt-4" onClick={() => window.location.href = '/patient/login'}>Login</Button>
      </div>
    )
  }

  if (loading) return <div className="text-center py-8"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div>

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Dashboard</h1>
        <div className="flex items-center gap-2 text-sm">
          <span className={cn(wsConnected ? 'text-green-600' : 'text-red-600')}>
            {wsConnected ? '🟢 Live' : '🔴 Offline'}
          </span>
        </div>
      </div>

      {/* Walk-in disambiguation prompt — hidden when count is 0 */}
      <PendingMatchesBanner />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div><p className="text-sm text-gray-500">Upcoming Appointments</p><p className="text-2xl font-bold">{appointments.filter((a: any) => a.status === 'scheduled').length}</p></div>
            <CalendarDays className="h-8 w-8 text-primary-600" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div><p className="text-sm text-gray-500">Unread Notifications</p><p className="text-2xl font-bold">{notifications.filter((n: any) => !n.read).length}</p></div>
            <Bell className="h-8 w-8 text-yellow-600" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div><p className="text-sm text-gray-500">Reports Available</p><p className="text-2xl font-bold">{notifications.filter((n: any) => n.kind === 'report_available').length}</p></div>
            <FileText className="h-8 w-8 text-green-600" />
          </CardContent>
        </Card>
      </div>

      {appointments.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Upcoming Appointments</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {appointments.filter((a: any) => a.status === 'scheduled').slice(0, 5).map((apt: any) => (
              <div key={apt.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">{new Date(apt.start_at).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</p>
                  <p className="text-sm text-gray-500">{new Date(apt.start_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })} - {apt.reason || 'Consultation'}</p>
                </div>
                <Badge variant="default" className="bg-green-100 text-green-700">{apt.status}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {notifications.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Recent Notifications</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {notifications.slice(0, 5).map((n: any) => (
              <div key={n.id} className={cn('p-3 rounded-lg', n.read ? 'bg-gray-50 dark:bg-gray-800/30' : 'bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800')}>
                <div className="flex items-center justify-between">
                  <p className="font-medium text-sm text-gray-900 dark:text-white">{n.subject}</p>
                  {!n.read && <span className="h-2 w-2 rounded-full bg-blue-500" />}
                </div>
                <p className="text-xs text-gray-500 mt-1">{n.body}</p>
                <p className="text-[10px] text-gray-400 mt-1">{new Date(n.created_at).toLocaleDateString()}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
