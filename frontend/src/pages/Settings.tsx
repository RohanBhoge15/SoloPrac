import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { apiClient } from '@/services/api'
import { MapPicker } from '@/components/MapPicker'
import { ImageCropModal } from '@/components/ImageCropModal'
import { User, Bell, Shield, Calendar, CreditCard, MapPin, Camera, Loader2, CheckCircle, AlertCircle, Star } from 'lucide-react'

// C-9 (Piece 6): validate the ?tab= deep-link. Without this the notification
// popover's "Manage notification preferences →" link always drops the user
// on the Profile tab.
const VALID_TABS = ['profile', 'notifications', 'schedule', 'security', 'billing'] as const

// Metadata for the currently-active tab header — icon, title, subtitle.
// Keeping it colocated so adding a new section is a one-line change.
const TAB_META: Record<
  typeof VALID_TABS[number],
  { icon: React.ComponentType<{ className?: string }>; title: string; subtitle: string }
> = {
  profile: { icon: User, title: 'Profile', subtitle: 'Your public profile and clinic details' },
  notifications: { icon: Bell, title: 'Notifications', subtitle: 'Choose which events reach you and how' },
  schedule: { icon: Calendar, title: 'Schedule', subtitle: 'Working hours and slot availability' },
  security: { icon: Shield, title: 'Security', subtitle: 'Password, sessions, and account safety' },
  billing: { icon: CreditCard, title: 'Billing', subtitle: 'Plan, invoices, and payment method' },
}

// Local override of TabsTrigger styling — the shared component uses
// background/foreground CSS variables that on the dark theme render the
// active tab almost invisibly. Bumping to a primary-tinted pill so the
// doctor can see at a glance which section they're on, without changing
// the shared component (other pages may prefer the subtler look).
const ACTIVE_TAB_CLASSES =
  'data-[state=active]:bg-primary-600 data-[state=active]:text-white data-[state=active]:shadow ' +
  'data-[state=inactive]:hover:bg-gray-200 data-[state=inactive]:dark:hover:bg-gray-700 ' +
  'transition-colors'

export function Settings() {
  const [searchParams] = useSearchParams()
  const initialTab = (() => {
    const q = searchParams.get('tab')
    return q && (VALID_TABS as readonly string[]).includes(q) ? q : 'profile'
  })()
  const [activeTab, setActiveTab] = useState(initialTab)
  const current = TAB_META[activeTab as typeof VALID_TABS[number]] ?? TAB_META.profile
  const CurrentIcon = current.icon

  return (
    <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
      {/* Section header — repeats the active tab's title / subtitle so the
          doctor always has an anchor telling them where they are, even after
          scrolling past the tab bar. */}
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
          <CurrentIcon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-strong-fg">Settings — {current.title}</h1>
          <p className="text-sm text-muted-fg">{current.subtitle}</p>
        </div>
      </div>

      <TabsList className="grid w-full grid-cols-5 h-11 p-1">
        <TabsTrigger value="profile" className={ACTIVE_TAB_CLASSES}><User className="h-4 w-4 mr-2" />Profile</TabsTrigger>
        <TabsTrigger value="notifications" className={ACTIVE_TAB_CLASSES}><Bell className="h-4 w-4 mr-2" />Notifications</TabsTrigger>
        <TabsTrigger value="schedule" className={ACTIVE_TAB_CLASSES}><Calendar className="h-4 w-4 mr-2" />Schedule</TabsTrigger>
        <TabsTrigger value="security" className={ACTIVE_TAB_CLASSES}><Shield className="h-4 w-4 mr-2" />Security</TabsTrigger>
        <TabsTrigger value="billing" className={ACTIVE_TAB_CLASSES}><CreditCard className="h-4 w-4 mr-2" />Billing</TabsTrigger>
      </TabsList>

      <TabsContent value="profile" className="space-y-6 mt-6">
        <ProfileTab />
      </TabsContent>

      <TabsContent value="notifications" className="space-y-6 mt-6">
        <NotificationsTab />
      </TabsContent>

      <TabsContent value="schedule" className="space-y-6 mt-6">
        <ScheduleTab />
      </TabsContent>

      <TabsContent value="security" className="space-y-6 mt-6">
        <SecurityTab />
      </TabsContent>

      <TabsContent value="billing" className="space-y-6 mt-6">
        <BillingTab />
      </TabsContent>
    </Tabs>
  )
}

