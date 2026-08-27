'use client'

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { apiClient } from '@/services/api'
import { ImageIcon, Eye, Edit3, Save, X, Loader2, Calendar } from 'lucide-react'

interface ImageVersion {
  version_id: string
  version_number: number
  filename: string
  s3_key: string
  mime_type: string
  clinical_summary: string
  created_at: string
}

interface ImageGalleryProps {
  patientId: string
}

// D-13 Part A: previously the thumbnail column always showed a static <ImageIcon>
// placeholder. This component lazily fetches the actual image bytes via the
// same /images/file endpoint used by handleView (which follows the 307 to a
// presigned S3 URL) and renders a small <img>. Clicking the thumbnail opens
// the full viewer via the same onView flow.
function ImageThumbnail({
  patientId,
  s3Key,
  onClick,
}: {
  patientId: string
  s3Key: string
  onClick: () => void
}) {
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let createdUrl: string | null = null
    ;(async () => {
      try {
        const res = await apiClient.get(`/patients/${patientId}/images/file`, {
          params: { s3_key: s3Key },
          responseType: 'blob',
        })
        if (cancelled) return
        createdUrl = URL.createObjectURL(res.data)
        setThumbUrl(createdUrl)
      } catch {
        // Fall back to placeholder icon
      }
    })()
    return () => {
      cancelled = true
      if (createdUrl) URL.revokeObjectURL(createdUrl)
    }
  }, [patientId, s3Key])

  return (
    <button
      type="button"
      onClick={onClick}
      title="View image"
      className="shrink-0 w-16 h-16 rounded-md bg-gray-200 dark:bg-gray-700 flex items-center justify-center overflow-hidden focus:outline-none focus:ring-2 focus:ring-primary-500"
    >
      {thumbUrl ? (
        <img src={thumbUrl} alt="thumbnail" className="w-full h-full object-cover" />
      ) : (
        <ImageIcon className="h-6 w-6 text-gray-400" />
      )}
    </button>
  )
}

export function ImageGallery({ patientId }: ImageGalleryProps) {
  const [images, setImages] = useState<ImageVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editSummary, setEditSummary] = useState('')
  const [saving, setSaving] = useState(false)
  const [viewingImage, setViewingImage] = useState<ImageVersion | null>(null)
  const [viewerUrl, setViewerUrl] = useState<string | null>(null)

  const fetchImages = useCallback(async () => {
    try {
      setLoading(true)
      const res = await apiClient.get(`/patients/${patientId}/images/list`)
      setImages(res.data)
    } catch {
      console.warn('Failed to load images')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  useEffect(() => { fetchImages() }, [fetchImages])

  const handleEdit = (img: ImageVersion) => {
    setEditingId(img.version_id)
    setEditSummary(img.clinical_summary)
  }

  const handleSave = async (versionId: string) => {
    setSaving(true)
    try {
      await apiClient.patch(`/patients/${patientId}/images/${versionId}/summary`, {
        clinical_summary: editSummary,
      })
      setImages(prev => prev.map(img =>
        img.version_id === versionId ? { ...img, clinical_summary: editSummary } : img
      ))
      setEditingId(null)
    } catch {
      console.warn('Failed to save summary')
    } finally {
      setSaving(false)
    }
  }

  const handleView = async (img: ImageVersion) => {
    setViewingImage(img)
    setViewerUrl(null)
    try {
      // D-13 Part B: Previously the code set maxRedirects:0 and tried to read
      // res.headers.location from a 307 response. Browsers hide the Location
      // header on cross-origin responses unless the server exposes it via CORS
      // (which main.py does not), so viewerUrl was always null.
      // Fix: let axios follow the redirect to the presigned S3 URL and fetch
      // the bytes as a blob, then wrap in an object URL for the <img> tag.
      const res = await apiClient.get(`/patients/${patientId}/images/file`, {
        params: { s3_key: img.s3_key },
        responseType: 'blob',
      })
      const blobUrl = URL.createObjectURL(res.data)
      setViewerUrl(blobUrl)
    } catch {
      setViewerUrl(null)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto text-gray-400" />
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ImageIcon className="h-5 w-5 text-primary-600" />
            Patient Images ({images.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {images.length === 0 ? (
            <p className="text-center text-gray-500 py-6">No images uploaded yet</p>
          ) : (
            <div className="space-y-3">
              {images.map((img) => (
                <div key={img.version_id} className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                  <ImageThumbnail
                    patientId={patientId}
                    s3Key={img.s3_key}
                    onClick={() => handleView(img)}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm text-gray-900 dark:text-white truncate">{img.filename}</span>
                      <span className="text-xs text-gray-400">v{img.version_number}</span>
                      <span className="text-xs text-gray-400 flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {new Date(img.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    {editingId === img.version_id ? (
                      <div className="mt-2">
                        <textarea
                          value={editSummary}
                          onChange={(e) => setEditSummary(e.target.value)}
                          rows={3}
                          className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white resize-none focus:outline-none focus:ring-2 focus:ring-primary-500"
                          placeholder="AI-generated clinical summary..."
                        />
                        <div className="flex gap-2 mt-2">
                          <Button size="sm" onClick={() => handleSave(img.version_id)} disabled={saving}>
                            {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Save className="h-3 w-3 mr-1" />}
                            Save
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                            <X className="h-3 w-3 mr-1" /> Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                        {img.clinical_summary || 'No summary yet — analyzing...'}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button variant="ghost" size="icon" title="View image" onClick={() => handleView(img)}>
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" title="Edit summary" onClick={() => handleEdit(img)}>
                      <Edit3 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Image Viewer Modal */}
      {viewingImage && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => { setViewingImage(null); if (viewerUrl) URL.revokeObjectURL(viewerUrl); setViewerUrl(null) }}
        >
          <div className="bg-white dark:bg-gray-900 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <span className="font-medium text-sm">{viewingImage.filename}</span>
              <Button variant="ghost" size="icon" onClick={() => { setViewingImage(null); if (viewerUrl) URL.revokeObjectURL(viewerUrl); setViewerUrl(null) }}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <div className="flex-1 overflow-auto p-4 flex items-center justify-center bg-gray-100 dark:bg-gray-800">
              {viewerUrl ? (
                <img src={viewerUrl} alt={viewingImage.filename} className="max-w-full max-h-[70vh] object-contain" />
              ) : (
                <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
              )}
            </div>
            {viewingImage.clinical_summary && (
              <div className="p-4 border-t border-gray-200 dark:border-gray-700">
                <p className="text-xs text-gray-500 mb-1">Clinical Summary</p>
                <p className="text-sm text-gray-900 dark:text-white">{viewingImage.clinical_summary}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
