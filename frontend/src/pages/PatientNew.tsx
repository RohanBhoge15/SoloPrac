import { useState, FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { apiClient } from '@/services/api'
import { toast } from '@/components/ui/Toast'
import { ArrowLeft, Loader2, UserPlus, Info } from 'lucide-react'

// Manual "walk-in" patient creation. In India most patients don't self-register
// as app users, so the doctor types demographics and the backend creates a
// Patient row on the spot. If the same phone number later signs up as a User,
// backend auto-links (see create_patient in routers/patients.py — phone match
// against User.phone, bounded to 500-row scan).
export function PatientNew() {
  const navigate = useNavigate()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: '',
    phone: '',
    age: '',
    gender: '' as '' | 'male' | 'female' | 'other',
    address: '',
    notes: '',
  })

  const update = (k: keyof typeof form) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => setForm(prev => ({ ...prev, [k]: e.target.value }))

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      toast.error('Name is required')
      return
    }

    setSaving(true)
    try {
      // Backend expects PatientVersionCreate — state_jsonb.demographics is
      // the shape the rest of the app reads from (PatientDetail, timeline,
      // weekly report all pull name/phone/gender/age from here).
      const demographics: Record<string, unknown> = { name: form.name.trim() }
      if (form.phone.trim()) demographics.phone = form.phone.trim()
      if (form.age.trim()) {
        const n = parseInt(form.age.trim(), 10)
        if (!Number.isNaN(n) && n >= 0 && n <= 150) demographics.age = n
      }
      if (form.gender) demographics.gender = form.gender
      if (form.address.trim()) demographics.address = form.address.trim()

      const state_jsonb: Record<string, unknown> = { demographics }
      if (form.notes.trim()) state_jsonb.notes = form.notes.trim()

      const res = await apiClient.post('/patients', {
        state_jsonb,
        edit_type: 'manual',
        summary: `Manually added: ${form.name.trim()}`,
        tags: ['manual_entry'],
        clinical_significance: 0.3,
      })

      // Response is a PatientVersionRead — patient_id is the field we want.
      const patientId = res.data?.patient_id
      toast.success('Patient added', {
        description: form.phone.trim()
          ? 'If they sign up with this phone number, their account will auto-link.'
          : 'You can add a phone number later so their account auto-links on sign-up.',
      })
      if (patientId) {
        navigate(`/patients/${patientId}`)
      } else {
        navigate('/dashboard')
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to add patient'
      toast.error('Could not add patient', { description: String(msg).slice(0, 200) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4 animate-in fade-in duration-300">
      <div>
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5 text-primary-600" />
            Add new patient
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* Explainer for the walk-in flow — worth repeating on every entry
              so the doctor knows the phone number's role. */}
          <div className="mb-4 flex gap-2 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 p-3">
            <Info className="h-4 w-4 flex-shrink-0 text-blue-600 dark:text-blue-400 mt-0.5" />
            <p className="text-xs text-blue-800 dark:text-blue-200">
              Only the name is required. If you enter a phone number and the patient later signs
              up as a SoloPrac user with the same number, their account will be linked
              automatically — you don't have to do anything.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="name">
                Full name <span className="text-red-500">*</span>
              </Label>
              <Input
                id="name"
                value={form.name}
                onChange={update('name')}
                placeholder="e.g. Priya Sharma"
                autoFocus
                required
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="phone">Phone number</Label>
                <Input
                  id="phone"
                  type="tel"
                  value={form.phone}
                  onChange={update('phone')}
                  placeholder="e.g. 9876543210"
                  inputMode="tel"
                />
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                  Used for auto-linking if they sign up later
                </p>
              </div>
              <div>
                <Label htmlFor="age">Age</Label>
                <Input
                  id="age"
                  type="number"
                  min={0}
                  max={150}
                  value={form.age}
                  onChange={update('age')}
                  placeholder="e.g. 42"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="gender">Gender</Label>
              <select
                id="gender"
                value={form.gender}
                onChange={update('gender')}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
              >
                <option value="">Prefer not to say</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div>
              <Label htmlFor="address">Address</Label>
              <Input
                id="address"
                value={form.address}
                onChange={update('address')}
                placeholder="Optional — city or full address"
              />
            </div>

            <div>
              <Label htmlFor="notes">Initial notes</Label>
              <textarea
                id="notes"
                value={form.notes}
                onChange={update('notes')}
                placeholder="Optional — chief complaint, allergies, anything worth noting on day one"
                rows={3}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm resize-y"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate(-1)}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={saving || !form.name.trim()}>
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Adding…
                  </>
                ) : (
                  <>
                    <UserPlus className="h-4 w-4 mr-2" /> Add patient
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
