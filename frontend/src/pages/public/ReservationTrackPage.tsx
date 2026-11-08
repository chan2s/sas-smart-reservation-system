import { useEffect, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, CalendarDays, Check, CircleAlert, KeyRound, MapPin, Search, ShieldCheck } from 'lucide-react'
import { format } from 'date-fns'
import { endpoints, type PublicReservationTracking } from '@/lib/api'
import type { ReservationStatus } from '@/lib/types'
import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Field, Input } from '@/components/ui/Form'
import { Spinner } from '@/components/ui/Misc'
import { BrandMark } from '@/components/auth/AuthPanel'

/**
 * Public status view for a guest reservation request.
 *
 * Guest submissions have been retired in favour of the shared authenticated
 * reservation workflow, but links emailed before that change must keep working.
 * The page deliberately reuses the application's own design tokens and
 * components — it is not a second portal. It exposes only the minimal status
 * payload returned by the token-protected endpoint.
 */
export function ReservationTrackPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const urlToken = searchParams.get('token') ?? ''
  const [tokenInput, setTokenInput] = useState(urlToken)
  const [activeToken, setActiveToken] = useState(urlToken)

  useEffect(() => {
    if (urlToken) {
      setTokenInput(urlToken)
      setActiveToken(urlToken)
    }
  }, [urlToken])

  const trackQuery = useQuery({
    queryKey: ['reservation-tracking', activeToken],
    queryFn: () => endpoints.trackPublicReservation(activeToken),
    enabled: Boolean(activeToken),
    retry: false,
    staleTime: 0,
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const token = tokenInput.trim()
    if (!token) return
    setSearchParams({ token }, { replace: true })
    setActiveToken(token)
  }

  return (
    <div className="min-h-dvh bg-soft">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex min-h-[72px] w-full max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" aria-label="SAS Reserve home">
            <BrandMark />
          </Link>
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="text-sm font-medium text-body transition-colors hover:text-ink"
            >
              Staff/Admin Login
            </Link>
            <Link
              to="/reserve"
              className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-dark"
            >
              Create Reservation
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
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
          Use the private tracking link sent to your representative email.
          Reservation references alone cannot open a request.
        </p>

        {!trackQuery.data && (
          <Card className="mt-7">
            <form onSubmit={submit}>
              <Field
                label="Private tracking token"
                htmlFor="tracking-token"
                hint="If you followed the email link, this check runs automatically. Otherwise, paste the token from that link."
              >
                <div className="relative">
                  <KeyRound
                    className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted"
                    aria-hidden
                  />
                  <Input
                    id="tracking-token"
                    value={tokenInput}
                    onChange={(event) => setTokenInput(event.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    required
                    placeholder="Paste private token"
                    className="pl-10 font-mono text-sm"
                  />
                </div>
              </Field>
              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  type="submit"
                  loading={trackQuery.isFetching}
                  disabled={!tokenInput.trim()}
                  icon={<Search className="size-4" aria-hidden />}
                >
                  View status
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
                  That tracking link could not be verified. Check that you copied the complete
                  token from the email.
                </p>
              )}
            </form>
          </Card>
        )}

        {trackQuery.isLoading && activeToken && (
          <Card className="mt-7 flex items-center gap-3">
            <Spinner />
            <p className="text-sm text-body" role="status">
              Verifying your private tracking link…
            </p>
          </Card>
        )}

        {trackQuery.data && <TrackingResult reservation={trackQuery.data} />}

        <div className="mt-6 flex gap-3 rounded-xl border border-line bg-surface p-4">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />
          <p className="text-xs leading-5 text-body">
            This view shows only the reservation reference, organization, event, facility,
            schedule, and status. It never shows contact details or internal SAS notes.
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
          Keep the tracking link private. Only share the reservation reference with SAS for
          follow-up.
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
