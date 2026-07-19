import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Loader2, User, ArrowRight } from 'lucide-react'
import { apiClient } from '@/services/api'

export function PatientLogin() {
  const [mode, setMode] = useState<'login' | 'otp'>('login')
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSendOTP = async () => {
    if (!phone || phone.length < 10) return
    setLoading(true)
    setError(null)
    try {
      await apiClient.post('/api/public/auth/send-otp', { phone })
      setMode('otp')
    } catch {
      setError('Failed to send OTP. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyOTP = async () => {
    if (!otp || otp.length < 4) return
    setLoading(true)
    setError(null)
    try {
      const res = await apiClient.post('/api/public/auth/verify-otp', { phone, otp })
      localStorage.setItem('patient_token', res.data.token)
      localStorage.setItem('patient_id', res.data.patient_id)
      window.location.href = '/patient/dashboard'
    } catch {
      setError('Invalid or expired OTP')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary-600">
              <User className="h-6 w-6 text-white" />
            </div>
          </div>
          <CardTitle className="text-lg">Patient Login</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="phone">Phone Number</Label>
            <Input id="phone" value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91-9876543210" type="tel" disabled={mode === 'otp'} />
          </div>
          {mode === 'otp' && (
            <div>
              <Label htmlFor="otp">OTP</Label>
              <Input id="otp" value={otp} onChange={e => setOtp(e.target.value)} placeholder="Enter OTP" type="text" maxLength={6} />
            </div>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button
            className="w-full"
            onClick={mode === 'login' ? handleSendOTP : handleVerifyOTP}
            disabled={loading || (mode === 'login' ? phone.length < 10 : otp.length < 4)}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            {mode === 'login' ? 'Send OTP' : 'Login'}
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
          <p className="text-xs text-center text-gray-400">Use any 6-digit OTP for demo. Patient data is for demo purposes.</p>
        </CardContent>
      </Card>
    </div>
  )
}
