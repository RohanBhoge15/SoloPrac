import { useState, useRef, useCallback, useEffect } from 'react'
import { Button } from '@/components/ui/Button'
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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > maxSizeMB * 1024 * 1024) {
      alert(`File too large. Max ${maxSizeMB}MB.`)
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

    // Calculate source rectangle from the visible crop area
    const imgEl = imgRef.current
    const displayW = imgEl.clientWidth
    const displayH = imgEl.clientHeight
    const scaleX = img.naturalWidth / displayW
    const scaleY = img.naturalHeight / displayH

    // Center of crop circle relative to displayed image
    const cropCenterX = displayW / 2
    const cropCenterY = displayH / 2

    // Source coordinates (in natural image pixels)
    const srcRadius = (cropSize / 2) * Math.max(scaleX, scaleY)
    const srcCenterX = (cropCenterX - position.x) * scaleX
    const srcCenterY = (cropCenterY - position.y) * scaleY

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
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
