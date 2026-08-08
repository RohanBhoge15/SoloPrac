'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { TimelineScrubber } from '@/components/TimelineScrubber'
import { ContextPanel } from '@/components/ContextPanel'
import { ChatUI } from '@/components/ChatUI'
import { ImageComparison } from '@/components/ImageComparison'
import { ImageGallery } from '@/components/ImageGallery'
import { Edit, Plus, Clock, FileText, ArrowUpDown, Search, Save, X, Check, Loader2, AlertCircle, RefreshCw, Download, Upload, Pill, Receipt, FileBadge, Eye } from 'lucide-react'
import { usePatientStore } from '@/store'
import { useNotificationStore } from '@/store'
import apiClient from '@/services/api'

interface Demographics {
  name: string
  age: number
  gender: string
  phone: string
  email: string
  address: string
  dob: string
}

interface DocumentItem {
  name: string
  type: string
  date: string
  size: string
  id: string
  has_pdf?: boolean
  pdf_url?: string
  version_number?: number
  metadata?: Record<string, any>
}

export function PatientDetail() {
  const { id } = useParams()
  const {
    activeHead,
    timeline, timelineLoading,
    fetchTimeline, patchFields, setActivePatient,
  } = usePatientStore()

  const [activeVersion, setActiveVersion] = useState<number | null>(null)
  const [showTimeline, setShowTimeline] = useState(true)
  const [showContextPanel, setShowContextPanel] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [editedFields, setEditedFields] = useState<Partial<Demographics>>({})
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [documentsLoading, setDocumentsLoading] = useState(true)
  const [viewingDocument, setViewingDocument] = useState<DocumentItem | null>(null)
  const [reportLayout, setReportLayout] = useState<'clinical' | 'executive' | 'family_friendly'>('clinical')
  const [reportDownloading, setReportDownloading] = useState(false)
  const [patientError, setPatientError] = useState<string | null>(null)

  // ── Batch Import state ──
  const [batchImporting, setBatchImporting] = useState(false)
  const [batchImportResult, setBatchImportResult] = useState<{
    status: string
    total_pages: number
    pages_processed: number
    versions: any[]
    errors: string[]
    took_ms: number
  } | null>(null)

  const handleBatchImport = async (file: File) => {
    if (!id) return
    setBatchImporting(true)
    setBatchImportResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('patient_id', id)
      const res = await apiClient.post('/documents/batch-import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setBatchImportResult(res.data)
      // Refresh timeline so new versions appear
      fetchTimeline(id)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Import failed'
      setBatchImportResult({ status: 'error', total_pages: 0, pages_processed: 0, versions: [], errors: [msg], took_ms: 0 })
    } finally {
      setBatchImporting(false)
    }
  }

  // Get the notification store for email/websocket notifications
  const pushNotification = useNotificationStore(state => state.pushNotification)

  // Handle weekly report PDF download
  const handleDownloadWeeklyReport = async () => {
    if (!id) return
    setReportDownloading(true)
    try {
      const res = await apiClient.get(`/patients/${id}/weekly-report/pdf`, {
        params: { layout: reportLayout },
        responseType: 'blob',
      })
      // Create blob download
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `weekly-report-${id}-${reportLayout}-${new Date().toISOString().slice(0, 10)}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      // Push notification to doctor (will trigger email if patient has email)
      pushNotification({
        id: crypto.randomUUID(),
        kind: 'weekly_report_ready',
        subject: 'Weekly Report Generated',
        body: `Weekly clinical report (${reportLayout}) generated and downloaded for patient ${displayDemographics.name || id}`,
        read: false,
        created_at: new Date().toISOString(),
        meta: { patientId: id, layout: reportLayout },
      })
    } catch (err) {
      console.error('Failed to download weekly report:', err)
      pushNotification({
        id: crypto.randomUUID(),
        kind: 'error',
        subject: 'Report Generation Failed',
        body: 'Failed to generate weekly report PDF. Please try again.',
        read: false,
        created_at: new Date().toISOString(),
        meta: { patientId: id },
      })
    } finally {
      setReportDownloading(false)
    }
  }

  // P2.16 — Fetch every independent patient resource in one round-trip.
  //
  // The four requests (head, patient row, timeline, documents) are truly
  // independent so we fire them all in parallel via Promise.all. Total wall-
  // clock ≈ slowest request instead of sum-of-four; each panel of the page
  // renders as soon as its data lands (state is set per-response).
  useEffect(() => {
    if (!id) return
    let cancelled = false
    setDocumentsLoading(true)

    Promise.all([
      apiClient.get(`/patients/${id}/head`).catch(() => null),
      apiClient.get(`/patients/${id}`).catch(() => null),
      // fetchTimeline() sets its own store state internally — treat as fire-
      // and-forget so it races alongside the others.
      Promise.resolve(fetchTimeline(id)).catch(() => null),
      apiClient.get(`/patients/${id}/documents`).catch(() => null),
    ])
      .then(([headRes, patientRes, _timelineRes, docsRes]) => {
        if (cancelled) return

        if (headRes?.data) usePatientStore.setState({ activeHead: headRes.data })
        if (patientRes?.data) setActivePatient(patientRes.data)
        if (!patientRes?.data && !headRes?.data) {
          setPatientError('Patient not found')
        }

        const allDocs: DocumentItem[] = (docsRes?.data?.documents ?? []).map((d: any) => ({
          name: d.title,
          type: d.type,
          date: d.date?.slice(0, 10) ?? '',
          size: d.has_pdf ? 'PDF' : '',
          id: d.id,
          has_pdf: d.has_pdf,
          pdf_url: d.pdf_url,
          version_number: d.version_number,
          metadata: d.metadata,
        }))
        setDocuments(allDocs)
      })
      .catch(() => {
        if (!cancelled) setPatientError('Failed to load patient')
      })
      .finally(() => {
        if (!cancelled) setDocumentsLoading(false)
      })

    return () => { cancelled = true }
  }, [id, fetchTimeline, setActivePatient])

  const state = activeHead?.state_jsonb ?? {}
  const demographicsRaw = state.demographics ?? {} as any
  const clinical = state.clinical ?? {} as any

  const demographics: Demographics = {
    name: demographicsRaw.name ?? 'Unknown',
    age: demographicsRaw.age ?? 0,
    gender: demographicsRaw.gender ?? 'Not specified',
    phone: demographicsRaw.phone ?? '',
    email: demographicsRaw.email ?? '',
    address: demographicsRaw.address ?? '',
    dob: demographicsRaw.dob ?? '',
  }

  const diagnoses: string[] = clinical.diagnoses ?? []
  const medications: any[] = clinical.medications ?? []

  const handleSelectVersion = (versionNumber: number) => {
    setActiveVersion(versionNumber)
    if (id) {
      apiClient.get(`/patients/${id}/at_version/${versionNumber}`)
        .then(res => {
          if (res.data?.state_jsonb) {
            usePatientStore.setState({ activeHead: { ...activeHead, state_jsonb: res.data.state_jsonb, version_number: versionNumber } as any })
          }
        })
        .catch((err) => {
          console.warn('[PatientDetail] Failed to load version:', err)
        })
    }
  }

  const handleCompare = (_v1: number, v2: number) => {
    setActiveVersion(v2)
  }

  const handleCiteVersion = (versionNumber: number) => {
    setActiveVersion(versionNumber)
    const el = document.querySelector(`[data-ver="${versionNumber}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const toggleEditMode = () => {
    if (editMode) {
      setEditMode(false)
      setEditedFields({})
      setSaveError(null)
    } else {
      setEditMode(true)
    }
  }

  const handleFieldEdit = (field: keyof Demographics, value: string) => {
    setEditedFields(prev => ({ ...prev, [field]: value }))
  }

  const handleSaveEdit = async () => {
    if (!id || !activeHead) return
    setSaving(true)
    setSaveError(null)
    try {
      const result = await patchFields(id, editedFields as Record<string, unknown>, activeHead.version_number)
      if (result) {
        setSaving(false)
        setEditMode(false)
        setEditedFields({})
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
      } else {
        setSaveError('Failed to save. The record may have been updated by another session. Reload and retry.')
        setSaving(false)
      }
    } catch (e: any) {
      setSaveError(e?.response?.data?.detail || 'Failed to save changes')
      setSaving(false)
    }
  }

  const displayDemographics: Demographics = { ...demographics, ...editedFields }

  if (patientError) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="max-w-md w-full">
          <CardContent className="p-6 text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Patient Not Found</h2>
            <p className="text-gray-500 dark:text-gray-400 mb-4">{patientError}</p>
            <Button onClick={() => window.location.reload()}>
              <RefreshCw className="h-4 w-4 mr-2" /> Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header with patient info */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="h-16 w-16 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                <span className="text-2xl font-bold text-primary-700 dark:text-primary-300">
                  {displayDemographics.name.split(' ').map(n => n[0]).join('')}
                </span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{displayDemographics.name}</h1>
                <p className="text-gray-500 dark:text-gray-400">{displayDemographics.age} years &bull; {displayDemographics.gender} &bull; ID: {id}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {editMode ? (
                <>
                  <Button variant="outline" onClick={toggleEditMode} disabled={saving}>
                    <X className="h-4 w-4 mr-2" />Cancel
                  </Button>
                  <Button onClick={handleSaveEdit} disabled={saving || Object.keys(editedFields).length === 0}>
                    {saving ? (
                      <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving...</>
                    ) : saved ? (
                      <><Check className="h-4 w-4 mr-2" />Saved!</>
                    ) : (
                      <><Save className="h-4 w-4 mr-2" />Save Changes</>
                    )}
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" onClick={() => setShowTimeline(!showTimeline)}>
                    <Clock className="h-4 w-4 mr-2" />Timeline
                  </Button>
                  <Button variant="outline" onClick={toggleEditMode}>
                    <Edit className="h-4 w-4 mr-2" />Edit Fields
                  </Button>
                  <Button onClick={() => setShowContextPanel(!showContextPanel)}>
                    <Plus className="h-4 w-4 mr-2" />Context
                  </Button>
                </>
              )}
            </div>
          </div>

          {saveError && (
            <div className="mt-4 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {saveError}
            </div>
          )}

          {/* Timeline Scrubber */}
          {showTimeline && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <TimelineScrubber
                versions={timeline}
                activeVersion={activeVersion}
                onSelectVersion={handleSelectVersion}
                onCompare={handleCompare}
              />
              {timelineLoading && (
                <div className="text-center py-4 text-gray-500 dark:text-gray-400">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2" />
                  Loading timeline...
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Main Content + Right Rail */}
      <div className="flex gap-6">
        <div className="flex-1 min-w-0">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="images">Images</TabsTrigger>
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="chat">AI Chat</TabsTrigger>
            </TabsList>

            {/* Overview Tab */}
            <TabsContent value="overview" className="space-y-6 mt-4">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Demographics */}
                <Card className="lg:col-span-1">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Clock className="h-5 w-5 text-primary-600" />
                      Demographics
                      {editMode && (
                        <Badge variant="secondary" className="ml-auto text-[10px]">Editing</Badge>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {Object.entries(displayDemographics).map(([k, v]) => (
                      <div key={k} className="flex justify-between items-center">
                        <span className="text-sm text-gray-500 dark:text-gray-400 capitalize">{k.replace('_', ' ')}</span>
                        {editMode ? (
                          <Input
                            defaultValue={String(v)}
                            onChange={(e) => handleFieldEdit(k as keyof Demographics, e.target.value)}
                            className="w-40 h-7 text-xs text-right"
                          />
                        ) : (
                          <span className="font-medium text-gray-900 dark:text-white text-sm">{String(v) || '—'}</span>
                        )}
                      </div>
                    ))}
                  </CardContent>
                </Card>

                {/* Clinical */}
                <Card className="lg:col-span-2">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-primary-600" />
                      Clinical Summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <h4 className="font-medium text-gray-900 dark:text-white mb-2">Diagnoses</h4>
                      <div className="flex flex-wrap gap-2">
                        {diagnoses.length > 0 ? (
                          diagnoses.map((d, i) => (
                            <Badge key={i} variant="default" className="bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                              {d}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-sm text-gray-500 dark:text-gray-400">No diagnoses recorded</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <h4 className="font-medium text-gray-900 dark:text-white mb-2">Current Medications</h4>
                      <div className="space-y-2">
                        {medications.length > 0 ? (
                          medications.map((m, i) => (
                            <div key={i} className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                              <div className="flex-1">
                                <p className="font-medium text-gray-900 dark:text-white">{m.drug} {m.strength}</p>
                                <p className="text-sm text-gray-500 dark:text-gray-400">{m.dose} &bull; {m.frequency}</p>
                                {m.duration && <p className="text-xs text-gray-400">{m.duration}</p>}
                              </div>
                            </div>
                          ))
                        ) : (
                          <span className="text-sm text-gray-500 dark:text-gray-400">No medications recorded</span>
                        )}
                       </div>
                    </div>
                    </CardContent>
                  </Card>
                  </div>
            </TabsContent>

            {/* Timeline Tab */}
            <TabsContent value="timeline" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Version History</CardTitle>
                </CardHeader>
                <CardContent>
                  <TimelineScrubber
                    versions={timeline}
                    activeVersion={activeVersion}
                    onSelectVersion={handleSelectVersion}
                    onCompare={handleCompare}
                  />
                  <div className="mt-6 space-y-4">
                    {timeline.map((v) => (
                      <div
                        key={v.version_number}
                        className={cn(
                          'flex items-start gap-4 p-4 rounded-lg border transition-colors cursor-pointer',
                          activeVersion === v.version_number
                            ? 'border-primary-300 dark:border-primary-700 bg-primary-50 dark:bg-primary-900/10'
                            : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50'
                        )}
                        onClick={() => handleSelectVersion(v.version_number)}
                      >
                        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                          <ArrowUpDown className="h-5 w-5 text-primary-700 dark:text-primary-300" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3">
                            <span className="font-medium text-gray-900 dark:text-white">Version {v.version_number}</span>
                            <Badge variant="secondary" className="text-xs">
                              {v.edit_type}
                            </Badge>
                            <Badge variant="outline" className="text-xs">
                              {v.author}
                            </Badge>
                          </div>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{v.summary}</p>
                          <p className="text-xs text-gray-400 mt-1">{new Date(v.timestamp).toLocaleString()}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="icon" title="View this version"><Search className="h-4 w-4" /></Button>
                          <Button variant="ghost" size="icon" title="Compare"><ArrowUpDown className="h-4 w-4" /></Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Images Tab */}
            <TabsContent value="images" className="mt-4">
              <ImageGallery patientId={id || ''} />
              <div className="mt-6">
                <ImageComparison patientId={id || ''} />
              </div>
            </TabsContent>

            {/* Documents Tab */}
            <TabsContent value="documents" className="mt-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    All Documents
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {documentsLoading ? (
                    <div className="text-center py-8">
                      <Loader2 className="h-6 w-6 animate-spin mx-auto" />
                    </div>
                  ) : documents.length === 0 ? (
                    <p className="text-center text-gray-500 py-8">No documents yet</p>
                  ) : (
                    <div className="space-y-2">
                      {documents.map((doc, i) => (
                        <div
                          key={`${doc.type}-${doc.id}-${i}`}
                          className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                          onClick={() => doc.has_pdf && doc.pdf_url ? setViewingDocument(doc) : undefined}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className={cn(
                              'flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center',
                              doc.type === 'prescription' && 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
                              doc.type === 'invoice' && 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
                              doc.type === 'certificate' && 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
                              doc.type === 'uploaded_document' && 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
                            )}>
                              {doc.type === 'prescription' && <Pill className="h-4 w-4" />}
                              {doc.type === 'invoice' && <Receipt className="h-4 w-4" />}
                              {doc.type === 'certificate' && <FileBadge className="h-4 w-4" />}
                              {doc.type === 'uploaded_document' && <FileText className="h-4 w-4" />}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="font-medium text-gray-900 dark:text-white text-sm truncate">{doc.name}</p>
                                {doc.version_number && (
                                  <Badge variant="outline" className="text-[10px] flex-shrink-0">v{doc.version_number}</Badge>
                                )}
                              </div>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                {doc.date}
                                {doc.metadata?.diagnosis && ` — ${doc.metadata.diagnosis}`}
                                {doc.metadata?.total != null && ` — ₹${doc.metadata.total}`}
                                {doc.metadata?.status && ` (${doc.metadata.status})`}
                                {doc.metadata?.edit_type && ` — ${doc.metadata.edit_type}`}
                                {doc.metadata?.doc_type && ` — ${doc.metadata.doc_type}`}
                              </p>
                            </div>
                          </div>
                          {doc.has_pdf && (
                            <Eye className="h-4 w-4 text-gray-400 flex-shrink-0" />
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Document Viewer Modal */}
              {viewingDocument && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setViewingDocument(null)}>
                  <div className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl max-w-4xl w-full mx-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                      <div className="flex items-center gap-2 min-w-0">
                        <Badge variant="outline" className="text-xs">{viewingDocument.type}</Badge>
                        {viewingDocument.version_number && <Badge variant="secondary" className="text-xs">v{viewingDocument.version_number}</Badge>}
                        <span className="text-sm font-medium text-gray-900 dark:text-white truncate">{viewingDocument.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {viewingDocument.pdf_url && (
                          <Button variant="ghost" size="sm" onClick={() => window.open(viewingDocument.pdf_url, '_blank')}>
                            <Download className="h-3.5 w-3.5 mr-1" /> Download
                          </Button>
                        )}
                        <button onClick={() => setViewingDocument(null)} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    <div className="flex-1 overflow-auto p-4">
                      {viewingDocument.pdf_url ? (
                        <iframe src={viewingDocument.pdf_url} className="w-full h-[70vh] border-0 rounded" title={viewingDocument.name} />
                      ) : (
                        <p className="text-center text-gray-500 py-8">Preview not available</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

                  {/* ── Batch Import: multi-page prescription PDF → version chain ── */}
                  <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">Import Past Prescriptions</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          Upload a PDF with multiple prescription pages (oldest → newest). Each page becomes a version.
                        </p>
                      </div>
                    </div>

                    {/* Hidden file input */}
                    <input
                      type="file"
                      accept=".pdf,application/pdf"
                      className="hidden"
                      id="batch-import-input"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) handleBatchImport(file)
                        e.target.value = ''
                      }}
                    />

                    <div className="flex items-center gap-3">
                      <Button
                        variant="default"
                        onClick={() => document.getElementById('batch-import-input')?.click()}
                        disabled={batchImporting}
                      >
                        {batchImporting ? (
                          <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Importing...</>
                        ) : (
                          <><Upload className="h-4 w-4 mr-2" />Upload Prescription PDF</>
                        )}
                      </Button>
                      <span className="text-xs text-gray-400">Max 50 pages · PDF only</span>
                    </div>

                    {/* Batch import result */}
                    {batchImportResult && (
                      <div className="mt-3 p-3 rounded-lg border text-sm space-y-1" style={{
                        borderColor: batchImportResult.status === 'error' ? '#fecaca' : batchImportResult.errors?.length ? '#fed7aa' : '#bbf7d0',
                        backgroundColor: batchImportResult.status === 'error' ? '#fef2f2' : batchImportResult.errors?.length ? '#fff7ed' : '#f0fdf4',
                      }}>
                        {batchImportResult.status === 'error' ? (
                          <p className="text-red-700 flex items-center gap-1">
                            <AlertCircle className="h-4 w-4" /> {batchImportResult.errors?.[0] || 'Import failed'}
                          </p>
                        ) : (
                          <>
                            <p className={batchImportResult.errors?.length ? 'text-amber-700' : 'text-green-700'}>
                              <Check className="h-4 w-4 inline mr-1" />
                              Processed {batchImportResult.pages_processed}/{batchImportResult.total_pages} pages
                              {batchImportResult.took_ms > 0 && ` in ${(batchImportResult.took_ms / 1000).toFixed(1)}s`}
                            </p>
                            {batchImportResult.versions?.length > 0 && (
                              <div className="mt-2 space-y-1">
                                {batchImportResult.versions.map((v: any) => (
                                  <div key={v.id} className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                                    <span className="inline-block w-2 h-2 rounded-full bg-primary-500" />
                                    <span>v{v.version_number} &mdash; Page {v.page_number}</span>
                                    <span className="text-xs text-gray-400">({v.doc_type}, conf={v.confidence.toFixed(2)})</span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {batchImportResult.errors?.length > 0 && (
                              <div className="mt-2 text-xs text-amber-600">
                                {batchImportResult.errors.slice(0, 5).map((e: string, i: number) => (
                                  <p key={i}>⚠ {e}</p>
                                ))}
                                {batchImportResult.errors.length > 5 && (
                                  <p>...and {batchImportResult.errors.length - 5} more</p>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Weekly Report section */}
                  <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">Weekly Clinical Report</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">Download the recent weekly report as PDF</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <select
                          value={reportLayout}
                          onChange={e => setReportLayout(e.target.value as 'clinical' | 'executive' | 'family_friendly')}
                          className="px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-xs"
                        >
                          <option value="clinical">Clinical</option>
                          <option value="executive">Executive</option>
                          <option value="family_friendly">Family</option>
                        </select>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleDownloadWeeklyReport}
                          disabled={reportDownloading}
                        >
                          {reportDownloading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Download className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
            </TabsContent>

            {/* Chat / AI Assistant integrated tab */}
            <TabsContent value="chat" className="mt-4">
              <Card className="h-[500px]">
                <CardContent className="p-0 h-full">
                  <ChatUI
                    patientId={id}
                    onCiteVersion={handleCiteVersion}
                    initialMessage="Ask me about this patient's records. I can search their version history using temporal-aware RAG."
                  />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        {/* Right Rail — Context Panel */}
        {showContextPanel && (
          <div className="w-72 shrink-0 hidden xl:block">
            <div className="sticky top-24">
              <ContextPanel
                patient={{
                  name: displayDemographics.name,
                  age: displayDemographics.age,
                  gender: displayDemographics.gender,
                  id: id || '',
                }}
                vitals={{
                  bp_systolic: clinical.vitals?.[0]?.bp_systolic ?? null,
                  bp_diastolic: clinical.vitals?.[0]?.bp_diastolic ?? null,
                  heart_rate: clinical.vitals?.[0]?.heart_rate ?? null,
                  weight: clinical.vitals?.[0]?.weight ?? null,
                  date: clinical.vitals?.[0]?.date ?? null,
                }}
                medications={medications}
                diagnoses={diagnoses}
                nextAppointment={null}
                alerts={[]}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}