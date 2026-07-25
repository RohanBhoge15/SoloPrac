'use client'

import { toast as sonnerToast, Toaster } from 'sonner'
import { motion } from 'framer-motion'
import { cn } from '@/utils/helpers'

// Toast types
export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading' | 'promise'

export interface ToastOptions {
  description?: string
  action?: { label: string; onClick: () => void }
  duration?: number
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'top-center' | 'bottom-center'
}

// Enhanced toast function with better UX
export const toast = {
  success: (message: string, options?: ToastOptions) => sonnerToast.success(message, options),
  error: (message: string, options?: ToastOptions) => sonnerToast.error(message, options),
  warning: (message: string, options?: ToastOptions) => sonnerToast.warning(message, options),
  info: (message: string, options?: ToastOptions) => sonnerToast.info(message, options),
  loading: (message: string, options?: ToastOptions) => sonnerToast.loading(message, options),
  promise: <T,>(promise: Promise<T>, messages: { loading: string; success: string | ((data: T) => string); error: string | ((error: Error) => string) }) =>
    sonnerToast.promise(promise, messages),
  dismiss: (id?: string | number) => sonnerToast.dismiss(id),
}

// Custom hook with additional helpers
export function useToast() {
  return {
    success: (message: string, options?: ToastOptions) => toast.success(message, options),
    error: (message: string, options?: ToastOptions) => toast.error(message, options),
    warning: (message: string, options?: ToastOptions) => toast.warning(message, options),
    info: (message: string, options?: ToastOptions) => toast.info(message, options),
    loading: (message: string, options?: ToastOptions) => toast.loading(message, options),
    promise: <T,>(promise: Promise<T>, messages: { loading: string; success: string | ((data: T) => string); error: string | ((error: Error) => string) }) =>
      toast.promise(promise, messages),
    dismiss: (id?: string | number) => toast.dismiss(id),
  }
}

// ToastProvider component to wrap the app
export function ToastProvider({ children, position = 'top-right', theme = 'system' }: {
  children: React.ReactNode
  position?: ToastOptions['position']
  theme?: 'light' | 'dark' | 'system'
}) {
  return (
    <>
      {children}
      <Toaster
        position={position}
        theme={theme}
        toastOptions={{
          duration: 4000,
          style: {
            background: 'var(--toast-bg)',
            color: 'var(--toast-fg)',
            border: '1px solid var(--toast-border)',
            boxShadow: 'var(--toast-shadow)',
          },
        }}
        icons={{
          success: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>,
          error: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>,
          warning: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>,
          info: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
        }}
      />
    </>
  )
}

// Inline toast component for forms/pages (non-sonner)
interface InlineToastProps {
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  description?: string
  onDismiss?: () => void
  action?: { label: string; onClick: () => void }
  className?: string
}

const ICONS = {
  success: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>,
  error: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>,
  warning: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>,
  info: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
}

const COLORS = {
  success: 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-400 border-green-200 dark:border-green-800',
  error: 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-400 border-red-200 dark:border-red-800',
  warning: 'bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800',
  info: 'bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-400 border-blue-200 dark:border-blue-800',
}

export function InlineToast({
  type,
  title,
  description,
  onDismiss,
  action,
  className,
}: InlineToastProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10, height: 0 }}
      animate={{ opacity: 1, y: 0, height: 'auto' }}
      exit={{ opacity: 0, y: -10, height: 0 }}
      className={cn(
        'flex items-start gap-3 p-4 rounded-xl border',
        COLORS[type],
        className
      )}
      role="alert"
    >
      <div className={cn('flex-shrink-0 mt-0.5', {
        'text-green-600 dark:text-green-400': type === 'success',
        'text-red-600 dark:text-red-400': type === 'error',
        'text-yellow-600 dark:text-yellow-400': type === 'warning',
        'text-blue-600 dark:text-blue-400': type === 'info',
      })}>
        {ICONS[type]}
      </div>

      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900 dark:text-white">{title}</p>
        {description && (
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{description}</p>
        )}
        {action && (
          <button
            onClick={action.onClick}
            className="mt-3 text-sm font-medium underline hover:no-underline focus:outline-none focus:ring-2 focus:ring-offset-2"
            style={{ color: `var(--${type}-color)` }}
          >
            {action.label}
          </button>
        )}
      </div>

      {onDismiss && (
        <button
          onClick={onDismiss}
          className="flex-shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Dismiss"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </motion.div>
  )
}