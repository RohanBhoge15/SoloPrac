// Patient-side disambiguation for walk-in records that phone-match this
// user but weren't strong-linked automatically. One tap per row: Claim
// (add to my records) or Not me (hide forever).
//
// Doctors never see this screen — this is the patient doing the last-mile
// tie-break themselves (the same pattern Google Photos uses for face
// grouping). Zero cost to the doctor's time.

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Check, X, Building2, Stethoscope, CalendarClock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { apiClient } from '@/services/api'

interface PendingMatch {
  patient_id: string
  clinic_name?: string
  doctor_name?: string
  doctor_speciality?: string
  created_at?: string
  record_name?: string
  record_dob?: string
  record_gender?: string
}

export function PatientPendingMatches() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<PendingMatch[]>({
    queryKey: ['patient', 'pending-matches'],
    queryFn: async () => {
      const res = await apiClient.get('/patient/me/pending-matches')
      return (res.data as PendingMatch[]) ?? []
    },
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['patient', 'pending-matches'] })
    qc.invalidateQueries({ queryKey: ['patient', 'profile-pending'] })
    qc.invalidateQueries({ queryKey: ['patient', 'profile'] })
  }

  const claim = useMutation({
    mutationFn: (pid: string) => apiClient.post(`/patient/me/claim/${pid}`),
    onSuccess: invalidate,
  })
  const reject = useMutation({
    mutationFn: (pid: string) => apiClient.post(`/patient/me/reject/${pid}`),
    onSuccess: invalidate,
  })

  if (isLoading) {
    return (
      <div className="text-center py-12">
        <Loader2 className="h-6 w-6 animate-spin mx-auto text-gray-400" />
      </div>
    )
  }

  const matches = data ?? []

  return (
    <div className="max-w-2xl mx-auto space-y-4 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Records to review
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          These clinic records were created with your phone number but we
          couldn&apos;t confirm they&apos;re yours. Confirm which are you.
        </p>
      </div>

      {matches.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-gray-500">
            <Check className="h-10 w-10 mx-auto text-green-500 mb-2" />
            <p className="font-medium">All caught up.</p>
            <p className="text-sm mt-1">
              We&apos;ll let you know if new records arrive.
            </p>
          </CardContent>
        </Card>
      ) : (
        matches.map((m) => {
          const pending = claim.isPending || reject.isPending
          return (
            <Card key={m.patient_id} className="overflow-hidden">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                    <Building2 className="h-5 w-5 text-blue-700 dark:text-blue-300" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-900 dark:text-white truncate">
                      {m.clinic_name || 'Unknown clinic'}
                    </p>
                    <p className="text-sm text-gray-600 dark:text-gray-400 flex items-center gap-1 mt-0.5">
                      <Stethoscope className="h-3 w-3" />
                      Dr. {m.doctor_name || '—'}
                      {m.doctor_speciality && (
                        <span className="text-gray-400">
                          · {m.doctor_speciality}
                        </span>
                      )}
                    </p>
                    {m.created_at && (
                      <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                        <CalendarClock className="h-3 w-3" />
                        Added {new Date(m.created_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                </div>

                <div className="text-sm bg-gray-50 dark:bg-gray-800/40 rounded p-3 border border-gray-100 dark:border-gray-800">
                  <p className="text-gray-500 text-xs mb-1">
                    Record on file:
                  </p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {m.record_name || 'Unnamed record'}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {[m.record_gender, m.record_dob].filter(Boolean).join(' · ') ||
                      'No additional details'}
                  </p>
                </div>

                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    className="flex-1"
                    disabled={pending}
                    onClick={() => reject.mutate(m.patient_id)}
                  >
                    <X className="h-4 w-4 mr-1" />
                    Not me
                  </Button>
                  <Button
                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                    disabled={pending}
                    onClick={() => claim.mutate(m.patient_id)}
                  >
                    <Check className="h-4 w-4 mr-1" />
                    This is me
                  </Button>
                </div>
              </CardContent>
            </Card>
          )
        })
      )}
    </div>
  )
}
