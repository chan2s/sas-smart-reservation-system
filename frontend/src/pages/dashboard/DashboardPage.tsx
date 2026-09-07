import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Building2,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Package,
  Plus,
  Ticket,
  TriangleAlert,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  useDashboardSummary,
  useEquipment,
  useFacilities,
  useReservations,
  useUtilization,
} from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { PageHeader, Skeleton, EmptyState } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Backdrop } from '@/components/decor/Backdrop'
import { cn, formatTime, STATUS_META } from '@/lib/utils'
import type { ReservationSummary } from '@/lib/types'

const todayISO = format(new Date(), 'yyyy-MM-dd')

export function DashboardPage() {
  const navigate = useNavigate()
  const { isStaff } = useAuth()
  const { data: summary, isLoading: summaryLoading } = useDashboardSummary()
  const { data: reservations } = useReservations({ page: 1 })
  const { data: facilities } = useFacilities()
  const { data: equipment } = useEquipment()
  const { data: utilization } = useUtilization(30)

  const today = (reservations?.results ?? []).filter((r) => r.date === todayISO)
  const upcoming = (reservations?.results ?? [])
    .filter((r) => r.date >= todayISO && r.status === 'APPROVED')
    .sort((a, b) => a.date.localeCompare(b.date) || a.start_time.localeCompare(b.start_time))
    .slice(0, 5)
  const pending = (reservations?.results ?? []).filter((r) => r.status === 'PENDING').slice(0, 5)
  const recentActivity = (reservations?.results ?? []).slice(0, 6)
  const equipmentAttention = (equipment ?? []).filter(
    (item) => item.availability.status !== 'AVAILABLE' || item.condition === 'POOR',
  )

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

      {/* Statistics */}
      <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={<Ticket className="size-[18px]" />}
          label="Total Reservations"
          value={summary?.total_reservations}
          loading={summaryLoading}
        />
        <StatCard
          icon={<ClipboardList className="size-[18px]" />}
          label="Pending Requests"
          value={summary?.pending_requests}
          loading={summaryLoading}
          accent="text-status-pending"
        />
        <StatCard
          icon={<Building2 className="size-[18px]" />}
          label="Active Facilities"
          value={summary?.facilities}
          loading={summaryLoading}
        />
        <StatCard
          icon={<Package className="size-[18px]" />}
          label="Equipment Items"
          value={summary?.equipment}
          loading={summaryLoading}
        />
      </div>

      {/* Campus vs external usage split */}
      {isStaff && (
        <p className="mt-3 text-sm text-muted">
          Campus reservations:{' '}
          <span className="font-semibold tabular-nums text-ink">
            {summary?.campus_reservations ?? 0}
          </span>{' '}· External reservations:{' '}
          <span className="font-semibold tabular-nums text-ink">
            {summary?.external_reservations ?? 0}
          </span>{' '}·{' '}
          <Link to="/analytics" className="font-medium text-brand hover:text-brand-dark">
            View breakdown
          </Link>
        </p>
      )}

      {/* Row: today + utilization */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Today's reservations"
            description={format(new Date(), 'EEEE, MMMM d, yyyy')}
            action={
              <Link
                to="/calendar"
                className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:text-brand-dark"
              >
                View calendar <ArrowRight className="size-3.5" />
              </Link>
            }
          />
          {today.length === 0 ? (
            <EmptyState
              title="No reservations today"
              description="The facility calendar is clear — create a reservation to get started."
              action={
                <Button size="sm" onClick={() => navigate('/reservations/new')}>
                  Create reservation
                </Button>
              }
            />
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {today.map((reservation) => (
                <TodayRow key={reservation.id} reservation={reservation} />
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Facility utilization"
            description="Share of operating hours booked — last 30 days"
          />
          <div className="mt-5 space-y-4">
            {(utilization?.facility.facilities ?? []).slice(0, 5).map((facility) => (
              <div key={facility.facility_id}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3">
                  <p className="truncate text-sm font-medium text-ink">{facility.name}</p>
                  <p className="shrink-0 text-[13px] tabular-nums text-body">
                    {facility.utilization}%
                  </p>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-softer" role="presentation">
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
            {!utilization && <Skeleton className="h-24" />}
          </div>
        </Card>
      </div>

      {/* Row: pending + upcoming + facility availability */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader
            title={isStaff ? 'Pending approval' : 'My pending requests'}
            description={isStaff ? 'Requests awaiting your decision' : 'Requests awaiting SAS review'}
          />
          {pending.length === 0 ? (
            <p className="mt-4 text-sm text-muted">Nothing awaiting approval.</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {pending.map((reservation) => (
                <PendingRow key={reservation.id} reservation={reservation} />
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader title="Upcoming reservations" description="Approved events in the next 7 days" />
          {upcoming.length === 0 ? (
            <p className="mt-4 text-sm text-muted">No approved events on the horizon.</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {upcoming.map((reservation) => (
                <UpcomingRow key={reservation.id} reservation={reservation} />
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Facility availability"
            action={
              <Link
                to="/facilities"
                className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:text-brand-dark"
              >
                All facilities <ArrowRight className="size-3.5" />
              </Link>
            }
          />
          <ul className="mt-4 space-y-3">
            {(facilities ?? []).map((facility) => (
              <li key={facility.id}>
                <Link
                  to={`/facilities/${facility.id}`}
                  className="group flex items-center gap-3 rounded-xl border border-line p-3 transition-colors duration-150 hover:border-line-strong hover:bg-soft"
                >
                  <span
                    className={cn(
                      'size-2 shrink-0 rounded-full',
                      facility.status === 'MAINTENANCE'
                        ? 'bg-status-maintenance'
                        : facility.availability.available === false
                          ? 'bg-status-rejected'
                          : 'bg-status-available',
                    )}
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{facility.name}</p>
                    <p className="truncate text-xs text-muted">
                      {facility.location} · Capacity {facility.capacity}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs font-medium text-body group-hover:text-brand">
                    {facility.status === 'MAINTENANCE'
                      ? 'Maintenance'
                      : facility.availability.available === false
                        ? 'Reserved'
                        : 'Available'}
                  </span>
                </Link>
              </li>
            ))}
            {!facilities && <Skeleton className="h-24" />}
          </ul>
        </Card>
      </div>

      {/* Row: equipment attention + activity */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Equipment requiring attention"
            description="Low availability, maintenance, or poor condition"
            action={
              <Link
                to="/equipment"
                className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:text-brand-dark"
              >
                Inventory <ArrowRight className="size-3.5" />
              </Link>
            }
          />
          {equipmentAttention.length === 0 ? (
            <p className="mt-4 text-sm text-muted">All equipment is in good standing.</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {equipmentAttention.slice(0, 5).map((item) => (
                <li key={item.id} className="flex items-center gap-3 py-2.5">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-status-maintenance-bg text-status-maintenance">
                    <TriangleAlert className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <Link to={`/equipment/${item.id}`} className="text-sm font-medium text-ink hover:text-brand">
                      {item.name}
                    </Link>
                    <p className="text-xs text-muted">
                      {item.category.name} · {item.condition_label}
                    </p>
                  </div>
                  <span
                    className={cn(
                      'shrink-0 rounded-md px-2 py-0.5 text-xs font-medium',
                      item.availability.status === 'AVAILABLE'
                        ? 'bg-status-available-bg text-status-available'
                        : item.availability.status === 'PARTIAL'
                          ? 'bg-status-partial-bg text-status-partial'
                          : 'bg-status-rejected-bg text-status-rejected',
                    )}
                  >
                    {item.availability.available} / {item.total_quantity} available
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader title="Reservation activity" description="Most recent requests across the system" />
          {recentActivity.length === 0 ? (
            <p className="mt-4 text-sm text-muted">No reservation activity yet.</p>
          ) : (
            <ol className="mt-4 space-y-0">
              {recentActivity.map((reservation, index) => (
                <li key={reservation.id} className="relative flex gap-4 pb-5 last:pb-0">
                  {index < recentActivity.length - 1 && (
                    <span
                      className="absolute left-[7px] top-5 h-full w-px bg-line"
                      aria-hidden
                    />
                  )}
                  <span
                    className={cn(
                      'relative mt-1.5 size-3.5 shrink-0 rounded-full border-2 border-surface',
                      STATUS_META[reservation.status].dot,
                    )}
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3">
                      <Link
                        to={`/reservations/${reservation.id}`}
                        className="truncate text-sm font-medium text-ink hover:text-brand"
                      >
                        {reservation.event_name}
                      </Link>
                      <StatusBadge status={reservation.status} />
                    </div>
                    <p className="mt-0.5 text-xs text-muted">
                      {format(new Date(reservation.date), 'MMM d')} ·{' '}
                      {formatTime(reservation.start_time)}–{formatTime(reservation.end_time)} ·{' '}
                      {reservation.facility}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
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
  accent,
}: {
  icon: React.ReactNode
  label: string
  value?: number
  loading?: boolean
  accent?: string
}) {
  return (
    <div className="card flex items-start gap-4 p-5">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
        {icon}
      </span>
      <div className="min-w-0">
        {loading ? (
          <Skeleton className="h-8 w-14" />
        ) : (
          <p className={cn('text-[26px] font-semibold leading-none tabular-nums tracking-tight', accent ?? 'text-ink')}>
            {value ?? 0}
          </p>
        )}
        <p className="mt-1.5 text-[13px] text-body">{label}</p>
      </div>
    </div>
  )
}

function TodayRow({ reservation }: { reservation: ReservationSummary }) {
  return (
    <li>
      <Link
        to={`/reservations/${reservation.id}`}
        className="flex items-center gap-4 rounded-lg px-2 py-3 transition-colors hover:bg-soft"
      >
        <span className="flex size-10 shrink-0 flex-col items-center justify-center rounded-xl bg-soft leading-none">
          <Clock3 className="mb-0.5 size-3.5 text-muted" aria-hidden />
          <span className="text-[11px] font-semibold tabular-nums text-ink">
            {formatTime(reservation.start_time).replace(/\s?(AM|PM)/, '')}
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{reservation.event_name}</p>
          <p className="truncate text-xs text-muted">
            {reservation.facility} · {reservation.requester}
          </p>
        </div>
        <StatusBadge status={reservation.status} />
      </Link>
    </li>
  )
}

function PendingRow({ reservation }: { reservation: ReservationSummary }) {
  return (
    <li>
      <Link
        to={`/reservations/${reservation.id}`}
        className="flex items-center gap-3 py-2.5 transition-colors hover:opacity-80"
      >
        <CalendarClock className="size-4 shrink-0 text-status-pending" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{reservation.event_name}</p>
          <p className="truncate text-xs text-muted">
            {format(new Date(reservation.date), 'MMM d')} · {reservation.facility} ·{' '}
            {reservation.requester}
          </p>
        </div>
        <ArrowRight className="size-3.5 shrink-0 text-muted" aria-hidden />
      </Link>
    </li>
  )
}

function UpcomingRow({ reservation }: { reservation: ReservationSummary }) {
  return (
    <li>
      <Link
        to={`/reservations/${reservation.id}`}
        className="flex items-center gap-3 py-2.5 transition-colors hover:opacity-80"
      >
        <span className="flex size-9 shrink-0 flex-col items-center justify-center rounded-lg bg-brand-soft leading-none">
          <span className="text-[13px] font-bold text-brand">
            {format(new Date(reservation.date), 'd')}
          </span>
          <span className="text-[9px] font-semibold uppercase text-brand/70">
            {format(new Date(reservation.date), 'MMM')}
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{reservation.event_name}</p>
          <p className="truncate text-xs text-muted">
            {reservation.facility} · {formatTime(reservation.start_time)}–{formatTime(reservation.end_time)}
          </p>
        </div>
        <CheckCircle2 className="size-4 shrink-0 text-status-available" aria-hidden />
      </Link>
    </li>
  )
}