function ProfileTab() {
  const [form, setForm] = useState({
    name: '',
    speciality: '',
    clinic_name: '',
    clinic_address: '',
    phone: '',
    registration_number: '',
    latitude: null as number | null,
    longitude: null as number | null,
  })
  const [original, setOriginal] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const [verificationStatus, setVerificationStatus] = useState('unverified')
  const [showCropModal, setShowCropModal] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [yearsExperience, setYearsExperience] = useState<number | null>(null)
  // Clinic branding
  const [clinicLogoUrl, setClinicLogoUrl] = useState<string | null>(null)
  const [signatureUrl, setSignatureUrl] = useState<string | null>(null)
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [uploadingSignature, setUploadingSignature] = useState(false)

  useEffect(() => {
    apiClient.get('/auth/me')
      .then(r => {
        const d = r.data
        const values = {
          name: d.name || '',
          speciality: d.speciality || '',
          clinic_name: d.clinic_name || '',
          clinic_address: d.clinic_address || '',
          phone: d.phone || '',
          registration_number: d.registration_number || '',
          latitude: d.latitude ?? null,
          longitude: d.longitude ?? null,
        }
        setForm(values)
        setOriginal(values)
        setPhotoUrl(d.photo_url || null)
        setVerificationStatus(d.verification_status || 'unverified')
        setYearsExperience(d.years_experience ?? null)
        setClinicLogoUrl(d.settings?.clinic_logo_url || null)
        setSignatureUrl(d.settings?.signature_url || null)
      })
      .catch(() => setError('Failed to load profile'))
      .finally(() => setLoading(false))
  }, [])

  const handleChange = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm(prev => ({ ...prev, [field]: e.target.value }))
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      // Only send changed fields
      const changes: Record<string, any> = {}
      Object.entries(form).forEach(([key, value]) => {
        if (value !== original[key]) {
          changes[key] = value
        }
      })
      if (Object.keys(changes).length === 0) {
        setSaving(false)
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
        return
      }
      await apiClient.put('/auth/me', changes)
      setOriginal({ ...form })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const hasChanges = Object.keys(form).some(k => (form as any)[k] !== (original as any)[k])

  const handlePhotoCropped = async (blob: Blob) => {
    setUploadingPhoto(true)
    try {
      const formData = new FormData()
      formData.append('file', blob, 'photo.jpg')
      const res = await apiClient.post('/auth/me/photo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setPhotoUrl(res.data.photo_url)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload photo')
    } finally {
      setUploadingPhoto(false)
    }
  }

  // ── Clinic logo + signature upload handlers ──
  // Both use the same POST-file / DELETE-file dance against
  // /auth/me/clinic-logo and /auth/me/signature.
  const uploadBrandingAsset = async (
    file: File,
    endpoint: '/auth/me/clinic-logo' | '/auth/me/signature',
    responseKey: 'clinic_logo_url' | 'signature_url',
    setUrl: (u: string | null) => void,
    setUploading: (b: boolean) => void,
  ) => {
    if (!file.type.startsWith('image/')) {
      setError('Please choose an image file (JPG, PNG, or WebP)')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      setError('File must be under 2MB')
      return
    }
    setUploading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await apiClient.post(endpoint, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUrl(res.data[responseKey])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) void uploadBrandingAsset(file, '/auth/me/clinic-logo', 'clinic_logo_url', setClinicLogoUrl, setUploadingLogo)
  }

  const handleSignatureUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) void uploadBrandingAsset(file, '/auth/me/signature', 'signature_url', setSignatureUrl, setUploadingSignature)
  }

  const handleLogoDelete = async () => {
    try {
      await apiClient.delete('/auth/me/clinic-logo')
      setClinicLogoUrl(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to remove logo')
    }
  }

  const handleSignatureDelete = async () => {
    try {
      await apiClient.delete('/auth/me/signature')
      setSignatureUrl(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to remove signature')
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-gray-400">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
          Loading profile...
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><User className="h-5 w-5" />Profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="p-3 rounded-lg bg-red-50 text-sm text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />{error}
          </div>
        )}

        {/* Verification + Photo Banner */}
        {verificationStatus !== 'verified' && (
          <div className="p-4 rounded-xl bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 border border-warning/15">
            <div className="flex items-start gap-3">
              <Shield className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-200">
                  Complete your profile to appear in patient search
                </p>
                <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                  Add your profile photo and submit your NMC verification to start receiving patient bookings.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Profile Photo */}
        <div className="flex items-center gap-4 p-4 bg-surface-3 rounded-xl">
          <div className="relative group">
            {photoUrl ? (
              <img
                src={photoUrl}
                alt="Profile"
                className="h-20 w-20 rounded-full object-cover border-2 border-white dark:border-gray-700 shadow-sm"
              />
            ) : (
              <div className="h-20 w-20 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center border-2 border-dashed border-gray-300 dark:border-gray-600">
                <Camera className="h-6 w-6 text-gray-400" />
              </div>
            )}
            <button
              onClick={() => setShowCropModal(true)}
              disabled={uploadingPhoto}
              className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
            >
              {uploadingPhoto ? (
                <Loader2 className="h-5 w-5 text-white animate-spin" />
              ) : (
                <Camera className="h-5 w-5 text-white" />
              )}
            </button>
          </div>
          <div>
            <p className="font-medium text-strong-fg">{form.name || 'Your Name'}</p>
            <p className="text-sm text-muted-fg">{form.speciality || 'Speciality'}</p>
            {yearsExperience !== null && (
              <div className="flex items-center gap-1 mt-1">
                <Star className="h-3 w-3 text-amber-500 fill-amber-500" />
                <span className="text-xs text-gray-500">{yearsExperience} years experience</span>
              </div>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => setShowCropModal(true)}
            disabled={uploadingPhoto}
          >
            {uploadingPhoto ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Camera className="h-4 w-4 mr-1" />}
            {photoUrl ? 'Change Photo' : 'Add Photo'}
          </Button>
        </div>

        {/* ── Clinic Branding — Logo + Signature ── */}
        <div className="p-4 rounded-xl bg-surface-3 space-y-4">
          <div>
            <p className="text-sm font-medium text-strong-fg">Clinic Branding</p>
            <p className="text-xs text-muted-fg mt-0.5">
              Your logo appears at the top of every prescription, invoice and certificate.
              Your signature appears above your name in the sign-off area.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Clinic logo */}
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wide text-gray-500">Clinic Logo</Label>
              <div className="flex items-center gap-3">
                <div className="h-16 w-24 rounded-lg bg-surface-2 border border-border flex items-center justify-center overflow-hidden shrink-0">
                  {clinicLogoUrl ? (
                    <img src={clinicLogoUrl} alt="Clinic logo" className="max-h-full max-w-full object-contain" />
                  ) : (
                    <span className="text-[10px] text-gray-400">No logo</span>
                  )}
                </div>
                <div className="flex-1 flex flex-col gap-1.5">
                  <input
                    id="clinic-logo-input"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleLogoUpload}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => document.getElementById('clinic-logo-input')?.click()}
                    disabled={uploadingLogo}
                  >
                    {uploadingLogo ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                    {clinicLogoUrl ? 'Replace' : 'Upload'}
                  </Button>
                  {clinicLogoUrl && (
                    <Button variant="ghost" size="sm" className="text-xs text-red-600 hover:text-red-700" onClick={handleLogoDelete}>
                      Remove
                    </Button>
                  )}
                </div>
              </div>
              <p className="text-[10px] text-gray-400">JPG, PNG or WebP · max 2MB · shown ≤200×56px on PDFs</p>
            </div>

            {/* Signature */}
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wide text-gray-500">Signature</Label>
              <div className="flex items-center gap-3">
                <div className="h-16 w-24 rounded-lg bg-surface-2 border border-border flex items-center justify-center overflow-hidden shrink-0">
                  {signatureUrl ? (
                    <img src={signatureUrl} alt="Signature" className="max-h-full max-w-full object-contain" />
                  ) : (
                    <span className="text-[10px] text-gray-400">No signature</span>
                  )}
                </div>
                <div className="flex-1 flex flex-col gap-1.5">
                  <input
                    id="signature-input"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleSignatureUpload}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => document.getElementById('signature-input')?.click()}
                    disabled={uploadingSignature}
                  >
                    {uploadingSignature ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                    {signatureUrl ? 'Replace' : 'Upload'}
                  </Button>
                  {signatureUrl && (
                    <Button variant="ghost" size="sm" className="text-xs text-red-600 hover:text-red-700" onClick={handleSignatureDelete}>
                      Remove
                    </Button>
                  )}
                </div>
              </div>
              <p className="text-[10px] text-gray-400">PNG with transparent background works best · max 2MB</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Label htmlFor="name">Full Name</Label>
            <Input id="name" value={form.name} onChange={handleChange('name')} />
          </div>
          <div>
            <Label htmlFor="speciality">Speciality</Label>
            <Input id="speciality" value={form.speciality} onChange={handleChange('speciality')} />
          </div>
          <div>
            <Label htmlFor="registration">Registration Number</Label>
            <Input id="registration" value={form.registration_number} onChange={handleChange('registration_number')} />
          </div>
          <div>
            <Label htmlFor="clinic">Clinic Name</Label>
            <Input id="clinic" value={form.clinic_name} onChange={handleChange('clinic_name')} />
          </div>
          <div className="md:col-span-2">
            <Label htmlFor="address">Clinic Address</Label>
            <Input id="address" value={form.clinic_address} onChange={handleChange('clinic_address')} />
          </div>
          <div>
            <Label htmlFor="phone">Phone</Label>
            <Input id="phone" value={form.phone} onChange={handleChange('phone')} />
          </div>
        </div>

        <div className="border-t border-border pt-4">
          <Label className="flex items-center gap-2 mb-2">
            <MapPin className="h-4 w-4 text-primary-500" />
            Practice Location
          </Label>
          <p className="text-sm text-muted-fg mb-3">
            Pin your clinic location on the map so patients can find you.
            Click the map or search an address to place the marker.
          </p>
          <MapPicker
            latitude={form.latitude}
            longitude={form.longitude}
            onChange={(lat, lng) => {
              setForm(prev => ({ ...prev, latitude: lat, longitude: lng }))
            }}
          />
        </div>

        <Button onClick={handleSave} disabled={saving || !hasChanges}>
          {saving ? (
            <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</>
          ) : saved ? (
            <><CheckCircle className="mr-2 h-4 w-4 text-green-500" />Saved!</>
          ) : (
            'Save Changes'
          )}
        </Button>
      </CardContent>

      <ImageCropModal
        open={showCropModal}
        onClose={() => setShowCropModal(false)}
        onCropped={handlePhotoCropped}
      />
    </Card>
  )
}

