import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Building2,
  CalendarDays,
  ClipboardList,
  Package,
  Plus,
  RefreshCw,
  Ticket,
  TriangleAlert,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  useDashboardSummary,
  useFacilities,
  useUtilization,
} from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { PageHeader, Skeleton } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import {
  ResponsiveTable,
  type ResponsiveTableColumn,
} from '@/components/ui/ResponsiveTable'
import { Backdrop } from '@/components/decor/Backdrop'
import { cn, formatTime } from '@/lib/utils'
import type { DashboardReservationRow, Facility } from '@/lib/types'

// Compact caps — the dashboard surfaces only the most relevant rows and links
// out to the full lists.
const MAX_MY_RESERVATIONS = 3
const MAX_FACILITIES = 5
const MAX_UPCOMING = 5
const MAX_UTILIZATION_BARS = 5

const upcomingColumns: ResponsiveTableColumn[] = [
  { key: 'facility', label: 'Facility' },
  { key: 'event', label: 'Event' },
  { key: 'date', label: 'Date' },
  { key: 'time', label: 'Time' },
  { key: 'status', label: 'Status', align: 'right' },
]

export function DashboardPage() {
  const navigate = useNavigate()
  const { isStaff } = useAuth()
  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
    refetch: summaryRefetch,
    isFetching: summaryFetching,
  } = useDashboardSummary()
  const { data: facilities } = useFacilities()
  const { data: utilization, isError: utilizationError } = useUtilization(30)

  // All dashboard rows come from the backend summary — computed with the
  // backend's Asia/Manila clock and scoped server-side to the signed-in
  // user's role. The frontend applies no filtering of its own.
  //
  // "My Reservations" consolidates the old today/pending cards into one list:
  // today's schedule, requests awaiting review, and what's coming up —
  // deduped, soonest first.
  const myReservations = useMemo(() => {
    if (!summary) return []
    const seen = new Set<number>()
    return [...summary.today, ...summary.pending, ...summary.upcoming]
      .filter((row) => (seen.has(row.id) ? false : (seen.add(row.id), true)))
      .sort((a, b) =>
        `${a.date} ${a.start_time}`.localeCompare(`${b.date} ${b.start_time}`),
      )
      .slice(0, MAX_MY_RESERVATIONS)
  }, [summary])

  const upcoming = (summary?.upcoming ?? []).slice(0, MAX_UPCOMING)

  return (
    <div className="relative">
      <Backdrop />

      <PageHeader
        eyebrow="SAS Reservation Management"
        title="Manage your campus resources"
        description="Monitor reservations, facilities, equipment, and upcoming events from one centralized workspace."
        actions={
          <Button onClick={() => navigate('/reservations/new')} icon={<Plus className="size-4" />}>
            Create Reservation
          </Button>
        }
      />

      {/* Error state — never fake numbers when the API fails. */}
      {summaryError && (
        <Card className="mt-8 border-status-rejected/40">
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-status-rejected-bg text-status-rejected">
                <TriangleAlert className="size-5" aria-hidden />
              </span>
              <div>
                <p className="text-[15px] font-semibold text-ink">
                  Couldn't load dashboard statistics
                </p>
                <p className="mt-0.5 text-sm text-body">
                  The server didn't return the latest numbers. Nothing shown below is a
                  placeholder — retry to load real data.
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              onClick={() => void summaryRefetch()}
              loading={summaryFetching}
              icon={<RefreshCw className="size-4" />}
            >
              Retry
            </Button>
          </div>
        </Card>
      )}

      {/* Statistics — one column on phones so labels never crush; 2×2 on
          tablets, 4-up on desktop */}
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<Ticket className="size-4" />}
          label="Total Reservations"
          value={summary?.total_reservations}
          loading={summaryLoading}
        />
        <StatCard
          icon={<ClipboardList className="size-4" />}
          label="Pending Requests"
          value={summary?.pending_requests}
          loading={summaryLoading}
        />
        <StatCard
          icon={<Building2 className="size-4" />}
          label="Active Facilities"
          value={summary?.facilities}
          loading={summaryLoading}
        />
        <StatCard
          icon={<Package className="size-4" />}
          label="Total Equipment Units"
          value={summary?.equipment}
          loading={summaryLoading}
        />
      </div>

      {/* Main row: reservations + facility availability. min-w-0 on the cards
          lets truncate() work inside grid tracks (grid items default to
          min-width:auto). */}
      <div className="mt-5 grid gap-5 lg:grid-cols-5 [&>*]:min-w-0">
        <Card className="flex flex-col lg:col-span-3">
          <CardHeader
            title="My Reservations"
            description={
              summary?.today_date
                ? format(new Date(`${summary.today_date}T00:00:00`), 'EEEE, MMMM d, yyyy')
                : undefined
            }
            action={<SectionLink to="/reservations">View all</SectionLink>}
          />
          {summaryLoading ? (
            <div className="mt-4 space-y-3" aria-busy="true" aria-label="Loading reservations">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          ) : myReservations.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center px-6 py-10 text-center">
              <div className="flex size-11 items-center justify-center rounded-full bg-soft text-muted">
                <CalendarDays className="size-5" aria-hidden />
              </div>
              <h3 className="mt-3 text-sm font-semibold text-ink">
                {isStaff ? 'Nothing scheduled today' : 'No reservations yet'}
              </h3>
              <p className="mt-1 max-w-xs text-[13px] text-body">
                {isStaff
                  ? "Today's calendar is clear — new requests awaiting your approval will appear here."
                  : 'Reservations you book — and requests awaiting review — will appear here.'}
              </p>
              <Button size="sm" className="mt-4" onClick={() => navigate('/reservations/new')}>
                Create reservation
              </Button>
            </div>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {myReservations.map((reservation) => (
                <MyReservationRow
                  key={reservation.id}
                  reservation={reservation}
                  showRequester={isStaff}
                />
              ))}
            </ul>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Facility Availability"
            action={<SectionLink to="/facilities">View all</SectionLink>}
          />
          {!facilities ? (
            <div className="mt-4 space-y-3" aria-busy="true" aria-label="Loading facilities">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : facilities.length === 0 ? (
            <p className="mt-4 text-sm text-muted">No facilities have been added yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {facilities.slice(0, MAX_FACILITIES).map((facility) => (
                <FacilityRow key={facility.id} facility={facility} />
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Bottom row: upcoming reservations (+ utilization for staff — the
          analytics endpoint is SAS-staff-only, so requesters get the full
          width for the table instead of a permanently empty panel) */}
      <div className="mt-5 grid gap-5 lg:grid-cols-5 [&>*]:min-w-0">
        <Card
          padding="none"
          className={cn('overflow-hidden', isStaff ? 'lg:col-span-3' : 'lg:col-span-5')}
        >
          <div className="px-5 pt-5">
            <CardHeader
              title="Upcoming Reservations"
              description="Approved events in the next 7 days"
              action={<SectionLink to="/calendar">View calendar</SectionLink>}
            />
          </div>
          <ResponsiveTable
            columns={upcomingColumns}
            data={upcoming}
            rowKey={(row) => row.id}
            isLoading={summaryLoading}
            isEmpty={!summaryLoading && upcoming.length === 0}
            skeletonRows={3}
            breakpoint="md"
            caption="Upcoming reservations"
            renderDesktopRow={(row) => (
              <tr className="group transition-colors hover:bg-soft">
                <td className="max-w-[10rem] px-4 py-3 text-sm first:pl-5">
                  <Link
                    to={`/facilities/${row.facility_id}`}
                    className="block truncate font-medium text-ink hover:text-brand"
                  >
                    {row.facility}
                  </Link>
                </td>
                <td className="px-4 py-3 text-sm">
                  <Link
                    to={`/reservations/${row.id}`}
                    className="block truncate text-body hover:text-brand"
                  >
                    {row.event_name}
                  </Link>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm tabular-nums text-body">
                  {format(new Date(row.date), 'MMM d')}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm tabular-nums text-body">
                  {formatTime(row.start_time)} – {formatTime(row.end_time)}
                </td>
                <td className="px-4 py-3 text-right last:pr-5">
                  <StatusBadge status={row.status} />
                </td>
              </tr>
            )}
            renderMobileCard={(row) => (
              <div className="px-5 py-3.5">
                <div className="flex items-center justify-between gap-3">
                  <Link
                    to={`/facilities/${row.facility_id}`}
                    className="min-w-0 truncate text-sm font-medium text-ink"
                  >
                    {row.facility}
                  </Link>
                  <StatusBadge status={row.status} className="shrink-0" />
                </div>
                <Link to={`/reservations/${row.id}`} className="mt-0.5 block truncate text-[13px] text-body">
                  {row.event_name}
                </Link>
                <p className="mt-0.5 text-xs tabular-nums text-muted">
                  {format(new Date(row.date), 'MMM d, yyyy')} ·{' '}
                  {formatTime(row.start_time)} – {formatTime(row.end_time)}
                </p>
              </div>
            )}
            emptyState={
              <div className="flex flex-col items-center px-6 py-9 text-center">
                <p className="text-sm font-medium text-ink">No upcoming reservations</p>
                <p className="mt-0.5 text-[13px] text-body">
                  Approved events for the next 7 days will appear here.
                </p>
              </div>
            }
          />
        </Card>

        {isStaff && (
          <Card className="flex flex-col lg:col-span-2">
            <CardHeader
              title="Facility Utilization"
              description="Share of operating hours booked — last 30 days"
            />
            {utilizationError ? (
              <p className="mt-4 flex flex-1 items-center justify-center text-center text-sm text-muted">
                Usage data is unavailable right now.
              </p>
            ) : !utilization ? (
              <div className="mt-5 space-y-4" aria-busy="true" aria-label="Loading utilization">
                {[0, 1, 2].map((index) => (
                  <div key={index}>
                    <Skeleton className="mb-2 h-3 w-24" />
                    <Skeleton className="h-1.5 w-full" />
                  </div>
                ))}
              </div>
            ) : utilization.facility.facilities.length === 0 ? (
              <p className="mt-4 flex flex-1 items-center justify-center text-center text-sm text-muted">
                No facility usage recorded in this period.
              </p>
            ) : (
              <div className="mt-5 space-y-4">
                {utilization.facility.facilities
                  .slice(0, MAX_UTILIZATION_BARS)
                  .map((facility) => (
                    <div key={facility.facility_id}>
                      <div className="mb-1.5 flex items-baseline justify-between gap-3">
                        <p className="truncate text-[13px] font-medium text-ink">{facility.name}</p>
                        <p className="shrink-0 text-xs tabular-nums text-body">
                          {facility.utilization}%
                        </p>
                      </div>
                      <div
                        className="h-1.5 overflow-hidden rounded-full bg-softer"
                        role="presentation"
                      >
                        <div
                          className={cn(
                            'h-full rounded-full transition-all duration-500',
                            facility.utilization > 75
                              ? 'bg-status-pending'
                              : facility.utilization > 40
                                ? 'bg-brand'
                                : 'bg-status-available',
                          )}
                          style={{ width: `${Math.min(facility.utilization, 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function StatCard({
  icon,
  label,
  value,
  loading,
}: {
  icon: React.ReactNode
  label: string
  value?: number
  loading?: boolean
}) {
  return (
    <div className="card p-4 sm:p-5">
      <div className="flex items-center gap-2.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
          {icon}
        </span>
        <p className="truncate text-[13px] font-medium text-body">{label}</p>
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-7 w-14" />
      ) : (
        <p className="mt-2.5 text-[28px] font-semibold leading-none tabular-nums tracking-tight text-ink">
          {value ?? 0}
        </p>
      )}
    </div>
  )
}

/** Small "View all →" link used in every section header. */
function SectionLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex shrink-0 items-center gap-1 self-center text-[13px] font-medium text-brand hover:text-brand-dark"
    >
      {children}
      <ArrowRight className="size-3.5" aria-hidden />
    </Link>
  )
}

function MyReservationRow({
  reservation,
  showRequester,
}: {
  reservation: DashboardReservationRow
  showRequester: boolean
}) {
  return (
    <li>
      <Link
        to={`/reservations/${reservation.id}`}
        className="-mx-2 flex flex-col gap-0.5 rounded-lg px-2 py-3 transition-colors hover:bg-soft"
      >
        <div className="flex items-center justify-between gap-3">
          <p className="truncate text-sm font-semibold text-ink">{reservation.facility}</p>
          <StatusBadge status={reservation.status} className="shrink-0" />
        </div>
        <p className="truncate text-[13px] text-body">
          {reservation.event_name}
          {showRequester && reservation.requester ? ` · ${reservation.requester}` : ''}
        </p>
        <p className="text-xs tabular-nums text-muted">
          {format(new Date(reservation.date), 'MMM d, yyyy')} · {formatTime(reservation.start_time)}{' '}
          – {formatTime(reservation.end_time)}
        </p>
      </Link>
    </li>
  )
}

/** Dot + status text for a facility, derived from its schedule/status. */
function facilityAvailabilityMeta(facility: Facility) {
  if (facility.status === 'MAINTENANCE') {
    return { label: 'Maintenance', dot: 'bg-status-maintenance', text: 'text-status-maintenance' }
  }
  if (facility.availability.available === false) {
    return { label: 'Reserved', dot: 'bg-status-rejected', text: 'text-status-rejected' }
  }
  return { label: 'Available', dot: 'bg-status-available', text: 'text-status-available' }
}

function FacilityRow({ facility }: { facility: Facility }) {
  const meta = facilityAvailabilityMeta(facility)
  // Some seeded facilities have no location — never render a dangling "·".
  const detail = [facility.location.trim(), `Capacity ${facility.capacity}`]
    .filter(Boolean)
    .join(' · ')
  return (
    <li>
      <Link
        to={`/facilities/${facility.id}`}
        className="group -mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-soft"
      >
        <span className={cn('size-2 shrink-0 rounded-full', meta.dot)} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{facility.name}</p>
          <p className="truncate text-xs text-muted">{detail}</p>
        </div>
        <span className={cn('shrink-0 text-xs font-medium', meta.text)}>{meta.label}</span>
      </Link>
    </li>
  )
}
