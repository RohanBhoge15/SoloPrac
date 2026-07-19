import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { Search, Clock, Stethoscope, Loader2, AlertCircle, CheckCircle } from 'lucide-react'

export function DoctorSearch() {
  const [query, setQuery] = useState('')
  const [speciality, setSpeciality] = useState('')
  const [doctors, setDoctors] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedDoctor, setSelectedDoctor] = useState<any>(null)
  const [slots, setSlots] = useState<any[]>([])
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [bookingSlot, setBookingSlot] = useState<any>(null)
  const [booking, setBooking] = useState(false)
  const [booked, setBooked] = useState(false)

  useEffect(() => {
    loadDoctors()
  }, [])

  const loadDoctors = async () => {
    setLoading(true)
    setError(null)
    try {
      const params: any = {}
      if (speciality) params.speciality = speciality
      if (query) params.q = query
      const res = await apiClient.get('/api/public/doctors/search', { params })
      setDoctors(res.data?.doctors || [])
    } catch {
      setError('Failed to load doctors')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = () => loadDoctors()

  const handleSelectDoctor = async (doc: any) => {
    setSelectedDoctor(doc)
    setBookingSlot(null)
    setBooked(false)
    setLoadingSlots(true)
    try {
      const today = new Date().toISOString().split('T')[0]
      const nextWeek = new Date(Date.now() + 7 * 86400000).toISOString().split('T')[0]
      const res = await apiClient.get(`/api/public/doctors/${doc.id}`, { params: { date_from: today, date_to: nextWeek } })
      setSlots(res.data?.available_slots || [])
    } catch {
      setError('Failed to load slots')
    } finally {
      setLoadingSlots(false)
    }
  }

  const handleBookSlot = async (slot: any) => {
    const patientId = localStorage.getItem('patient_id')
    if (!patientId) {
      window.location.href = '/patient/login'
      return
    }
    setBooking(true)
    try {
      await apiClient.post('/api/public/appointments', {
        doctor_id: selectedDoctor.id,
        patient_id: patientId,
        start_at: slot.start,
        end_at: slot.end,
        reason: 'Online booking',
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
            <Button onClick={handleSearch} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
            </Button>
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
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                      <span className="text-lg font-bold text-primary-700">{doc.name.split(' ').map((n: string) => n[0]).join('')}</span>
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{doc.name}</p>
                      <p className="text-sm text-gray-500 flex items-center gap-1"><Stethoscope className="h-3 w-3" /> {doc.speciality}</p>
                      {doc.clinic_name && <p className="text-xs text-gray-400">{doc.clinic_name}</p>}
                    </div>
                  </div>
                  <Badge variant="outline">{doc.clinic_address?.split(',')[0] || 'Available'}</Badge>
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
                  <p><span className="text-gray-500">Speciality:</span> {selectedDoctor.speciality}</p>
                  <p><span className="text-gray-500">Clinic:</span> {selectedDoctor.clinic_name || 'N/A'}</p>
                  <p><span className="text-gray-500">Address:</span> {selectedDoctor.clinic_address || 'N/A'}</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle className="text-sm flex items-center gap-1"><Clock className="h-4 w-4" />Available Slots</CardTitle></CardHeader>
                <CardContent>
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
