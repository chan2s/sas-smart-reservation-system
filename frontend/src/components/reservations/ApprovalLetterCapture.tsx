import { useEffect, useRef, useState } from 'react'
import { Camera, RotateCcw, SwitchCamera, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'

const MAX_FILE_BYTES = 5 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']

type Props = {
  inputId?: string
  file: File | null
  onFileChange: (file: File | null) => void
  onError: (message: string) => void
}

function validateFile(file: File): string | null {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(extension ?? '')) {
    return 'Choose a JPG, JPEG, PNG, or WEBP image.'
  }
  if (file.size > MAX_FILE_BYTES) return 'The image must be 5 MB or smaller.'
  return null
}

function cameraErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'Camera access was denied. Allow camera access in your browser settings, or upload an image file instead.'
  }
  if (error instanceof DOMException && ['NotFoundError', 'DevicesNotFoundError'].includes(error.name)) {
    return 'No camera is available on this device. Upload an image file instead.'
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return 'Camera capture is unavailable in this browser or page. Use a secure HTTPS connection or upload an image file instead.'
  }
  return 'The camera could not be started. Check that it is connected and not being used by another app, or upload an image file instead.'
}

export function ApprovalLetterCapture({ inputId = 'approval-letter-image-upload', file, onFileChange, onError }: Props) {
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [cameraError, setCameraError] = useState('')
  const [cameraIds, setCameraIds] = useState<string[]>([])
  const [cameraIndex, setCameraIndex] = useState(0)
  const [capturedFile, setCapturedFile] = useState<File | null>(null)
  const [capturedUrl, setCapturedUrl] = useState('')
  const [selectedPreviewUrl, setSelectedPreviewUrl] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const cameraSessionRef = useRef(false)
  const capturedUrlRef = useRef('')

  useEffect(() => {
    if (!file) {
      setSelectedPreviewUrl('')
      return
    }
    const url = URL.createObjectURL(file)
    setSelectedPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  useEffect(() => {
    if (!cameraOpen || capturedFile) return
    let cancelled = false

    async function startCamera() {
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error('Camera API unavailable')
        }
        const selectedId = cameraIds[cameraIndex]
        const constraints: MediaStreamConstraints = {
          audio: false,
          video: selectedId
            ? { deviceId: { exact: selectedId }, width: { ideal: 2560 }, height: { ideal: 1440 } }
            : { facingMode: { ideal: 'environment' }, width: { ideal: 2560 }, height: { ideal: 1440 } },
        }
        const stream = await navigator.mediaDevices.getUserMedia(constraints)
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play().catch(() => undefined)
        }
        if (!cancelled) setCameraReady(true)
        const devices = await navigator.mediaDevices.enumerateDevices().catch(() => [])
        if (!cancelled) {
          const ids = devices.filter((device) => device.kind === 'videoinput').map((device) => device.deviceId)
          setCameraIds((current) => current.length === ids.length && current.every((id, index) => id === ids[index]) ? current : ids)
          if (selectedId) {
            const selectedIndex = ids.indexOf(selectedId)
            if (selectedIndex >= 0 && selectedIndex !== cameraIndex) setCameraIndex(selectedIndex)
          }
        }
      } catch (error) {
        if (!cancelled) setCameraError(cameraErrorMessage(error))
      }
    }

    setCameraError('')
    void startCamera()
    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }, [cameraOpen, cameraIndex, capturedFile])

  useEffect(() => () => {
    cameraSessionRef.current = false
    if (capturedUrlRef.current) URL.revokeObjectURL(capturedUrlRef.current)
    streamRef.current?.getTracks().forEach((track) => track.stop())
  }, [])

  function clearCapture() {
    if (capturedUrlRef.current) URL.revokeObjectURL(capturedUrlRef.current)
    capturedUrlRef.current = ''
    setCapturedUrl('')
    setCapturedFile(null)
    setCameraReady(false)
  }

  function closeCamera() {
    cameraSessionRef.current = false
    clearCapture()
    setCameraOpen(false)
  }

  function capturePhoto() {
    const video = videoRef.current
    if (!video || !video.videoWidth || !video.videoHeight) {
      setCameraError('The camera preview is not ready yet. Please wait a moment and try again.')
      return
    }
    const canvas = document.createElement('canvas')
    const scale = Math.min(1, 2800 / Math.max(video.videoWidth, video.videoHeight))
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    const context = canvas.getContext('2d')
    if (!context) {
      setCameraError('This browser could not prepare the photo. Please try another browser or upload an image file.')
      return
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setCameraReady(false)
    const encode = (quality: number) => new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, 'image/jpeg', quality)
    })
    void (async () => {
      let blob = await encode(0.88)
      if (blob && blob.size > MAX_FILE_BYTES) blob = await encode(0.72)
      if (blob && blob.size > MAX_FILE_BYTES) blob = await encode(0.58)
      if (!cameraSessionRef.current) return
      if (!blob) {
        setCameraError('The photo could not be captured. Please try again.')
        return
      }
      const photo = new File([blob], `approval-letter-${Date.now()}.jpg`, { type: 'image/jpeg' })
      const issue = validateFile(photo)
      if (issue) {
        setCameraError(issue)
        return
      }
      const url = URL.createObjectURL(blob)
      capturedUrlRef.current = url
      setCapturedUrl(url)
      setCapturedFile(photo)
      setCameraError('')
    })()
  }

  function usePhoto() {
    if (!capturedFile) return
    onFileChange(capturedFile)
    clearCapture()
    setCameraOpen(false)
  }

  function chooseFile(file: File | null) {
    if (!file) return
    const issue = validateFile(file)
    if (issue) {
      onFileChange(null)
      onError(issue)
      return
    }
    onFileChange(file)
    onError('')
  }

  return (
    <>
      <div className="space-y-3">
        <p className="text-sm leading-relaxed text-body">Add a clear photo or upload a scanned image of the signed event approval letter.</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            type="button"
            variant="outline"
            className="w-full sm:w-auto"
            icon={<Camera className="size-4" aria-hidden />}
            onClick={() => {
              clearCapture()
              cameraSessionRef.current = true
              setCameraReady(false)
              setCameraOpen(true)
            }}
          >
            Take Photo
          </Button>
          <label className="inline-flex min-h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-ink transition-colors hover:bg-slate-50 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand sm:w-auto">
            <Upload className="size-4" aria-hidden />
            Upload File
            <input
              id={inputId}
              className="sr-only"
              type="file"
              accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
              aria-label="Upload approval letter image"
              onChange={(event) => {
                chooseFile(event.target.files?.[0] ?? null)
                event.target.value = ''
              }}
            />
          </label>
        </div>
        <p className="text-xs text-muted">JPG, JPEG, PNG, or WEBP; maximum 5 MB.</p>
        {file && (
          <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:flex-row sm:items-center">
            {selectedPreviewUrl && (
              <img
                src={selectedPreviewUrl}
                alt="Selected event approval letter preview"
                className="max-h-48 w-full rounded-lg bg-white object-contain sm:w-40"
              />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink" role="status">Selected file</p>
              <p className="mt-0.5 break-all text-xs text-body">{file.name}</p>
            </div>
            <Button
              type="button"
              variant="outline"
              className="w-full shrink-0 sm:w-auto"
              onClick={() => {
                onFileChange(null)
                onError('')
              }}
            >
              Remove file
            </Button>
          </div>
        )}
      </div>

      {cameraOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/75 p-3 sm:p-6" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeCamera()
        }}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="approval-camera-title"
            className="my-auto w-full max-w-2xl rounded-xl bg-white p-4 shadow-xl sm:p-6"
            onKeyDown={(event) => {
              if (event.key === 'Escape') closeCamera()
            }}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="approval-camera-title" className="text-lg font-semibold text-ink">Take a photo</h2>
                <p className="mt-1 text-sm text-body">Place the full signed page in view with good lighting.</p>
              </div>
              <Button type="button" variant="ghost" size="sm" aria-label="Close camera" onClick={closeCamera}>
                <X className="size-4" aria-hidden />
              </Button>
            </div>

            <div className="mt-4 overflow-hidden rounded-xl bg-black">
              {capturedUrl ? (
                <img src={capturedUrl} alt="Captured approval letter preview" className="mx-auto max-h-[60dvh] w-full object-contain" />
              ) : (
                <video ref={videoRef} autoPlay playsInline muted className="mx-auto max-h-[60dvh] min-h-52 w-full object-contain" />
              )}
            </div>
            {cameraError && <p role="alert" className="mt-3 text-sm text-status-rejected">{cameraError}</p>}

            <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              {capturedFile ? (
                <>
                  <Button type="button" variant="outline" onClick={clearCapture} icon={<RotateCcw className="size-4" aria-hidden />}>Retake</Button>
                  <Button type="button" onClick={usePhoto}>Use Photo</Button>
                </>
              ) : (
                <>
                  {cameraIds.length > 1 && (
                    <Button
                      type="button"
                      variant="outline"
                      className="sm:mr-auto"
                      icon={<SwitchCamera className="size-4" aria-hidden />}
                      onClick={() => {
                        setCameraReady(false)
                        setCameraIndex((index) => (index + 1) % cameraIds.length)
                      }}
                    >
                      Switch Camera
                    </Button>
                  )}
                  <Button type="button" variant="outline" onClick={closeCamera}>Cancel</Button>
                  <Button type="button" disabled={!cameraReady || !streamRef.current || Boolean(cameraError)} onClick={capturePhoto} icon={<Camera className="size-4" aria-hidden />}>Capture</Button>
                </>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  )
}
