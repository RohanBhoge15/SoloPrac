import { useState, useCallback } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { DocumentUpload, type UploadedFile } from '@/components/DocumentUpload'
import { Upload, FileText, X, User, CheckCircle, Loader2 } from 'lucide-react'

// Mock patients list for demo
const MOCK_PATIENTS = [
  { id: '1', initials: 'PS', name: 'Priya Sharma' },
  { id: '2', initials: 'RK', name: 'Rajesh Kumar' },
  { id: '3', initials: 'AP', name: 'Anita Patel' },
]

export function Scratchpad() {
  const [files, setFiles] = useState<{ name: string; size: number; type: string }[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [extractedText, setExtractedText] = useState<string | null>(null)
  const [processingComplete, setProcessingComplete] = useState(false)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [selectedPatient, setSelectedPatient] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Called when DocumentUpload finishes processing
  const handleUploadComplete = useCallback((uploadedFiles: UploadedFile[]) => {
    const completedFiles = uploadedFiles.filter(f => f.status === 'completed')
    if (completedFiles.length > 0) {
      setFiles(prev => [
        ...prev,
        ...completedFiles.map(f => ({ name: f.file.name, size: f.file.size, type: f.file.type })),
      ])
      // Combine extracted text from all completed files
      const combinedText = completedFiles
        .map(f => f.extractedText || '')
        .filter(Boolean)
        .join('\n\n')
      setExtractedText(combinedText)
      setProcessingComplete(true)
    }
  }, [])

  const removeFile = (name: string) => {
    setFiles(prev => prev.filter(f => f.name !== name))
    if (files.length <= 1) {
      setExtractedText(null)
      setProcessingComplete(false)
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleSaveToPatient = async () => {
    if (!selectedPatient || !extractedText) return
    setSaving(true)
    // Simulate saving
    await new Promise(r => setTimeout(r, 1500))
    setSaving(false)
    setSaved(true)
    setTimeout(() => {
      setSaved(false)
      setShowSaveDialog(false)
      setFiles([])
      setExtractedText(null)
      setProcessingComplete(false)
      setSelectedPatient(null)
    }, 2000)
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Scratchpad</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Drop any document or image — AI will extract text and summarize</p>
      </div>

      {/* Document Upload Component (drag-drop zone with preview) */}
      <DocumentUpload onUploadComplete={handleUploadComplete} maxFiles={5} maxSizeMB={20} />

      {/* Simple Upload Zone (alternative) */}
      {!processingComplete && (
        <>
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-gray-300 dark:border-gray-600" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-gray-50 dark:bg-gray-950 px-2 text-gray-500">or upload directly</span>
            </div>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              const droppedFiles = Array.from(e.dataTransfer.files)
              setFiles(prev => [...prev, ...droppedFiles.map(f => ({ name: f.name, size: f.size, type: f.type }))])
            }}
            className={cn(
              'border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer',
              dragOver
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:bg-gray-50 dark:hover:bg-gray-800/50'
            )}
          >
            <Upload className="mx-auto h-8 w-8 text-gray-400" />
            <p className="mt-2 text-sm font-medium text-gray-900 dark:text-white">
              or click to browse — PDF, JPG, PNG (max 20MB)
            </p>
            <Input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp" />
            <Button variant="outline" className="mt-3" size="sm" onClick={() => {}}>
              Browse Files
            </Button>
          </div>
        </>
      )}

      {/* Files List */}
      {files.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Uploaded Files ({files.length})</CardTitle>
            {processingComplete && (
              <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                <CheckCircle className="h-3.5 w-3.5" />
                Processing complete
              </span>
            )}
          </CardHeader>
          <CardContent className="space-y-2">
            {files.map((file) => (
              <div key={file.name} className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                <div className="flex items-center gap-3">
                  <FileText className="h-8 w-8 text-primary-600" />
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{file.name}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{formatSize(file.size)}</p>
                  </div>
                </div>
                <Button variant="ghost" size="icon" onClick={() => removeFile(file.name)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Extracted Content */}
      {extractedText && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Extracted Content</CardTitle>
            <Button
              variant="default"
              size="sm"
              onClick={() => setShowSaveDialog(true)}
            >
              <User className="h-4 w-4 mr-2" />
              Save to Patient
            </Button>
          </CardHeader>
          <CardContent>
            <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 min-h-[120px] text-gray-900 dark:text-white text-sm whitespace-pre-wrap font-mono">
              {extractedText}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Save to Patient Dialog */}
      {showSaveDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => !saving && setShowSaveDialog(false)}>
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl border border-gray-200 dark:border-gray-700" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Save to Patient Record</h3>

            {saved ? (
              <div className="text-center py-6">
                <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
                <p className="text-green-700 dark:text-green-300 font-medium">Saved successfully!</p>
                <p className="text-sm text-gray-500 mt-1">Content added to patient record.</p>
              </div>
            ) : (
              <>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  Select a patient to save this extracted content as a new version.
                </p>
                <div className="space-y-2 mb-6">
                  {MOCK_PATIENTS.map((p) => (
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
                    </button>
                  ))}
                </div>
                <div className="flex items-center justify-end gap-3">
                  <Button variant="outline" onClick={() => setShowSaveDialog(false)} disabled={saving}>
                    Cancel
                  </Button>
                  <Button onClick={handleSaveToPatient} disabled={!selectedPatient || saving}>
                    {saving ? (
                      <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving...</>
                    ) : (
                      'Save'
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