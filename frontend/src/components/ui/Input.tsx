import * as React from 'react'
import { cn } from '@/utils/helpers'

// Input re-themed to clinical tokens. Adds an `error` prop that flips the
// left border + ring red — the old version had no clear error visual so
// form failures had to be surfaced only via toast, which the user misses.
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, error, ...props }, ref) => {
    return (
      <input
        type={type}
        aria-invalid={error || undefined}
        className={cn(
          'flex h-10 w-full rounded-md border bg-surface-2 px-3 py-2 text-sm text-strong-fg',
          'placeholder:text-muted-fg',
          'focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-60',
          error
            ? 'border-severity-critical focus:ring-severity-critical/30 focus:border-severity-critical'
            : 'border-border focus:border-primary-600 focus:ring-primary-600/25',
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = 'Input'

export { Input }
