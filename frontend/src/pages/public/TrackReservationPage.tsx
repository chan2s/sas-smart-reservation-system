import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  CalendarDays,
  CheckCircle2,
  Clock3,
  Package,
  Search,
  Users,
  XCircle,
} from 'lucide-react'
import { format } from 'date-fns'
import { useTrackReservation } from '@/hooks/public-queries'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Field, Input } from '@/components/ui/Form'
import { PublicShell } from '@/components/layout/PublicShell'
import { formatTime } from '@/lib/utils'
import type { TrackStatus, TrackResult } from '@/lib/types'

const STATUS_STYLES: Record<TrackStatus, { badge: string; icon: 'ok' | 'wait' | 'bad' }> = {
  PENDING: { badge: 'bg-status-pending-bg text-status-pending', icon: 'wait' },
  APPROVED: { badge: 'bg-status-available-bg text-status-available', icon: 'ok' },
  REJECTED: { badge: 'bg-status-rejected-bg text-status-rejected', icon: 'bad' },
  CANCELLED: { badge: 'bg-status-cancelled-bg text-status-cancelled', icon: 'bad' },
  COMPLETED: { badge: 'bg-status-completed-bg text-status-completed', icon: 'ok' },
  CHECKED_IN: { badge: 'bg-status-active-bg text-status-active', icon: 'ok' },
}

function StatusPill({ status, label }: { status: TrackStatus; label: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.PENDING
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold ${style.badge}`}
    >
      {style.icon === 'ok' ? (
        <CheckCircle2 className="size-3.5" aria-hidden />
      ) : style.icon === 'bad' ? (
        <XCircle className="size-3.5" aria-hidden />
      ) : (
        <Clock3 className="size-3.5" aria-hidden />
      )}
      {label}
    </span>
  )
}

/**
 * Public reservation tracking for external requesters.
 * Requires BOTH the reservation code and the email used on the reservation;
 * the response is a restricted payload with only the requester's own data.
 */
export function TrackReservationPage() {
  const track = useTrackReservation()
  const [code, setCode] = useState('')
  const [email, setEmail] = useState('')

  const result: TrackResult | null = track.data ?? null
  const notFound = track.isError && track.error instanceof ApiError && track.error.status === 404

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!code.trim() || !email.trim()) return
    track.mutate({ reservation_code: code.trim(), email: email.trim() })
  }

  return (
    <PublicShell>
      <div className="mx-auto max-w-2xl">
        <div className="text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            SAS Reserve
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">
            Track Reservation
          </h1>
          <p className="mx-auto mt-2 max-w-md text-sm text-body">
            Enter your reservation code and the email address you provided when
            submitting. No account needed.
          </p>
        </div>

        <Card className="mt-8 p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="Reservation code" htmlFor="track-code">
              <Input
                id="track-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="e.g. SAS-2026-00481"
                autoComplete="off"
                required
              />
            </Field>
            <Field label="Email address" htmlFor="track-email">
              <Input
                id="track-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="e.g. juan@example.com"
                autoComplete="email"
                required
              />
            </Field>

            {(track.isError || notFound) && (
              <p
                role="alert"
                className="rounded-lg border border-status-rejected/25 bg-status-rejected-bg px-3.5 py-2.5 text-sm text-status-rejected"
              >
                {notFound
                  ? 'No reservation found matching that code and email. Double-check both fields and try again.'
                  : 'Unable to look up the reservation. Please try again.'}
              </p>
            )}

            <Button type="submit" loading={track.isPending} className="w-full" size="lg">
              <Search className="size-4" aria-hidden />
              Track Reservation
            </Button>
          </form>
        </Card>

        {result && (
          <Card className="mt-6 p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
                  {result.reservation_id}
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
                  {result.event_name}
                </h2>
              </div>
              <StatusPill status={result.status} label={result.status_label} />
            </div>

            {result.status === 'PENDING' && (
              <p className="mt-3 rounded-lg bg-status-pending-bg px-3.5 py-2.5 text-[13px] text-status-pending">
                This reservation is awaiting review by the SAS Office. It is not
                confirmed until approved.
              </p>
            )}
            {result.status === 'APPROVED' && (
              <p className="mt-3 rounded-lg bg-status-available-bg px-3.5 py-2.5 text-[13px] text-status-available">
                Approved! Check-in opens 3 hours before your scheduled event time.
              </p>
            )}
            {result.status === 'REJECTED' && (
              <p className="mt-3 rounded-lg bg-status-rejected-bg px-3.5 py-2.5 text-[13px] text-status-rejected">
                This reservation was not approved. Contact the SAS Office for details.
              </p>
            )}

            <dl className="mt-5 divide-y divide-line">
              <TrackRow
                icon={<Users className="size-4" aria-hidden />}
                label="Requester"
                value={
                  result.organization_type_label
                    ? `${result.organization} — ${result.organization_type_label}`
                    : result.organization
                }
                sub={result.contact_person ? `Contact: ${result.contact_person}` : undefined}
              />
              <TrackRow
                icon={<CalendarDays className="size-4" aria-hidden />}
                label="Schedule"
                value={format(new Date(`${result.date}T00:00:00`), 'EEEE, MMMM d, yyyy')}
                sub={`${formatTime(result.start_time)} – ${formatTime(result.end_time)}`}
              />
              <TrackRow
                icon={<Package className="size-4" aria-hidden />}
                label="Event"
                value={`${result.event_name} — ${result.event_type_label}`}
                sub={
                  result.expected_participants
                    ? `${result.expected_participants.toLocaleString()} expected participants`
                    : undefined
                }
              />
              <TrackRow
                icon={<CheckCircle2 className="size-4" aria-hidden />}
                label="Facility"
                value={result.facility}
              />
              <TrackRow
                icon={<Package className="size-4" aria-hidden />}
                label="Resources"
                value={result.resources.length ? result.resources.join(', ') : 'None requested'}
              />
            </dl>
          </Card>
        )}

        <p className="mt-8 text-center text-sm text-body">
          Need to make a new reservation?{' '}
          <Link to="/reserve" className="font-medium text-brand hover:text-brand-dark">
            Reserve a facility
          </Link>
        </p>
      </div>
    </PublicShell>
  )
}

function TrackRow({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="flex items-start gap-3 py-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-soft text-muted">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
          {label}
        </dt>
        <dd className="mt-0.5 text-sm font-medium text-ink">{value}</dd>
        {sub && <dd className="mt-0.5 text-xs text-body">{sub}</dd>}
      </div>
    </div>
  )
}
