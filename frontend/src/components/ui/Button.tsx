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
    'transition-colors duration-150 ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2 ' +
    'disabled:opacity-50 disabled:pointer-events-none',
  {
    variants: {
      variant: {
        default: 'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 shadow-sm',
        primary: 'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 shadow-sm',
        destructive: 'bg-severity-critical text-white hover:brightness-95 active:brightness-90 shadow-sm',
        outline:
          'border border-border bg-transparent text-strong-fg hover:bg-surface-2 hover:border-primary-300',
        secondary:
          'bg-surface-2 border border-border text-strong-fg hover:bg-primary-50 hover:border-primary-300',
        ghost: 'bg-transparent text-strong-fg hover:bg-surface-2',
        link: 'text-primary-700 underline-offset-4 hover:underline p-0 h-auto',
        accent: 'bg-accent-600 text-white hover:bg-accent-700 active:bg-accent-800 shadow-sm',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 px-3 text-[13px]',
        lg: 'h-11 px-6',
        xl: 'h-12 px-8 text-base',
        icon: 'h-10 w-10',
        'icon-sm': 'h-8 w-8',
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
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }
