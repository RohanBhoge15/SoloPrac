import { Link, useLocation, useParams } from 'react-router-dom'
import { ChevronRight, Home } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/services/api'

// Human-facing labels for known top-level routes. Anything not listed falls
// back to a title-cased slug (`weekly-report` → `Weekly Report`).
const ROUTE_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  patients: 'Patients',
  new: 'New Patient',
  calendar: 'Calendar',
  chat: 'AI Assistant',
  scratchpad: 'Scratchpad',
  settings: 'Settings',
  'weekly-report': 'Weekly Report',
  reports: 'Reports',
  approvals: 'Approvals',
  admin: 'Admin',
}

function titleCase(slug: string): string {
  if (ROUTE_LABELS[slug]) return ROUTE_LABELS[slug]
  return slug
    .split('-')
    .map(s => s.charAt(0).toUpperCase() + s.slice(1))
    .join(' ')
}

// Looks like a UUID — used to detect resource IDs in the path so we can
// swap them for a friendlier label (patient name) when possible.
const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/

interface PatientLite {
  id: string
  name?: string
  full_name?: string
}

export function Breadcrumbs() {
  const location = useLocation()
  const params = useParams()
  const segments = location.pathname.split('/').filter(Boolean)

  // Resolve patient name for /patients/:id breadcrumbs. Enabled only on that
  // shape so we don't hit the API on unrelated pages.
  const patientId = params.id && UUID_RE.test(params.id) && segments[0] === 'patients' ? params.id : null
  const { data: patient } = useQuery<PatientLite>({
    queryKey: ['breadcrumb-patient', patientId],
    queryFn: async () => {
      const res = await apiClient.get(`/patients/${patientId}`)
      return res.data as PatientLite
    },
    enabled: !!patientId,
    staleTime: 60_000,
  })

  if (segments.length === 0) return null

  // Build the crumb list. Each crumb needs (label, href).
  const crumbs: { label: string; href: string; isLast: boolean }[] = []
  let acc = ''
  segments.forEach((seg, idx) => {
    acc += '/' + seg
    const isLast = idx === segments.length - 1
    let label: string
    if (UUID_RE.test(seg)) {
      // Prefer the resolved resource name; fall back to short id.
      const name = patient?.name || patient?.full_name
      label = name || seg.slice(0, 8)
    } else {
      label = titleCase(seg)
    }
    crumbs.push({ label, href: acc, isLast })
  })

  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center gap-1.5 text-sm text-muted-fg mb-4"
    >
      <Link
        to="/dashboard"
        className="flex items-center gap-1 hover:text-strong-fg transition-colors"
        aria-label="Home"
      >
        <Home className="h-3.5 w-3.5" />
      </Link>
      {crumbs.map((c) => (
        <div key={c.href} className="flex items-center gap-1.5">
          <ChevronRight className="h-3.5 w-3.5 text-muted-fg/60" aria-hidden="true" />
          {c.isLast ? (
            <span className="font-medium text-strong-fg" aria-current="page">
              {c.label}
            </span>
          ) : (
            <Link
              to={c.href}
              className="hover:text-strong-fg transition-colors"
            >
              {c.label}
            </Link>
          )}
        </div>
      ))}
    </nav>
  )
}
