import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Loader2, User, Mail, Lock, Phone, MapPin, Calendar, ArrowRight } from 'lucide-react'
import { apiClient } from '@/services/api'

export function PatientRegistration() {
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    phone: '',
    dob: '',
    gender: '',
    address: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateField = (field: string, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (form.password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setLoading(true)
    try {
      await apiClient.post('/public/auth/register', {
        name: form.name,
        email: form.email,
        password: form.password,
        phone: form.phone,
        dob: form.dob,
        gender: form.gender,
        address: form.address,
      })
      // No localStorage - HttpOnly cookies are set by backend
      window.location.href = '/patient/dashboard'
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-6">
          <Link to="/" className="inline-flex items-center gap-2 text-2xl font-bold text-primary-600 dark:text-primary-400">
            <User className="h-8 w-8" />
            SoloPrac AI
          </Link>
          <p className="mt-2 text-muted-fg">Patient portal</p>
        </div>

        <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary-600">
              <User className="h-6 w-6 text-white" />
            </div>
          </div>
          <CardTitle className="text-lg">Patient Registration</CardTitle>
          <p className="text-sm text-gray-500">Create your account to book appointments</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-3">
            {error && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
                {error}
              </div>
            )}

            <div>
              <Label htmlFor="name">Full Name *</Label>
              <Input id="name" value={form.name} onChange={e => updateField('name', e.target.value)} placeholder="John Doe" required disabled={loading} />
            </div>

            <div>
              <Label htmlFor="email">Email *</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <Input id="email" type="email" value={form.email} onChange={e => updateField('email', e.target.value)} placeholder="john@example.com" className="pl-9" required disabled={loading} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="password">Password *</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <Input id="password" type="password" value={form.password} onChange={e => updateField('password', e.target.value)} placeholder="Min 8 chars" className="pl-9" required disabled={loading} />
                </div>
              </div>
              <div>
                <Label htmlFor="confirmPassword">Confirm *</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <Input id="confirmPassword" type="password" value={form.confirmPassword} onChange={e => updateField('confirmPassword', e.target.value)} placeholder="Re-enter" className="pl-9" required disabled={loading} />
                </div>
              </div>
            </div>

            <div>
              <Label htmlFor="phone">Phone *</Label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <Input id="phone" type="tel" value={form.phone} onChange={e => updateField('phone', e.target.value)} placeholder="+91-9876543210" className="pl-9" required disabled={loading} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="dob">Date of Birth *</Label>
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <Input id="dob" type="date" value={form.dob} onChange={e => updateField('dob', e.target.value)} className="pl-9" required disabled={loading} />
                </div>
              </div>
              <div>
                <Label htmlFor="gender">Gender *</Label>
                <select
                  id="gender"
                  value={form.gender}
                  onChange={e => updateField('gender', e.target.value)}
                  className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
                  required
                  disabled={loading}
                >
                  <option value="">Select</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>

            <div>
              <Label htmlFor="address">Address *</Label>
              <div className="relative">
                <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <Input id="address" value={form.address} onChange={e => updateField('address', e.target.value)} placeholder="Full address" className="pl-9" required disabled={loading} />
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Create Account
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-gray-500">
            Already have an account?{' '}
            <Link to="/patient/login" className="text-primary-600 hover:underline">Sign in</Link>
          </p>
        </CardContent>
      </Card>
      </div>
    </div>
  )
}
