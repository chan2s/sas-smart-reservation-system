import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import {
  ArrowLeft,
  Building2,
  CalendarDays,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  ScanLine,
  UserRound,
} from 'lucide-react'
import { format } from 'date-fns'
import { useReservation } from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/Badge'
import { Field, Input } from '@/components/ui/Form'
import { Skeleton } from '@/components/ui/Misc'
import { formatTime } from '@/lib/utils'

export function CheckInPage() {
  const { id } = useParams()
  const reservationId = Number(id)
  const { isStaff } = useAuth()
  const { data: reservation, isLoading } = useReservation(reservationId)

  if (isLoading || !reservation) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-96" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Link
        to={`/reservations/${reservation.id}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> Back to reservation
      </Link>

      <div className="mt-4 flex items-center gap-2.5">
        <h1 className="text-[32px] font-semibold tracking-tight text-ink">Check-in</h1>
        <StatusBadge status={reservation.status} />
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        {/* Requester QR card */}
        <Card className="flex flex-col items-center text-center">
          <div className="flex items-center gap-2 text-status-available">
            <CheckCircle2 className="size-4.5" aria-hidden />
            <span className="text-sm font-semibold">Reservation confirmed</span>
          </div>

          <div className="mt-6 rounded-2xl border border-line bg-surface p-6 shadow-card">
            <QRCodeSVG
              value={reservation.checkin_code}
              size={176}
              level="M"
              marginSize={0}
              aria-label={`QR code for reservation ${reservation.reservation_id}`}
            />
          </div>

          <dl className="mt-6 w-full space-y-3 text-left">
            <InfoRow icon={<CalendarDays className="size-4" />} label="Reservation" value={reservation.reservation_id} />
            <InfoRow icon={<Building2 className="size-4" />} label="Facility" value={reservation.facility} />
            <InfoRow
              icon={<CalendarDays className="size-4" />}
              label="Schedule"
              value={`${format(new Date(reservation.date), 'MMM d, yyyy')} · ${formatTime(reservation.start_time)}–${formatTime(reservation.end_time)}`}
            />
            <InfoRow icon={<UserRound className="size-4" />} label="Requester" value={reservation.requester} />
          </dl>

          <p className="mt-6 rounded-lg bg-soft px-4 py-2.5 text-[13px] text-body">
            Show this QR code to SAS staff when you arrive.
          </p>
        </Card>

        {/* Staff scanning interface */}
        <div className="space-y-6">
          {isStaff ? (
            <StaffScanner />
          ) : (
            <Card>
              <CardHeader
                title="For SAS staff"
                description="Staff scan this code to verify the reservation on arrival."
              />
              <p className="mt-3 flex items-center gap-2 text-sm text-muted">
                <ScanLine className="size-4" aria-hidden />
                The code is unique to this reservation.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-soft text-muted">
        {icon}
      </span>
      <div className="min-w-0">
        <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">{label}</dt>
        <dd className="truncate text-sm font-medium text-ink">{value}</dd>
      </div>
    </div>
  )
}

function StaffScanner() {
  const [code, setCode] = useState('')
  const [result, setResult] = useState<number | null>(null)
  const [foundId, setFoundId] = useState('')
  const [error, setError] = useState('')
  const [scanning, setScanning] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const navigate = useNavigate()

  async function startCamera() {
    setError('')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const Detector = (window as any).BarcodeDetector
    if (!Detector) {
      setError('Camera scanning is not supported in this browser — enter the code manually instead.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      })
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setScanning(true)
      const detector = new Detector({ formats: ['qr_code'] })
      const tick = async () => {
        if (!videoRef.current) return
        try {
          const codes = await detector.detect(videoRef.current)
          if (codes.length > 0 && codes[0].rawValue) {
            setCode(codes[0].rawValue)
            stopCamera()
          } else {
            requestAnimationFrame(() => void tick())
          }
        } catch {
          requestAnimationFrame(() => void tick())
        }
      }
      void tick()
    } catch {
      setError('Unable to access the camera. Enter the code manually instead.')
    }
  }

  function stopCamera() {
    setScanning(false)
    const stream = videoRef.current?.srcObject as MediaStream | null
    stream?.getTracks().forEach((track) => track.stop())
    if (videoRef.current) videoRef.current.srcObject = null
  }

  function lookup(codeToLookup: string) {
    const trimmed = codeToLookup.trim()
    if (!trimmed) return
    setResult(null)
    setError('')
    // The QR value is a UUID; keep the page simple by routing through the API.
    fetch(`/api/reservations/checkin/${trimmed}/`)
      .then((response) => {
        if (!response.ok) throw new Error('Reservation not found')
        return response.json() as Promise<{ id: number; reservation_id: string }>
      })
      .then((data) => {
        setResult(data.id)
        setFoundId(data.reservation_id)
      })
      .catch(() => setError('No reservation found for this code.'))
  }

  return (
    <Card>
      <CardHeader
        title="Scan QR code"
        description="Point the camera at the requester's QR code or enter it manually."
      />

      <div className="mt-5 space-y-4">
        {scanning && (
          <div className="relative overflow-hidden rounded-xl border border-line bg-ink">
            <video ref={videoRef} muted playsInline className="aspect-video w-full object-cover" />
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <div className="size-40 rounded-xl border-2 border-white/80" aria-hidden />
            </div>
          </div>
        )}

        <Button variant="outline" onClick={scanning ? stopCamera : startCamera} icon={<Camera className="size-4" />}>
          {scanning ? 'Stop camera' : 'Open camera'}
        </Button>

        <div className="flex gap-2.5">
          <Field label="QR code value" htmlFor="qr-code" className="flex-1">
            <Input
              id="qr-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="Paste or scan the code…"
              onKeyDown={(event) => event.key === 'Enter' && lookup(code)}
            />
          </Field>
          <div className="flex items-end">
            <Button onClick={() => lookup(code)} icon={<ScanLine className="size-4" />}>
              Verify
            </Button>
          </div>
        </div>

        {error && <p className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected">{error}</p>}

        {result && (
          <div className="rounded-xl border border-status-available/25 bg-status-available-bg p-4">
            <p className="flex items-center gap-2 text-sm font-semibold text-status-available">
              <CheckCircle2 className="size-4" /> Reservation verified
            </p>
            <Button
              size="sm"
              className="mt-3"
              icon={<ClipboardCheck className="size-4" />}
              onClick={() => navigate(`/reservations/${result}`)}
            >
              Open {foundId}
            </Button>
          </div>
        )}
      </div>
    </Card>
  )
}