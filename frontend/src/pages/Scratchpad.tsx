import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { Upload, FileText, X, User, CheckCircle, Loader2, Eye, File, Search } from 'lucide-react'

interface ParsedDocument {
  doc_id: string
  filename: string
  doc_type: string
  doc_format: string
  raw_text: string
  structured: Record<string, unknown>
  confidence: number
  took_ms: number
}

interface UploadingFile {
  id: string
  name: string
  size: number
  type: string
  preview: string
  status: 'uploading' | 'parsing' | 'completed' | 'error'
  result?: ParsedDocument
  error?: string
}

interface PatientSummary {
  id: string
  initials: string
  name: string
}

const DOC_TYPE_LABELS: Record<string, string> = {
  prescription: 'Prescription',
  lab_report: 'Lab Report',
  discharge_summary: 'Discharge Summary',
  referral_letter: 'Referral Letter',
  imaging_report: 'Imaging Report',
  general_document: 'Document',
}

const DOC_TYPE_COLORS: Record<string, string> = {
  prescription: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  lab_report: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  discharge_summary: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  referral_letter: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  imaging_report: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300',
}

export function Scratchpad() {
  const [files, setFiles] = useState<UploadingFile[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [selectedPatient, setSelectedPatient] = useState<string | null>(null)
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [patients, setPatients] = useState<PatientSummary[]>([])
  const [patientsLoading, setPatientsLoading] = useState(false)
  const [patientSearch, setPatientSearch] = useState('')

  // Fetch real patients on mount
  useEffect(() => {
    let cancelled = false
    setPatientsLoading(true)
    apiClient.get('/patients', { params: { limit: 200 } })
      .then(res => {
        if (cancelled) return
        const data = res.data ?? []
        const mapped: PatientSummary[] = data.map((p: any) => {
          const demo = p.head_version?.state_jsonb?.demographics ?? {}
          const name = demo.name ?? `Patient ${p.id.slice(0, 8)}`
          return {
            id: p.id,
            initials: name.split(' ').map((n: string) => n[0]).join(''),
            name,
          }
        })
        setPatients(mapped)
      })
      .catch((err) => {
        console.warn('[Scratchpad] Failed to load patients:', err)
      })
      .finally(() => { if (!cancelled) setPatientsLoading(false) })
    return () => { cancelled = true }
  }, [])

  const filteredPatients = patientSearch.trim()
    ? patients.filter(p => p.name.toLowerCase().includes(patientSearch.toLowerCase()))
    : patients

  const handleDrop = useCallback(async (droppedFiles: FileList | File[]) => {
    const newFiles: UploadingFile[] = Array.from(droppedFiles).map((f) => ({
      id: Date.now().toString(36) + '-' + Math.random().toString(36).substr(2, 9),
      name: f.name,
      size: f.size,
      type: f.type,
      preview: f.type.startsWith('image/') ? URL.createObjectURL(f) : '',
      status: 'uploading' as const,
    }))

    if (newFiles.length > 0) {
      setFiles(prev => [...prev, ...newFiles])
    }

    // Upload each file to the parse API
    for (const nf of newFiles) {
      setFiles(prev => prev.map(f => f.id === nf.id ? { ...f, status: 'uploading' as const } : f))

      try {
        const formData = new FormData()
        const fileObj = Array.from(droppedFiles).find(f => f.name === nf.name)
        if (fileObj) {
          formData.append('file', fileObj)
        }

        const response = await apiClient.post('/documents/parse', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 60000,
        })

        const result: ParsedDocument = response.data
        setFiles(prev => prev.map(f =>
          f.id === nf.id ? { ...f, status: 'completed' as const, result } : f
        ))
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Upload failed'
        setFiles(prev => prev.map(f =>
          f.id === nf.id ? { ...f, status: 'error' as const, error: errorMsg } : f
        ))
      }
    }
  }, [])

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = () => setDragOver(false)

  const handleDropEvent = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleDrop(e.dataTransfer.files)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleDrop(e.target.files)
      e.target.value = ''
    }
  }

  const removeFile = (id: string) => {
    setFiles(prev => {
      const file = prev.find(f => f.id === id)
      if (file?.preview) URL.revokeObjectURL(file.preview)
      return prev.filter(f => f.id !== id)
    })
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleSaveToPatient = async () => {
    if (!selectedPatient || !selectedDocId) return
    setSaving(true)
    try {
      const formData = new FormData()
      formData.append('patient_id', selectedPatient)
      await apiClient.post(`/documents/${selectedDocId}/save-to-patient`, formData)
      setSaving(false)
      setSaved(true)
      setTimeout(() => {
        setSaved(false)
        setShowSaveDialog(false)
        setFiles([])
        setSelectedPatient(null)
        setSelectedDocId(null)
      }, 2000)
    } catch {
      setSaving(false)
    }
  }

  const openSaveDialog = (docId: string) => {
    setSelectedDocId(docId)
    setSelectedPatient(null)
    setPatientSearch('')
    setShowSaveDialog(true)
  }

  const completedFiles = files.filter(f => f.status === 'completed')
  const hasContent = completedFiles.length > 0

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Scratchpad</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Drop any document — PDF, JPG, PNG, WebP — AI will extract text and classify the document type
        </p>
      </div>

      {/* Upload Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDropEvent}
        onClick={() => document.getElementById('file-input')?.click()}
        className={cn(
          'border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer',
          dragOver
            ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
            : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:bg-gray-50 dark:hover:bg-gray-800/50'
        )}
      >
        <Upload className="mx-auto h-12 w-12 text-gray-400" />
        <p className="mt-4 text-lg font-medium text-gray-900 dark:text-white">
          Drop documents here or click to browse
        </p>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          PDF, JPG, PNG, WebP — max 25MB each
        </p>
        <Input
          id="file-input"
          type="file"
          className="hidden"
          accept=".pdf,.jpg,.jpeg,.png,.webp"
          multiple
          onChange={handleFileInput}
        />
      </div>

      {/* Files List */}
      {files.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Uploaded Files ({files.length})</CardTitle>
            {hasContent && (
              <span className="flex items-center gap-1 text-xs text-green-600">
                <CheckCircle className="h-3.5 w-3.5" />
                {completedFiles.length} parsed
              </span>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {files.map((file) => (
              <div
                key={file.id}
                className={cn(
                  'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                  file.status === 'completed' && 'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800',
                  file.status === 'error' && 'bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800',
                  file.status === 'uploading' && 'bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-800',
                  (file.status === 'parsing' || file.status === 'uploading') && 'bg-yellow-50 dark:bg-yellow-900/10 border-yellow-200 dark:border-yellow-800',
                )}
              >
                {/* Thumbnail/Icon */}
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-800 overflow-hidden">
                  {file.preview ? (
                    <img src={file.preview} alt={file.name} className="h-full w-full object-cover" />
                  ) : file.type === 'application/pdf' ? (
                    <FileText className="h-6 w-6 text-red-500" />
                  ) : (
                    <File className="h-6 w-6 text-gray-400" />
                  )}
                </div>

                {/* Details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-gray-900 dark:text-white truncate">{file.name}</p>
                    {file.result?.doc_type && (
                      <Badge variant="secondary" className={cn('text-[10px]', DOC_TYPE_COLORS[file.result.doc_type] || '')}>
                        {DOC_TYPE_LABELS[file.result.doc_type] || file.result.doc_type}
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-gray-500">{formatSize(file.size)}</p>

                  {/* Status / Progress */}
                  {file.status === 'uploading' && (
                    <div className="flex items-center gap-1.5 mt-1">
                      <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
                      <span className="text-xs text-blue-600">Uploading & parsing...</span>
                    </div>
                  )}
                  {file.status === 'completed' && file.result && (
                    <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                      <span>Confidence: {(file.result.confidence * 100).toFixed(0)}%</span>
                      <span>·</span>
                      <span>{(file.result.took_ms / 1000).toFixed(1)}s</span>
                      {file.result.structured && typeof file.result.structured === 'object' && 'text_length' in file.result.structured && (
                        <>
                          <span>·</span>
                          <span>{String(file.result.structured.text_length)} chars</span>
                        </>
                      )}
                    </div>
                  )}
                  {file.status === 'error' && (
                    <p className="text-xs text-red-600 mt-1">{file.error}</p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 shrink-0">
                  {file.status === 'completed' && file.result && (
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        title="View extracted text"
                        onClick={() => {}}
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={() => file.result && openSaveDialog(file.result.doc_id)}
                      >
                        <User className="h-3 w-3 mr-1" />
                        Save
                      </Button>
                    </>
                  )}
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removeFile(file.id)}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Extracted Content Details */}
      {hasContent && (
        <div className="space-y-4">
          {completedFiles.filter(f => f.result?.raw_text).map((file) => (
            <Card key={file.id}>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-sm">
                  Extracted — {file.result?.doc_type ? DOC_TYPE_LABELS[file.result.doc_type] || file.result.doc_type : 'Document'}
                </CardTitle>
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => openSaveDialog(file.result!.doc_id)}
                >
                  <User className="h-4 w-4 mr-2" />
                  Save to Patient
                </Button>
              </CardHeader>
              <CardContent>
                <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 min-h-[100px] max-h-[300px] overflow-y-auto text-gray-900 dark:text-white text-sm whitespace-pre-wrap font-mono">
                  {file.result?.raw_text || 'No text extracted.'}
                </div>

                {/* Structured data preview */}
                {file.result?.structured && Object.keys(file.result.structured).length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    <p className="text-xs font-semibold text-gray-500 uppercase">Structured Fields</p>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(file.result.structured).filter(([k]) => !['type', 'extracted_at', 'text_length'].includes(k)).slice(0, 8).map(([key, value]) => (
                        <div key={key} className="p-1.5 rounded bg-gray-50 dark:bg-gray-800/50">
                          <span className="text-gray-500 capitalize">{key.replace('_', ' ')}</span>
                          <p className="font-medium truncate">
                            {Array.isArray(value) ? `${value.length} items` : String(value).slice(0, 60)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Save to Patient Dialog — Real Patient List */}
      {showSaveDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => !saving && setShowSaveDialog(false)}>
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl border border-gray-200 dark:border-gray-700 max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Save to Patient Record</h3>

            {saved ? (
              <div className="text-center py-6">
                <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
                <p className="text-green-700 dark:text-green-300 font-medium">Saved successfully!</p>
                <p className="text-sm text-gray-500 mt-1">Document added to patient record as a new version.</p>
              </div>
            ) : (
              <>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  Select a patient to save this parsed document as a new versioned record entry.
                </p>

                {/* Patient search */}
                <div className="relative mb-4">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <Input
                    value={patientSearch}
                    onChange={e => setPatientSearch(e.target.value)}
                    placeholder="Search patients..."
                    className="pl-10"
                  />
                </div>

                {/* Patient list */}
                <div className="space-y-2 mb-6 overflow-y-auto flex-1 max-h-[300px]">
                  {patientsLoading ? (
                    <div className="flex items-center justify-center py-6">
                      <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
                    </div>
                  ) : filteredPatients.length === 0 ? (
                    <p className="text-center text-sm text-gray-500 py-4">
                      {patientSearch ? 'No patients match your search' : 'No patients found. Create a patient first.'}
                    </p>
                  ) : (
                    filteredPatients.slice(0, 30).map((p) => (
                      <button
                        key={p.id}
                        onClick={() => setSelectedPatient(p.id)}
                        className={cn(
                          'flex items-center gap-3 w-full p-3 rounded-lg border transition-colors text-left',
                          selectedPatient === p.id
                            ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                            : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'
                        )}
                      >
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                          <span className="text-xs font-medium text-primary-700 dark:text-primary-300">{p.initials}</span>
                        </div>
                        <span className="font-medium text-gray-900 dark:text-white">{p.name}</span>
                        {selectedPatient === p.id && (
                          <CheckCircle className="h-4 w-4 text-primary-600 ml-auto" />
                        )}
                      </button>
                    ))
                  )}
                </div>

                <div className="flex items-center justify-end gap-3">
                  <Button variant="outline" onClick={() => setShowSaveDialog(false)} disabled={saving}>
                    Cancel
                  </Button>
                  <Button onClick={handleSaveToPatient} disabled={!selectedPatient || saving}>
                    {saving ? (
                      <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving...</>
                    ) : (
                      'Save to Patient Record'
                    )}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}