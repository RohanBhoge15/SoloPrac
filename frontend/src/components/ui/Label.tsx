import { cn } from '@/utils/helpers'

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={cn('text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 block', className)} {...props} />
  )
}