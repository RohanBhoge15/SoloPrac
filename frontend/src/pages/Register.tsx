import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import { MapPicker } from '@/components/MapPicker'
import { Stethoscope, Mail, Lock, User, Phone, MapPin, Building, Loader2, AlertCircle } from 'lucide-react'

export function Register() {
  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    clinic_name: '',
    clinic_address: '',
    password: '',
    confirmPassword: '',
    latitude: null as number | null,
    longitude: null as number | null,
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const update = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (form.password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (form.latitude === null || form.longitude === null) {
      setError('Please pin your clinic location on the map so patients can find you')
      return
    }

    setLoading(true)
    try {
      const { confirmPassword: _ignored, ...payload } = form
      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Registration failed')
      }
      // Registration sets cookies, re-initialize auth
      await login(form.email, form.password)
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4 py-8">
      <div className="w-full max-w-xl">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 text-2xl font-bold text-primary-600 dark:text-primary-400">
            <Stethoscope className="h-8 w-8" />
            SoloPrac AI
          </Link>
          <p className="mt-2 text-gray-500 dark:text-gray-400">
            Create your clinical workspace
          </p>
        </div>

        {/* Registration Card */}
        <Card className="p-6">
          {error && (
            <div className="mb-4 flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Full Name</label>
              <div className="relative mt-1">
                <User className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  type="text"
                  value={form.name}
                  onChange={(e) => update('name', e.target.value)}
                  placeholder="Dr. Priya Sharma"
                  className="pl-10"
                  required
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
              <div className="relative mt-1">
                <Mail className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => update('email', e.target.value)}
                  placeholder="doctor@clinic.com"
                  className="pl-10"
                  required
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Phone</label>
              <div className="relative mt-1">
                <Phone className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  type="tel"
                  value={form.phone}
                  onChange={(e) => update('phone', e.target.value)}
                  placeholder="9876543210"
                  className="pl-10"
                  required
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Clinic Name</label>
              <div className="relative mt-1">
                <Building className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  type="text"
                  value={form.clinic_name}
                  onChange={(e) => update('clinic_name', e.target.value)}
                  placeholder="Sharma Clinic"
                  className="pl-10"
                  required
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Clinic Address</label>
              <div className="relative mt-1">
                <MapPin className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  type="text"
                  value={form.clinic_address}
                  onChange={(e) => update('clinic_address', e.target.value)}
                  placeholder="123 MG Road, Mumbai 400001"
                  className="pl-10"
                  required
                  disabled={loading}
                />
              </div>
            </div>

            {/* Geo-pin the clinic on a map so patients can find it via location search.
                Captured at signup because a doctor account is useless in patient search
                without coordinates. */}
            <div>
              <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
                <MapPin className="h-4 w-4 text-primary-500" />
                Pin your clinic on the map
              </label>
              <p className="mt-0.5 mb-2 text-xs text-gray-500 dark:text-gray-400">
                Click the map or search an address. Patients search by distance from your pin.
              </p>
              <MapPicker
                latitude={form.latitude}
                longitude={form.longitude}
                onChange={(lat, lng) => setForm(prev => ({ ...prev, latitude: lat, longitude: lng }))}
              />
              {form.latitude !== null && form.longitude !== null && (
                <p className="mt-1 text-[10px] text-green-600 dark:text-green-400">
                  ✓ Pinned at {form.latitude.toFixed(5)}, {form.longitude.toFixed(5)}
                </p>
              )}
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Password</label>
              <div className="relative mt-1">
                <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  type="password"
                  value={form.password}
                  onChange={(e) => update('password', e.target.value)}
                  placeholder="Min 8 characters"
                  className="pl-10"
                  required
                  minLength={8}
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Confirm Password</label>
              <div className="relative mt-1">
                <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  type="password"
                  value={form.confirmPassword}
                  onChange={(e) => update('confirmPassword', e.target.value)}
                  placeholder="Re-enter password"
                  className="pl-10"
                  required
                  minLength={8}
                  disabled={loading}
                />
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating account...
                </>
              ) : (
                'Create Account'
              )}
            </Button>
          </form>
        </Card>

        <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
          Already have an account?{' '}
          <Link to="/login" className="text-primary-600 hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
