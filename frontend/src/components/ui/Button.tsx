import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/helpers'

// Clinical-direction button. Variants tuned so:
//  - `primary` is the ONE strong action per screen (teal-blue 600)
//  - `secondary` is the read-safe alternative that lives next to it
//  - `outline` is for tertiary actions on a busy card
//  - `ghost` is for icon-only affordances in toolbars
//  - `destructive` uses the severity-critical token (not raw red-600)
// Focus ring is 2px, offset from the surface token — reads clearly on both light/dark.
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ' +
    'transition-all duration-150 select-none ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2 focus-visible:ring-offset-surface ' +
    'disabled:opacity-50 disabled:pointer-events-none disabled:shadow-none ' +
    'active:scale-[0.98]',
  {
    variants: {
      variant: {
        default: 'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 shadow-sm',
        primary: 'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 shadow-sm',
        destructive: 'bg-critical text-white hover:bg-critical/90 active:bg-critical/80 shadow-sm',
        outline:
          'border border-border bg-surface-2 text-strong-fg hover:bg-surface-3 hover:border-border-strong',
        secondary:
          'bg-surface-2 border border-border text-strong-fg hover:bg-primary-50 hover:border-primary-200 hover:text-primary-700',
        ghost: 'bg-transparent text-strong-fg hover:bg-surface-3 active:bg-surface-3',
        link: 'text-primary-700 underline-offset-4 hover:underline p-0 h-auto shadow-none',
        accent: 'bg-accent-600 text-white hover:bg-accent-700 active:bg-accent-800 shadow-sm',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 px-3 text-[13px]',
        lg: 'h-11 px-6',
        xl: 'h-12 px-8 text-base',
        icon: 'h-10 w-10 shrink-0',
        'icon-sm': 'h-8 w-8 shrink-0',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }), loading && 'pointer-events-none')}
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading && (
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
        )}
        {children}
      </Comp>
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }
