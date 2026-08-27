import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { toast } from '@/components/ui/Toast'
import { AlertTriangle, Activity, ChevronDown, ChevronUp, Loader2, FileText, Download } from 'lucide-react'

type Layout = 'executive' | 'clinical' | 'family_friendly'

interface ReportSection {
  date: string
  summary: string
  tier: string
  score: number
  components?: Record<string, number>
  tags?: string[]
  edit_type?: string
  state_preview?: { vitals?: Record<string, number>; diagnoses?: string[] }
}

interface WeeklyReport {
  layout: Layout
  patient_name: string
  title: string
  description: string
  total_events: number
  sections: ReportSection[]
  critical_count?: number
  notable_count?: number
  routine_count?: number
  critical?: ReportSection[]
  notable?: ReportSection[]
  routine?: ReportSection[]
  generated_at: string
}

function cn(...classes: any[]) { return classes.filter(Boolean).join(' ') }

const TIER_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  notable: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  routine: 'bg-blue-100 text-blue-700 border-blue-200',
  informational: 'bg-gray-100 text-gray-600 border-gray-200',
}

export function WeeklyReport() {
  const [patients, setPatients] = useState<any[]>([])
  const [selectedPatient, setSelectedPatient] = useState<string>('')
  const [layout, setLayout] = useState<Layout>('clinical')
  const [days, setDays] = useState(7)
  const [report, setReport] = useState<WeeklyReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedSection, setExpandedSection] = useState<number | null>(null)
  const [aiSummary, setAiSummary] = useState<string | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(false)

  useEffect(() => {
    loadPatients()
  }, [])

  const loadPatients = async () => {
    try {
      const res = await apiClient.get('/patients')
      setPatients(res.data || [])
    } catch (err) {
      // R-8: surface load failure instead of leaving picker mysteriously empty.
      console.error('[WeeklyReport] failed to load patients:', err)
      toast.error('Failed to load patient list')
    }
  }

  const handleGenerate = async () => {
    if (!selectedPatient) return
    setLoading(true)
    setError(null)
    setReport(null)
    setAiSummary(null)
    try {
      const res = await apiClient.post(`/patients/${selectedPatient}/weekly-report`, null, {
        params: { layout, days },
      })
      setReport(res.data)
    } catch {
      setError('Failed to generate report')
    } finally {
      setLoading(false)
    }
  }

  const handleGenerateAISummary = async () => {
    if (!selectedPatient) return
    setLoadingSummary(true)
    try {
      const res = await apiClient.post(`/weekly-report/${selectedPatient}/ai-summary`, null, {
        params: { layout, days },
      })
      setAiSummary(res.data?.ai_summary?.summary || 'AI summary not available')
    } catch (err) {
      // R-8: surface AI summary failure.
      console.error('[WeeklyReport] AI summary failed:', err)
      toast.error('Failed to generate AI summary')
    }
    setLoadingSummary(false)
  }

  // D-12: The download button previously produced a raw JSON dump of the
  // report state. Users expect a PDF (which the backend already renders via
  // /patients/{id}/weekly-report/pdf). Mirror the pattern used in
  // PatientDetail.handleDownloadWeeklyReport: request the endpoint with
  // responseType: 'blob' and trigger a browser download of the PDF blob.
  const handleDownload = async () => {
    if (!report || !selectedPatient) return
    try {
      const res = await apiClient.get(`/patients/${selectedPatient}/weekly-report/pdf`, {
        params: { layout, days },
        responseType: 'blob',
      })
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      const yyyymmdd = new Date().toISOString().slice(0, 10).replace(/-/g, '')
      const safeName = (report.patient_name || selectedPatient).replace(/[^\w.-]+/g, '_')
      link.download = `weekly-report-${safeName}-${yyyymmdd}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch {
      setError('Failed to download PDF')
    }
  }

  const renderSection = (s: ReportSection, idx: number) => (
    <div key={idx} className={cn('p-3 rounded-lg border', TIER_COLORS[s.tier] || 'border-gray-200')}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-500">{s.date}</span>
        <Badge className={cn('text-[10px]', TIER_COLORS[s.tier])}>{s.tier}</Badge>
      </div>
      <p className="text-sm text-strong-fg">{s.summary}</p>
      {s.score && (
        <div className="mt-1 flex items-center gap-2">
          <span className="text-[10px] text-gray-400">Significance: {s.score.toFixed(3)}</span>
        </div>
      )}
      {layout === 'clinical' && s.components && (
        <button
          className="mt-1 text-[10px] text-primary-600 flex items-center gap-1"
          onClick={() => setExpandedSection(expandedSection === idx ? null : idx)}
        >
          {expandedSection === idx ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          Score breakdown
        </button>
      )}
      {expandedSection === idx && s.components && (
        <div className="mt-1 p-2 rounded bg-white/50 dark:bg-gray-800/50 text-[10px] space-y-0.5">
          {Object.entries(s.components).map(([key, val]) => (
            <div key={key} className="flex justify-between">
              <span className="text-gray-500">{key.replace(/_/g, ' ')}</span>
              <span>{(val as number).toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-strong-fg">Weekly Reports</h1>
        <Badge variant="outline" className="text-[10px]">Feature F</Badge>
      </div>

      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Patient</label>
              <select
                value={selectedPatient}
                onChange={e => { setSelectedPatient(e.target.value); setReport(null) }}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
              >
                <option value="">Select patient...</option>
                {patients.map((p: any) => (
                  <option key={p.id} value={p.id}>{p.name || p.id.slice(0, 8)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Layout</label>
              <select
                value={layout}
                onChange={e => setLayout(e.target.value as Layout)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
              >
                <option value="executive">Executive — compact summary</option>
                <option value="clinical">Clinical — full detail</option>
                <option value="family_friendly">Family-friendly — plain language</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Lookback</label>
              {/* Backend accepts days=0 as sentinel for "no cutoff, full patient history".
                  We surface a few common presets + "Full history" instead of raw number entry
                  — users kept asking for a full-history option and 90 days was arbitrary. */}
              <select
                value={days}
                onChange={e => setDays(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
              >
                <option value={7}>Last 7 days</option>
                <option value={14}>Last 14 days</option>
                <option value={30}>Last 30 days</option>
                <option value={90}>Last 90 days</option>
                <option value={0}>Full history</option>
              </select>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={handleGenerate} disabled={loading || !selectedPatient}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <FileText className="h-4 w-4 mr-1" />}
              Generate Report
            </Button>
            {report && (
              <>
                <Button variant="outline" onClick={handleDownload}>
                  <Download className="h-4 w-4 mr-1" /> Download
                </Button>
                <Button variant="outline" onClick={handleGenerateAISummary} disabled={loadingSummary}>
                  {loadingSummary ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                  AI Summary
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {error && <div className="p-3 rounded-lg bg-red-50 text-sm text-red-700 flex items-center gap-2"><AlertTriangle className="h-4 w-4" />{error}</div>}

      {aiSummary && (
        <Card className="bg-primary-50 dark:bg-primary-900/10 border-primary-200">
          <CardContent className="p-4">
            <p className="text-sm text-gray-700 dark:text-gray-300">{aiSummary}</p>
          </CardContent>
        </Card>
      )}

      {report && report.total_events === 0 && (
        <Card>
          <CardContent className="p-6 text-center">
            <Activity className="h-8 w-8 mx-auto text-gray-300 mb-2" />
            <p className="text-gray-400">No clinical events this week for this patient.</p>
          </CardContent>
        </Card>
      )}

      {/* Layout-specific rendering */}
      {report && report.layout === 'clinical' && report.critical && (
        <>
          {report.critical.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-red-600" />
                  Critical ({report.critical_count})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">{report.critical.map((s, i) => renderSection(s, i))}</CardContent>
            </Card>
          )}

          {report.notable && report.notable.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <Activity className="h-4 w-4 text-yellow-600" />
                  Notable ({report.notable_count})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">{report.notable.map((s, i) => renderSection(s, i + (report.critical?.length || 0)))}</CardContent>
            </Card>
          )}

          {report.routine && report.routine.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm text-gray-500">
                  Routine ({report.routine_count})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {report.routine.map((s, i) => (
                  <div key={i} className="text-sm text-gray-500 py-1 border-b border-gray-100 last:border-0">
                    <span className="text-xs text-gray-400 mr-2">{s.date}</span>{s.summary}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {(report?.layout === 'executive' || report?.layout === 'family_friendly') && report?.sections && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{report.title}</CardTitle>
            <p className="text-xs text-gray-500">{report.description}</p>
          </CardHeader>
          <CardContent className="space-y-2">
            {report.sections.map((s, i) => renderSection(s, i))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
