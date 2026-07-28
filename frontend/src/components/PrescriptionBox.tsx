'use client'

import { useState, useRef, useCallback } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Badge } from '@/components/ui/Badge'
import { Plus, X, Printer, Download, FileText, Loader2, AlertCircle, Pill, CheckCircle, Mic, MicOff } from 'lucide-react'
import apiClient from '@/services/api'

interface Medication {
  drug: string
  strength: string
  dose: string
  frequency: string
  duration: string
  instructions?: string
}

interface PrescriptionBoxProps {
  patientId: string
  patientName: string
  patientAge: number
  patientGender: string
  className?: string
}

export function PrescriptionBox({
  patientId,
  patientName,
  patientAge,
  patientGender,
  className,
}: PrescriptionBoxProps) {
  const [diagnosis, setDiagnosis] = useState('')
  const [medications, setMedications] = useState<Medication[]>([
    { drug: '', strength: '', dose: '', frequency: '', duration: '' },
  ])
  const [instructions, setInstructions] = useState('')
  const [followUp, setFollowUp] = useState('')
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<{ id: string; pdf_path?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showApproval, setShowApproval] = useState(false)
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)
  const [versionInfo, setVersionInfo] = useState<{ version_number: number } | null>(null)
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [recordingField, setRecordingField] = useState<'diagnosis' | 'instructions' | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const addMedication = () => {
    setMedications([...medications, { drug: '', strength: '', dose: '', frequency: '', duration: '' }])
  }

  const removeMedication = (idx: number) => {
    if (medications.length > 1) {
      setMedications(medications.filter((_, i) => i !== idx))
    }
  }

  const updateMedication = (idx: number, field: keyof Medication, value: string) => {
    setMedications(medications.map((m, i) => i === idx ? { ...m, [field]: value } : m))
  }

  const toggleRecording = useCallback(async (field: 'diagnosis' | 'instructions') => {
    if (recording) {
      // Stop recording
      mediaRecorderRef.current?.stop()
      setRecording(false)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm',
      })
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        if (blob.size < 1000) return

        setTranscribing(true)
        try {
          const formData = new FormData()
          formData.append('file', blob, `voice-${Date.now()}.webm`)
          const res = await apiClient.post('/voice/transcribe', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 30000,
          })
          const text = res.data?.text || ''
          if (text) {
            if (field === 'diagnosis') setDiagnosis(prev => prev ? `${prev} ${text}` : text)
            else setInstructions(prev => prev ? `${prev} ${text}` : text)
          }
        } catch (err: any) {
          const msg = err?.response?.status === 503
            ? 'Voice transcription not available — ASR model not installed'
            : 'Transcription failed'
          console.warn('[Voice]', msg, err)
        } finally {
          setTranscribing(false)
          setRecordingField(null)
        }
      }

      mediaRecorderRef.current = mediaRecorder
      mediaRecorder.start()
      setRecording(true)
      setRecordingField(field)
    } catch (err) {
      console.warn('[Voice] Microphone access denied:', err)
    }
  }, [recording])

  const isValid = diagnosis.trim() && medications.some(m => m.drug.trim())

  const handleCreatePrescription = async () => {
    if (!isValid) return
    setGenerating(true)
    setError(null)
    setResult(null)

    try {
      const response = await apiClient.post(`/patients/${patientId}/prescriptions`, {
        patient_name: patientName,
        patient_age: patientAge,
        patient_gender: patientGender,
        diagnosis,
        medications: medications.filter(m => m.drug.trim()),
        instructions,
        follow_up: followUp,
      })
      setResult(response.data)
      setShowApproval(true) // Show approval popup after PDF is created
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to create prescription')
    } finally {
      setGenerating(false)
    }
  }

  const handleApprove = async () => {
    if (!result?.id) return
    setApproving(true)
    setError(null)

    try {
      const response = await apiClient.post(`/prescriptions/${result.id}/approve`)
      setVersionInfo(response.data)
      setApproved(true)
      setShowApproval(false)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to approve prescription')
    } finally {
      setApproving(false)
    }
  }

  const handleDismiss = () => {
    setShowApproval(false)
  }

  return (
    <Card className={cn('w-full border-2 border-yellow-200 dark:border-yellow-800', className)}>
      <CardHeader className="bg-yellow-50 dark:bg-yellow-900/10 border-b border-yellow-200 dark:border-yellow-800">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Pill className="h-5 w-5 text-yellow-600" />
          Prescription Box
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        {/* Diagnosis */}
        <div>
          <div className="flex items-center gap-2">
            <Label htmlFor="diagnosis">Diagnosis</Label>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={cn(
                'h-6 w-6',
                recording && 'text-red-500 animate-pulse',
                transcribing && 'text-blue-500 animate-spin',
              )}
              onClick={() => toggleRecording('diagnosis')}
              disabled={transcribing}
              title={recording ? 'Stop recording' : 'Voice input'}
            >
              {recording && recordingField === 'diagnosis' ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
            </Button>
            {(recording || transcribing) && recordingField === 'diagnosis' && (
              <span className="text-xs text-gray-400">
                {recording ? 'Recording... tap to stop' : 'Transcribing...'}
              </span>
            )}
          </div>
          <Input
            id="diagnosis"
            value={diagnosis}
            onChange={e => setDiagnosis(e.target.value)}
            placeholder="e.g., Type 2 Diabetes Mellitus"
            className="mt-1"
          />
        </div>

        {/* Medications Table */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <Label>Medications</Label>
            <Button variant="ghost" size="sm" onClick={addMedication}>
              <Plus className="h-3 w-3 mr-1" /> Add
            </Button>
          </div>
          <div className="space-y-2">
            {medications.map((med, idx) => (
              <div key={idx} className="flex items-start gap-1 p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-1 flex-1">
                  <Input placeholder="Drug" value={med.drug} onChange={e => updateMedication(idx, 'drug', e.target.value)} className="h-8 text-xs" />
                  <Input placeholder="Strength" value={med.strength} onChange={e => updateMedication(idx, 'strength', e.target.value)} className="h-8 text-xs" />
                  <Input placeholder="Dose" value={med.dose} onChange={e => updateMedication(idx, 'dose', e.target.value)} className="h-8 text-xs" />
                  <Input placeholder="Frequency" value={med.frequency} onChange={e => updateMedication(idx, 'frequency', e.target.value)} className="h-8 text-xs" />
                  <Input placeholder="Duration" value={med.duration} onChange={e => updateMedication(idx, 'duration', e.target.value)} className="h-8 text-xs" />
                </div>
                {medications.length > 1 && (
                  <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => removeMedication(idx)}>
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Instructions */}
        <div>
          <div className="flex items-center gap-2">
            <Label htmlFor="instructions">Instructions</Label>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={cn(
                'h-6 w-6',
                recording && recordingField === 'instructions' && 'text-red-500 animate-pulse',
                transcribing && recordingField === 'instructions' && 'text-blue-500 animate-spin',
              )}
              onClick={() => toggleRecording('instructions')}
              disabled={transcribing}
              title={recording ? 'Stop recording' : 'Voice input'}
            >
              {recording && recordingField === 'instructions' ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
            </Button>
            {(recording || transcribing) && recordingField === 'instructions' && (
              <span className="text-xs text-gray-400">
                {recording ? 'Recording... tap to stop' : 'Transcribing...'}
              </span>
            )}
          </div>
          <Input id="instructions" value={instructions} onChange={e => setInstructions(e.target.value)} placeholder="e.g., Take after meals" className="mt-1" />
        </div>

        {/* Follow-up */}
        <div>
          <Label htmlFor="followUp">Follow-up</Label>
          <Input id="followUp" value={followUp} onChange={e => setFollowUp(e.target.value)} placeholder="e.g., Review in 4 weeks" className="mt-1" />
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-2">
          {result?.pdf_path && (
            <div className="flex items-center gap-2">
              <Badge variant="default" className="bg-green-100 text-green-700">PDF Ready</Badge>
              <Button variant="outline" size="sm" onClick={() => window.open(result.pdf_path, '_blank')}>
                <Download className="h-3 w-3 mr-1" /> Download
              </Button>
              <Button variant="outline" size="sm" onClick={() => window.open(result.pdf_path, '_blank')}>
                <Printer className="h-3 w-3 mr-1" /> Print
              </Button>
            </div>
          )}
          <Button onClick={handleCreatePrescription} disabled={!isValid || generating} className="ml-auto">
            {generating ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating...</> : <><FileText className="h-4 w-4 mr-2" /> Generate Prescription</>}
          </Button>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-2 rounded-lg bg-red-50 text-sm text-red-700">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}

        {/* Approval Popup */}
        {showApproval && (
          <div className="mt-4 p-4 rounded-lg border-2 border-blue-200 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-800">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">
                <CheckCircle className="h-5 w-5 text-blue-600" />
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-medium text-blue-900 dark:text-blue-100">
                  Prescription Ready
                </h4>
                <p className="mt-1 text-sm text-blue-700 dark:text-blue-300">
                  Add this prescription to <strong>{patientName}</strong>'s record? This will create a new version (v{versionInfo?.version_number ? versionInfo.version_number + 1 : '?'}) with the diagnosis and medications.
                </p>
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
                    onClick={handleDismiss}
                    disabled={approving}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Approval Success */}
        {approved && versionInfo && (
          <div className="mt-4 p-4 rounded-lg border-2 border-green-200 bg-green-50 dark:bg-green-900/20 dark:border-green-800">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">
                <CheckCircle className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <h4 className="text-sm font-medium text-green-900 dark:text-green-100">
                  Record Updated
                </h4>
                <p className="mt-1 text-sm text-green-700 dark:text-green-300">
                  {patientName}'s record is now at <strong>v{versionInfo.version_number}</strong>
                </p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
