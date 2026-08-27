import { useEffect, useState } from 'react'
import { X, Loader2, AlertCircle, CheckCircle, FilePlus2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Label } from '@/components/ui/Label'
import apiClient from '@/services/api'

interface NewVersionModalProps {
  open: boolean
  onClose: () => void
  patientId: string
  headState?: any
  headVersion?: number | null
  onCreated: (version: any) => void
}

export function NewVersionModal({
  open,
  onClose,
  patientId,
  onCreated,
}: NewVersionModalProps) {
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<{ version_number: number } | null>(null)

  useEffect(() => {
    if (open) {
      setNote('')
      setError(null)
      setSaving(false)
      setDone(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const handleSubmit = async () => {
    const trimmed = note.trim()
    if (!trimmed) {
      setError('Enter a status note before saving.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const res = await apiClient.post(`/patients/${patientId}/versions/note`, { note: trimmed })
      setDone({ version_number: res.data.version_number })
      onCreated(res.data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create version')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-version-title"
    >
      <div
        className="relative bg-surface-2 rounded-lg shadow-card-hover w-full max-w-lg max-h-[92vh] flex flex-col border border-border"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <FilePlus2 className="h-5 w-5 text-primary-600" />
            <div>
              <h2 id="new-version-title" className="text-base font-semibold text-strong-fg">
                New Version
              </h2>
              <p className="text-xs text-muted-fg">
                Records a status update that inherits all current patient data
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-surface text-muted-fg hover:text-strong-fg"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {done ? (
            <div className="p-4 rounded-lg border-2 border-green-200 bg-green-50 dark:bg-green-900/20 dark:border-green-800">
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <h4 className="text-sm font-medium text-green-900 dark:text-green-100">
                    Version created
                  </h4>
                  <p className="mt-1 text-sm text-green-700 dark:text-green-300">
                    The record is now at <strong>v{done.version_number}</strong>. The
                    status note is indexed and will be cited in future chats.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div>
              <Label htmlFor="nv-note">Status note</Label>
              <textarea
                id="nv-note"
                value={note}
                onChange={e => setNote(e.target.value)}
                rows={5}
                autoFocus
                placeholder="e.g. Patient recovered from hypertension; off medication, monitoring BP."
                className="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
              />
              <p className="mt-2 text-xs text-muted-fg">
                This creates a new immutable version carrying forward the existing
                history (diagnoses, medications, vitals). Use a prescription to
                record medication changes.
              </p>
            </div>
          )}

          {error && (
            <div className="p-3 rounded-md border border-red-200 bg-red-50 text-sm text-severity-critical flex items-center gap-2">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-surface">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            {done ? 'Close' : 'Cancel'}
          </Button>
          {!done && (
            <Button onClick={handleSubmit} disabled={saving}>
              {saving ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving...</>
              ) : (
                <><CheckCircle className="h-4 w-4 mr-2" />Create version</>
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
