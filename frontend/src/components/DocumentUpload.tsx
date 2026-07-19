import { useDropzone } from 'react-dropzone'
import { useState, useCallback } from 'react'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Upload, FileText, X, Loader2, CheckCircle, AlertCircle, Eye } from 'lucide-react'

export interface UploadedFile {
  id: string
  file: File
  preview: string
  status: 'pending' | 'processing' | 'completed' | 'error'
  extractedText?: string
  error?: string
}

interface DocumentUploadProps {
  onUploadComplete?: (files: UploadedFile[]) => void
  maxFiles?: number
  maxSizeMB?: number
}

const dropzoneOptions = {
  accept: {
    'application/pdf': ['.pdf'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/webp': ['.webp'],
  },
  maxFiles: 5,
  maxSize: 20 * 1024 * 1024,
  multiple: true,
  onDragEnter: () => {},
  onDragLeave: () => {},
  onDragOver: () => {},
} as const

export function DocumentUpload({
  onUploadComplete,
  maxFiles = 5,
  maxSizeMB = 20,
}: DocumentUploadProps) {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [isProcessing, setIsProcessing] = useState(false)

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const currentCount = files.length
    const fileNames = files.map(f => f.file.name)
    const newFiles: UploadedFile[] = acceptedFiles
      .filter(f => currentCount + fileNames.filter(n => n === f.name).length < maxFiles)
      .slice(0, maxFiles - currentCount)
      .map(file => {
        const id = Date.now().toString(36) + '-' + Math.random().toString(36).substr(2, 9)
        const preview = URL.createObjectURL(file)
        return { id, file, preview, status: 'pending' as const }
      })
    if (newFiles.length > 0) {
      setFiles(prev => [...prev, ...newFiles])
    }
  }, [files, maxFiles])

  const dzConfig = {
    ...dropzoneOptions,
    onDrop,
    maxFiles,
    maxSize: maxSizeMB * 1024 * 1024,
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone(dzConfig as any)

  const removeFile = (id: string) => {
    setFiles(prev => {
      const file = prev.find(f => f.id === id)
      if (file) URL.revokeObjectURL(file.preview)
      return prev.filter(f => f.id !== id)
    })
  }

  const processFiles = async () => {
    const pendingFiles = files.filter(f => f.status === 'pending')
    if (pendingFiles.length === 0) return
    setIsProcessing(true)
    for (const file of pendingFiles) {
      setFiles(prev => prev.map(f =>
        f.id === file.id ? { ...f, status: 'processing' as const } : f
      ))
      try {
        await new Promise(r => setTimeout(r, 1500))
        const extractedText = file.file.type === 'application/pdf'
          ? '[PDF Content Extracted]\\n' + file.file.name
          : '[Image OCR Extracted]\\n' + file.file.name
        setFiles(prev => prev.map(f =>
          f.id === file.id ? { ...f, status: 'completed' as const, extractedText } : f
        ))
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Processing failed'
        setFiles(prev => prev.map(f =>
          f.id === file.id ? { ...f, status: 'error' as const, error: errorMsg } : f
        ))
      }
    }
    setIsProcessing(false)
    onUploadComplete?.(files.filter(f => f.status === 'completed'))
  }

  const canProcess = files.some(f => f.status === 'pending') && !isProcessing

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          Document Upload
          <span className="text-sm text-gray-500 dark:text-gray-400 font-normal">
            {files.length}/{maxFiles} files
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          {...getRootProps()}
          className={cn(
            'relative border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer',
            isDragActive
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
              : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 dark:hover:border-primary-600'
          )}
        >
          <input {...getInputProps()} aria-label="Upload files" />
          <Upload className="mx-auto h-12 w-12 text-gray-400" />
          <p className="mt-4 text-lg text-gray-900 dark:text-white">
            {isDragActive ? 'Drop files here...' : 'Drag & drop files or click to browse'}
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Max {maxFiles} files | {maxSizeMB}MB each | PDF, JPG, PNG, WebP
          </p>
        </div>

        {files.length > 0 && (
          <div className="mt-6 space-y-3">
            <h4 className="text-sm font-medium text-gray-900 dark:text-white">Uploaded Files</h4>
            {files.map(file => (
              <div
                key={file.id}
                className={cn(
                  'flex items-center justify-between p-3 rounded-lg border',
                  file.status === 'processing' && 'bg-blue-50 dark:bg-blue-900/20 border-blue-200',
                  file.status === 'completed' && 'bg-green-50 dark:bg-green-900/20 border-green-200',
                  file.status === 'error' && 'bg-red-50 dark:bg-red-900/20 border-red-200',
                  file.status === 'pending' && 'bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700'
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-lg shrink-0',
                    file.file.type === 'application/pdf' && 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400',
                    file.file.type.startsWith('image/') && 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
                  )}>
                    {file.file.type === 'application/pdf' ? <FileText className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 dark:text-white truncate max-w-xs">{file.file.name}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {(file.file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {file.status === 'pending' && <span className="text-xs text-gray-500">Waiting...</span>}
                  {file.status === 'processing' && (
                    <span className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Processing...
                    </span>
                  )}
                  {file.status === 'completed' && (
                    <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                      <CheckCircle className="h-3 w-3" />
                      Ready
                    </span>
                  )}
                  {file.status === 'error' && (
                    <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                      <AlertCircle className="h-3 w-3" />
                      {file.error}
                    </span>
                  )}
                  <Button variant="ghost" size="icon" onClick={() => removeFile(file.id)} disabled={isProcessing}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {files.length > 0 && (
          <div className="mt-6 flex items-center justify-end gap-3">
            <Button variant="outline" onClick={() => setFiles([])} disabled={isProcessing}>
              Clear All
            </Button>
            <Button onClick={processFiles} disabled={!canProcess || isProcessing}>
              {isProcessing ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing...</>
              ) : canProcess ? (
                'Process Files'
              ) : (
                'No Files to Process'
              )}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}