import { useState, useCallback } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Upload, FileText, X } from 'lucide-react'

export function Scratchpad() {
  const [files, setFiles] = useState<{ name: string; size: number; type: string }[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [processing, setProcessing] = useState(false)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const droppedFiles = Array.from(e.dataTransfer.files)
    setFiles(prev => [...prev, ...droppedFiles.map(f => ({ name: f.name, size: f.size, type: f.type }))])
  }, [])

  const removeFile = (name: string) => {
    setFiles(prev => prev.filter(f => f.name !== name))
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Scratchpad</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Drop any document or image — AI will extract text and summarize</p>
      </div>

      {/* Upload Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          'border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer',
          dragOver
            ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
            : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:bg-gray-50 dark:hover:bg-gray-800/50'
        )}
      >
        <Upload className="mx-auto h-12 w-12 text-gray-400" />
        <p className="mt-4 text-lg font-medium text-gray-900 dark:text-white">
          Drop documents here
        </p>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          or click to browse — PDF, JPG, PNG (max 20MB)
        </p>
        <Input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp" />
        <Button variant="outline" className="mt-4" onClick={() => {}}>
          Browse Files
        </Button>
      </div>

      {/* Files List */}
      {files.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Uploaded Files ({files.length})</CardTitle>
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

      {/* Actions */}
      {files.length > 0 && (
        <div className="flex items-center gap-3 justify-end">
          <Button variant="outline" onClick={() => setFiles([])}>Clear All</Button>
          <Button onClick={() => setProcessing(true)} disabled={processing}>
            {processing ? 'Processing...' : 'Extract & Summarize'}
          </Button>
        </div>
      )}

      {/* Result Area */}
      <Card>
        <CardHeader>
          <CardTitle>Extracted Content</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 min-h-[120px] text-gray-500 dark:text-gray-400 text-sm">
            {files.length === 0
              ? 'Upload a document to see extracted content here.'
              : processing
                ? 'Processing document... AI is extracting text and identifying structured data.'
                : 'Click "Extract & Summarize" to begin processing.'}
          </div>
          <div className="mt-4 flex justify-end">
            <Button variant="outline" disabled={files.length === 0 || processing}>
              Save to Patient
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}