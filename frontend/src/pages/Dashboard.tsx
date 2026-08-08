import { useEffect, useState } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Calendar, FileText, Search, Mic, Plus, Users, Stethoscope, TrendingUp, AlertTriangle } from 'lucide-react'
import { RiskAlertsPanel } from '@/components/RiskAlerts'
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

  const [stats, setStats] = useState<StatCard[]>([
    { label: 'Total Patients', value: 0, change: '', icon: Users, color: 'text-blue-600 bg-blue-100' },
    { label: "Today's Appointments", value: 0, change: '', icon: Calendar, color: 'text-green-600 bg-green-100' },
    { label: 'Pending Reports', value: 0, change: '', icon: FileText, color: 'text-orange-600 bg-orange-100' },
    { label: 'AI Alerts', value: 0, change: '', icon: TrendingUp, color: 'text-red-600 bg-red-100' },
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
    const todayAppointments = appointments.filter(a => a.status === 'scheduled').length
    const criticalAlerts = alerts.filter(a => a.severity > 0.7).length

    setStats([
      {
        label: 'Total Patients',
        value: totalPatients,
        change: totalPatients > 0 ? 'Active' : 'No patients yet',
        icon: Users,
        color: 'text-blue-600 bg-blue-100',
      },
      {
        label: "Today's Appointments",
        value: todayAppointments,
        change: todayAppointments > 0 ? `${todayAppointments} scheduled` : 'No appointments',
        icon: Calendar,
        color: 'text-green-600 bg-green-100',
      },
      { label: 'Pending Reports', value: 0, change: 'No data', icon: FileText, color: 'text-orange-600 bg-orange-100' },
      {
        label: 'AI Alerts',
        value: alerts.length,
        change: criticalAlerts > 0 ? `${criticalAlerts} high priority` : alerts.length > 0 ? 'All normal' : 'No alerts',
        icon: TrendingUp,
        color: 'text-red-600 bg-red-100',
      },
    ])
  }, [patients.length, appointments.length, alerts.length])

  const quickActions = [
    { label: 'New Patient', icon: Plus, href: '/patients/new', color: 'bg-primary-600 hover:bg-primary-700' },
    { label: 'Upload Document', icon: FileText, href: '/scratchpad', color: 'bg-green-600 hover:bg-green-700' },
    { label: "Today's Calendar", icon: Calendar, href: '/calendar', color: 'bg-blue-600 hover:bg-blue-700' },
    { label: 'Voice Scheduling', icon: Mic, href: '/calendar?voice=true', color: 'bg-purple-600 hover:bg-purple-700' },
  ]

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Welcome back! Here's your practice overview.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-outline" onClick={() => {}}>
            <Search className="h-4 w-4 mr-2" />
            Search
            <kbd className="ml-1.5 px-1.5 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 rounded">⌘K</kbd>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <Card key={stat.label} className="card-hover">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{stat.label}</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{stat.value}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{stat.change}</p>
                </div>
                <div className={cn('p-3 rounded-xl', stat.color.replace('text-', 'bg-').replace('bg-', 'bg-').replace('600', '100').replace('500', '100'))}>
                  <stat.icon className={cn('h-5 w-5', stat.color)} />
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
              <AlertTriangle className="h-5 w-5 text-red-600" />
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
            <a href="/patients" className="text-sm text-primary-600 hover:underline">View all</a>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {patients.length === 0 ? (
                <p className="text-center text-gray-500 dark:text-gray-400 py-8">
                  No patients yet. <a href="/patients/new" className="text-primary-600 underline">Add your first patient</a>
                </p>
              ) : (
                patients.slice(0, 5).map((patient) => {
                  const latestState = patient.head_version?.state_jsonb
                  const demo = latestState?.demographics ?? {}
                  const name = demo.name ?? `Patient ${patient.id.slice(0, 8)}`
                  const lastVisit = patient.updated_at
                    ? new Date(patient.updated_at).toLocaleDateString()
                    : 'Never'
                  return (
                    <div
                      key={patient.id}
                      className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                      onClick={() => window.location.href = `/patients/${patient.id}`}
                      {...prefetchPatient(patient.id)}
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                          <span className="text-sm font-medium text-primary-700 dark:text-primary-300">
                            {name.split(' ').map(n => n[0]).join('')}
                          </span>
                        </div>
                        <div>
                          <p className="font-medium text-gray-900 dark:text-white">{name}</p>
                          <p className="text-sm text-gray-500 dark:text-gray-400">{demo.age ?? '?'} years • Last visit: {lastVisit}</p>
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
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Connect the weekly report and trajectory clustering endpoints to populate insights.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
