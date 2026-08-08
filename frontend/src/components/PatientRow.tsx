/**
 * P2.21 — Memoized patient-list row.
 *
 * Every list of patients (Dashboard "Recent Patients", the search results
 * panel, the walk-in linker) used to re-render every row when the parent
 * re-rendered — which happens on every keystroke in the search box.
 *
 * Wrapping the row in React.memo with a shallow-eq comparator (default)
 * means only rows whose `patient` reference changed re-render. Combined
 * with the router prefetch hook from P2.20, this makes the list feel
 * instantaneous at 600+ patients.
 */

import { memo } from 'react'
import { usePrefetchPatient } from '@/hooks/usePrefetchPatient'

export interface PatientRowProps {
  patient: {
    id: string
    demographics?: { name?: string; age?: number }
    // We only touch fields used in the row so the memo comparison is stable.
    last_visit?: string
  }
  onOpen: (patientId: string) => void
}

function initials(name: string): string {
  return name.split(' ').filter(Boolean).map(n => n[0]).join('').slice(0, 3).toUpperCase()
}

function PatientRowImpl({ patient, onOpen }: PatientRowProps) {
  const prefetch = usePrefetchPatient()
  const name = patient.demographics?.name ?? 'Unknown'
  const age = patient.demographics?.age ?? '?'
  const lastVisit = patient.last_visit
    ? new Date(patient.last_visit).toLocaleDateString()
    : 'Never'

  return (
    <div
      className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer"
      onClick={() => onOpen(patient.id)}
      {...prefetch(patient.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(patient.id)
        }
      }}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
          <span className="text-sm font-medium text-primary-700 dark:text-primary-300">
            {initials(name)}
          </span>
        </div>
        <div>
          <p className="font-medium text-gray-900 dark:text-white">{name}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {age} years • Last visit: {lastVisit}
          </p>
        </div>
      </div>
    </div>
  )
}

// Default shallow equality is what we want — parent needs to keep the
// `patient` reference stable (usePatientStore's zustand array only re-refs
// when its contents change). `onOpen` should be wrapped in useCallback by
// the parent for the memo to hold.
export const PatientRow = memo(PatientRowImpl)
