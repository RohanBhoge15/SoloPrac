import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Edit, Plus, Save, X, Check, Loader2, AlertCircle, RefreshCw,
  Pill, FileText, User, Activity, Sparkles, Upload,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'

import { VersionChain } from '@/components/patient/VersionChain'
import { CopilotPane } from '@/components/patient/CopilotPane'
import { NewVersionModal } from '@/components/patient/NewVersionModal'
import { NewPrescriptionModal } from '@/components/patient/NewPrescriptionModal'
import { ImageGallery } from '@/components/ImageGallery'
import { CertificateUI } from '@/components/CertificateUI'
import { InvoiceUI } from '@/components/InvoiceUI'
import { ImageComparison } from '@/components/ImageComparison'

import { usePatientStore } from '@/store'
import apiClient from '@/services/api'
import { cn } from '@/utils/helpers'

// PatientDetail — split view (patient record left, Copilot right) with the
// version chain sitting between the identity strip and the record body.
//
// The old page mixed twelve concerns into 800 lines of JSX. This rewrite
// pulls each concern into its own component and keeps the page itself as
// a thin composition + data-loading shell.

interface Demographics {
  name: string
  age: number | string
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
  id: string
  has_pdf?: boolean
  pdf_url?: string
  version_number?: number
}

export function PatientDetail() {
  const { id } = useParams()
  const {
    activeHead, timeline, timelineLoading,
    fetchTimeline, patchFields, setActivePatient,
  } = usePatientStore()

  const [activeVersion, setActiveVersion] = useState<number | null>(null)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [documentsLoading, setDocumentsLoading] = useState(true)
  const [patientError, setPatientError] = useState<string | null>(null)

  // Inline demographics edit — kept on the identity card so quick fixes
  // (typo in phone, wrong age) don't need the full New Version modal.
  const [editMode, setEditMode] = useState(false)
  const [editedFields, setEditedFields] = useState<Partial<Demographics>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Modal toggles.
  const [newVersionOpen, setNewVersionOpen] = useState(false)
  const [newRxOpen, setNewRxOpen] = useState(false)

  // Kick off every independent patient resource in parallel — matches the
  // pattern already established in the old page (P2.16).
  useEffect(() => {
    if (!id) return
    let cancelled = false
    setDocumentsLoading(true)

    Promise.all([
      apiClient.get(`/patients/${id}/head`).catch(() => null),
      apiClient.get(`/patients/${id}`).catch(() => null),
      Promise.resolve(fetchTimeline(id)).catch(() => null),
      apiClient.get(`/patients/${id}/documents`).catch(() => null),
    ])
      .then(([headRes, patientRes, _t, docsRes]) => {
        if (cancelled) return
        if (headRes?.data) usePatientStore.setState({ activeHead: headRes.data })
        if (patientRes?.data) setActivePatient(patientRes.data)
        if (!headRes?.data && !patientRes?.data) setPatientError('Patient not found')

        const docs: DocumentItem[] = (docsRes?.data?.documents ?? []).map((d: any) => ({
          name: d.title,
          type: d.type,
          date: d.date?.slice(0, 10) ?? '',
          id: d.id,
          has_pdf: d.has_pdf,
          pdf_url: d.pdf_url,
          version_number: d.version_number,
        }))
        setDocuments(docs)
      })
      .catch(() => { if (!cancelled) setPatientError('Failed to load patient') })
      .finally(() => { if (!cancelled) setDocumentsLoading(false) })

    return () => { cancelled = true }
  }, [id, fetchTimeline, setActivePatient])

  const state = activeHead?.state_jsonb ?? {}
  const demographicsRaw = (state.demographics ?? {}) as Record<string, any>
  const clinical = (state.clinical ?? {}) as Record<string, any>

  const demographics: Demographics = {
    name: demographicsRaw.name ?? 'Unknown',
    age: demographicsRaw.age ?? '',
    gender: demographicsRaw.gender ?? '',
    phone: demographicsRaw.phone ?? '',
    email: demographicsRaw.email ?? '',
    address: demographicsRaw.address ?? '',
    dob: demographicsRaw.dob ?? '',
  }
  const displayDemo: Demographics = { ...demographics, ...editedFields }
  const initials = String(displayDemo.name || '?')
    .split(' ')
    .filter(Boolean)
    .map(s => s[0]?.toUpperCase())
    .slice(0, 2)
    .join('') || '?'

  const diagnoses: string[] = clinical.diagnoses ?? []
  const medications: any[] = clinical.medications ?? []
  const vitals = clinical.vitals?.[0] ?? {}

  const handleSelectVersion = (v: number) => {
    setActiveVersion(v)
    if (!id) return
    apiClient.get(`/patients/${id}/at_version/${v}`)
      .then(res => {
        if (res.data?.state_jsonb) {
          usePatientStore.setState({
            activeHead: { ...activeHead, state_jsonb: res.data.state_jsonb, version_number: v } as any,
          })
        }
      })
      .catch(err => console.warn('[PatientDetail] Failed to load version:', err))
  }

  const toggleEdit = () => {
    if (editMode) { setEditMode(false); setEditedFields({}); setSaveError(null) }
    else { setEditMode(true) }
  }
  const handleFieldEdit = (k: keyof Demographics, value: string) => {
    setEditedFields(p => ({ ...p, [k]: value }))
  }
  const handleSaveEdit = async () => {
    if (!id || !activeHead) return
    setSaving(true); setSaveError(null)
    try {
      const result = await patchFields(id, editedFields as Record<string, unknown>, activeHead.version_number)
      if (result) {
        setEditMode(false); setEditedFields({})
        setSaved(true); setTimeout(() => setSaved(false), 2000)
      } else {
        setSaveError('Version conflict — reload and retry.')
      }
    } catch (e: any) {
      setSaveError(e?.response?.data?.detail || 'Failed to save changes')
    } finally {
      setSaving(false)
    }
  }

  if (patientError) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="max-w-md w-full">
          <CardContent className="p-6 text-center">
            <AlertCircle className="h-12 w-12 text-severity-critical mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-strong-fg mb-2">Patient Not Found</h2>
            <p className="text-muted-fg mb-4">{patientError}</p>
            <Button onClick={() => window.location.reload()}>
              <RefreshCw className="h-4 w-4 mr-2" /> Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const currentVersion = activeHead?.version_number ?? 0

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-6 animate-in">
      {/* ─────────── Left column: patient record ─────────── */}
      <div className="min-w-0 space-y-4">
        {/* Identity strip */}
        <Card>
          <CardContent className="p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex items-center gap-4 min-w-0">
                <div className="h-14 w-14 rounded-full bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center flex-shrink-0">
                  <span className="text-lg font-semibold text-primary-700 dark:text-primary-200 tracking-tight">
                    {initials}
                  </span>
                </div>
                <div className="min-w-0">
                  <h1 className="text-xl font-semibold text-strong-fg tracking-tight truncate">
                    {displayDemo.name}
                  </h1>
                  <div className="flex items-center gap-2 text-sm text-muted-fg mt-0.5 flex-wrap">
                    {displayDemo.age && <span className="tnum">{displayDemo.age}y</span>}
                    {displayDemo.gender && <span>· {displayDemo.gender}</span>}
                    <span className="text-[11px] font-mono opacity-70">· {id?.slice(0, 8)}</span>
                    {currentVersion > 0 && (
                      <Badge variant="secondary" className="text-[10px]">v{currentVersion}</Badge>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                {editMode ? (
                  <>
                    <Button variant="outline" onClick={toggleEdit} disabled={saving}>
                      <X className="h-4 w-4 mr-2" />Cancel
                    </Button>
                    <Button onClick={handleSaveEdit} disabled={saving || Object.keys(editedFields).length === 0}>
                      {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving</>
                        : saved ? <><Check className="h-4 w-4 mr-2" />Saved!</>
                        : <><Save className="h-4 w-4 mr-2" />Save</>}
                    </Button>
                  </>
                ) : (
                  <>
                    <Button variant="outline" size="sm" onClick={toggleEdit}>
                      <Edit className="h-4 w-4 mr-2" />Quick edit
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setNewRxOpen(true)}>
                      <Pill className="h-4 w-4 mr-2" />New Rx
                    </Button>
                    <Button size="sm" onClick={() => setNewVersionOpen(true)}>
                      <Plus className="h-4 w-4 mr-2" />New Version
                    </Button>
                  </>
                )}
              </div>
            </div>

            {saveError && (
              <div className="mt-3 p-3 rounded-md bg-red-50 border border-red-200 text-sm text-severity-critical flex items-center gap-2">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                {saveError}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Version chain */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary-600" />
                Version History
              </CardTitle>
              <p className="text-xs text-muted-fg mt-0.5">
                Every edit is a new version — hover to preview, click to jump.
              </p>
            </div>
            {timelineLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-fg" />}
          </CardHeader>
          <CardContent className="pt-0">
            <VersionChain
              versions={timeline as any}
              activeVersion={activeVersion ?? currentVersion}
              onSelect={handleSelectVersion}
            />
          </CardContent>
        </Card>

        {/* Record tabs */}
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="w-full flex overflow-x-auto gap-1">
            <TabsTrigger value="overview" className="shrink-0">Overview</TabsTrigger>
            <TabsTrigger value="images" className="shrink-0">Images</TabsTrigger>
            <TabsTrigger value="documents" className="shrink-0">Documents</TabsTrigger>
            <TabsTrigger value="rx" className="shrink-0">Prescriptions</TabsTrigger>
            <TabsTrigger value="certificate" className="shrink-0">Certificate</TabsTrigger>
            <TabsTrigger value="invoice" className="shrink-0">Invoice</TabsTrigger>
          </TabsList>

          {/* ─── Overview ─── */}
          <TabsContent value="overview" className="space-y-4 mt-3">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Demographics */}
              <Card className="lg:col-span-1">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <User className="h-4 w-4 text-primary-600" />
                    Demographics
                    {editMode && <Badge variant="secondary" className="ml-auto text-[10px]">Editing</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {(Object.keys(displayDemo) as (keyof Demographics)[]).map(k => (
                    <div key={k} className="flex justify-between items-center gap-2 py-1">
                      <span className="text-xs text-muted-fg capitalize shrink-0">{k}</span>
                      {editMode ? (
                        <Input
                          value={String(displayDemo[k] || '')}
                          onChange={e => handleFieldEdit(k, e.target.value)}
                          className="w-40 h-7 text-xs text-right"
                          aria-label={`Edit ${k}`}
                        />
                      ) : (
                        <span className="text-sm text-strong-fg font-medium text-right truncate max-w-[10rem]">
                          {String(displayDemo[k]) || '—'}
                        </span>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Vitals */}
              <Card className="lg:col-span-1">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-primary-600" />
                    Vitals
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-3">
                    <VitalCell
                      label="BP"
                      value={vitals.bp_systolic && vitals.bp_diastolic
                        ? `${vitals.bp_systolic}/${vitals.bp_diastolic}`
                        : '—'}
                    />
                    <VitalCell label="HR" value={vitals.heart_rate ? `${vitals.heart_rate} bpm` : '—'} />
                    <VitalCell label="Weight" value={vitals.weight ? `${vitals.weight} kg` : '—'} />
                    <VitalCell label="Temp" value={vitals.temperature ? `${vitals.temperature}°` : '—'} />
                  </div>
                  {vitals.date && (
                    <p className="text-[11px] text-muted-fg mt-3">
                      Recorded {new Date(vitals.date).toLocaleDateString()}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Diagnoses + Medications */}
              <Card className="lg:col-span-1">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-primary-600" />
                    Clinical
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-muted-fg font-medium mb-1">Diagnoses</p>
                    <div className="flex flex-wrap gap-1">
                      {diagnoses.length > 0
                        ? diagnoses.map((d, i) => <Badge key={i} variant="primary">{d}</Badge>)
                        : <span className="text-xs text-muted-fg italic">None recorded</span>}
                    </div>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-muted-fg font-medium mb-1">Medications</p>
                    <div className="space-y-1">
                      {medications.length > 0
                        ? medications.slice(0, 3).map((m, i) => (
                            <div key={i} className="text-xs text-strong-fg">
                              <span className="font-medium">{m.drug}</span>
                              {m.strength ? ` ${m.strength}` : ''}
                              {m.frequency ? <span className="text-muted-fg"> · {m.frequency}</span> : null}
                            </div>
                          ))
                        : <span className="text-xs text-muted-fg italic">None recorded</span>}
                      {medications.length > 3 && (
                        <span className="text-[11px] text-muted-fg">+{medications.length - 3} more</span>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* ─── Images ─── */}
          <TabsContent value="images" className="mt-3">
            <ImageGallery patientId={id || ''} />
            <div className="mt-6">
              <ImageComparison patientId={id || ''} />
            </div>
          </TabsContent>

          {/* ─── Documents ─── */}
          <TabsContent value="documents" className="mt-3">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary-600" /> Documents
                </CardTitle>
                <label htmlFor="pd-upload" className="cursor-pointer">
                  <span className="inline-flex items-center gap-2 text-sm font-medium text-primary-700 hover:text-primary-800">
                    <Upload className="h-4 w-4" /> Upload
                  </span>
                  <input
                    id="pd-upload"
                    type="file"
                    className="hidden"
                    accept="image/*,application/pdf"
                    onChange={async e => {
                      const f = e.target.files?.[0]
                      if (!f || !id) return
                      const fd = new FormData()
                      fd.append('file', f)
                      fd.append('patient_id', id)
                      try {
                        await apiClient.post('/documents/parse', fd, {
                          headers: { 'Content-Type': 'multipart/form-data' },
                        })
                        // Refresh document list.
                        const docsRes = await apiClient.get(`/patients/${id}/documents`)
                        setDocuments((docsRes.data?.documents ?? []).map((d: any) => ({
                          name: d.title, type: d.type, date: d.date?.slice(0, 10) ?? '',
                          id: d.id, has_pdf: d.has_pdf, pdf_url: d.pdf_url,
                          version_number: d.version_number,
                        })))
                      } catch (err) {
                        console.warn('upload failed', err)
                      } finally {
                        e.target.value = ''
                      }
                    }}
                  />
                </label>
              </CardHeader>
              <CardContent>
                {documentsLoading ? (
                  <div className="text-center py-6"><Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-fg" /></div>
                ) : documents.length === 0 ? (
                  <p className="text-center text-sm text-muted-fg py-6 italic">No documents yet</p>
                ) : (
                  <div className="space-y-2">
                    {documents.map((d, i) => (
                      <div
                        key={`${d.type}-${d.id}-${i}`}
                        className="flex items-center justify-between p-3 rounded-md border border-border bg-surface hover:bg-surface-2 transition-colors"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-strong-fg truncate">{d.name}</p>
                          <p className="text-xs text-muted-fg">
                            {d.date} · <span className="capitalize">{d.type.replace('_', ' ')}</span>
                            {d.version_number ? ` · v${d.version_number}` : ''}
                          </p>
                        </div>
                        {d.has_pdf && d.pdf_url && (
                          <Button variant="ghost" size="sm" onClick={() => window.open(d.pdf_url, '_blank')}>
                            View
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ─── Prescriptions ─── */}
          <TabsContent value="rx" className="mt-3">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Pill className="h-4 w-4 text-primary-600" /> Prescriptions
                </CardTitle>
                <Button size="sm" onClick={() => setNewRxOpen(true)}>
                  <Plus className="h-4 w-4 mr-1" /> New Rx
                </Button>
              </CardHeader>
              <CardContent>
                {documents.filter(d => d.type === 'prescription').length === 0 ? (
                  <p className="text-center text-sm text-muted-fg py-6 italic">
                    No prescriptions yet. Click "New Rx" to create one.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {documents.filter(d => d.type === 'prescription').map((d, i) => (
                      <div
                        key={i}
                        className={cn(
                          'flex items-center justify-between p-3 rounded-md border border-border bg-surface',
                          'hover:bg-surface-2 transition-colors'
                        )}
                      >
                        <div>
                          <p className="text-sm font-medium text-strong-fg">{d.name}</p>
                          <p className="text-xs text-muted-fg">{d.date}</p>
                        </div>
                        {d.pdf_url && (
                          <Button variant="ghost" size="sm" onClick={() => window.open(d.pdf_url, '_blank')}>
                            View PDF
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ─── Certificate ─── */}
          <TabsContent value="certificate" className="mt-3">
            <CertificateUI patientId={id || ''} patientName={String(displayDemo.name || 'Patient')} />
          </TabsContent>

          {/* ─── Invoice ─── */}
          <TabsContent value="invoice" className="mt-3">
            <InvoiceUI patientId={id || ''} />
          </TabsContent>
        </Tabs>
      </div>

      {/* ─────────── Right column: Copilot pane ─────────── */}
      <div className="hidden xl:block">
        <div className="sticky top-20 h-[calc(100vh-6rem)]">
          <CopilotPane
            patientId={id || ''}
            patientName={typeof displayDemo.name === 'string' ? displayDemo.name : undefined}
            onCiteVersion={handleSelectVersion}
          />
        </div>
      </div>

      {/* Mobile Copilot — accessible as a bottom sheet button on small screens. */}
      <MobileCopilotSheet patientId={id || ''} patientName={String(displayDemo.name || '')} onCiteVersion={handleSelectVersion} />

      {/* Modals */}
      {id && activeHead && (
        <NewVersionModal
          open={newVersionOpen}
          onClose={() => setNewVersionOpen(false)}
          patientId={id}
          headState={state}
          headVersion={currentVersion}
          onCreated={v => {
            fetchTimeline(id)
            handleSelectVersion(v)
          }}
        />
      )}
      {id && (
        <NewPrescriptionModal
          open={newRxOpen}
          onClose={() => setNewRxOpen(false)}
          patientId={id}
          patient={{
            name: typeof displayDemo.name === 'string' ? displayDemo.name : 'Patient',
            age: typeof displayDemo.age === 'number' ? displayDemo.age : Number(displayDemo.age) || 0,
            gender: displayDemo.gender,
          }}
          onCreated={async () => {
            const docsRes = await apiClient.get(`/patients/${id}/documents`).catch(() => null)
            if (docsRes?.data?.documents) {
              setDocuments(docsRes.data.documents.map((d: any) => ({
                name: d.title, type: d.type, date: d.date?.slice(0, 10) ?? '',
                id: d.id, has_pdf: d.has_pdf, pdf_url: d.pdf_url,
                version_number: d.version_number,
              })))
            }
            fetchTimeline(id)
          }}
        />
      )}
    </div>
  )
}

// ── Small local widgets ─────────────────────────────────────

function VitalCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="vital-label">{label}</p>
      <p className="vital-value text-vital-md">{value}</p>
    </div>
  )
}

// Mobile bottom-right FAB → opens the Copilot as a full-height side sheet.
// XL breakpoints already show the sticky rail; this only mounts under xl.
function MobileCopilotSheet({
  patientId, patientName, onCiteVersion,
}: { patientId: string; patientName: string; onCiteVersion: (v: number) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="xl:hidden">
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] right-4 z-30 h-12 w-12 rounded-full bg-primary-600 text-white shadow-card-elevated flex items-center justify-center hover:bg-primary-700 active:scale-95 transition-transform"
        aria-label="Open Clinical Copilot"
      >
        <Sparkles className="h-5 w-5" />
      </button>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/40" onClick={() => setOpen(false)}>
          <div
            className="absolute right-0 top-0 bottom-0 w-full sm:w-[380px] bg-surface-2 shadow-card-hover"
            onClick={e => e.stopPropagation()}
          >
            <div className="h-full flex flex-col">
              <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                <span className="text-sm font-semibold text-strong-fg">Clinical Copilot</span>
                <button onClick={() => setOpen(false)} aria-label="Close" className="p-1 rounded hover:bg-surface">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="flex-1 min-h-0">
                <CopilotPane
                  patientId={patientId}
                  patientName={patientName}
                  onCiteVersion={onCiteVersion}
                  className="rounded-none border-0 h-full"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
