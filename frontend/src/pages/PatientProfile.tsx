'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Loader2, Save, CheckCircle, AlertCircle, User } from 'lucide-react'
import { apiClient } from '@/services/api'

interface UserProfile {
  id: string
  email: string
  name: string
  phone: string
  dob: string | null
  gender: string | null
  address: string | null
  blood_group: string | null
  allergies: string | null
  known_conditions: string | null
  height_cm: number | null
  weight_kg: number | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  insurance_info: string | null
  profile_complete: boolean
}

export function PatientProfile() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const res = await apiClient.get('/patient/me/profile')
        setProfile(res.data)
      } catch {
        setError('Failed to load profile')
      } finally {
        setLoading(false)
      }
    }
    fetchProfile()
  }, [])

  const updateField = (field: string, value: string | number | null) => {
    if (!profile) return
    setProfile({ ...profile, [field]: value })
  }

  const handleSave = async () => {
    if (!profile) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await apiClient.put('/patient/me/profile', {
        name: profile.name,
        phone: profile.phone,
        dob: profile.dob,
        gender: profile.gender,
        address: profile.address,
        blood_group: profile.blood_group,
        allergies: profile.allergies,
        known_conditions: profile.known_conditions,
        height_cm: profile.height_cm,
        weight_kg: profile.weight_kg,
        emergency_contact_name: profile.emergency_contact_name,
        emergency_contact_phone: profile.emergency_contact_phone,
        insurance_info: profile.insurance_info,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {
      setError('Failed to save profile')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="p-8 text-center text-red-600">
        <AlertCircle className="h-6 w-6 mx-auto mb-2" />
        Failed to load profile
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5 text-primary-600" />
            Personal Information
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Full Name</Label>
              <Input value={profile.name} onChange={e => updateField('name', e.target.value)} />
            </div>
            <div>
              <Label>Email</Label>
              <Input value={profile.email} disabled className="bg-gray-50 dark:bg-gray-800" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Phone</Label>
              <Input value={profile.phone} onChange={e => updateField('phone', e.target.value)} />
            </div>
            <div>
              <Label>Date of Birth</Label>
              <Input type="date" value={profile.dob ? profile.dob.split('T')[0] : ''} onChange={e => updateField('dob', e.target.value || null)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Gender</Label>
              <select value={profile.gender || ''} onChange={e => updateField('gender', e.target.value || null)} className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm">
                <option value="">Select</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <Label>Blood Group *</Label>
              <select value={profile.blood_group || ''} onChange={e => updateField('blood_group', e.target.value || null)} className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm" required>
                <option value="">Select</option>
                <option value="A+">A+</option>
                <option value="A-">A-</option>
                <option value="B+">B+</option>
                <option value="B-">B-</option>
                <option value="AB+">AB+</option>
                <option value="AB-">AB-</option>
                <option value="O+">O+</option>
                <option value="O-">O-</option>
              </select>
            </div>
          </div>
          <div>
            <Label>Address</Label>
            <Input value={profile.address || ''} onChange={e => updateField('address', e.target.value || null)} placeholder="Full address" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Medical Profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Height (cm)</Label>
              <Input type="number" value={profile.height_cm || ''} onChange={e => updateField('height_cm', e.target.value ? Number(e.target.value) : null)} placeholder="170" />
            </div>
            <div>
              <Label>Weight (kg)</Label>
              <Input type="number" value={profile.weight_kg || ''} onChange={e => updateField('weight_kg', e.target.value ? Number(e.target.value) : null)} placeholder="70" />
            </div>
          </div>
          <div>
            <Label>Allergies</Label>
            <textarea
              value={profile.allergies || ''}
              onChange={e => updateField('allergies', e.target.value || null)}
              rows={2}
              className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm resize-none"
              placeholder="e.g. Penicillin, Peanuts"
            />
          </div>
          <div>
            <Label>Known Conditions</Label>
            <textarea
              value={profile.known_conditions || ''}
              onChange={e => updateField('known_conditions', e.target.value || null)}
              rows={2}
              className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm resize-none"
              placeholder="e.g. Diabetes, Hypertension"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Emergency Contact & Insurance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Emergency Contact Name</Label>
              <Input value={profile.emergency_contact_name || ''} onChange={e => updateField('emergency_contact_name', e.target.value || null)} />
            </div>
            <div>
              <Label>Emergency Contact Phone</Label>
              <Input value={profile.emergency_contact_phone || ''} onChange={e => updateField('emergency_contact_phone', e.target.value || null)} />
            </div>
          </div>
          <div>
            <Label>Insurance Info</Label>
            <Input value={profile.insurance_info || ''} onChange={e => updateField('insurance_info', e.target.value || null)} placeholder="Provider + Policy number" />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {saved && (
          <div className="flex items-center gap-1 text-sm text-green-600">
            <CheckCircle className="h-4 w-4" /> Saved
          </div>
        )}
        <Button onClick={handleSave} disabled={saving} className="ml-auto">
          {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
          Save Profile
        </Button>
      </div>
    </div>
  )
}
