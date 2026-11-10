import { useEffect, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, CalendarDays, Check, CircleAlert, MapPin, Search, ShieldCheck, Upload } from 'lucide-react'
import { format } from 'date-fns'
import { endpoints, type PublicReservationTracking } from '@/lib/api'
import type { ReservationStatus } from '@/lib/types'
import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Field, Input } from '@/components/ui/Form'
import { Spinner } from '@/components/ui/Misc'
import { BrandMark } from '@/components/auth/AuthPanel'
import { ApprovalLetterCapture } from '@/components/reservations/ApprovalLetterCapture'

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

  return (
    <div className="min-h-dvh bg-soft">
      <header className="sticky top-0 z-30">
        <div className="mx-auto max-w-[1400px] px-3 pt-3 sm:px-6 sm:pt-4">
        <div className="flex min-h-[64px] w-full flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-2xl border border-[var(--nav-scrolled-border)] bg-[var(--nav-scrolled-background)] px-4 py-2 shadow-float backdrop-blur-lg sm:min-h-[72px] sm:flex-nowrap sm:px-6 sm:py-0">
          <Link to="/" aria-label="SAS Reserve home" className="rounded-lg focus-ring">
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
                  placeholder="SAS-2026-00024"
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

        {trackQuery.data && <TrackingResult reservation={trackQuery.data} />}
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

function TrackingResult({ reservation }: { reservation: PublicReservationTracking }) {
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
              the SAS Office and provide your reservation reference.
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
              ? 'The SAS Office has not made a decision yet. You will receive an email when the status changes.'
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
          Sign in to SAS Reserve
        </Link>
      </div>
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
