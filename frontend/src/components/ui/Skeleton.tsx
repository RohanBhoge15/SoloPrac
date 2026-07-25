import { motion } from 'framer-motion'
import { cn } from '@/utils/helpers'
import { HTMLAttributes } from 'react'

// Base skeleton with shimmer animation
interface SkeletonBaseProps {
  className?: string
  style?: React.CSSProperties
}

function SkeletonBase({ className, style }: SkeletonBaseProps) {
  return (
    <motion.div
      initial={{ opacity: 0.4 }}
      animate={{ opacity: [0.4, 1, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
      className={cn(
        'bg-gray-200 dark:bg-gray-700 rounded overflow-hidden',
        className
      )}
      style={style}
    />
  )
}

// Generic skeleton component
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <SkeletonBase className={cn('h-4 w-full', className)} {...props} />
}

// Card skeleton
export function CardSkeleton({ variant = 'default' }: { variant?: 'default' | 'compact' | 'stats' }) {
  if (variant === 'compact') {
    return (
      <div className="space-y-3 p-4">
        <div className="flex items-center gap-3">
          <SkeletonBase className="h-10 w-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <SkeletonBase className="h-4 w-3/4" />
            <SkeletonBase className="h-3 w-1/2" />
          </div>
        </div>
      </div>
    )
  }

  if (variant === 'stats') {
    return (
      <div className="p-4 space-y-3">
        <SkeletonBase className="h-4 w-1/4" />
        <SkeletonBase className="h-8 w-1/2" />
        <SkeletonBase className="h-3 w-1/3" />
      </div>
    )
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <SkeletonBase className="h-6 w-32" />
        <SkeletonBase className="h-6 w-20" />
      </div>
      <div className="space-y-3">
        <SkeletonBase className="h-12 w-full" />
        <SkeletonBase className="h-12 w-full" />
        <SkeletonBase className="h-12 w-full" />
      </div>
    </div>
  )
}

// Table row skeleton
export function TableRowSkeleton({ columns = 4 }: { columns?: number }) {
  return (
    <tr className="border-b border-gray-200 dark:border-gray-700">
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="py-3 px-4">
          <SkeletonBase className="h-4 w-full" style={{ width: i === 0 ? '60%' : '80%' }} />
        </td>
      ))}
    </tr>
  )
}

// Table skeleton with multiple rows
export function TableSkeleton({ rows = 5, columns = 4, showHeader = true }: { rows?: number; columns?: number; showHeader?: boolean }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="w-full">
        <thead>
          {showHeader && (
            <tr className="bg-gray-50 dark:bg-gray-800/50">
              {Array.from({ length: columns }).map((_, i) => (
                <th key={i} className="py-3 px-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <SkeletonBase className="h-4 w-3/4" />
                </th>
              ))}
            </tr>
          )}
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <TableRowSkeleton key={rowIndex} columns={columns} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

// List skeleton
export function ListSkeleton({ items = 5, showAvatar = true, lines = 2 }: { items?: number; showAvatar?: boolean; lines?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="flex gap-3 items-start">
          {showAvatar && <SkeletonBase className="h-10 w-10 rounded-full mt-1 flex-shrink-0" />}
          <div className="flex-1 space-y-2 min-w-0">
            <SkeletonBase className="h-4 w-3/4" />
            {Array.from({ length: lines - 1 }).map((_, j) => (
              <SkeletonBase key={j} className="h-3 w-full" style={{ width: j === lines - 2 ? '60%' : '100%' }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// Calendar/day grid skeleton
export function CalendarSkeleton({ weeks = 1 }: { weeks?: number }) {
  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="grid grid-cols-7 gap-1 text-center text-xs font-medium text-gray-500 dark:text-gray-400 py-2">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => (
          <div key={day}>{day}</div>
        ))}
      </div>

      {/* Weeks */}
      <div className="space-y-1">
        {Array.from({ length: weeks * 7 }).map((_, i) => (
          <div
            key={i}
            className={cn(
              'aspect-square rounded-lg flex items-center justify-center',
              i % 7 === 0 && 'col-start-1'
            )}
          >
            <SkeletonBase className="h-6 w-6" />
          </div>
        ))}
      </div>
    </div>
  )
}

// Patient card skeleton
export function PatientCardSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-3">
        <SkeletonBase className="h-12 w-12 rounded-full" />
        <div className="flex-1 space-y-2">
          <SkeletonBase className="h-5 w-40" />
          <SkeletonBase className="h-4 w-32" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <SkeletonBase className="h-6 w-24 rounded-full" />
        <SkeletonBase className="h-6 w-24 rounded-full" />
        <SkeletonBase className="h-6 w-24 rounded-full" />
      </div>
      <div className="space-y-2 pt-2 border-t border-gray-200 dark:border-gray-700">
        <SkeletonBase className="h-4 w-full" />
        <SkeletonBase className="h-4 w-3/4" />
      </div>
    </div>
  )
}

// Appointment slot skeleton
export function AppointmentSlotSkeleton() {
  return (
    <div className="p-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <div className="flex items-center gap-2">
        <SkeletonBase className="h-4 w-16" />
        <SkeletonBase className="h-3 w-24 flex-1" />
      </div>
    </div>
  )
}

// Dashboard stats grid skeleton
export function StatsGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} variant="stats" />
      ))}
    </div>
  )
}

// Form skeleton
export function FormSkeleton({ fields = 4 }: { fields?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: fields }).map((_, i) => (
        <div key={i} className="space-y-1.5">
          <SkeletonBase className="h-4 w-1/4" />
          <SkeletonBase className="h-10 w-full" />
        </div>
      ))}
    </div>
  )
}

// Chat/message skeleton
export function ChatSkeleton({ messages = 3 }: { messages?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: messages }).map((_, i) => (
        <div key={i} className="flex gap-3" style={{ alignSelf: i % 2 === 0 ? 'flex-start' : 'flex-end' }}>
          <SkeletonBase className="h-8 w-8 rounded-full flex-shrink-0" />
          <div className="flex-1 max-w-xs">
            <SkeletonBase className="h-8 w-full rounded-xl" />
            <SkeletonBase className="h-6 w-3/4 rounded-xl mt-1" />
          </div>
        </div>
      ))}
    </div>
  )
}

// Generic page skeleton
export function PageSkeleton({ showHeader = true, showSidebar = false }: { showHeader?: boolean; showSidebar?: boolean }) {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {showHeader && (
        <header className="border-b border-gray-200 dark:border-gray-800">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <SkeletonBase className="h-8 w-32" />
            <div className="flex items-center gap-4">
              <SkeletonBase className="h-8 w-8 rounded-full" />
              <SkeletonBase className="h-8 w-24" />
            </div>
          </div>
        </header>
      )}

      <div className={cn('flex', showSidebar && 'lg:flex')}>
        {showSidebar && (
          <aside className="w-64 border-r border-gray-200 dark:border-gray-800 hidden lg:block">
            <nav className="p-4 space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <SkeletonBase key={i} className="h-10 w-full rounded-lg" />
              ))}
            </nav>
          </aside>
        )}

        <main className="flex-1 p-6 space-y-6">
          <div>
            <SkeletonBase className="h-8 w-48" />
            <SkeletonBase className="h-4 w-64 mt-2" />
          </div>

          <StatsGridSkeleton count={4} />

          <CardSkeleton />
          <CardSkeleton />
        </main>
      </div>
    </div>
  )
}