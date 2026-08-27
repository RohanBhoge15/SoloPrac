import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { Search, Clock, Stethoscope, Loader2, AlertCircle, CheckCircle, Locate } from 'lucide-react'
import { ResponsiveAvatar } from '@/components/ui/ResponsiveAvatar'

// Indian pincode: 6 digits, first digit 1-9 (0 isn't a valid postal region).
const PINCODE_RE = /^[1-9]\d{5}$/

export function DoctorSearch() {
  const [query, setQuery] = useState('')
  const [speciality, setSpeciality] = useState('')
  const [pincode, setPincode] = useState('')
  const [pincodeError, setPincodeError] = useState<string | null>(null)
  const [doctors, setDoctors] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedDoctor, setSelectedDoctor] = useState<any>(null)
  const [slots, setSlots] = useState<any[]>([])
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [bookingSlot, setBookingSlot] = useState<any>(null)
  const [booking, setBooking] = useState(false)
  const [booked, setBooked] = useState(false)
  const [patientId, setPatientId] = useState<string>('')
  const [telemedicineConsent, setTelemedicineConsent] = useState(false)

  // ── Location-based discovery ──
  const [lat, setLat] = useState<number | null>(null)
  const [lng, setLng] = useState<number | null>(null)
  const [radius, setRadius] = useState(10)
  const [usingGeo, setUsingGeo] = useState(false)
  const [geoStatus, setGeoStatus] = useState<string | null>(null)

  // Fallback centre = where the demo doctors are (Bengaluru) so the demo always
  // returns results even if the browser denies geolocation.
  const DEFAULT_LOCATION = { lat: 12.9716, lng: 77.5946 }
  const RADIUS_STEPS = [10, 25, 50, 100]

  const fetchDoctors = async (params: any) => {
    const res = await apiClient.get('/public/doctors/search', { params })
    return res.data?.doctors || []
  }

  const runLocationSearch = async (la: number, ln: number, allowDefaultFallback = true) => {
    setUsingGeo(true)
    try {
      for (const r of RADIUS_STEPS) {
        setRadius(r)
        setGeoStatus(`Searching within ${r} km…`)
        const docs = await fetchDoctors({
          lat: la, lng: ln, radius_km: r,
          speciality: speciality || undefined,
          q: query || undefined,
        })
        if (docs.length) {
          setDoctors(docs)
          setGeoStatus(`Showing ${docs.length} doctor(s) within ${r} km of your location`)
          return
        }
      }
      if (allowDefaultFallback) {
        setGeoStatus('No doctors near you — showing the demo area instead')
        await runLocationSearch(DEFAULT_LOCATION.lat, DEFAULT_LOCATION.lng, false)
      } else {
        setDoctors([])
        setGeoStatus('No doctors found nearby. Try searching by name or speciality.')
      }
    } finally {
      setLoading(false)
    }
  }

  const searchAtRadius = async (r: number) => {
    if (lat == null || lng == null) return
    setRadius(r)
    setGeoStatus(`Searching within ${r} km…`)
    const docs = await fetchDoctors({ lat, lng, radius_km: r, speciality: speciality || undefined, q: query || undefined })
    setDoctors(docs)
    setGeoStatus(docs.length ? `Showing ${docs.length} doctor(s) within ${r} km` : `No doctors within ${r} km`)
  }

  const useMyLocation = () => {
    setLoading(true)
    const fallback = () => {
      setLat(DEFAULT_LOCATION.lat); setLng(DEFAULT_LOCATION.lng)
      setGeoStatus('Location unavailable — showing doctors near the demo area')
      runLocationSearch(DEFAULT_LOCATION.lat, DEFAULT_LOCATION.lng)
    }
    if (!('geolocation' in navigator)) { fallback(); return }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude); setLng(pos.coords.longitude)
        setGeoStatus('Using your location')
        runLocationSearch(pos.coords.latitude, pos.coords.longitude)
      },
      () => fallback(),
      { enableHighAccuracy: false, timeout: 10000 },
    )
  }

  // Fetch patient ID from profile endpoint on mount
  useEffect(() => {
    apiClient.get('/patient/me/profile')
      .then(res => {
        if (res.data?.user_id) {
          setPatientId(res.data.user_id)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadDoctors()
  }, [])

  const loadDoctors = async () => {
    setUsingGeo(false)
    setGeoStatus(null)
    setLoading(true)
    setError(null)
    try {
      const params: any = {}
      if (speciality) params.speciality = speciality
      if (pincode) params.pincode = pincode
      if (query) params.q = query
      const res = await apiClient.get('/public/doctors/search', { params })
      setDoctors(res.data?.doctors || [])
    } catch {
      setError('Failed to load doctors')
    } finally {
      setLoading(false)
    }
  }

  const handlePincodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Strip non-digits so users can't type garbage.
    const cleaned = e.target.value.replace(/\D/g, '').slice(0, 6)
    setPincode(cleaned)
    if (cleaned === '' || PINCODE_RE.test(cleaned)) {
      setPincodeError(null)
    } else if (cleaned.length === 6) {
      setPincodeError('Invalid Indian pincode (first digit must be 1-9)')
    } else {
      setPincodeError('Pincode must be 6 digits')
    }
  }

  const handleSearch = () => {
    // Block search if pincode was typed but is invalid; empty pincode is fine.
    if (pincode && !PINCODE_RE.test(pincode)) {
      setPincodeError('Enter a valid 6-digit Indian pincode')
      return
    }
    loadDoctors()
  }

  const handleSelectDoctor = async (doc: any) => {
    setSelectedDoctor(doc)
    setBookingSlot(null)
    setBooked(false)
    setLoadingSlots(true)
    try {
      const today = new Date().toISOString().split('T')[0]
      const nextWeek = new Date(Date.now() + 7 * 86400000).toISOString().split('T')[0]
      const res = await apiClient.get(`/public/doctors/${doc.id}`, { params: { date_from: today, date_to: nextWeek } })
      setSlots(res.data?.available_slots || [])
    } catch {
      setError('Failed to load slots')
    } finally {
      setLoadingSlots(false)
    }
  }

  const handleBookSlot = async (slot: any) => {
    if (!patientId) {
      window.location.href = '/patient/login'
      return
    }
    setBooking(true)
    try {
      await apiClient.post('/patient/appointments', {
        doctor_id: selectedDoctor.id,
        patient_id: patientId,
        start_at: slot.start,
        end_at: slot.end,
        reason: 'Online booking',
        telemedicine_consent: telemedicineConsent,
      })
      setBookingSlot(slot)
      setBooked(true)
      setSlots(slots.filter(s => s.start !== slot.start))
    } catch {
      setError('Booking failed. Please try again.')
    } finally {
      setBooking(false)
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Find a Doctor</h1>

      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <Input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by name, clinic, or speciality..." className="pl-10" onKeyDown={e => e.key === 'Enter' && handleSearch()} />
            </div>
            <select value={speciality} onChange={e => setSpeciality(e.target.value)} className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm">
              <option value="">All</option>
              <option value="General Practice">General Practice</option>
              <option value="Cardiology">Cardiology</option>
              <option value="Dermatology">Dermatology</option>
              <option value="Orthopedics">Orthopedics</option>
              <option value="Pediatrics">Pediatrics</option>
              <option value="Gynecology">Gynecology</option>
            </select>
            <div className="flex flex-col">
              <Input
                value={pincode}
                onChange={handlePincodeChange}
                placeholder="PIN code"
                inputMode="numeric"
                maxLength={6}
                aria-invalid={!!pincodeError}
                aria-describedby={pincodeError ? 'pincode-error' : undefined}
                className={cn(
                  'w-28',
                  pincodeError && 'border-red-500 focus:ring-red-500'
                )}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
              {pincodeError && (
                <p id="pincode-error" className="mt-1 text-[10px] text-red-600 dark:text-red-400">
                  {pincodeError}
                </p>
              )}
            </div>
            <Button onClick={handleSearch} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
            </Button>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-border pt-3">
            <Button variant="outline" size="sm" onClick={useMyLocation}>
              <Locate className="h-4 w-4 mr-1" /> Use my location
            </Button>
            {usingGeo && (
              <div className="flex items-center gap-2 text-xs text-muted-fg">
                <span>Radius:</span>
                <input
                  type="range"
                  min={1}
                  max={100}
                  value={radius}
                  onChange={(e) => searchAtRadius(Number(e.target.value))}
                  className="accent-primary-600"
                />
                <span className="tnum w-16">{radius} km</span>
              </div>
            )}
            {geoStatus && <span className="text-xs text-muted-fg">{geoStatus}</span>}
          </div>
        </CardContent>
      </Card>

      {error && <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 text-sm text-red-700"><AlertCircle className="h-4 w-4" /> {error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          {loading && <div className="text-center py-8"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div>}
          {!loading && doctors.length === 0 && <p className="text-center text-gray-400 py-8">No doctors found. Try a different search.</p>}
          {doctors.map((doc: any) => (
            <Card key={doc.id} className={cn('cursor-pointer transition-all hover:shadow-md', selectedDoctor?.id === doc.id && 'ring-2 ring-primary-500')} onClick={() => handleSelectDoctor(doc)}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <ResponsiveAvatar
                      src={doc.photo_url}
                      alt={doc.name}
                      size={48}
                      className="h-12 w-12 rounded-full object-cover"
                    />
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{doc.name}</p>
                      <p className="text-sm text-gray-500 flex items-center gap-1"><Stethoscope className="h-3 w-3" /> {doc.speciality}</p>
                      {doc.clinic_name && <p className="text-xs text-gray-400">{doc.clinic_name}</p>}
                      {doc.years_experience != null && (
                        <p className="text-xs text-gray-400">{doc.years_experience} years experience</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {doc.distance_km != null && (
                      <Badge className="bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
                        {doc.distance_km} km away
                      </Badge>
                    )}
                    <Badge variant="outline">{doc.clinic_address?.split(',')[0] || 'Available'}</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="lg:col-span-1 space-y-4">
          {selectedDoctor && (
            <>
              <Card>
                <CardHeader><CardTitle className="text-sm">{selectedDoctor.name}</CardTitle></CardHeader>
                <CardContent className="text-sm space-y-1">
                  {selectedDoctor.photo_url && (
                    <ResponsiveAvatar
                      src={selectedDoctor.photo_url}
                      alt={selectedDoctor.name}
                      size={64}
                      className="h-16 w-16 rounded-full object-cover mx-auto mb-2"
                    />
                  )}
                  <p><span className="text-gray-500">Speciality:</span> {selectedDoctor.speciality}</p>
                  <p><span className="text-gray-500">Clinic:</span> {selectedDoctor.clinic_name || 'N/A'}</p>
                  <p><span className="text-gray-500">Address:</span> {selectedDoctor.clinic_address || 'N/A'}</p>
                  {selectedDoctor.years_experience != null && (
                    <p><span className="text-gray-500">Experience:</span> {selectedDoctor.years_experience} years</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle className="text-sm flex items-center gap-1"><Clock className="h-4 w-4" />Available Slots</CardTitle></CardHeader>
                <CardContent>
                  <label className="flex items-start gap-2 mb-3 p-2 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-xs text-blue-700 dark:text-blue-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={telemedicineConsent}
                      onChange={e => setTelemedicineConsent(e.target.checked)}
                      className="mt-0.5 accent-primary-600"
                    />
                    <span>I consent to telemedicine consultation as per the Telemedicine Practice Guidelines (2020). I understand that this consultation is not a substitute for in-person examination.</span>
                  </label>
                  {loadingSlots ? <Loader2 className="h-5 w-5 animate-spin mx-auto" /> : slots.length === 0 ? <p className="text-sm text-gray-400">No slots available this week</p> : (
                    <div className="space-y-1.5 max-h-64 overflow-y-auto">
                      {slots.slice(0, 15).map((slot, i) => (
                        <button key={i} onClick={() => !booked && handleBookSlot(slot)} disabled={booking || booked} className={cn('w-full p-2 rounded-lg text-xs text-left border transition-colors', bookingSlot?.start === slot.start && booked ? 'bg-green-50 border-green-300 border-2' : 'hover:bg-gray-50 dark:hover:bg-gray-800 border-gray-200 dark:border-gray-700')}>
                          <span className="font-medium">{slot.date?.slice(5)}</span>
                          <span className="ml-2 text-gray-500">{slot.time}</span>
                          <span className="ml-1 text-[10px] text-gray-400">({slot.duration_minutes}min)</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {booked && (
                    <div className="mt-3 p-2 rounded-lg bg-green-50 text-green-700 text-xs flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" /> Booked! Check your appointments.
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function cn(...classes: any[]) { return classes.filter(Boolean).join(' ') }
