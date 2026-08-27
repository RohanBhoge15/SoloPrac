import { useEffect, useState } from 'react'
import { X, Plus, Trash2, Save, Loader2, AlertCircle, Pill, CheckCircle, Download } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Label } from '@/components/ui/Label'
import apiClient from '@/services/api'
import { openPdfViaBlob } from '@/utils/helpers'

interface Med {
  drug: string
  strength: string
  dose: string
  frequency: string
  duration: string
}

interface NewPrescriptionModalProps {
  open: boolean
  onClose: () => void
  patientId: string
  patient: {
    name?: string
    age?: number
    gender?: string
  }
  onCreated: (prescription: any) => void
  onApproved?: (versionInfo: any) => void
}

const EMPTY_MED: Med = { drug: '', strength: '', dose: '', frequency: '', duration: '' }

export function NewPrescriptionModal({
  open,
  onClose,
  patientId,
  patient,
  onCreated,
  onApproved,
}: NewPrescriptionModalProps) {
  const [meds, setMeds] = useState<Med[]>([{ ...EMPTY_MED }])
  const [diagnosis, setDiagnosis] = useState('')
  const [instructions, setInstructions] = useState('')
  const [followUp, setFollowUp] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showApproval, setShowApproval] = useState(false)
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)
  const [createdRx, setCreatedRx] = useState<any>(null)
  const [versionInfo, setVersionInfo] = useState<any>(null)

  useEffect(() => {
    if (open) {
      setMeds([{ ...EMPTY_MED }])
      setDiagnosis('')
      setInstructions('')
      setFollowUp('')
      setError(null)
      setShowApproval(false)
      setApproved(false)
      setCreatedRx(null)
      setVersionInfo(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const updateMed = (idx: number, patch: Partial<Med>) => {
    setMeds(m => m.map((row, i) => i === idx ? { ...row, ...patch } : row))
  }

  const addMed = () => setMeds(m => [...m, { ...EMPTY_MED }])
  const removeMed = (idx: number) => {
    setMeds(m => m.length === 1 ? m : m.filter((_, i) => i !== idx))
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const validMeds = meds.filter(m => m.drug.trim())
      if (validMeds.length === 0 && !diagnosis.trim()) {
        setError('Add at least one medication or a diagnosis.')
        setSaving(false)
        return
      }

      const body = {
        medications: validMeds,
        diagnosis,
        instructions,
        follow_up: followUp,
        patient_name: patient.name || 'Patient',
        patient_age: patient.age || 0,
        patient_gender: patient.gender || '',
      }

      const res = await apiClient.post(`/patients/${patientId}/prescriptions`, body)
      setCreatedRx(res.data)
      setShowApproval(true)
      setSaving(false)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create prescription')
      setSaving(false)
    }
  }

  const handleApprove = async () => {
    if (!createdRx?.id) return
    setApproving(true)
    setError(null)
    try {
      const res = await apiClient.post(`/prescriptions/${createdRx.id}/approve`)
      setVersionInfo(res.data)
      setApproved(true)
      setShowApproval(false)
      onApproved?.(res.data)
      onCreated(res.data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to approve prescription')
    } finally {
      setApproving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-rx-title"
    >
      <div
        className="relative bg-surface-2 rounded-lg shadow-card-hover w-full max-w-2xl max-h-[92vh] flex flex-col border border-border"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Pill className="h-5 w-5 text-primary-600" />
            <div>
              <h2 id="new-rx-title" className="text-base font-semibold text-strong-fg">
                {approved ? 'Prescription Approved' : 'New Prescription'}
              </h2>
              <p className="text-xs text-muted-fg">
                for {patient.name || 'Patient'}{patient.age ? ` · ${patient.age}y` : ''}{patient.gender ? ` · ${patient.gender}` : ''}
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

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {/* Form fields - hidden when showing approval/success */}
          {!showApproval && !approved && (
            <>
              <div>
                <Label htmlFor="nrx-diagnosis">Diagnosis</Label>
                <input
                  id="nrx-diagnosis"
                  type="text"
                  value={diagnosis}
                  onChange={e => setDiagnosis(e.target.value)}
                  placeholder="e.g. Acute pharyngitis"
                  className="flex h-10 w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label>Medications</Label>
                  <Button variant="ghost" size="sm" onClick={addMed}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add medication
                  </Button>
                </div>
                <div className="space-y-2">
                  {meds.map((m, idx) => (
                    <div key={idx} className="rounded-md border border-border bg-surface p-3">
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          type="text"
                          value={m.drug}
                          onChange={e => updateMed(idx, { drug: e.target.value })}
                          placeholder="Drug (e.g. Amoxicillin)"
                          className="col-span-2 flex h-9 w-full rounded-md border border-border bg-surface-2 px-3 py-1.5 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                        />
                        <input
                          type="text"
                          value={m.strength}
                          onChange={e => updateMed(idx, { strength: e.target.value })}
                          placeholder="Strength (500mg)"
                          className="flex h-9 w-full rounded-md border border-border bg-surface-2 px-3 py-1.5 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                        />
                        <input
                          type="text"
                          value={m.dose}
                          onChange={e => updateMed(idx, { dose: e.target.value })}
                          placeholder="Dose (1 tab)"
                          className="flex h-9 w-full rounded-md border border-border bg-surface-2 px-3 py-1.5 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                        />
                        <input
                          type="text"
                          value={m.frequency}
                          onChange={e => updateMed(idx, { frequency: e.target.value })}
                          placeholder="Frequency (TID)"
                          className="flex h-9 w-full rounded-md border border-border bg-surface-2 px-3 py-1.5 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                        />
                        <input
                          type="text"
                          value={m.duration}
                          onChange={e => updateMed(idx, { duration: e.target.value })}
                          placeholder="Duration (5 days)"
                          className="flex h-9 w-full rounded-md border border-border bg-surface-2 px-3 py-1.5 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                        />
                      </div>
                      {meds.length > 1 && (
                        <div className="flex justify-end mt-2">
                          <button
                            type="button"
                            onClick={() => removeMed(idx)}
                            className="text-xs text-muted-fg hover:text-severity-critical inline-flex items-center gap-1"
                          >
                            <Trash2 className="h-3 w-3" /> Remove
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <Label htmlFor="nrx-instructions">Instructions</Label>
                <textarea
                  id="nrx-instructions"
                  value={instructions}
                  onChange={e => setInstructions(e.target.value)}
                  rows={3}
                  placeholder="Take with food. Complete the full course."
                  className="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                />
              </div>

              <div>
                <Label htmlFor="nrx-follow">Follow-up</Label>
                <input
                  id="nrx-follow"
                  type="text"
                  value={followUp}
                  onChange={e => setFollowUp(e.target.value)}
                  placeholder="e.g. In 7 days if symptoms persist"
                  className="flex h-10 w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600"
                />
              </div>
            </>
          )}

          {/* Approval Popup */}
          {showApproval && (
            <div className="p-4 rounded-lg border-2 border-blue-200 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-800">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-0.5">
                  <CheckCircle className="h-5 w-5 text-blue-600" />
                </div>
                <div className="flex-1">
                  <h4 className="text-sm font-medium text-blue-900 dark:text-blue-100">
                    Prescription Ready
                  </h4>
                  <p className="mt-1 text-sm text-blue-700 dark:text-blue-300">
                    Add this prescription to <strong>{patient.name}</strong>'s record?
                    This will create a new version with the diagnosis and medications.
                  </p>
                  {createdRx?.pdf_path && (
                    <div className="mt-2 flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openPdfViaBlob(`/patients/${patientId}/prescriptions/${createdRx.id}/pdf`)}
                      >
                        <Download className="h-3 w-3 mr-1" /> Preview PDF
                      </Button>
                    </div>
                  )}
                  <div className="mt-3 flex items-center gap-2">
                    <Button
                      size="sm"
                      onClick={handleApprove}
                      disabled={approving}
                      className="bg-blue-600 hover:bg-blue-700 text-white"
                    >
                      {approving ? (
                        <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Approving...</>
                      ) : (
                        <><CheckCircle className="h-3 w-3 mr-1" /> Approve to Record</>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => { setShowApproval(false); onCreated(createdRx); }}
                      disabled={approving}
                    >
                      Skip
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Approval Success */}
          {approved && versionInfo && (
            <div className="p-4 rounded-lg border-2 border-green-200 bg-green-50 dark:bg-green-900/20 dark:border-green-800">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-0.5">
                  <CheckCircle className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <h4 className="text-sm font-medium text-green-900 dark:text-green-100">
                    Record Updated
                  </h4>
                  <p className="mt-1 text-sm text-green-700 dark:text-green-300">
                    {patient.name}'s record is now at <strong>v{versionInfo.version_number}</strong>
                  </p>
                </div>
              </div>
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
          <Button variant="outline" onClick={onClose} disabled={saving || approving}>
            {approved ? 'Close' : 'Cancel'}
          </Button>
          {!showApproval && !approved && (
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Generating...</> : <><Save className="h-4 w-4 mr-2" />Create prescription</>}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
