import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import { Mail, Lock, Stethoscope, AlertCircle } from 'lucide-react'

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login, devLogin } = useAuth()
  const navigate = useNavigate()

const handleDevLogin = async () => {
  setError('')
  setLoading(true)
  try {
    await devLogin()
    navigate('/')
  } catch (err: any) {
      setError(err.response?.data?.detail || 'Dev login failed')
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4 py-8">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 text-2xl font-bold text-primary-600 hover:text-primary-700 transition-colors">
            <div className="h-9 w-9 rounded-lg bg-primary-600 flex items-center justify-center shadow-sm">
              <Stethoscope className="h-5 w-5 text-white" />
            </div>
            SoloPrac AI
          </Link>
          <p className="mt-2 text-sm text-muted-fg">Sign in to your clinical workspace</p>
        </div>

        {/* Login Card */}
        <Card className="p-6 shadow-card-elevated">
          {error && (
            <div className="mb-4 flex items-center gap-2 p-3 bg-critical-subtle border border-critical/15 rounded-lg text-red-700 dark:text-red-300 text-sm" role="alert">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="label">Email</label>
              <div className="relative mt-1">
                <Mail className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="doctor@clinic.com"
                  className="pl-10"
                  required
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="label">Password</label>
              <div className="relative mt-1">
                <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="pl-10"
                  required
                  disabled={loading}
                />
              </div>
            </div>

            <Button type="submit" className="w-full" loading={loading}>
              Sign in
            </Button>
          </form>

          {import.meta.env.DEV && (
            <Button
              variant="outline"
              className="w-full mt-4 border-dashed border-amber-400 text-amber-700 dark:text-amber-400"
              onClick={handleDevLogin}
              disabled={loading}
            >
              Dev login (doctor)
            </Button>
          )}
        </Card>

        <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
          Don't have an account?{' '}
          <Link to="/register" className="text-primary-600 hover:underline">
            Register here
          </Link>
        </p>
      </div>
    </div>
  )
}
