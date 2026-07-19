import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { apiClient } from '@/services/api'
import { User, Bell, Shield, Calendar, CreditCard, Loader2, CheckCircle } from 'lucide-react'

export function Settings() {
  const [activeTab, setActiveTab] = useState('profile')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  return (
    <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
      <TabsList className="grid w-full grid-cols-5">
        <TabsTrigger value="profile"><User className="h-4 w-4 mr-2" />Profile</TabsTrigger>
        <TabsTrigger value="notifications"><Bell className="h-4 w-4 mr-2" />Notifications</TabsTrigger>
        <TabsTrigger value="schedule"><Calendar className="h-4 w-4 mr-2" />Schedule</TabsTrigger>
        <TabsTrigger value="security"><Shield className="h-4 w-4 mr-2" />Security</TabsTrigger>
        <TabsTrigger value="billing"><CreditCard className="h-4 w-4 mr-2" />Billing</TabsTrigger>
      </TabsList>

      <TabsContent value="profile" className="space-y-6 mt-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><User className="h-5 w-5" />Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="name">Full Name</Label>
                <Input id="name" defaultValue="Dr. Rohan Bhoge" />
              </div>
              <div>
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" defaultValue="rohan.bhoge15@gmail.com" />
              </div>
              <div>
                <Label htmlFor="speciality">Speciality</Label>
                <Input id="speciality" defaultValue="General Practice" />
              </div>
              <div>
                <Label htmlFor="registration">Registration Number</Label>
                <Input id="registration" defaultValue="MH-12345" />
              </div>
              <div>
                <Label htmlFor="clinic">Clinic Name</Label>
                <Input id="clinic" defaultValue="Bhoge Clinic" />
              </div>
              <div>
                <Label htmlFor="address">Clinic Address</Label>
                <Input id="address" defaultValue="Aundh, Pune" />
              </div>
            </div>
            <Button onClick={() => { setSaving(true); setTimeout(() => { setSaving(false); setSaved(true); setTimeout(() => setSaved(false), 3000) }, 1000) }} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : saved ? (
                'Saved!'
              ) : (
                'Save Changes'
              )}
            </Button>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="notifications" className="space-y-6 mt-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Bell className="h-5 w-5" />Notification Preferences</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              { key: 'appointment_reminder', label: 'Appointment Reminders', defaultHours: 2, channels: ['in_app', 'email'] },
              { key: 'new_report', label: 'New Report Available', defaultHours: 0, channels: ['in_app', 'email'] },
              { key: 'invoice_generated', label: 'Invoice Generated', defaultHours: 0, channels: ['in_app'] },
              { key: 'booking_confirmation', label: 'Booking Confirmations', defaultHours: 0, channels: ['in_app', 'email'] },
              { key: 'reschedule_notification', label: 'Reschedule Notifications', defaultHours: 0, channels: ['in_app', 'email'] },
              { key: 'certificate_issued', label: 'Certificate Issued', defaultHours: 0, channels: ['in_app'] },
            ].map((n) => (
              <div key={n.key} className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{n.label}</p>
                    <p className="text-sm text-gray-500">
                      {n.defaultHours > 0 ? (n.defaultHours + "h before") : "immediately"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {n.channels.includes('in_app') && <Badge variant="default">In-App</Badge>}
                    {n.channels.includes('email') && <Badge variant="secondary">Email</Badge>}
                  </div>
                </div>
              </div>
            ))}
            <Button>Save Preferences</Button>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="schedule" className="space-y-6 mt-6">
        <ScheduleTab />
      </TabsContent>

      <TabsContent value="security" className="space-y-6 mt-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Shield className="h-5 w-5" />Security</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="outline" onClick={() => {}}>Change Password</Button>
            <Button variant="outline" onClick={() => {}}>Enable Two-Factor Authentication</Button>
            <Button variant="outline" onClick={() => {}}>View Active Sessions</Button>
            <Button variant="outline" onClick={() => {}}>Export My Data</Button>
            <Button variant="destructive" onClick={() => {}}>Delete Account</Button>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="billing" className="space-y-6 mt-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><CreditCard className="h-5 w-5" />Billing & Usage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
              <p className="font-medium text-green-900 dark:text-green-100">Free Tier Active</p>
              <p className="text-sm text-green-700 dark:text-green-300">You're on the free tier. No charges will apply.</p>
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                <p className="text-2xl font-bold text-primary-600">0</p>
                <p className="text-sm text-gray-500">API Calls This Month</p>
              </div>
              <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                <p className="text-2xl font-bold text-primary-600">0</p>
                <p className="text-sm text-gray-500">Patients</p>
              </div>
              <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                <p className="text-2xl font-bold text-primary-600">₹0</p>
                <p className="text-sm text-gray-500">Total Billed</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  )
}

