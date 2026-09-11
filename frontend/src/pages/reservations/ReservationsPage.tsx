import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowRight, Plus, Search } from 'lucide-react'
import { format } from 'date-fns'
import { useFacilities, useReservationCounts, useReservations } from '@/hooks/queries'
import { PageHeader, Skeleton, EmptyState } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { Tabs, type TabItem } from '@/components/ui/Tabs'
import { StatusBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Select, Input } from '@/components/ui/Form'
import { cn, formatTime } from '@/lib/utils'
import type { ReservationStatus, ReservationSummary } from '@/lib/types'

const STATUS_TABS: { key: string; label: string }[] = [
  { key: 'ALL', label: 'All' },
  { key: 'PENDING', label: 'Pending' },
  { key: 'APPROVED', label: 'Approved' },
  { key: 'ACTIVE', label: 'Active' },
  { key: 'COMPLETED', label: 'Completed' },
  { key: 'REJECTED', label: 'Rejected' },
  { key: 'CANCELLED', label: 'Cancelled' },
]

export function ReservationsPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('ALL')
  const [requesterType, setRequesterType] = useState<'ALL' | 'CAMPUS' | 'EXTERNAL'>('ALL')
  const [search, setSearch] = useState('')
  const [facility, setFacility] = useState('')
  const [date, setDate] = useState('')
  const { data: counts } = useReservationCounts()
  const { data: facilities } = useFacilities()

  const {
    data,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useReservations({
    status: status === 'ALL' ? undefined : (status as ReservationStatus),
    requester_type: requesterType === 'ALL' ? undefined : requesterType,
    search: search || undefined,
    facility: facility ? Number(facility) : undefined,
    date: date || undefined,
    ordering: '-date,-start_time',
  })

  const tabItems: TabItem[] = useMemo(
    () =>
      STATUS_TABS.map((tab) => ({
        key: tab.key,
        label: tab.label,
        count: counts?.[tab.key] ?? undefined,
      })),
    [counts],
  )

  const reservations = data?.results ?? []

  // Distinguish LOADING / ERROR / EMPTY / DATA. An API failure (401, 403,
  // 500, network) must never render as "No reservations found" — that would
  // falsely tell an administrator the records do not exist.
  if (error) {
    const apiError = error as { status?: number; message?: string }
    return (
      <div>
        <PageHeader
          eyebrow="SAS Reservations"
          title="Reservations"
          description="Review, approve, and manage every reservation request across the campus."
          actions={
            <Button onClick={() => navigate('/reservations/new')} icon={<Plus className="size-4" />}>
              Create Reservation
            </Button>
          }
        />
        <Card className="mt-8">
          <EmptyState
            icon={<AlertTriangle className="size-5 text-orange-500" />}
            title="Could not load reservations"
            description={
              apiError.status
                ? `The server returned an error (${apiError.status}). ${apiError.message ?? ''}`.trim()
                : 'The reservations service could not be reached. Check your connection and try again.'
            }
            action={
              <Button variant="secondary" onClick={() => void refetch()}>
                Try again
              </Button>
            }
          />
        </Card>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        eyebrow="SAS Reservations"
        title="Reservations"
        description="Review, approve, and manage every reservation request across the campus."
        actions={
          <Button onClick={() => navigate('/reservations/new')} icon={<Plus className="size-4" />}>
            Create Reservation
          </Button>
        }
      />

      <div className="mt-8">
        <Tabs items={tabItems} active={status} onChange={setStatus} />

        {/* Requester type filter — campus vs external at a glance */}
        <div className="mt-4 flex items-center gap-2">
          <span className="text-[13px] font-medium text-muted">Requester:</span>
          {(
            [
              ['ALL', 'All'],
              ['CAMPUS', 'Campus'],
              ['EXTERNAL', 'External'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setRequesterType(value)}
              className={cn(
                'rounded-full border px-3 py-1 text-[13px] font-medium transition-colors duration-150',
                requesterType === value
                  ? 'border-brand bg-brand text-white'
                  : 'border-line bg-surface text-body hover:border-line-strong hover:text-ink',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="mt-5 flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative flex-1 md:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <Input
              type="search"
              placeholder="Search event, requester, or ID…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-9"
              aria-label="Search reservations"
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <Select
              value={facility}
              onChange={(event) => setFacility(event.target.value)}
              aria-label="Filter by facility"
              className="w-full md:w-auto"
            >
              <option value="">All facilities</option>
              {(facilities ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </Select>
            <Input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              aria-label="Filter by date"
              className="w-full md:w-auto"
            />
            {(search || facility || date || requesterType !== 'ALL') && (
              <Button
                variant="ghost"
                onClick={() => {
                  setSearch('')
                  setFacility('')
                  setDate('')
                  setRequesterType('ALL')
                }}
              >
                Clear filters
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Table */}
      <Card className="mt-5 overflow-hidden p-0" padding="none">
        {isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </div>
        ) : reservations.length === 0 ? (
          <EmptyState
            title="No reservations found"
            description={
              search || facility || date || status !== 'ALL' || requesterType !== 'ALL'
                ? 'Try adjusting your filters, or create a new reservation.'
                : 'Reservation requests will appear here once submitted.'
            }
            action={
              !(search || facility || date || status !== 'ALL' || requesterType !== 'ALL') ? (
                <Button size="sm" onClick={() => navigate('/reservations/new')}>
                  Create reservation
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            {/* Desktop table */}
            <table className="hidden w-full md:table">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
                  <th className="px-5 py-3.5">Requester</th>
                  <th className="px-4 py-3.5">Event</th>
                  <th className="px-4 py-3.5">Facility</th>
                  <th className="px-4 py-3.5">Date</th>
                  <th className="px-4 py-3.5">Time</th>
                  <th className="px-4 py-3.5">Resources</th>
                  <th className="px-4 py-3.5">Status</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {reservations.map((reservation) => (
                  <ReservationTableRow key={reservation.id} reservation={reservation} />
                ))}
              </tbody>
            </table>

            {/* Mobile cards */}
            <ul className="divide-y divide-line md:hidden">
              {reservations.map((reservation) => (
                <ReservationMobileRow key={reservation.id} reservation={reservation} />
              ))}
            </ul>
          </>
        )}
        {isFetching && !isLoading && (
          <p className="px-5 py-3 text-xs text-muted" role="status">
            Updating…
          </p>
        )}
      </Card>

      {/* Pagination */}
      {data && data.count > 20 && (
        <p className="mt-4 text-sm text-muted">
          Showing {reservations.length} of {data.count} — refine your filters for a narrower view.
        </p>
      )}
    </div>
  )
}

function RequesterTypeBadge({ type }: { type: ReservationSummary['requester_type'] }) {
  return type === 'EXTERNAL' ? (
    <Badge tone="orange">External</Badge>
  ) : (
    <Badge tone="brand">Campus User</Badge>
  )
}

function ReservationTableRow({ reservation }: { reservation: ReservationSummary }) {
  return (
    <tr className="transition-colors hover:bg-soft/70">
      <td className="px-5 py-4">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-ink">{reservation.requester}</p>
          <RequesterTypeBadge type={reservation.requester_type} />
        </div>
        <p className="text-xs text-muted">{reservation.organization || '—'}</p>
      </td>
      <td className="px-4 py-4">
        <Link to={`/reservations/${reservation.id}`} className="text-sm font-medium text-ink hover:text-brand">
          {reservation.event_name}
        </Link>
        <p className="text-xs text-muted">{reservation.reservation_id}</p>
      </td>
      <td className="px-4 py-4 text-sm text-body">{reservation.facility}</td>
      <td className="px-4 py-4 text-sm tabular-nums text-body">
        {format(new Date(reservation.date), 'MMM d, yyyy')}
      </td>
      <td className="px-4 py-4 text-sm tabular-nums text-body">
        {formatTime(reservation.start_time)}–{formatTime(reservation.end_time)}
      </td>
      <td className="max-w-[220px] px-4 py-4">
        <p className="truncate text-[13px] text-body" title={reservation.resources.join(', ')}>
          {reservation.resources.length ? reservation.resources.join(', ') : '—'}
        </p>
      </td>
      <td className="px-4 py-4">
        <StatusBadge status={reservation.status} />
      </td>
      <td className="px-5 py-4 text-right">
        <Link
          to={`/reservations/${reservation.id}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:text-brand-dark"
        >
          Review <ArrowRight className="size-3.5" />
        </Link>
      </td>
    </tr>
  )
}

function ReservationMobileRow({ reservation }: { reservation: ReservationSummary }) {
  return (
    <li>
      <Link to={`/reservations/${reservation.id}`} className="flex items-start gap-3 px-5 py-4">
        <span className="flex size-10 shrink-0 flex-col items-center justify-center rounded-xl bg-soft leading-none">
          <span className="text-[13px] font-bold text-ink">{format(new Date(reservation.date), 'd')}</span>
          <span className="text-[9px] font-semibold uppercase text-muted">
            {format(new Date(reservation.date), 'MMM')}
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{reservation.event_name}</p>
          <p className="mt-0.5 truncate text-xs text-muted">
            {reservation.facility} · {formatTime(reservation.start_time)}–{formatTime(reservation.end_time)}
          </p>
          <p className="mt-0.5 truncate text-xs text-muted">
            {reservation.requester} · {reservation.reservation_id}
          </p>
          <div className="mt-2 flex items-center gap-1.5">
            <StatusBadge status={reservation.status} />
            <RequesterTypeBadge type={reservation.requester_type} />
          </div>
        </div>
        <ArrowRight className="mt-3 size-4 shrink-0 text-muted" aria-hidden />
      </Link>
    </li>
  )
}