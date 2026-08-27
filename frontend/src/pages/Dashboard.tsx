import { useEffect, useState } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Calendar, FileText, Search, Mic, Plus, Users, Stethoscope, TrendingUp, AlertTriangle } from 'lucide-react'
import { RiskAlertsPanel } from '@/components/RiskAlerts'
import { useCommandPalette } from '@/components/CommandPalette'
import { useDoctorWebSocket } from '@/hooks/useWebSocket'
import { useAuth } from '@/contexts/AuthContext'
import { useRiskStore, usePatientStore, useNotificationStore } from '@/store'
import type { RiskAlert } from '@/types'
import { usePrefetchPatient } from '@/hooks/usePrefetchPatient'

interface StatCard {
  label: string
  value: string | number
  change: string
  icon: React.ElementType
  color: string
}

export function Dashboard() {
  const { user } = useAuth()
  const { alerts, fetchAlerts, pushAlert } = useRiskStore()
  const { patients, fetchPatients } = usePatientStore()
  const { fetchAppointments, appointments } = useNotificationStore()
  const { lastEvent } = useDoctorWebSocket(user?.id ?? null)
  const prefetchPatient = usePrefetchPatient()
  // D-1 (AUDIT.md): header Search button was a no-op. Wire it to the global
  // command palette so it matches the ⌘K shortcut advertised on the badge.
  const { openPalette } = useCommandPalette()

  // Stat cards — color pair is a foreground token (icon) + backdrop token
  // (icon tile). Kept short so the JSX below can stay readable.
  const [stats, setStats] = useState<StatCard[]>([
    { label: 'Total Patients', value: 0, change: '', icon: Users, color: 'text-primary-700 bg-primary-50' },
    { label: "Today's Appointments", value: 0, change: '', icon: Calendar, color: 'text-accent-700 bg-accent-50' },
    { label: 'Pending Reports', value: 0, change: '', icon: FileText, color: 'text-severity-moderate bg-amber-50' },
    { label: 'AI Alerts', value: 0, change: '', icon: TrendingUp, color: 'text-severity-critical bg-red-50' },
  ])

  useEffect(() => { fetchAlerts() }, [fetchAlerts])
  useEffect(() => { fetchPatients() }, [fetchPatients])

  useEffect(() => {
    if (lastEvent?.type === 'risk_alert' && lastEvent.data) {
      pushAlert(lastEvent.data as RiskAlert)
    }
  }, [lastEvent, pushAlert])

  useEffect(() => {
    const today = new Date().toISOString().split('T')[0]
    fetchAppointments(today, today)
  }, [fetchAppointments])

  useEffect(() => {
    const totalPatients = patients.length
    const todayAppointments = appointments.filter(a => a.status === 'scheduled' || a.status === 'confirmed').length
    const criticalAlerts = alerts.filter(a => a.severity > 0.7).length

    setStats([
      {
        label: 'Total Patients',
        value: totalPatients,
        change: totalPatients > 0 ? 'Active' : 'No patients yet',
        icon: Users,
        color: 'text-primary-700 bg-primary-50',
      },
      {
        label: "Today's Appointments",
        value: todayAppointments,
        change: todayAppointments > 0 ? `${todayAppointments} scheduled` : 'No appointments',
        icon: Calendar,
        color: 'text-accent-700 bg-accent-50',
      },
      { label: 'Pending Reports', value: 0, change: 'No data', icon: FileText, color: 'text-severity-moderate bg-amber-50' },
      {
        label: 'AI Alerts',
        value: alerts.length,
        change: criticalAlerts > 0 ? `${criticalAlerts} high priority` : alerts.length > 0 ? 'All normal' : 'No alerts',
        icon: TrendingUp,
        color: 'text-severity-critical bg-red-50',
      },
    ])
  }, [patients.length, appointments.length, alerts.length])

  // Quick actions — the primary lives up top (teal-600), the rest use the
  // accent + neutral variants so the eye lands on "New Patient" first.
  const quickActions = [
    { label: 'New Patient', icon: Plus, href: '/patients/new', color: 'bg-primary-600 hover:bg-primary-700' },
    { label: 'Upload Document', icon: FileText, href: '/scratchpad', color: 'bg-accent-600 hover:bg-accent-700' },
    { label: "Today's Calendar", icon: Calendar, href: '/calendar', color: 'bg-primary-700 hover:bg-primary-800' },
    { label: 'Voice Scheduling', icon: Mic, href: '/calendar?voice=true', color: 'bg-severity-low hover:brightness-95' },
  ]

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-strong-fg tracking-tight">Dashboard</h1>
          <p className="text-muted-fg mt-1 text-sm">Welcome back{user?.name ? `, Dr. ${user.name.split(' ').slice(-1)[0]}` : ''}. Here's your practice overview.</p>
        </div>
        <div className="flex items-center gap-2">
          {/* D-1 (AUDIT.md): open the global command palette instead of no-op. */}
          <button className="btn-outline" onClick={openPalette} aria-label="Open search (⌘K)">
            <Search className="h-4 w-4 mr-2" />
            Search
            <kbd className="ml-1.5 px-1.5 py-0.5 text-[11px] bg-surface border border-border rounded font-medium">⌘K</kbd>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <Card key={stat.label} className="transition-shadow hover:shadow-card-hover">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="vital-label">{stat.label}</p>
                  <p className="text-vital-md text-strong-fg mt-1 tnum">{stat.value}</p>
                  <p className="text-xs text-muted-fg mt-1">{stat.change}</p>
                </div>
                <div className={cn('p-3 rounded-lg', stat.color.split(' ').find(c => c.startsWith('bg-')))}>
                  <stat.icon className={cn('h-5 w-5', stat.color.split(' ').find(c => c.startsWith('text-')))} />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Proactive Risk Alerts */}
      {alerts.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-severity-critical" />
              Proactive Risk Alerts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <RiskAlertsPanel alerts={alerts} loading={false} />
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Stethoscope className="h-5 w-5 text-primary-600" />
              Quick Actions
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {quickActions.map((action) => (
              <a
                key={action.label}
                href={action.href}
                className={cn('flex items-center gap-3 w-full p-3 rounded-lg text-white transition-colors', action.color)}
              >
                <action.icon className="h-5 w-5" />
                <span className="font-medium">{action.label}</span>
              </a>
            ))}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Patients</CardTitle>
            <a href="/patients" className="text-sm font-medium text-primary-700 hover:underline">View all →</a>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {patients.length === 0 ? (
                <div className="text-center py-8">
                  <Users className="h-8 w-8 text-muted-fg/50 mx-auto mb-2" />
                  <p className="text-sm text-muted-fg mb-2">No patients yet.</p>
                  <a
                    href="/patients/new"
                    className="text-sm font-medium text-primary-700 hover:underline"
                  >
                    Add your first patient →
                  </a>
                </div>
              ) : (
                patients.slice(0, 5).map((patient) => {
                  const latestState = patient.head_version?.state_jsonb
                  const demo = latestState?.demographics ?? {}
                  const name = demo.name ?? `Patient ${patient.id.slice(0, 8)}`
                  const initials = String(name).split(' ').filter(Boolean).map((n: string) => n[0]).slice(0, 2).join('').toUpperCase()
                  const lastVisit = patient.updated_at
                    ? new Date(patient.updated_at).toLocaleDateString()
                    : 'Never'
                  return (
                    <div
                      key={patient.id}
                      className="flex items-center justify-between p-2.5 rounded-md hover:bg-surface transition-colors cursor-pointer"
                      onClick={() => window.location.href = `/patients/${patient.id}`}
                      {...prefetchPatient(patient.id)}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/40 flex-shrink-0">
                          <span className="text-xs font-semibold text-primary-700 dark:text-primary-200 tracking-tight">
                            {initials || '?'}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium text-sm text-strong-fg truncate">{name}</p>
                          <p className="text-xs text-muted-fg">
                            {demo.age ? `${demo.age}y` : '?y'} · Last visit {lastVisit}
                          </p>
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary-600" />
            AI Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-fg">
            Connect the weekly report and trajectory clustering endpoints to populate insights.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