function ScheduleTab() {
  const [buffer, setBuffer] = useState(5)
  const [duration, setDuration] = useState(20)
  const [hours, setHours] = useState<Record<string, { start: string; end: string; enabled: boolean }>>({
    monday: { start: '09:00', end: '13:00', enabled: true },
    tuesday: { start: '09:00', end: '13:00', enabled: true },
    wednesday: { start: '09:00', end: '13:00', enabled: true },
    thursday: { start: '09:00', end: '13:00', enabled: true },
    friday: { start: '09:00', end: '13:00', enabled: true },
    saturday: { start: '09:00', end: '12:00', enabled: false },
    sunday: { start: '', end: '', enabled: false },
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  const dayNames: Record<string, string> = { monday: 'Monday', tuesday: 'Tuesday', wednesday: 'Wednesday', thursday: 'Thursday', friday: 'Friday', saturday: 'Saturday', sunday: 'Sunday' }

  useEffect(() => {
    apiClient.get('/api/v1/calendar/working-hours').then(r => {
      const data = r.data
      setBuffer(data.buffer_minutes || 5)
      setDuration(data.default_duration || 20)
      const wh = data.working_hours_json || {}
      if (Object.keys(wh).length > 0) {
        setHours(prev => {
          const updated = { ...prev }
          Object.entries(wh).forEach(([day, windows]: [string, any]) => {
            if (updated[day] && Array.isArray(windows) && windows.length > 0) {
              updated[day] = { start: windows[0][0] || '', end: windows[0][1] || '', enabled: true }
            }
          })
          return updated
        })
      }
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const workingHoursJson: Record<string, string[][]> = {}
      Object.entries(hours).forEach(([day, h]) => {
        if (h.enabled && h.start && h.end) workingHoursJson[day] = [[h.start, h.end]]
      })
      await apiClient.put('/api/v1/calendar/working-hours', {
        working_hours_json: workingHoursJson,
        buffer_minutes: buffer,
        default_duration: duration,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch { alert('Failed to save. Check console.') }
    finally { setSaving(false) }
  }

  if (loading) return <div className="text-center py-8 text-gray-500"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Calendar className="h-5 w-5" />Working Hours</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(hours).map(([day, h]) => (
            <div key={day} className="flex items-center gap-2 p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <input type="checkbox" checked={h.enabled} onChange={e => setHours(prev => ({ ...prev, [day]: { ...prev[day], enabled: e.target.checked } }))} className="mr-1 accent-primary-600" />
              <span className="w-20 text-sm font-medium">{dayNames[day]}</span>
              {h.enabled ? (
                <><Input type="time" value={h.start} onChange={e => setHours(prev => ({ ...prev, [day]: { ...prev[day], start: e.target.value } }))} className="w-24 text-sm" />
                <span className="text-gray-400 text-sm">-</span>
                <Input type="time" value={h.end} onChange={e => setHours(prev => ({ ...prev, [day]: { ...prev[day], end: e.target.value } }))} className="w-24 text-sm" /></>
              ) : <span className="text-xs text-gray-400 ml-2">Day off</span>}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <Label htmlFor="buffer" className="text-sm">Buffer (min):</Label>
          <Input id="buffer" type="number" min={0} max={60} value={buffer} onChange={e => setBuffer(Number(e.target.value))} className="w-20" />
          <Label htmlFor="duration" className="text-sm ml-4">Duration (min):</Label>
          <Input id="duration" type="number" min={5} max={120} value={duration} onChange={e => setDuration(Number(e.target.value))} className="w-20" />
        </div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : saved ? <><CheckCircle className="h-4 w-4 mr-2 text-green-500" /> Saved!</> : 'Save Schedule'}
        </Button>
      </CardContent>
    </Card>
  )
}