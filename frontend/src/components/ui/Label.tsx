import { cn } from '@/utils/helpers'

// Field label — clinical token version. Slightly heavier weight than shadcn's
// default (500) because form-heavy screens (patient intake, prescription
// editor) read better when the labels aren't ghost-thin.
export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        'text-sm font-medium text-strong-fg mb-1 block leading-tight',
        className
      )}
      {...props}
    />
  )
}
