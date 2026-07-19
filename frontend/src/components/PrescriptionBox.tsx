'use client'

import { useState } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Badge } from '@/components/ui/Badge'
import { Plus, X, Printer, Download, FileText, Loader2, AlertCircle, Pill } from 'lucide-react'

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

  const isValid = diagnosis.trim() && medications.some(m => m.drug.trim())

  const handleCreatePrescription = async () => {
    if (!isValid) return
    setGenerating(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(`/api/v1/patients/${patientId}/prescriptions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        body: JSON.stringify({
          patient_name: patientName,
          patient_age: patientAge,
          patient_gender: patientGender,
          diagnosis,
          medications: medications.filter(m => m.drug.trim()),
          instructions,
          follow_up: followUp,
        }),
      })
      if (!response.ok) throw new Error('Failed to create prescription')
      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
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
          <Label htmlFor="diagnosis">Diagnosis</Label>
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
          <Label htmlFor="instructions">Instructions</Label>
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
      </CardContent>
    </Card>
  )
}
