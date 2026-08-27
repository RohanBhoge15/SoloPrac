import { useEffect, useRef, useState, useCallback } from 'react'
import { Camera, RotateCcw, Check, X, AlertCircle, Loader2, SwitchCamera } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/utils/helpers'

/**
 * CameraCaptureModal — live camera preview + capture-to-File flow.
 *
 * Uses navigator.mediaDevices.getUserMedia. Handles the three states a real
 * user actually hits:
 *   1. permission granted → live <video> preview, click to capture
 *   2. after capture → still frame + Retake / Use Photo buttons
 *   3. permission denied / no camera → clear error + "Upload from disk" escape hatch
 *
 * On mobile it prefers the rear ('environment') camera because that's what
 * doctors want when photographing prescriptions. Users can flip on any device
 * that exposes more than one camera.
 *
 * Props:
 *   open       — whether the modal is visible
 *   onClose    — called when user cancels
 *   onCapture  — called with a File (JPEG, ~0.92 quality) after user accepts
 *   onFallback — optional; called when the user clicks "Upload from disk"
 *                so the parent can trigger its regular file input
 */
export interface CameraCaptureModalProps {
  open: boolean
  onClose: () => void
  onCapture: (file: File) => void
  onFallback?: () => void
}

type FacingMode = 'environment' | 'user'

export function CameraCaptureModal({ open, onClose, onCapture, onFallback }: CameraCaptureModalProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const [status, setStatus] = useState<'idle' | 'starting' | 'ready' | 'captured' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState<string>('')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [capturedBlob, setCapturedBlob] = useState<Blob | null>(null)
  const [facing, setFacing] = useState<FacingMode>('environment')
  const [hasMultipleCameras, setHasMultipleCameras] = useState(false)

  // ── Start / stop the stream in lockstep with `open` and `facing` ──
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const startStream = useCallback(async (mode: FacingMode) => {
    setStatus('starting')
    setErrorMsg('')
    stopStream()

    // Feature-detect before calling — some older webviews don't expose this at all.
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setStatus('error')
      setErrorMsg('Your browser does not support camera capture. Please upload a photo instead.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: mode },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        // Wait for the metadata so we know the true dimensions before allowing capture.
        await new Promise<void>(resolve => {
          const v = videoRef.current!
          if (v.readyState >= 2) return resolve()
          v.onloadedmetadata = () => resolve()
        })
        await videoRef.current.play().catch(() => { /* iOS Safari sometimes rejects — the srcObject still renders */ })
      }
      setStatus('ready')

      // Detect if there is more than one video input so we know whether to show the flip button.
      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        const cams = devices.filter(d => d.kind === 'videoinput')
        setHasMultipleCameras(cams.length > 1)
      } catch { /* enumerateDevices requires permission on some browsers; ignore */ }
    } catch (err: any) {
      setStatus('error')
      // These are the DOMException names the spec defines. Handle each with a real user message.
      const name = err?.name || ''
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        setErrorMsg('Camera access was blocked. Enable camera permission in your browser settings, or upload a photo from disk.')
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        setErrorMsg('No camera was detected on this device. Please upload a photo from disk instead.')
      } else if (name === 'NotReadableError' || name === 'TrackStartError') {
        setErrorMsg('Your camera is being used by another application. Close it and try again.')
      } else if (name === 'OverconstrainedError') {
        setErrorMsg('This camera does not support the requested settings. Try switching cameras.')
      } else {
        setErrorMsg('Could not start the camera: ' + (err?.message || name || 'unknown error'))
      }
    }
  }, [stopStream])

  // Mount / unmount lifecycle
  useEffect(() => {
    if (!open) {
      stopStream()
      setStatus('idle')
      setPreviewUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null })
      setCapturedBlob(null)
      setErrorMsg('')
      return
    }
    void startStream(facing)
    return () => { stopStream() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Facing-mode switch: only restart when already open + ready (avoid double-start on mount).
  useEffect(() => {
    if (open && status !== 'idle' && status !== 'starting') {
      void startStream(facing)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facing])

  // Modal ESC rollout: close on Escape key.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // ── Capture + retake ──
  const handleCapture = useCallback(() => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas || status !== 'ready') return
    const w = video.videoWidth
    const h = video.videoHeight
    if (!w || !h) return
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(video, 0, 0, w, h)
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        setCapturedBlob(blob)
        const url = URL.createObjectURL(blob)
        setPreviewUrl(prev => { if (prev) URL.revokeObjectURL(prev); return url })
        setStatus('captured')
      },
      'image/jpeg',
      0.92,
    )
  }, [status])

  const handleRetake = () => {
    setPreviewUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null })
    setCapturedBlob(null)
    setStatus('ready')
  }

  const handleAccept = () => {
    if (!capturedBlob) return
    const filename = `capture-${Date.now()}.jpg`
    const file = new File([capturedBlob], filename, { type: 'image/jpeg' })
    onCapture(file)
    // parent should close the modal in its onCapture; also do it here defensively
    onClose()
  }

  const handleFlipCamera = () => {
    setFacing(prev => (prev === 'environment' ? 'user' : 'environment'))
  }

  const handleFallback = () => {
    stopStream()
    onFallback?.()
    onClose()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 w-[95vw] max-w-2xl max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Take a photo"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Camera className="h-4 w-4 text-primary-600" />
            <span className="text-sm font-medium text-gray-900 dark:text-white">
              {status === 'captured' ? 'Review Photo' : 'Take Photo'}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
            aria-label="Close camera"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="relative flex-1 bg-black overflow-hidden min-h-[280px]">
          {/* Loading overlay */}
          {status === 'starting' && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60 z-10 text-white text-sm">
              <Loader2 className="h-6 w-6 animate-spin mr-2" /> Starting camera…
            </div>
          )}

          {/* Error state */}
          {status === 'error' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 bg-black/80 text-white text-center">
              <AlertCircle className="h-8 w-8 text-amber-400" />
              <p className="text-sm max-w-md">{errorMsg}</p>
              <div className="flex gap-2 mt-1">
                <Button variant="outline" size="sm" onClick={() => startStream(facing)}>Retry</Button>
                {onFallback && (
                  <Button size="sm" onClick={handleFallback}>Upload from disk</Button>
                )}
              </div>
            </div>
          )}

          {/* Live video (hidden when we're showing the captured still) */}
          <video
            ref={videoRef}
            className={cn(
              'w-full h-full object-contain',
              status === 'captured' && 'hidden',
              // Front cameras mirror by convention; keep back camera un-mirrored.
              facing === 'user' && 'scale-x-[-1]'
            )}
            playsInline
            muted
          />

          {/* Captured still */}
          {status === 'captured' && previewUrl && (
            <img
              src={previewUrl}
              alt="Captured"
              className="w-full h-full object-contain"
            />
          )}

          {/* Hidden canvas for grabbing frames */}
          <canvas ref={canvasRef} className="hidden" />
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-gray-200 dark:border-gray-700">
          {status === 'captured' ? (
            <>
              <Button variant="outline" onClick={handleRetake}>
                <RotateCcw className="h-4 w-4 mr-1" /> Retake
              </Button>
              <Button onClick={handleAccept}>
                <Check className="h-4 w-4 mr-1" /> Use Photo
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <div className="flex items-center gap-2">
                {hasMultipleCameras && status === 'ready' && (
                  <Button variant="outline" size="icon" onClick={handleFlipCamera} title="Switch camera">
                    <SwitchCamera className="h-4 w-4" />
                  </Button>
                )}
                <Button onClick={handleCapture} disabled={status !== 'ready'}>
                  <Camera className="h-4 w-4 mr-1" /> Capture
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
