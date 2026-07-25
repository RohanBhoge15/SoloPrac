'use client'

import { useState, useCallback } from 'react'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { Upload, ImageIcon, ArrowLeftRight, Loader2, Save, CheckCircle, AlertCircle, SlidersHorizontal, Percent, GitCompare, Activity } from 'lucide-react'

interface ComparisonMetrics {
  area_change_pct?: number
  edge_convergence_score?: number
  color_histogram_shift?: number
  num_matches?: number
  homography_confidence?: number
}

interface ComparisonResult {
  status: string
  comparison_id: string
  matched: boolean
  current_image: { path: string; filename: string }
  matched_image?: { path: string; version_id?: string; score?: number }
  overlay_path?: string
  warped_previous_path?: string
  metrics: ComparisonMetrics
  message: string
  clinical_summary?: string
  summary_confidence?: number
}

interface ImageComparisonProps {
  patientId: string
  onSaveToRecord?: (comparisonId: string) => void
}

export function ImageComparison({ patientId, onSaveToRecord }: ImageComparisonProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<ComparisonResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [opacity, setOpacity] = useState(50)
  const [activePanel, setActivePanel] = useState<'previous' | 'current' | 'overlay'>('overlay')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setSelectedFile(file)
    setPreview(URL.createObjectURL(file))
    setResult(null)
    setError(null)
    setSaved(false)
  }, [])

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return
    setUploading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await apiClient.post(
        `/patients/${patientId}/images/compare`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }
      )
      setResult(response.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Comparison failed')
    } finally {
      setUploading(false)
    }
  }, [selectedFile, patientId])

  const handleSaveToRecord = useCallback(async () => {
    if (!result?.comparison_id) return
    setSaving(true)
    try {
      await apiClient.post(`/patients/${patientId}/images/comparisons/${result.comparison_id}/save-to-record`)
      setSaved(true)
      onSaveToRecord?.(result.comparison_id)
    } catch {
      setError('Failed to save comparison to patient record')
    } finally {
      setSaving(false)
    }
  }, [result, patientId, onSaveToRecord])

  const metrics = result?.metrics
  const healingDirection = metrics?.area_change_pct
    ? (metrics.area_change_pct < -5 ? 'improving' : metrics.area_change_pct > 5 ? 'worsening' : 'stable')
    : 'unknown'

  const healingColor = healingDirection === 'improving' ? 'text-green-600' : healingDirection === 'worsening' ? 'text-red-600' : 'text-yellow-600'
  const healingBg = healingDirection === 'improving' ? 'bg-green-100 dark:bg-green-900/20 border-green-300' : healingDirection === 'worsening' ? 'bg-red-100 dark:bg-red-900/20 border-red-300' : 'bg-yellow-100 dark:bg-yellow-900/20 border-yellow-300'

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitCompare className="h-5 w-5 text-primary-600" />
            Image Comparison — Wound/Skin Assessment
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            Upload a current wound/skin photo to compare against the best-matching prior image.
            ORB feature matching, homography alignment, and AI clinical summary.
          </p>

          {/* File Input */}
          <div className="flex items-center gap-4">
            <label className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg border cursor-pointer transition-colors',
              'hover:bg-gray-50 dark:hover:bg-gray-800 border-gray-300 dark:border-gray-600'
            )}>
              <Upload className="h-4 w-4" />
              <span className="text-sm">Choose Photo</span>
              <input type="file" accept="image/*" className="hidden" onChange={handleFileSelect} />
            </label>
            {selectedFile && (
              <span className="text-sm text-gray-500">{selectedFile.name}</span>
            )}
            {selectedFile && (
              <Button onClick={handleUpload} disabled={uploading} size="sm">
                {uploading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Comparing...</> : 'Run Comparison'}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      {/* 3-Panel View */}
      {result && (
        <>
          {/* Image Source Selector */}
          <Card>
            <CardContent className="p-3">
              <div className="flex items-center gap-2">
                {[
                  { key: 'previous', label: 'Previous', path: result.matched_image?.path },
                  { key: 'current', label: 'Current', path: result.current_image.path },
                  { key: 'overlay', label: 'Overlay', path: result.overlay_path },
                ].map((panel) => (
                  <button
                    key={panel.key}
                    onClick={() => setActivePanel(panel.key as typeof activePanel)}
                    className={cn(
                      'flex-1 p-2 rounded-lg text-sm font-medium transition-colors text-center',
                      activePanel === panel.key
                        ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 border border-primary-300'
                        : 'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-100 border border-transparent'
                    )}
                  >
                    {panel.label}
                  </button>
                ))}
              </div>

              {/* Image Display */}
              <div className="mt-3 relative rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-800" style={{ minHeight: 300 }}>
                {activePanel === 'previous' && result.matched_image?.path && (
                  <img src={result.matched_image.path} alt="Previous visit" className="w-full h-full object-contain" style={{ maxHeight: 400 }} />
                )}
                {activePanel === 'current' && (
                  <img src={preview || result.current_image.path} alt="Current visit" className="w-full h-full object-contain" style={{ maxHeight: 400 }} />
                )}
                {activePanel === 'overlay' && result.overlay_path && (
                  <>
                    <img src={result.overlay_path} alt="Overlay" className="w-full h-full object-contain" style={{ maxHeight: 400 }} />
                    {/* Opacity slider */}
                    <div className="absolute bottom-3 left-3 right-3 flex items-center gap-2 bg-black/60 rounded-lg px-3 py-2">
                      <SlidersHorizontal className="h-4 w-4 text-white shrink-0" />
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={opacity}
                        onChange={(e) => setOpacity(Number(e.target.value))}
                        className="flex-1 accent-primary-500"
                      />
                      <span className="text-xs text-white w-8 text-right">{opacity}%</span>
                    </div>
                  </>
                )}
                {activePanel === 'overlay' && !result.overlay_path && (
                  <div className="flex items-center justify-center h-[300px] text-gray-400">
                    <p className="text-sm">No overlay available — insufficient feature matches</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Metrics Display */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Activity className="h-4 w-4 text-primary-600" />
                Comparison Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className={cn('p-3 rounded-lg border', healingBg)}>
                  <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
                    <Percent className="h-3 w-3" />
                    Area Change
                  </div>
                  <p className={cn('text-lg font-bold', healingColor)}>
                    {metrics?.area_change_pct !== undefined ? `${metrics.area_change_pct >= 0 ? '+' : ''}${metrics.area_change_pct.toFixed(1)}%` : 'N/A'}
                  </p>
                  <p className="text-xs text-gray-400 capitalize">{healingDirection}</p>
                </div>

                <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                  <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
                    <GitCompare className="h-3 w-3" />
                    Edge Convergence
                  </div>
                  <p className="text-lg font-bold text-blue-700 dark:text-blue-300">
                    {metrics?.edge_convergence_score !== undefined ? metrics.edge_convergence_score.toFixed(3) : 'N/A'}
                  </p>
                  <p className="text-xs text-gray-400">1.0 = perfect</p>
                </div>

                <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
                  <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
                    <ArrowLeftRight className="h-3 w-3" />
                    Color Shift
                  </div>
                  <p className="text-lg font-bold text-purple-700 dark:text-purple-300">
                    {metrics?.color_histogram_shift !== undefined ? metrics.color_histogram_shift.toFixed(4) : 'N/A'}
                  </p>
                  <p className="text-xs text-gray-400">0 = identical</p>
                </div>

                <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
                    <Activity className="h-3 w-3" />
                    Match Confidence
                  </div>
                  <p className="text-lg font-bold text-gray-900 dark:text-white">
                    {metrics?.homography_confidence !== undefined ? (metrics.homography_confidence * 100).toFixed(0) + '%' : 'N/A'}
                  </p>
                  <p className="text-xs text-gray-400">{metrics?.num_matches || 0} features</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Clinical Summary */}
          {result.clinical_summary && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Activity className="h-4 w-4 text-green-600" />
                  Clinical Assessment
                </CardTitle>
                {result.summary_confidence && (
                  <Badge variant="secondary" className="text-[10px]">
                    AI confidence: {(result.summary_confidence * 100).toFixed(0)}%
                  </Badge>
                )}
              </CardHeader>
              <CardContent>
                <p className="text-sm text-gray-900 dark:text-white whitespace-pre-wrap">
                  {result.clinical_summary}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Status Badge and Save Button */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Badge variant={result.matched ? 'default' : 'secondary'}>
                {result.matched ? 'Registration successful' : 'Side-by-side only'}
              </Badge>
              {result.message && (
                <span className="text-xs text-gray-500">{result.message}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {saved ? (
                <Button variant="outline" disabled>
                  <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
                  Saved to Record
                </Button>
              ) : (
                <Button onClick={handleSaveToRecord} disabled={saving}>
                  {saving ? (
                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</>
                  ) : (
                    <><Save className="h-4 w-4 mr-2" /> Save to Patient Record</>
                  )}
                </Button>
              )}
            </div>
          </div>
        </>
      )}

      {!result && !uploading && !selectedFile && (
        <Card>
          <CardContent className="p-12 text-center">
            <ImageIcon className="mx-auto h-12 w-12 text-gray-300" />
            <p className="mt-3 text-gray-500 text-sm">Upload a wound/skin photo to compare against prior visits</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
