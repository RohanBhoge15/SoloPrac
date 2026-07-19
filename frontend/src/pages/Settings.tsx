import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { Badge } from '@/components/ui/Badge'
import { User, Bell, Shield, Calendar, CreditCard } from 'lucide-react'
import { useState } from 'react'

export function Settings() {
  const [activeTab, setActiveTab] = useState('profile')

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
            <Button>Save Changes</Button>
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
                      Sent {n.defaultHours > 0 ? (n.defaultHours + "h before") : 'immediately'}
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
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Calendar className="h-5 w-5" />Working Hours</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((day) => (
                <div key={day} className="flex items-center gap-2 p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                  <span className="w-24 font-medium">{day}</span>
                  <Input type="time" defaultValue={['Saturday', 'Sunday'].includes(day) ? '' : '09:00'} className="w-24" />
                  <span className="text-gray-400">-</span>
                  <Input type="time" defaultValue={['Saturday', 'Sunday'].includes(day) ? '' : '13:00'} className="w-24" />
                </div>
              ))}
            </div>
            <div className="flex items-center gap-4">
              <Label htmlFor="buffer">Buffer between consultations (min)</Label>
              <Input id="buffer" type="number" defaultValue={5} className="w-20" />
            </div>
            <div className="flex items-center gap-4">
              <Label htmlFor="duration">Default consultation duration (min)</Label>
              <Input id="duration" type="number" defaultValue={20} className="w-20" />
            </div>
            <Button>Save Schedule</Button>
          </CardContent>
        </Card>
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