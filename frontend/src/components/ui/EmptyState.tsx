import { cn } from '@/utils/helpers'
import { Button } from './Button'
import { motion } from 'framer-motion'

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: { label: string; onClick: () => void; variant?: 'primary' | 'secondary' | 'outline' }
  secondaryAction?: { label: string; onClick: () => void }
  className?: string
  illustration?: 'appointments' | 'patients' | 'reports' | 'search' | 'calendar' | 'inbox' | 'settings' | 'no-data'
}

const ILLUSTRATIONS: Record<string, React.ReactNode> = {
  appointments: (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="20" y="40" width="160" height="120" rx="12" strokeWidth="2" />
      <rect x="20" y="40" width="160" height="36" rx="12" strokeWidth="2" />
      <path d="M40 58h120 M40 90h80 M40 122h100" strokeWidth="1.5" strokeDasharray="8 4" opacity="0.6" />
      <circle cx="170" cy="58" r="14" strokeWidth="2" opacity="0.4" />
      <path d="M165 58h10 M170 53v10" strokeWidth="2" />
    </svg>
  ),
  patients: (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="100" cy="70" r="30" strokeWidth="2" />
      <path d="M100 100c-30 0-50 20-50 40v10h100v-10c0-20-20-40-50-40z" strokeWidth="2" />
      <circle cx="50" cy="160" r="12" strokeWidth="1.5" opacity="0.4" />
      <circle cx="150" cy="160" r="12" strokeWidth="1.5" opacity="0.4" />
    </svg>
  ),
  reports: (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="25" y="30" width="150" height="140" rx="8" strokeWidth="2" />
      <rect x="25" y="30" width="150" height="32" rx="8" strokeWidth="2" />
      <path d="M45 80h110 M45 105h80 M45 130h90 M45 155h70" strokeWidth="1.5" strokeDasharray="6 3" opacity="0.7" />
      <path d="M45 130 L75 100 L105 120 L135 90 L165 115" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="80" cy="80" r="45" strokeWidth="3" />
      <path d="M105 105 L145 145" strokeWidth="3" strokeLinecap="round" />
      <circle cx="80" cy="80" r="18" strokeWidth="1.5" opacity="0.3" />
      <path d="M80 70v20 M70 80h20" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
    </svg>
  ),
  calendar: (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="20" y="40" width="160" height="120" rx="12" strokeWidth="2" />
      <rect x="20" y="40" width="160" height="36" rx="12" strokeWidth="2" />
      <rect x="40" y="52" width="28" height="20" rx="4" strokeWidth="1.5" fill="currentColor" opacity="0.3" />
      <rect x="76" y="52" width="28" height="20" rx="4" strokeWidth="1.5" opacity="0.3" />
      <rect x="112" y="52" width="28" height="20" rx="4" strokeWidth="1.5" opacity="0.3" />
      <path d="M40 100h120 M40 130h120 M40 160h120" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />
    </svg>
  ),
  inbox: (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M20 50h160a10 10 0 0 1 10 10v80a10 10 0 0 1-10 10H20a10 10 0 0 1-10-10V60a10 10 0 0 1 10-10z" strokeWidth="2" />
      <path d="M20 50l80 50 80-50" strokeWidth="2" fill="none" />
      <circle cx="160" cy="60" r="16" strokeWidth="1.5" opacity="0.3" />
      <path d="M155 60h10 M160 55v10" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="100" cy="100" r="50" strokeWidth="2" />
      <path d="M100 50v15 M100 135v15 M50 100h15 M135 100h15" strokeWidth="2" strokeLinecap="round" />
      <circle cx="100" cy="100" r="20" strokeWidth="1.5" strokeDasharray="8 4" opacity="0.5" />
      <path d="M75 75l10 10 M85 75l-10 10 M115 75l10 10 M125 75l-10 10" strokeWidth="1.5" opacity="0.6" />
    </svg>
  ),
  'no-data': (
    <svg viewBox="0 0 200 200" className="w-32 h-32 mx-auto text-gray-300 dark:text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="25" y="40" width="150" height="120" rx="8" strokeWidth="2" />
      <path d="M55 75h90 M55 105h60 M55 135h75" strokeWidth="1.5" strokeDasharray="6 4" opacity="0.5" />
      <path d="M100 40v120 M25 100h150" strokeWidth="1" strokeDasharray="4 4" opacity="0.3" />
    </svg>
  ),
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  className,
  illustration = 'no-data',
}: EmptyStateProps) {
  const Illus = icon || ILLUSTRATIONS[illustration]

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn('flex flex-col items-center justify-center p-10 text-center', className)}
      role="status"
      aria-live="polite"
    >
      <div className="mb-6">
        {Illus}
      </div>

      <h3 className="text-lg font-semibold text-strong-fg mb-2">
        {title}
      </h3>

      {description && (
        <p className="text-muted-fg max-w-sm mx-auto mb-6 leading-relaxed">
          {description}
        </p>
      )}

      <div className="flex flex-col sm:flex-row items-center gap-3 w-full max-w-xs">
        {action && (
          <Button
            onClick={action.onClick}
            variant={action.variant || 'primary'}
            className="w-full sm:w-auto"
          >
            {action.label}
          </Button>
        )}
        {secondaryAction && (
          <Button
            onClick={secondaryAction.onClick}
            variant="ghost"
            className="w-full sm:w-auto"
          >
            {secondaryAction.label}
          </Button>
        )}
      </div>
    </motion.div>
  )
}

// Pre-built empty states for common scenarios
export const EmptyStates = {
  noAppointments: (onBook?: () => void) => (
    <EmptyState
      illustration="appointments"
      title="No appointments yet"
      description="Your schedule is clear. Book your first appointment to get started."
      action={onBook ? { label: 'Book Appointment', onClick: onBook } : undefined}
    />
  ),

  noPatients: (onAdd?: () => void) => (
    <EmptyState
      illustration="patients"
      title="No patients found"
      description="Add your first patient to begin building their medical record."
      action={onAdd ? { label: 'Add Patient', onClick: onAdd } : undefined}
    />
  ),

  noReports: () => (
    <EmptyState
      illustration="reports"
      title="No reports available"
      description="Reports will appear here after consultations, lab uploads, or AI-generated summaries."
    />
  ),

  noSearchResults: (onClear?: () => void) => (
    <EmptyState
      illustration="search"
      title="No results found"
      description="Try adjusting your search terms or filters."
      action={onClear ? { label: 'Clear filters', onClick: onClear, variant: 'outline' } : undefined}
    />
  ),

  noInboxMessages: () => (
    <EmptyState
      illustration="inbox"
      title="Inbox is empty"
      description="You're all caught up! New notifications will appear here."
    />
  ),

  noCalendarEvents: (onAdd?: () => void) => (
    <EmptyState
      illustration="calendar"
      title="No events this week"
      description="Your calendar is clear. Enjoy the free time or schedule something."
      action={onAdd ? { label: 'Schedule Event', onClick: onAdd } : undefined}
    />
  ),
}