// ─── Notifications Tab ─────────────────────────────────────────
// Editable preferences per event type. Backend validates via
// notification_prefs.py; we mirror its DEFAULT_PREFERENCES shape.

type NotifChannel = 'in_app' | 'email'
type NotifPref = { enabled: boolean; hours_before?: number; channels: NotifChannel[] }

const NOTIF_EVENTS: { key: string; label: string; supportsHoursBefore?: boolean }[] = [
  { key: 'appointment_reminder', label: 'Appointment Reminders', supportsHoursBefore: true },
  { key: 'new_report', label: 'New Report Available' },
  { key: 'invoice_generated', label: 'Invoice Generated' },
  { key: 'booking_confirmation', label: 'Booking Confirmations' },
  { key: 'reschedule_notification', label: 'Reschedule Notifications' },
  { key: 'certificate_issued', label: 'Certificate Issued' },
]

const DEFAULT_NOTIF_PREFS: Record<string, NotifPref> = {
  appointment_reminder: { enabled: true, hours_before: 2, channels: ['in_app'] },
  new_report: { enabled: true, channels: ['in_app', 'email'] },
  invoice_generated: { enabled: true, channels: ['in_app'] },
  booking_confirmation: { enabled: true, channels: ['in_app'] },
  reschedule_notification: { enabled: true, channels: ['in_app'] },
  certificate_issued: { enabled: true, channels: ['in_app'] },
}

