import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/helpers'

// Clinical Badge. Every variant tints the background lightly and uses the
// dark token for text — the old gray/red/green hex literals are gone.
// Severity variants (critical/high/moderate/low) map to the tokens in
// tailwind.config.js so charts and badges speak the same color language.
const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default:
          'border-transparent bg-primary-50 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200',
        primary:
          'border-transparent bg-primary-50 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200',
        secondary: 'border-border bg-surface-2 text-muted-fg',
        accent:
          'border-transparent bg-accent-50 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200',
        success:
          'border-transparent bg-accent-50 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200',
        warning:
          'border-transparent bg-yellow-50 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
        destructive:
          'border-transparent bg-red-50 text-severity-critical dark:bg-red-900/40 dark:text-red-200',
        outline: 'border-border bg-transparent text-strong-fg',

        // Severity variants — align badges with severity coloring used in
        // charts and alerts. Same token, same meaning everywhere.
        critical: 'border-transparent bg-red-50 text-severity-critical',
        high: 'border-transparent bg-orange-50 text-severity-high',
        moderate: 'border-transparent bg-amber-50 text-severity-moderate',
        low: 'border-transparent bg-slate-100 text-severity-low',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
