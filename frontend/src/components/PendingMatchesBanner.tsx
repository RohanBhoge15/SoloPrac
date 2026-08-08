// Shows a subtle prompt on the patient dashboard when the backend has
// found walk-in Patient records that phone-match this user but weren't
// strong-linked (name/dob differed). Tapping opens the review page.
//
// Zero-state: renders nothing when count === 0.
// Non-blocking: dismissible via the review page's Claim/Reject actions.
//
// Backend contract: /patient/me/profile returns `pending_matches_count`.

import { useQuery } from '@tanstack/react-query'
import { Link2, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '@/services/api'

interface Profile {
  pending_matches_count?: number
}

export function PendingMatchesBanner() {
  const nav = useNavigate()

  const { data } = useQuery<Profile | null>({
    queryKey: ['patient', 'profile-pending'],
    queryFn: async () => {
      try {
        const res = await apiClient.get('/patient/me/profile')
        return res.data as Profile
      } catch {
        return null
      }
    },
    // Refresh reasonably often — new walk-ins can appear at any time as
    // doctors register patients. 60s is a good tradeoff between freshness
    // and cost (this hits the DB scan on every call).
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const count = data?.pending_matches_count ?? 0
  if (count <= 0) return null

  return (
    <button
      onClick={() => nav('/patient/pending-matches')}
      className="w-full text-left rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 p-4 flex items-center justify-between hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-full bg-amber-100 dark:bg-amber-800 flex items-center justify-center">
          <Link2 className="h-4 w-4 text-amber-700 dark:text-amber-200" />
        </div>
        <div>
          <p className="font-medium text-amber-900 dark:text-amber-100">
            {count === 1
              ? '1 clinic record matches your phone'
              : `${count} clinic records match your phone`}
          </p>
          <p className="text-sm text-amber-800/80 dark:text-amber-200/80">
            Tap to review — confirm which are yours.
          </p>
        </div>
      </div>
      <ChevronRight className="h-5 w-5 text-amber-700 dark:text-amber-300" />
    </button>
  )
}
