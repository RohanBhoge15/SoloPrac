import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Calendar, FileText, Search, Mic, Plus, Users, Stethoscope, TrendingUp } from 'lucide-react'

export function Dashboard() {
  const stats = [
    { label: 'Total Patients', value: '127', change: '+12%', icon: Users, color: 'text-blue-600 bg-blue-100' },
    { label: "Today's Appointments", value: '8', change: '3 pending', icon: Calendar, color: 'text-green-600 bg-green-100' },
    { label: 'Pending Reports', value: '5', change: '2 overdue', icon: FileText, color: 'text-orange-600 bg-orange-100' },
    { label: 'AI Alerts', value: '3', change: '1 high priority', icon: TrendingUp, color: 'text-red-600 bg-red-100' },
  ]

  const quickActions = [
    { label: 'New Patient', icon: Plus, href: '/patients/new', color: 'bg-primary-600 hover:bg-primary-700' },
    { label: 'Upload Document', icon: FileText, href: '/scratchpad', color: 'bg-green-600 hover:bg-green-700' },
    { label: 'Today\'s Calendar', icon: Calendar, href: '/calendar', color: 'bg-blue-600 hover:bg-blue-700' },
    { label: 'Voice Scheduling', icon: Mic, href: '/calendar?voice=true', color: 'bg-purple-600 hover:bg-purple-700' },
  ]

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Page Header */}
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

      {/* Stats Grid */}
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

      {/* Quick Actions + Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Quick Actions */}
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
                className={cn(
                  'flex items-center gap-3 w-full p-3 rounded-lg text-white transition-colors',
                  action.color
                )}
              >
                <action.icon className="h-5 w-5" />
                <span className="font-medium">{action.label}</span>
              </a>
            ))}
          </CardContent>
        </Card>

        {/* Recent Patients */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Patients</CardTitle>
            <a href="/patients" className="text-sm text-primary-600 hover:underline">View all</a>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[
                { name: 'Priya Sharma', age: 45, lastVisit: '2 days ago', status: 'Follow-up needed', color: 'badge-warning' },
                { name: 'Rajesh Kumar', age: 32, lastVisit: 'Yesterday', status: 'Stable', color: 'badge-success' },
                { name: 'Anita Patel', age: 58, lastVisit: '1 week ago', status: 'BP elevated', color: 'badge-danger' },
                { name: 'Mohammed Ali', age: 28, lastVisit: 'Today', status: 'New patient', color: 'badge-primary' },
                { name: 'Sunita Devi', age: 41, lastVisit: '3 days ago', status: 'Diabetes review', color: 'badge-warning' },
              ].map((patient) => (
                <div key={patient.name} className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                      <span className="text-sm font-medium text-primary-700 dark:text-primary-300">
                        {patient.name.split(' ').map(n => n[0]).join('')}
                      </span>
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{patient.name}</p>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{patient.age} years • Last visit: {patient.lastVisit}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={cn('badge', patient.color)}>{patient.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Insights */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary-600" />
            AI Insights This Week
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
              <p className="font-medium text-blue-900 dark:text-blue-100">Diabetes Trend Alert</p>
              <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">{"3 patients show HbA1c rising >0.5% in 90 days. Consider medication review."}</p>
              <button className="mt-2 text-sm text-blue-600 dark:text-blue-400 hover:underline">View patients</button>
            </div>
            <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
              <p className="font-medium text-green-900 dark:text-green-100">Wound Healing Progress</p>
              <p className="text-sm text-green-700 dark:text-green-300 mt-1">Mrs. Sharma's wound shows 34% area reduction over 14 days. Edges approximating well.</p>
              <button className="mt-2 text-sm text-green-600 dark:text-green-400 hover:underline">View comparison</button>
            </div>
            <div className="p-4 rounded-lg bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800">
              <p className="font-medium text-yellow-900 dark:text-yellow-100">Missed Follow-ups</p>
              <p className="text-sm text-yellow-700 dark:text-yellow-300 mt-1">5 patients overdue for 3-month diabetes review. Auto-reminders sent.</p>
              <button className="mt-2 text-sm text-yellow-600 dark:text-yellow-400 hover:underline">Send manual reminders</button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}