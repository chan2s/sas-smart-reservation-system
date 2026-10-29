import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Building2,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileSignature,
  Package,
  Plus,
  RefreshCw,
  Ticket,
  TriangleAlert,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  useApprovalLetters,
  useDashboardSummary,
  useFacilities,
  useNoShowAlerts,
  useUtilization,
} from '@/hooks/queries'
import { StageBadge, alertDateTime } from '@/components/notifications/NoShowAlerts'
import { useAuth } from '@/hooks/useAuth'
import { PageHeader, Skeleton } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { StatusBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import {
  ResponsiveTable,
  type ResponsiveTableColumn,
} from '@/components/ui/ResponsiveTable'
import { Backdrop } from '@/components/decor/Backdrop'
import { cn, formatTime } from '@/lib/utils'
import type {
  AwaitingNoShowReview,
  DashboardReservationRow,
  Facility,
  NoShowAlert,
} from '@/lib/types'

// Compact caps — the dashboard surfaces only the most relevant rows and links
// out to the full lists.
const MAX_MY_RESERVATIONS = 3
const MAX_FACILITIES = 5
const MAX_UPCOMING = 5
const MAX_UTILIZATION_BARS = 5

// One page of the combined no-show review list (both categories together).
const NO_SHOW_PAGE_SIZE = 3

const upcomingColumns: ResponsiveTableColumn[] = [
  { key: 'facility', label: 'Facility' },
  { key: 'event', label: 'Event' },
  { key: 'date', label: 'Date' },
  { key: 'time', label: 'Time' },
  { key: 'status', label: 'Status', align: 'right' },
]

export function DashboardPage() {
  const navigate = useNavigate()
  const { isStaff, isViewOnly, isApprovalSignatory } = useAuth()
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
          !isViewOnly && (
            <Button onClick={() => navigate('/reservations/new')} icon={<Plus className="size-4" />}>
              Create Reservation
            </Button>
          )
        }
      />

      {/* Persistent administrator alert section, immediately below the heading. */}
      {isStaff && <PossibleNoShowSection />}

      {/* Designated signatory: approval letters awaiting signature. */}
      {isApprovalSignatory && <ApprovalLettersSection />}

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
              {!isViewOnly && (
                <Button size="sm" className="mt-4" onClick={() => navigate('/reservations/new')}>
                  Create reservation
                </Button>
              )}
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

/**
 * Live no-show review for administrators, split into two clearly separate
 * groups:
 *
 * 1. Possible No-Shows — reservations inside the existing detection window.
 * 2. Awaiting No-Show Review — overdue reservations whose scheduled end time
 *    has passed without a check-in, completed state, cancellation, or explicit
 *    NO_SHOW decision.
 *
 * The backend owns both policies and computes every label. This section only
 * renders the response and links to the reservation detail page, where the
 * existing administrator action marks a reservation as No-Show. Nothing here
 * changes a status automatically.
 */
type NoShowEntry =
  | { kind: 'alert'; key: string; scheduled: number; alert: NoShowAlert }
  | { kind: 'review'; key: string; scheduled: number; review: AwaitingNoShowReview }

/**
 * Merge both review sources into one stable, most-overdue-first sequence.
 *
 * The API already keeps the groups separate and never returns the same
 * reservation twice; deduplicating by reservation id here makes that guarantee
 * hold for the combined list too (an active alert wins over a review row).
 */
function buildNoShowEntries(
  alerts: NoShowAlert[],
  review: AwaitingNoShowReview[],
): NoShowEntry[] {
  const seen = new Set<number>()
  const entries: NoShowEntry[] = []

  for (const alert of alerts) {
    if (seen.has(alert.reservation)) continue
    seen.add(alert.reservation)
    entries.push({
      kind: 'alert',
      key: `alert-${alert.id}`,
      scheduled: Date.parse(`${alert.date}T${alert.start_time}`),
      alert,
    })
  }

  for (const item of review) {
    if (seen.has(item.reservation)) continue
    seen.add(item.reservation)
    entries.push({
      kind: 'review',
      key: `review-${item.reservation}`,
      scheduled: Date.parse(`${item.date}T${item.start_time}`),
      review: item,
    })
  }

  // Earliest scheduled slot first: the most overdue reservation leads. The key
  // tie-break keeps the order deterministic (and therefore page-stable).
  return entries.sort(
    (a, b) => a.scheduled - b.scheduled || a.key.localeCompare(b.key),
  )
}

function PossibleNoShowSection() {
  const { data, isLoading, isError, refetch, isFetching } = useNoShowAlerts(true)
  const alerts = data?.results ?? []
  const unread = data?.unread ?? 0
  const review = data?.awaiting_review ?? []
  const [page, setPage] = useState(1)

  const entries = useMemo(
    () => buildNoShowEntries(data?.results ?? [], data?.awaiting_review ?? []),
    [data],
  )
  const pageCount = Math.max(1, Math.ceil(entries.length / NO_SHOW_PAGE_SIZE))
  // A refresh can shrink the list; never strand the administrator on a page
  // that no longer exists.
  const currentPage = Math.min(page, pageCount)
  const pageStart = (currentPage - 1) * NO_SHOW_PAGE_SIZE
  const pageEntries = entries.slice(pageStart, pageStart + NO_SHOW_PAGE_SIZE)
  const pageAlerts = pageEntries.flatMap((entry) =>
    entry.kind === 'alert' ? [entry.alert] : [],
  )
  const pageReview = pageEntries.flatMap((entry) =>
    entry.kind === 'review' ? [entry.review] : [],
  )

  return (
    <Card className="mt-4">
      <CardHeader
        title="Possible No-Show Alerts"
        description={
          isLoading
            ? 'Checking approved reservations with no recorded check-in…'
            : `${alerts.length} possible no-show${alerts.length === 1 ? '' : 's'}${
                unread > 0 ? ` · ${unread} unread` : ''
              } · ${review.length} awaiting review`
        }
      />

      {isError ? (
        <div className="mt-4 flex flex-col items-start gap-3 rounded-xl border border-status-rejected/30 bg-status-rejected-bg/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2.5">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-status-rejected" aria-hidden />
            <div>
              <p className="text-[13px] font-semibold text-ink">
                Couldn't load possible no-show alerts
              </p>
              <p className="mt-0.5 text-[12.5px] text-body">
                The request failed, so no alerts are shown — nothing here is mocked.
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            loading={isFetching}
            icon={<RefreshCw className="size-3.5" />}
          >
            Retry
          </Button>
        </div>
      ) : isLoading ? (
        <div className="mt-4 space-y-3" aria-busy="true" aria-label="Loading no-show alerts">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : (
        <div className="mt-4 space-y-6">
          <section aria-labelledby="possible-no-shows-heading">
            <GroupHeader
              id="possible-no-shows-heading"
              title="Possible No-Shows"
              count={alerts.length}
              hint="Identified by the existing no-show detection logic"
            />
            {alerts.length === 0 ? (
              <GroupEmpty>
                No possible no-shows detected right now — approved reservations with no
                recorded check-in will appear here.
              </GroupEmpty>
            ) : pageAlerts.length === 0 ? (
              <GroupOffPage />
            ) : (
              <ul className="mt-1 divide-y divide-line">
                {pageAlerts.map((alert) => (
                  <li
                    key={alert.id}
                    className={cn(
                      'flex flex-col gap-2 px-1 py-3 sm:flex-row sm:items-center sm:justify-between',
                      !alert.acknowledged && 'bg-brand-soft/20',
                    )}
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          to={alert.link}
                          className="text-sm font-semibold text-ink hover:text-brand"
                        >
                          {alert.reference}
                        </Link>
                        <StageBadge stage={alert.stage} label={alert.stage_label} />
                        <span className="text-[11px] font-medium text-muted">
                          {alert.no_check_in_label}
                        </span>
                      </div>
                      <p className="mt-0.5 truncate text-[13px] text-body">
                        {alert.event_name} · {alert.facility} ·{' '}
                        {alert.requester || 'No requester account'}
                      </p>
                      <p className="text-xs tabular-nums text-muted">
                        {alertDateTime(alert)} · {alert.time_label}
                      </p>
                    </div>
                    <Link
                      to={alert.link}
                      className="inline-flex shrink-0 items-center gap-1 self-start rounded-lg border border-line px-3 py-1.5 text-[12.5px] font-semibold text-ink transition-colors hover:border-brand hover:text-brand sm:self-center"
                    >
                      Review reservation
                      <ArrowRight className="size-3.5" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="awaiting-review-heading">
            <GroupHeader
              id="awaiting-review-heading"
              title="Awaiting No-Show Review"
              count={review.length}
              hint="Scheduled end time passed · no check-in"
            />
            {review.length === 0 ? (
              <GroupEmpty>
                No overdue reservations are awaiting a no-show decision.
              </GroupEmpty>
            ) : pageReview.length === 0 ? (
              <GroupOffPage />
            ) : (
              <ul className="mt-1 divide-y divide-line">
                {pageReview.map((reservation) => (
                  <AwaitingReviewRow key={reservation.reservation} reservation={reservation} />
                ))}
              </ul>
            )}
          </section>

          <NoShowPagination
            page={currentPage}
            pageCount={pageCount}
            total={entries.length}
            onChange={setPage}
          />
        </div>
      )}
    </Card>
  )
}

/**
 * Previous / Next paging for the combined list. Hidden while everything fits on
 * one page, so the section looks exactly as it did before pagination existed.
 */
function NoShowPagination({
  page,
  pageCount,
  total,
  onChange,
}: {
  page: number
  pageCount: number
  total: number
  onChange: (page: number) => void
}) {
  if (pageCount <= 1) return null

  const first = (page - 1) * NO_SHOW_PAGE_SIZE + 1
  const last = Math.min(page * NO_SHOW_PAGE_SIZE, total)

  return (
    <nav
      aria-label="Possible no-show alerts pagination"
      className="flex flex-col items-center justify-between gap-2 border-t border-line pt-3 sm:flex-row"
    >
      <p className="text-[12px] tabular-nums text-muted">
        Showing {first}–{last} of {total}
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          icon={<ChevronLeft className="size-3.5" aria-hidden />}
        >
          Previous
        </Button>
        <p className="text-[12px] font-medium tabular-nums text-body" aria-live="polite">
          Page {page} of {pageCount}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange(page + 1)}
          disabled={page >= pageCount}
        >
          Next
          <ChevronRight className="size-3.5" aria-hidden />
        </Button>
      </div>
    </nav>
  )
}

function GroupHeader({
  id,
  title,
  count,
  hint,
}: {
  id: string
  title: string
  count: number
  hint: string
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <div className="flex items-center gap-2">
        <h3 id={id} className="text-[13px] font-semibold text-ink">
          {title}
        </h3>
        <Badge tone={count > 0 ? 'amber' : 'neutral'}>{count}</Badge>
      </div>
      <p className="text-[11.5px] text-muted">{hint}</p>
    </div>
  )
}

function GroupEmpty({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2 rounded-lg border border-dashed border-line px-4 py-3 text-[13px] text-body">
      {children}
    </div>
  )
}

/** A category with rows overall, but none of them on the page being viewed. */
function GroupOffPage() {
  return (
    <p className="mt-2 px-1 text-[12px] text-muted">
      Nothing from this group on this page.
    </p>
  )
}

function AwaitingReviewRow({ reservation }: { reservation: AwaitingNoShowReview }) {
  return (
    <li className="flex flex-col gap-2 px-1 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={reservation.link}
            className="text-sm font-semibold text-ink hover:text-brand"
          >
            {reservation.reference}
          </Link>
          <Badge tone="amber">Awaiting no-show review</Badge>
          <span className="text-[11px] font-medium text-muted">
            {reservation.no_check_in_label}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[13px] text-body">
          {reservation.event_name} · {reservation.facility} ·{' '}
          {reservation.requester || 'No requester account'}
        </p>
        <p className="text-xs tabular-nums text-muted">
          {alertDateTime(reservation)} · {formatTime(reservation.start_time)} –{' '}
          {formatTime(reservation.end_time)} · {reservation.time_label}
        </p>
        {!reservation.can_mark_no_show && (
          <p className="mt-0.5 text-[11.5px] text-muted">
            Can be marked as a no-show from the day after the scheduled date.
          </p>
        )}
      </div>
      <Link
        to={reservation.link}
        className="inline-flex shrink-0 items-center gap-1 self-start rounded-lg border border-line px-3 py-1.5 text-[12.5px] font-semibold text-ink transition-colors hover:border-brand hover:text-brand sm:self-center"
      >
        Review &amp; mark no-show
        <ArrowRight className="size-3.5" aria-hidden />
      </Link>
    </li>
  )
}

// ---------------------------------------------------------------------------

/**
 * Designated signatory summary: approval letters awaiting signature.
 *
 * Compact companion to the full /approval-letters workspace — pending count,
 * the three oldest letters, and a link through. Rendered only for the
 * designated signatory (the backend re-verifies every request).
 */
const MAX_PENDING_LETTERS = 3

function ApprovalLettersSection() {
  const { data, isLoading, isError, refetch, isFetching } = useApprovalLetters(
    { status: 'PENDING_SIGNATURE' },
    true,
  )
  const pending = data?.results.slice(0, MAX_PENDING_LETTERS) ?? []
  const count = data?.count ?? 0

  return (
    <Card className="mt-4">
      <CardHeader
        title="Approval Letters"
        description={
          isLoading
            ? 'Checking letters awaiting your signature…'
            : `${count} letter${count === 1 ? '' : 's'} awaiting signature`
        }
        action={<SectionLink to="/approval-letters">Open workspace</SectionLink>}
      />

      {isError ? (
        <div className="mt-4 flex flex-col items-start gap-3 rounded-xl border border-status-rejected/30 bg-status-rejected-bg/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[13px] text-body">
            Couldn't load approval letters — the request failed. Nothing is mocked here.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            loading={isFetching}
            icon={<RefreshCw className="size-3.5" />}
          >
            Retry
          </Button>
        </div>
      ) : isLoading ? (
        <div className="mt-4 space-y-3" aria-busy="true" aria-label="Loading approval letters">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      ) : pending.length === 0 ? (
        <div className="mt-2 rounded-lg border border-dashed border-line px-4 py-3 text-[13px] text-body">
          No letters are awaiting your signature right now.
        </div>
      ) : (
        <ul className="mt-3 divide-y divide-line">
          {pending.map((letter) => (
            <li key={letter.id}>
              <Link
                to={`/approval-letters?letter=${letter.id}`}
                className="-mx-2 flex flex-col gap-0.5 rounded-lg px-2 py-3 transition-colors hover:bg-soft"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-semibold text-ink">
                    {letter.letter_id} · {letter.event_name}
                  </p>
                  <Badge tone="amber" className="shrink-0">
                    <FileSignature className="size-3" aria-hidden />
                    Awaiting signature
                  </Badge>
                </div>
                <p className="truncate text-[13px] text-body">
                  {letter.facility_name} · {letter.requester_name} ·{' '}
                  {letter.reservation_reference}
                </p>
                <p className="text-xs tabular-nums text-muted">
                  {format(new Date(letter.reservation_date), 'MMM d, yyyy')} ·{' '}
                  {formatTime(letter.start_time)} – {formatTime(letter.end_time)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
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
