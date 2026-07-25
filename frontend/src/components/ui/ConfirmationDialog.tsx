import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { cn } from '@/utils/helpers'
import { Button } from './Button'

interface ConfirmationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  variant?: 'danger' | 'warning' | 'info'
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void | Promise<void>
  loading?: boolean
  children?: React.ReactNode
}

const ICONS = {
  danger: AlertTriangle,
  warning: AlertTriangle,
  info: AlertTriangle,
}

const COLORS = {
  danger: 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800 text-red-900 dark:text-red-100',
  warning: 'bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-800 text-amber-900 dark:text-amber-100',
  info: 'bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-800 text-blue-900 dark:text-blue-100',
}

const BUTTON_COLORS = {
  danger: 'bg-red-600 hover:bg-red-700 focus:ring-red-500',
  warning: 'bg-amber-600 hover:bg-amber-700 focus:ring-amber-500',
  info: 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-500',
}

export function ConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  variant = 'danger',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  loading = false,
  children,
}: ConfirmationDialogProps) {
  const Icon = ICONS[variant]

  if (!open) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-description"
      >
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-black/50 backdrop-blur-sm"
          onClick={() => onOpenChange(false)}
        />

        {/* Dialog */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.15, ease: [0.4, 0, 0.2, 1] }}
          className={cn(
            'relative w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6',
            COLORS[variant]
          )}
        >
          {/* Icon */}
          <motion.div
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ delay: 0.1, duration: 0.3, type: 'spring', stiffness: 300, damping: 20 }}
            className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4"
            style={{ backgroundColor: variant === 'danger' ? '#fef2f2' : variant === 'warning' ? '#fffbeb' : '#eff6ff' }}
          >
            <Icon className="w-7 h-7" style={{ color: variant === 'danger' ? '#dc2626' : variant === 'warning' ? '#ca8a04' : '#2563eb' }} />
          </motion.div>

          {/* Title & Description */}
          <div className="text-center mb-6">
            <h2 id="dialog-title" className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              {title}
            </h2>
            <p id="dialog-description" className="text-sm text-gray-600 dark:text-gray-400">
              {description}
            </p>
          </div>

          {/* Custom content */}
          {children && (
            <div className="mb-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-sm text-gray-600 dark:text-gray-400">
              {children}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
              className="flex-1"
            >
              {cancelLabel}
            </Button>
            <Button
              onClick={async () => {
                await onConfirm()
                onOpenChange(false)
              }}
              disabled={loading}
              className={cn('flex-1', BUTTON_COLORS[variant])}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Confirming...
                </span>
              ) : (
                confirmLabel
              )}
            </Button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

// Hook for easy confirmation dialogs
import { useState, useCallback } from 'react'

export function useConfirmation() {
  const [dialog, setDialog] = useState<{
    open: boolean
    title: string
    description: string
    variant: 'danger' | 'warning' | 'info'
    confirmLabel: string
    onConfirm: () => void | Promise<void>
  } | null>(null)

  const confirm = useCallback((options: {
    title: string
    description: string
    variant?: 'danger' | 'warning' | 'info'
    confirmLabel?: string
    onConfirm: () => void | Promise<void>
  }) => {
    setDialog({
      open: true,
      variant: options.variant || 'danger',
      confirmLabel: options.confirmLabel || 'Confirm',
      ...options,
    })
  }, [])

  const close = useCallback(() => setDialog(null), [])

  return { dialog, confirm, close, setOpen: (open: boolean) => setDialog(d => d ? { ...d, open } : null) }
}

// Hook component to render the dialog
export function ConfirmationDialogProvider() {
  const { dialog, close } = useConfirmation()

  return dialog ? (
    <ConfirmationDialog
      open={dialog.open}
      onOpenChange={close}
      title={dialog.title}
      description={dialog.description}
      variant={dialog.variant}
      confirmLabel={dialog.confirmLabel}
      onConfirm={async () => {
        await dialog.onConfirm()
        close()
      }}
    />
  ) : null
}