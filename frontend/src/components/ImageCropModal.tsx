import { useState, useRef, useCallback, useEffect } from 'react'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toast'
import { X, ZoomIn, ZoomOut, Check, Loader2 } from 'lucide-react'

interface ImageCropModalProps {
  open: boolean
  onClose: () => void
  onCropped: (blob: Blob) => void
  maxSizeMB?: number
}

export function ImageCropModal({ open, onClose, onCropped, maxSizeMB = 5 }: ImageCropModalProps) {
  const [imageSrc, setImageSrc] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [cropping, setCropping] = useState(false)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cropSize = 300 // px — the circular crop area

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setImageSrc(null)
      setZoom(1)
      setPosition({ x: 0, y: 0 })
      setCropping(false)
    }
  }, [open])

  // Modal ESC rollout: close on Escape key.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > maxSizeMB * 1024 * 1024) {
      // Toast rollout: replace native alert() with the global toast.
      toast.error(`File too large. Max ${maxSizeMB}MB.`)
      return
    }
    const reader = new FileReader()
    reader.onload = () => setImageSrc(reader.result as string)
    reader.readAsDataURL(file)
    e.target.value = ''
  }

  const handleImgLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    imgRef.current = e.currentTarget
  }

  // ── Drag handling ──
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y })
  }

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return
    setPosition({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    })
  }, [isDragging, dragStart])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
      return () => {
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [isDragging, handleMouseMove, handleMouseUp])

  // ── Touch handling ──
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    setIsDragging(true)
    setDragStart({ x: touch.clientX - position.x, y: touch.clientY - position.y })
  }

  const handleTouchMove = useCallback((e: TouchEvent) => {
    if (!isDragging) return
    const touch = e.touches[0]
    setPosition({
      x: touch.clientX - dragStart.x,
      y: touch.clientY - dragStart.y,
    })
  }, [isDragging, dragStart])

  const handleTouchEnd = useCallback(() => {
    setIsDragging(false)
  }, [])

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('touchmove', handleTouchMove, { passive: false })
      window.addEventListener('touchend', handleTouchEnd)
      return () => {
        window.removeEventListener('touchmove', handleTouchMove)
        window.removeEventListener('touchend', handleTouchEnd)
      }
    }
  }, [isDragging, handleTouchMove, handleTouchEnd])

  // ── Crop and return blob ──
  const handleCrop = async () => {
    if (!imgRef.current || !imageSrc) return
    setCropping(true)

    const img = imgRef.current
    const canvas = document.createElement('canvas')
    const outputSize = 400 // output resolution
    canvas.width = outputSize
    canvas.height = outputSize
    const ctx = canvas.getContext('2d')!

    // D-9: Previous math ignored `zoom` entirely, so the exported blob was
    // always unzoomed regardless of what the user saw. The <img> is rendered
    // at natural size (maxWidth: 'none', no CSS width) and then transformed
    // with `translate(position) scale(zoom)` using transformOrigin center.
    //
    // Screen->natural mapping (with center-origin scale):
    //   Let C_screen = image center on screen = position + (naturalW/2, naturalH/2)
    //   (center-origin scaling leaves the center fixed after translate).
    //   For any screen point p, its natural-pixel counterpart is:
    //     n = (naturalW/2, naturalH/2) + (p - C_screen) / zoom
    //   The crop circle is centered at (cropSize/2, cropSize/2) on screen
    //   with screen radius cropSize/2, so its natural radius is (cropSize/2)/zoom.
    const naturalW = img.naturalWidth
    const naturalH = img.naturalHeight
    const centerScreenX = position.x + naturalW / 2
    const centerScreenY = position.y + naturalH / 2
    const srcCenterX = naturalW / 2 + (cropSize / 2 - centerScreenX) / zoom
    const srcCenterY = naturalH / 2 + (cropSize / 2 - centerScreenY) / zoom
    const srcRadius = (cropSize / 2) / zoom

    // Draw circular crop
    ctx.beginPath()
    ctx.arc(outputSize / 2, outputSize / 2, outputSize / 2, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()

    ctx.drawImage(
      img,
      srcCenterX - srcRadius,
      srcCenterY - srcRadius,
      srcRadius * 2,
      srcRadius * 2,
      0,
      0,
      outputSize,
      outputSize,
    )

    canvas.toBlob((blob) => {
      if (blob) {
        onCropped(blob)
        onClose()
      }
      setCropping(false)
    }, 'image/jpeg', 0.9)
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={imageSrc ? 'Adjust photo' : 'Upload photo'}
    >
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {imageSrc ? 'Adjust Photo' : 'Upload Photo'}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
            <X className="h-5 w-5" />
          </button>
        </div>

        {!imageSrc ? (
          /* File picker */
          <div className="space-y-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Choose a profile photo. You'll be able to adjust the crop before saving.
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={handleFileSelect}
            />
            <Button
              variant="outline"
              className="w-full h-32 border-dashed border-2"
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="text-center">
                <div className="text-3xl mb-2">📷</div>
                <span className="text-sm text-gray-500">Click to choose photo</span>
              </div>
            </Button>
            <p className="text-xs text-gray-400 text-center">JPG, PNG or WebP. Max {maxSizeMB}MB.</p>
          </div>
        ) : (
          /* Crop interface */
          <div className="space-y-4">
            <div
              className="relative mx-auto overflow-hidden rounded-xl bg-gray-100 dark:bg-gray-800"
              style={{ width: cropSize, height: cropSize, cursor: isDragging ? 'grabbing' : 'grab' }}
              onMouseDown={handleMouseDown}
              onTouchStart={handleTouchStart}
            >
              {/* Image */}
              <img
                src={imageSrc}
                alt="Crop preview"
                className="absolute top-0 left-0 select-none pointer-events-none"
                style={{
                  maxWidth: 'none',
                  transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
                  transformOrigin: 'center center',
                }}
                onLoad={handleImgLoad}
                draggable={false}
              />

              {/* Circular mask overlay — dark outside the circle */}
              <svg
                className="absolute inset-0 pointer-events-none"
                width={cropSize}
                height={cropSize}
                viewBox={`0 0 ${cropSize} ${cropSize}`}
              >
                <defs>
                  <mask id="cropMask">
                    <rect width={cropSize} height={cropSize} fill="white" />
                    <circle cx={cropSize / 2} cy={cropSize / 2} r={cropSize / 2 - 2} fill="black" />
                  </mask>
                </defs>
                <rect
                  width={cropSize}
                  height={cropSize}
                  fill="rgba(0,0,0,0.5)"
                  mask="url(#cropMask)"
                />
                <circle
                  cx={cropSize / 2}
                  cy={cropSize / 2}
                  r={cropSize / 2 - 2}
                  fill="none"
                  stroke="white"
                  strokeWidth="2"
                  opacity="0.8"
                />
              </svg>
            </div>

            {/* Zoom slider */}
            <div className="flex items-center gap-3 px-2">
              <ZoomOut className="h-4 w-4 text-gray-400 shrink-0" />
              <input
                type="range"
                min={0.5}
                max={3}
                step={0.05}
                value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
                className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-primary-600"
              />
              <ZoomIn className="h-4 w-4 text-gray-400 shrink-0" />
            </div>

            <p className="text-xs text-gray-400 text-center">Drag to reposition, use slider to zoom</p>

            {/* Actions */}
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => { setImageSrc(null); setZoom(1); setPosition({ x: 0, y: 0 }) }}
              >
                Choose Different
              </Button>
              <Button
                className="flex-1"
                onClick={handleCrop}
                disabled={cropping}
              >
                {cropping ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</>
                ) : (
                  <><Check className="mr-2 h-4 w-4" />Use Photo</>
                )}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