function NotificationsTab() {
  const [prefs, setPrefs] = useState<Record<string, NotifPref>>(DEFAULT_NOTIF_PREFS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiClient.get('/auth/me')
      .then(r => {
        const stored = r.data?.settings?.notification_preferences
        if (stored && typeof stored === 'object') {
          setPrefs({ ...DEFAULT_NOTIF_PREFS, ...stored })
        }
      })
      .catch(() => setError('Failed to load notification preferences'))
      .finally(() => setLoading(false))
  }, [])

  const updatePref = (key: string, patch: Partial<NotifPref>) => {
    setPrefs(prev => ({ ...prev, [key]: { ...prev[key], ...patch } }))
  }

  const toggleChannel = (key: string, channel: NotifChannel) => {
    setPrefs(prev => {
      const current = prev[key]
      const has = current.channels.includes(channel)
      const next = has
        ? current.channels.filter(c => c !== channel)
        : [...current.channels, channel]
      return { ...prev, [key]: { ...current, channels: next } }
    })
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await apiClient.put('/auth/me/settings', { notification_preferences: prefs })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save preferences')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-gray-400">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
          Loading preferences...
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Bell className="h-5 w-5" />Notification Preferences</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="p-3 rounded-lg bg-red-50 text-sm text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />{error}
          </div>
        )}

        {NOTIF_EVENTS.map(evt => {
          const p = prefs[evt.key] || DEFAULT_NOTIF_PREFS[evt.key]
          return (
            <div key={evt.key} className="p-4 rounded-lg border border-border space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-strong-fg">{evt.label}</p>
                  <p className="text-xs text-gray-500">
                    {p.enabled ? 'Enabled' : 'Disabled'}
                    {evt.supportsHoursBefore && p.enabled && p.hours_before ? ` · ${p.hours_before}h before` : ''}
                  </p>
                </div>
                {/* Enable / disable toggle */}
                <label className="inline-flex items-center cursor-pointer" aria-label={`Enable ${evt.label}`}>
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={p.enabled}
                    onChange={e => updatePref(evt.key, { enabled: e.target.checked })}
                  />
                  <span className="relative w-11 h-6 bg-border-strong rounded-full peer-checked:bg-primary-500 transition-colors">
                    <span className={`absolute left-0.5 top-0.5 h-5 w-5 bg-white rounded-full shadow transition-transform ${p.enabled ? 'translate-x-5' : ''}`} />
                  </span>
                </label>
              </div>

              {p.enabled && (
                <div className="flex items-center gap-3 pl-1">
                  {/* Channel checkboxes */}
                  <label className="inline-flex items-center gap-1.5 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={p.channels.includes('in_app')}
                      onChange={() => toggleChannel(evt.key, 'in_app')}
                      className="accent-primary-600"
                    />
                    <Badge variant={p.channels.includes('in_app') ? 'default' : 'outline'}>In-App</Badge>
                  </label>
                  <label className="inline-flex items-center gap-1.5 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={p.channels.includes('email')}
                      onChange={() => toggleChannel(evt.key, 'email')}
                      className="accent-primary-600"
                    />
                    <Badge variant={p.channels.includes('email') ? 'secondary' : 'outline'}>Email</Badge>
                  </label>

                  {evt.supportsHoursBefore && (
                    <div className="ml-auto flex items-center gap-2">
                      <Label htmlFor={`hours-${evt.key}`} className="text-xs">Hours before:</Label>
                      <Input
                        id={`hours-${evt.key}`}
                        type="number"
                        min={0}
                        max={720}
                        value={p.hours_before ?? 0}
                        onChange={e => updatePref(evt.key, { hours_before: Math.max(0, Math.min(720, Number(e.target.value) || 0)) })}
                        className="w-20 text-sm"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}

        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</>
          ) : saved ? (
            <><CheckCircle className="mr-2 h-4 w-4 text-green-500" />Saved!</>
          ) : (
            'Save Preferences'
          )}
        </Button>

        <p className="text-xs text-gray-500 italic pt-2 border-t border-border">
          Notifications are delivered via in-app WebSocket (free) and email (PDF reports only). SMS is not used.
        </p>
      </CardContent>
    </Card>
  )
}

function ScheduleTab() {
  const [buffer, setBuffer] = useState(5)
  const [duration, setDuration] = useState(20)
  const [maxPerWindow, setMaxPerWindow] = useState<number | null>(null)
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
    apiClient.get('/calendar/working-hours').then(r => {
      const data = r.data
      setBuffer(data.buffer_minutes || 5)
      setDuration(data.default_duration || 20)
      setMaxPerWindow(data.max_bookings_per_window ?? null)
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
    }).catch((err) => {
      console.warn('[Settings] Failed to load working hours:', err)
    }).finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const workingHoursJson: Record<string, string[][]> = {}
      Object.entries(hours).forEach(([day, h]) => {
        if (h.enabled && h.start && h.end) workingHoursJson[day] = [[h.start, h.end]]
      })
      await apiClient.put('/calendar/working-hours', {
        working_hours_json: workingHoursJson,
        buffer_minutes: buffer,
        default_duration: duration,
        max_bookings_per_window: maxPerWindow,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) { console.warn('[Settings] Failed to save schedule:', err); setSaved(false); }
    finally { setSaving(false) }
  }

  if (loading) return <div className="text-center py-8 text-gray-500"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Calendar className="h-5 w-5" />Working Hours</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(hours).map(([day, h]) => (
            <div key={day} className="flex items-center gap-2 p-2 rounded-lg bg-surface-3">
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
        <div className="flex items-center gap-3 flex-wrap">
          <Label htmlFor="buffer" className="text-sm">Buffer (min):</Label>
          <Input id="buffer" type="number" min={0} max={60} value={buffer} onChange={e => setBuffer(Number(e.target.value))} className="w-20" />
          <Label htmlFor="duration" className="text-sm ml-4">Duration (min):</Label>
          <Input id="duration" type="number" min={5} max={120} value={duration} onChange={e => setDuration(Number(e.target.value))} className="w-20" />
          <Label htmlFor="maxPerWindow" className="text-sm ml-4">Max bookings/window (0 = unlimited):</Label>
          <Input id="maxPerWindow" type="number" min={0} max={100} value={maxPerWindow ?? 0} onChange={e => setMaxPerWindow(Number(e.target.value) || null)} className="w-20" />
        </div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : saved ? <><CheckCircle className="h-4 w-4 mr-2 text-green-500" /> Saved!</> : 'Save Schedule'}
        </Button>
      </CardContent>
    </Card>
  )
}

function SecurityTab() {
  const [loading, setLoading] = useState(false)
  const [sessions, setSessions] = useState<any | null>(null)
  const [exporting, setExporting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const handleViewSessions = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/auth/sessions')
      setSessions(res.data)
    } catch (err: any) {
      setMessage('Failed to load sessions')
      console.warn(err)
    } finally {
      setLoading(false)
    }
  }

  const handleExportData = async () => {
    setExporting(true)
    try {
      const res = await apiClient.get('/auth/me/data')
      // Download as JSON file
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `soloprac-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      setMessage('Data exported successfully')
    } catch (err: any) {
      setMessage('Failed to export data')
      console.warn(err)
    } finally {
      setExporting(false)
    }
  }

  const handleDeleteAccount = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setDeleting(true)
    try {
      await apiClient.delete('/auth/me')
      // Clear cookies via logout endpoint
      await apiClient.post('/auth/logout')
      window.location.href = '/login'
    } catch (err: any) {
      setMessage('Failed to delete account')
      console.warn(err)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Shield className="h-5 w-5" />Security</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {message && (
          <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-sm text-blue-700 dark:text-blue-300">
            {message}
          </div>
        )}

        {sessions && (
          <div className="p-3 rounded-lg bg-surface-3 text-sm">
            <p className="font-medium mb-1">Session Info</p>
            <p className="text-muted-fg">{sessions.note}</p>
            <p className="text-gray-500 text-xs mt-1">
              Access token: {sessions.access_token_expiry_minutes} min &bull;
              Refresh token: {sessions.refresh_token_expiry_days} days
            </p>
          </div>
        )}

        <Button variant="outline" onClick={handleViewSessions} disabled={loading}>
          {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Loading...</> : 'View Active Sessions'}
        </Button>

        <Button variant="outline" onClick={handleExportData} disabled={exporting}>
          {exporting ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Exporting...</> : 'Export My Data'}
        </Button>

        {confirmDelete ? (
          <div className="p-3 rounded-lg bg-critical-subtle border border-critical/15">
            <p className="text-sm font-medium text-red-800 dark:text-red-200 mb-2">
              Are you sure? This will permanently delete all data.
            </p>
            <div className="flex gap-2">
              <Button variant="destructive" onClick={handleDeleteAccount} disabled={deleting}>
                {deleting ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Deleting...</> : 'Yes, Delete Everything'}
              </Button>
              <Button variant="outline" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <Button variant="destructive" onClick={handleDeleteAccount}>Delete Account</Button>
        )}
      </CardContent>
    </Card>
  )
}

function BillingTab() {
  const [billing, setBilling] = useState<any | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get('/auth/me/billing')
      .then(r => setBilling(r.data))
      .catch(err => console.warn('[Billing] Failed to load:', err))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-gray-400">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
          Loading usage stats...
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><CreditCard className="h-5 w-5" />Billing & Usage</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="p-4 rounded-lg bg-success-subtle border border-success/15">
          <p className="font-medium text-green-900 dark:text-green-100">Free Tier Active</p>
          <p className="text-sm text-success">{billing?.message || "You're on the free tier. No charges apply."}</p>
        </div>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div className="p-4 rounded-lg bg-surface-3">
            <p className="text-2xl font-bold text-primary-600">{billing?.notification_count ?? 0}</p>
            <p className="text-sm text-gray-500">Notifications</p>
          </div>
          <div className="p-4 rounded-lg bg-surface-3">
            <p className="text-2xl font-bold text-primary-600">{billing?.patient_count ?? 0}</p>
            <p className="text-sm text-gray-500">Patients</p>
          </div>
          <div className="p-4 rounded-lg bg-surface-3">
            <p className="text-2xl font-bold text-primary-600">₹{billing?.total_billed ?? 0}</p>
            <p className="text-sm text-gray-500">Total Billed</p>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-surface-3 text-sm text-muted-fg">
          <span className="font-medium">Appointments: </span>{billing?.appointment_count ?? 0}
        </div>
      </CardContent>
    </Card>
  )
}