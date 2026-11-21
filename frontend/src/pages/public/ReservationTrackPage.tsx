import { useEffect, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, CalendarDays, Check, CircleAlert, MapPin, Search, ShieldCheck, Upload } from 'lucide-react'
import { format } from 'date-fns'
import {
  endpoints,
  type PublicRescheduleRequest,
  type PublicReservationTracking,
  type RescheduleRequestPayload,
} from '@/lib/api'
import type { ReservationStatus } from '@/lib/types'
import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Field, Input, Textarea } from '@/components/ui/Form'
import { Spinner } from '@/components/ui/Misc'
import { BrandMark } from '@/components/auth/AuthPanel'
import { ApprovalLetterCapture } from '@/components/reservations/ApprovalLetterCapture'
import { draftForPublicReservationEdit, saveDraft } from '@/lib/reservationDraft'

/**
 * Public status view for a guest reservation request.
 *
 * Public guest reservation status is available with a reservation ID.
 * Legacy signed links are still supported.
 * The page deliberately reuses the application's own design tokens and
 * components — it is not a second portal. It exposes only the minimal status
 * payload returned by the public tracking endpoint.
 */
export function ReservationTrackPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const urlToken = searchParams.get('token') ?? ''
  const urlReference = searchParams.get('reservation_id') ?? ''
  const [reservationInput, setReservationInput] = useState(urlReference)
  const [trackingArgs, setTrackingArgs] = useState<{ token?: string; id?: string } | null>(null)
  const [approvalFile, setApprovalFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const [startingEdit, setStartingEdit] = useState(false)
  const [editError, setEditError] = useState('')
  const [rescheduleOpen, setRescheduleOpen] = useState(false)
  const [reschedulePayload, setReschedulePayload] = useState<RescheduleRequestPayload | null>(null)
  const [rescheduleSession, setRescheduleSession] = useState('')
  const [rescheduleOtp, setRescheduleOtp] = useState('')
  const [rescheduleError, setRescheduleError] = useState('')
  const [rescheduleNotice, setRescheduleNotice] = useState('')
  const [sendingReschedule, setSendingReschedule] = useState(false)
  const [verifyingReschedule, setVerifyingReschedule] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  useEffect(() => {
    if (urlToken) {
      setTrackingArgs({ token: urlToken })
    }
  }, [urlToken])

  useEffect(() => {
    if (urlReference) setReservationInput(urlReference)
  }, [urlReference])

  const queryKey = ['reservation-tracking', trackingArgs] as const
  const trackQuery = useQuery({
    queryKey,
    queryFn: () => trackingArgs?.token
      ? endpoints.trackPublicReservation(trackingArgs.token)
      : endpoints.trackReservationById(trackingArgs?.id ?? ''),
    enabled: Boolean(trackingArgs?.token || trackingArgs?.id),
    retry: false,
    staleTime: 0,
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const id = reservationInput.trim().toUpperCase()
    if (!id) return
    setSearchParams({ reservation_id: id }, { replace: true })
    setTrackingArgs({ id })
  }

  async function uploadApprovalLetter() {
    const id = trackingArgs?.id ?? trackQuery.data?.reservation_id
    if (!approvalFile || !id) return
    setUploading(true)
    setUploadError('')
    try {
      const result = await endpoints.uploadPublicApprovalLetter(id, approvalFile)
      queryClient.setQueryData(queryKey, result)
      setApprovalFile(null)
      setUploadSuccess(true)
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'The document could not be uploaded. Try again.')
    } finally {
      setUploading(false)
    }
  }

  async function submitRescheduleRequest(
    reservation: PublicReservationTracking,
    payload: RescheduleRequestPayload,
  ) {
    setSendingReschedule(true)
    setRescheduleError('')
    setRescheduleNotice('')
    try {
      const response = await endpoints.requestPublicRescheduleOTP(
        reservation.reservation_id,
        payload,
      )
      setReschedulePayload(payload)
      setRescheduleSession(response.verification_session ?? '')
      setRescheduleOtp('')
      setRescheduleNotice(
        `A verification code was sent to the email address on file${response.email_hint ? ` (${response.email_hint})` : ''}. It expires in 5 minutes.`,
      )
    } catch (error) {
      setRescheduleError(
        error instanceof Error ? error.message : 'The reschedule request could not be submitted.',
      )
    } finally {
      setSendingReschedule(false)
    }
  }

  async function verifyRescheduleOtp(reservation: PublicReservationTracking) {
    if (!rescheduleSession) return
    setVerifyingReschedule(true)
    setRescheduleError('')
    try {
      const result = await endpoints.verifyPublicRescheduleOTP(
        reservation.reservation_id,
        rescheduleSession,
        rescheduleOtp,
      )
      queryClient.setQueryData(queryKey, result)
      setRescheduleSession('')
      setReschedulePayload(null)
      setRescheduleOtp('')
      setRescheduleOpen(false)
      setRescheduleNotice(
        'Your reschedule request was verified and submitted. An administrator will review it. Approval is not guaranteed.',
      )
    } catch (error) {
      setRescheduleError(
        error instanceof Error ? error.message : 'The verification code could not be validated.',
      )
    } finally {
      setVerifyingReschedule(false)
    }
  }

  async function startEdit(reservation: PublicReservationTracking) {
    if (!reservation.can_edit || startingEdit) return
    setStartingEdit(true)
    setEditError('')
    try {
      const details = await endpoints.publicReservationEditDetails(reservation.reservation_id)
      saveDraft(draftForPublicReservationEdit(details), true)
      const organizationType = details.requester_type === 'EXTERNAL' ? 'external' : 'internal'
      navigate(`/reserve/${organizationType}?publicEdit=${encodeURIComponent(reservation.reservation_id)}`)
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'This reservation cannot be edited right now.')
    } finally {
      setStartingEdit(false)
    }
  }

  return (
    <div className="min-h-dvh bg-soft">
      <header className="sticky top-0 z-30">
        <div className="mx-auto max-w-[1400px] px-3 pt-3 sm:px-6 sm:pt-4">
        <div className="flex min-h-[64px] w-full flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-2xl border border-[var(--nav-scrolled-border)] bg-[var(--nav-scrolled-background)] px-4 py-2 shadow-float backdrop-blur-lg sm:min-h-[72px] sm:flex-nowrap sm:px-6 sm:py-0">
          <Link to="/" aria-label="GSO Reserve home" className="rounded-lg focus-ring">
            <BrandMark onDark />
          </Link>
          <div className="flex w-full flex-wrap items-center justify-end gap-1 sm:w-auto sm:flex-nowrap sm:gap-2">
            <Link
              to="/login"
              className="inline-flex whitespace-nowrap rounded-xl px-2.5 py-2 text-xs font-medium text-white/75 transition-colors hover:bg-white/10 hover:text-white sm:px-3.5 sm:text-sm"
            >
              Staff/Admin Login
            </Link>
            <Link
              to="/reserve"
              className="inline-flex h-9 items-center gap-1.5 rounded-full bg-[var(--nav-button-background)] px-3 text-xs font-semibold text-[var(--nav-button-foreground)] shadow-sm transition-colors hover:bg-brand-dark sm:h-10 sm:px-4 sm:text-sm"
            >
              Create Reservation
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
        </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl px-4 py-10 sm:px-6 sm:py-14">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand">
          Request status
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          Track a reservation request
        </h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-body">
          Enter your reservation ID to check the current status of your reservation request.
        </p>

        {!trackQuery.data && (
          <Card className="mt-7">
            <form onSubmit={submit}>
              <Field
                label="Reservation ID"
                htmlFor="reservation-id"
              >
                <Input
                  id="reservation-id"
                  value={reservationInput}
                  onChange={(event) => setReservationInput(event.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  required
                  placeholder="GSO-2026-00024"
                  className="font-mono text-sm"
                />
              </Field>
              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  type="submit"
                  loading={trackQuery.isFetching}
                  disabled={!reservationInput.trim()}
                  icon={<Search className="size-4" aria-hidden />}
                >
                  Track Reservation
                </Button>
                <Link
                  to="/login"
                  className="text-sm font-medium text-brand transition-colors hover:text-brand-dark"
                >
                  Have an account? View your reservations
                </Link>
              </div>
              {trackQuery.isError && (
                <p role="alert" className="mt-4 flex items-start gap-2 text-sm text-status-rejected">
                  <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                  We couldn&apos;t find a reservation with that ID. Check the reservation ID and try again.
                </p>
              )}
            </form>
          </Card>
        )}

        {trackQuery.isLoading && trackingArgs && (
          <Card className="mt-7 flex items-center gap-3">
            <Spinner />
            <p className="text-sm text-body" role="status">
              Checking reservation status…
            </p>
          </Card>
        )}

        {trackQuery.data && (
          <TrackingResult
            reservation={trackQuery.data}
            onEdit={() => void startEdit(trackQuery.data!)}
            editing={startingEdit}
            onRequestReschedule={() => {
              setRescheduleError('')
              setRescheduleNotice('')
              setRescheduleSession('')
              setReschedulePayload(null)
              setRescheduleOpen(true)
            }}
          />
        )}
        {editError && <p role="alert" className="mt-3 text-sm text-status-rejected">{editError}</p>}
        {rescheduleNotice && (
          <p role="status" className="mt-4 rounded-lg border border-status-available/25 bg-status-available-bg p-3 text-sm text-status-available">
            {rescheduleNotice}
          </p>
        )}
        {trackQuery.data?.reschedule?.request && (
          <RescheduleStatusCard request={trackQuery.data.reschedule.request} />
        )}
        {trackQuery.data && rescheduleOpen && (
          <RescheduleForm
            reservation={trackQuery.data}
            sessionActive={Boolean(rescheduleSession)}
            otp={rescheduleOtp}
            onOtpChange={setRescheduleOtp}
            error={rescheduleError}
            sending={sendingReschedule}
            verifying={verifyingReschedule}
            onSubmit={(payload) => void submitRescheduleRequest(trackQuery.data!, payload)}
            onVerify={() => void verifyRescheduleOtp(trackQuery.data!)}
            onResend={() => {
              if (reschedulePayload) {
                void submitRescheduleRequest(trackQuery.data!, reschedulePayload)
              }
            }}
            onCancel={() => {
              setRescheduleOpen(false)
              setRescheduleError('')
              setRescheduleSession('')
              setReschedulePayload(null)
            }}
          />
        )}
        {uploadSuccess && (
          <p role="status" className="mt-4 rounded-lg border border-status-available/25 bg-status-available-bg p-3 text-sm text-status-available">
            Event approval letter uploaded successfully.
          </p>
        )}

        {trackQuery.data && trackQuery.data.status === 'PENDING' &&
          trackQuery.data.approval_document_status === 'AWAITING' && (
            <Card className="mt-5">
              <h2 className="text-base font-semibold text-ink">Event Approval Letter</h2>
              <p className="mt-1 text-sm leading-6 text-body">
                This document is required before your reservation can be approved. Take a photo of your signed event approval letter or upload an image file.
              </p>
              <div className="mt-4">
                <ApprovalLetterCapture
                  inputId="later-approval-letter"
                  file={approvalFile}
                  onFileChange={(file) => {
                    setApprovalFile(file)
                    setUploadError('')
                  }}
                  onError={setUploadError}
                />
              </div>
              {uploadError && <p role="alert" className="mt-3 text-sm text-status-rejected">{uploadError}</p>}
              {uploading && <p className="mt-3 text-sm text-body" role="status">Uploading your approval letter…</p>}
              <Button
                className="mt-4"
                disabled={!approvalFile || uploading}
                loading={uploading}
                icon={<Upload className="size-4" aria-hidden />}
                onClick={() => void uploadApprovalLetter()}
              >
                Submit approval letter
              </Button>
            </Card>
          )}

        <div className="mt-6 flex gap-3 rounded-xl border border-line bg-surface p-4">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />
          <p className="text-xs leading-5 text-body">
            A matching reservation ID is required before status is shown. This view omits contact details, internal notes, and documents.
          </p>
        </div>
      </main>
    </div>
  )
}

function TrackingResult({
  reservation,
  onEdit,
  editing,
  onRequestReschedule,
}: {
  reservation: PublicReservationTracking
  onEdit: () => void
  editing: boolean
  onRequestReschedule: () => void
}) {
  const terminal = ['REJECTED', 'CANCELLED', 'EXPIRED', 'NO_SHOW', 'COMPLETED'].includes(
    reservation.status,
  )
  const rejected = ['REJECTED', 'CANCELLED', 'EXPIRED', 'NO_SHOW'].includes(reservation.status)
  const stages = [
    { label: 'Submitted', complete: true },
    { label: 'Under review', complete: reservation.status !== 'PENDING' },
    {
      label: 'Decision made',
      complete: [
        'APPROVED',
        'ACTIVE',
        'COMPLETED',
        'REJECTED',
        'CANCELLED',
        'EXPIRED',
        'NO_SHOW',
      ].includes(reservation.status),
    },
  ]

  return (
    <Card className="mt-7" padding="none">
      <div className="flex flex-col gap-3 border-b border-line p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">
            Reservation reference
          </p>
          <h2 className="mt-1 font-mono text-xl font-bold tracking-wide text-ink">
            {reservation.reservation_id}
          </h2>
        </div>
        <StatusBadge status={reservation.status as ReservationStatus} className="self-start" />
      </div>

      <div className="p-5 sm:p-6">
        <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
          <TrackingDetail label="Organization" value={reservation.organization} />
          <TrackingDetail label="Event" value={reservation.event_name} />
          <TrackingDetail
            label="Facility"
            value={reservation.facility}
            icon={<MapPin className="size-4" aria-hidden />}
          />
          <TrackingDetail
            label="Reservation date"
            value={format(new Date(`${reservation.date}T12:00:00`), 'MMMM d, yyyy')}
            icon={<CalendarDays className="size-4" aria-hidden />}
          />
          <TrackingDetail
            label="Time"
            value={`${reservation.start_time}–${reservation.end_time}`}
          />
          <TrackingDetail label="Approval letter" value={reservation.approval_document_status_label} />
        </dl>

        <div className="mt-7 rounded-xl border border-line p-4 sm:p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-muted">
            Request progress
          </p>
          {terminal && rejected ? (
            <p className="mt-4 rounded-lg bg-status-rejected-bg p-3.5 text-sm text-status-rejected">
              This request is {reservation.status_label.toLowerCase()}. For follow-up, contact
              the GSO Office and provide your reservation reference.
            </p>
          ) : (
            <ol className="mt-5 grid gap-4 sm:grid-cols-3">
              {stages.map((stage, index) => (
                <li key={stage.label} className="flex items-start gap-3 sm:flex-col sm:gap-2">
                  <span
                    className={
                      'flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ' +
                      (stage.complete
                        ? 'bg-status-available text-white'
                        : 'bg-soft text-muted')
                    }
                  >
                    {stage.complete ? (
                      <Check className="size-4" aria-hidden />
                    ) : (
                      index + 1
                    )}
                  </span>
                  <span
                    className={
                      'pt-1 text-sm font-medium sm:pt-0 ' +
                      (stage.complete ? 'text-ink' : 'text-muted')
                    }
                  >
                    {stage.label}
                  </span>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-4 text-xs leading-5 text-body">
            {reservation.status === 'PENDING'
              ? 'The GSO Office has not made a decision yet. You will receive an email when the status changes.'
              : reservation.status === 'APPROVED' || reservation.status === 'ACTIVE'
                ? 'The reservation has been approved. Review the approval email for any next steps.'
                : terminal && !rejected
                  ? 'This reservation has been completed.'
                  : `Latest status: ${reservation.status_label}.`}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t border-line p-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="text-xs text-muted">
          Share your Reservation ID only with the reservation contact.
        </p>
        <Link
          to="/login"
          className="inline-flex h-8 items-center justify-center rounded-lg border border-line bg-surface px-3 text-[13px] font-medium text-ink transition-colors hover:border-line-strong hover:bg-soft"
        >
          Sign in to GSO Reserve
        </Link>
        {reservation.can_edit && (
          <Button variant="outline" loading={editing} onClick={onEdit}>
            Edit Reservation
          </Button>
        )}
        {reservation.reschedule?.can_request && (
          <Button variant="outline" onClick={onRequestReschedule}>
            Request Reschedule
          </Button>
        )}
      </div>
    </Card>
  )
}

function scheduleLabel(
  date: string,
  start: string,
  end: string,
) {
  return `${format(new Date(`${date}T12:00:00`), 'MMMM d, yyyy')} · ${start}–${end}`
}

function RescheduleStatusCard({ request }: { request: PublicRescheduleRequest }) {
  return (
    <Card className="mt-5" padding="none">
      <div className="flex flex-col gap-2 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-muted">Reschedule request</p>
          <p className="mt-1 text-sm font-semibold text-ink">{request.status_label}</p>
        </div>
        <span className="text-xs text-muted">
          Submitted {format(new Date(request.submitted_at), 'MMMM d, yyyy')}
        </span>
      </div>
      <div className="p-5">
        <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
          <TrackingDetail
            label="Requested date and time"
            value={scheduleLabel(
              request.requested_date,
              request.requested_start_time,
              request.requested_end_time,
            )}
          />
          <TrackingDetail label="Your reason" value={request.reason} />
        </dl>
        {request.status === 'PENDING' && (
          <p className="mt-4 rounded-lg bg-soft p-3 text-sm text-body">
            This request is awaiting administrator review. Your current reservation remains
            unchanged until it is approved.
          </p>
        )}
        {request.status === 'REJECTED' && request.rejection_reason && (
          <p className="mt-4 rounded-lg bg-status-rejected-bg p-3.5 text-sm text-status-rejected">
            Rejected: {request.rejection_reason}
          </p>
        )}
        {request.status === 'INFO_REQUIRED' && request.admin_message && (
          <p className="mt-4 rounded-lg border border-line bg-soft p-3.5 text-sm text-body">
            GSO staff need more information: {request.admin_message}
          </p>
        )}
        {request.status === 'APPROVED' && (
          <p className="mt-4 rounded-lg border border-status-available/25 bg-status-available-bg p-3.5 text-sm text-status-available">
            Approved and rescheduled. The updated date and time are shown above.
          </p>
        )}
      </div>
    </Card>
  )
}

function RescheduleForm({
  reservation,
  sessionActive,
  otp,
  onOtpChange,
  error,
  sending,
  verifying,
  onSubmit,
  onVerify,
  onResend,
  onCancel,
}: {
  reservation: PublicReservationTracking
  sessionActive: boolean
  otp: string
  onOtpChange: (value: string) => void
  error: string
  sending: boolean
  verifying: boolean
  onSubmit: (payload: RescheduleRequestPayload) => void
  onVerify: () => void
  onResend: () => void
  onCancel: () => void
}) {
  const [date, setDate] = useState(reservation.date)
  const [start, setStart] = useState(reservation.start_time.slice(0, 5))
  const [end, setEnd] = useState(reservation.end_time.slice(0, 5))
  const [reason, setReason] = useState('')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit({
      requested_date: date,
      requested_start_time: start,
      requested_end_time: end,
      reason: reason.trim(),
    })
  }

  return (
    <Card className="mt-5">
      <h2 className="text-base font-semibold text-ink">Request a reschedule</h2>
      <p className="mt-1 text-sm leading-6 text-body">
        State the date and time you want and why. Submitting a request does not change
        your reservation and does not guarantee approval — GSO staff review every request
        and perform the actual reschedule.
      </p>

      <div className="mt-5 rounded-xl border border-line bg-soft p-4">
        <p className="text-xs font-bold uppercase tracking-wide text-muted">Current schedule</p>
        <p className="mt-1 text-sm font-medium text-ink">
          {scheduleLabel(reservation.date, reservation.start_time, reservation.end_time)}
        </p>
      </div>

      {!sessionActive ? (
        <form className="mt-5" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Requested new date" htmlFor="reschedule-date">
              <Input
                id="reschedule-date"
                type="date"
                value={date}
                min={new Date().toISOString().slice(0, 10)}
                onChange={(event) => setDate(event.target.value)}
                required
              />
            </Field>
            <Field label="Requested start time" htmlFor="reschedule-start">
              <Input
                id="reschedule-start"
                type="time"
                value={start}
                min="08:00"
                onChange={(event) => setStart(event.target.value)}
                required
              />
            </Field>
            <Field label="Requested end time" htmlFor="reschedule-end">
              <Input
                id="reschedule-end"
                type="time"
                value={end}
                onChange={(event) => setEnd(event.target.value)}
                required
              />
            </Field>
          </div>
          <div className="mt-4">
            <Field label="Reason for the request" htmlFor="reschedule-reason">
              <Textarea
                id="reschedule-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
                maxLength={2000}
                placeholder="Explain why you need a different date or time."
                required
              />
            </Field>
          </div>
          {error && (
            <p role="alert" className="mt-3 text-sm text-status-rejected">
              {error}
            </p>
          )}
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <Button type="submit" loading={sending} disabled={!reason.trim()}>
              Submit request and send code
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel} disabled={sending}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <form
          className="mt-5"
          onSubmit={(event) => {
            event.preventDefault()
            onVerify()
          }}
        >
          <Field label="Email verification code" htmlFor="reschedule-otp">
            <Input
              id="reschedule-otp"
              value={otp}
              onChange={(event) => onOtpChange(event.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="000000"
              maxLength={6}
              required
              className="font-mono tracking-[0.3em]"
            />
          </Field>
          <p className="mt-2 text-xs leading-5 text-body">
            Enter the six-digit code sent to the email address on file. For security, the
            address and code are validated by the server and the code cannot be reused.
          </p>
          {error && (
            <p role="alert" className="mt-3 text-sm text-status-rejected">
              {error}
            </p>
          )}
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <Button type="submit" loading={verifying} disabled={otp.length !== 6}>
              Verify and submit request
            </Button>
            <Button
              type="button"
              variant="ghost"
              loading={sending}
              disabled={sending}
              onClick={onResend}
            >
              Send a new code
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Card>
  )
}

function TrackingDetail({
  label,
  value,
  icon,
}: {
  label: string
  value: string
  icon?: React.ReactNode
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted">{label}</dt>
      <dd className="mt-1 flex items-center gap-2 break-words text-sm font-medium text-ink">
        {icon && <span className="shrink-0 text-brand">{icon}</span>}
        {value}
      </dd>
    </div>
  )
}
