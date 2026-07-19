'use client'

import { useState } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Label } from '@/components/ui/Label'
import { Printer, Download, FileText, Loader2, AlertCircle, Calendar, CalendarDays, CalendarX } from 'lucide-react'

interface CertificateUIProps {
  patientId: string
  patientName: string
  className?: string
}

const CERT_TYPES = [
  { value: 'sick_leave', label: 'Sick Leave', icon: CalendarX },
  { value: 'fitness', label: 'Fitness', icon: CalendarDays },
  { value: 'school', label: 'School', icon: Calendar },
  { value: 'disability', label: 'Disability', icon: Calendar },
  { value: 'other', label: 'Other', icon: Calendar },
] as const

export function CertificateUI({ patientId, patientName, className }: CertificateUIProps) {
  const [certType, setCertType] = useState<'sick_leave' | 'fitness' | 'school' | 'disability' | 'other'>('sick_leave')
  const [body, setBody] = useState('')
  const [recommendedRest, setRecommendedRest] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<{ id: string; verification_code?: string; pdf_path?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isValid = body.trim().length > 0

  const handleCreate = async () => {
    if (!isValid) return
    setGenerating(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(`/api/v1/patients/${patientId}/certificates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        body: JSON.stringify({
          cert_type: certType,
          body,
          recommended_rest: recommendedRest,
          patient_name: patientName,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        }),
      })
      if (!response.ok) throw new Error('Failed to create certificate')
      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Card className={cn('w-full border-2 border-purple-200 dark:border-purple-800', className)}>
      <CardHeader className="bg-purple-50 dark:bg-purple-900/10 border-b border-purple-200 dark:border-purple-800">
        <CardTitle className="flex items-center gap-2 text-lg">
          <FileText className="h-5 w-5 text-purple-600" />
          Certificate Generator
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {CERT_TYPES.map(type => (
            <button
              key={type.value}
              onClick={() => setCertType(type.value as typeof certType)}
              className={cn(
                'p-3 rounded-lg border-2 text-sm font-medium transition-colors',
                certType === type.value
                  ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300'
                  : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50'
              )}
            >
              <div className="flex items-center gap-2">
                <type.icon className="h-4 w-4" />
                <span>{type.label}</span>
              </div>
            </button>
          ))}
        </div>

        <div>
          <Label htmlFor="body">Certificate Body</Label>
          <textarea
            id="body"
            value={body}
            onChange={e => setBody(e.target.value)}
            rows={4}
            className={cn(
              'w-full p-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm',
              'focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent'
            )}
            placeholder="Enter certificate details..."
          />
        </div>

        {['sick_leave', 'fitness'].includes(certType) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label htmlFor="startDate">Start Date</Label>
              <Input id="startDate" type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label htmlFor="endDate">End Date</Label>
              <Input id="endDate" type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="mt-1" />
            </div>
          </div>
        )}

        <div>
          <Label htmlFor="recommendedRest">Recommended Rest / Notes</Label>
          <Input id="recommendedRest" value={recommendedRest} onChange={e => setRecommendedRest(e.target.value)} placeholder="e.g., 5 days bed rest, avoid heavy lifting" className="mt-1" />
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
          {result?.verification_code && (
            <div className="flex items-center gap-2">
              <Badge variant="default" className="bg-purple-100 text-purple-700">Code: {result.verification_code}</Badge>
              <Button variant="outline" size="sm" onClick={() => window.open(result.pdf_path, '_blank')}>
                <Download className="h-3 w-3 mr-1" /> Download
              </Button>
              <Button variant="outline" size="sm" onClick={() => window.open(result.pdf_path, '_blank')}>
                <Printer className="h-3 w-3 mr-1" /> Print
              </Button>
            </div>
          )}
          <Button onClick={handleCreate} disabled={!isValid || generating} className="ml-auto">
            {generating ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating...</> : <><FileText className="h-4 w-4 mr-2" /> Generate Certificate</>}
          </Button>
        </div>

        {error && <div className="flex items-center gap-2 p-2 rounded-lg bg-red-50 text-sm text-red-700"><AlertCircle className="h-4 w-4" /> {error}</div>}
      </CardContent>
    </Card>
  )
}