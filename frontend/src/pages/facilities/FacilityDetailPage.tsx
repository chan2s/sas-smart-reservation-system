import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  CalendarDays,
  Clock,
  MapPin,
  Package,
  ShieldCheck,
  Users,
  Wrench,
} from 'lucide-react'
import { format } from 'date-fns'
import { useEquipment, useFacility, useReservations } from '@/hooks/queries'
import { Skeleton, EmptyState } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { StatusBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import { Backdrop } from '@/components/decor/Backdrop'
import { cn, formatTime } from '@/lib/utils'

export function FacilityDetailPage() {
  const { id } = useParams()
  const facilityId = Number(id)
  const navigate = useNavigate()
  const { data: facility, isLoading } = useFacility(facilityId)
  const { data: reservations } = useReservations({ facility: facilityId })
  const { data: equipment } = useEquipment()

  if (isLoading || !facility) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-72 w-full rounded-2xl" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </div>
    )
  }

  const maintenance = facility.status === 'MAINTENANCE'
  const upcoming = (reservations?.results ?? []).filter(
    (reservation) => reservation.date >= format(new Date(), 'yyyy-MM-dd'),
  )
  const facilityEquipment = (equipment ?? []).filter(
    (item) => item.availability.status !== 'UNAVAILABLE',
  )

  return (
    <div className="relative">
      <Backdrop />

      <Link
        to="/facilities"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> All facilities
      </Link>

      {/* Hero */}
      <div className="mt-4 overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
        <div className="relative h-60 sm:h-72">
          <FacilityImage
            name={facility.name}
            facilityType={facility.facility_type}
            src={facility.image}
            rounded="rounded-none"
          />
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-ink/70 to-transparent px-6 pb-5 pt-16 sm:px-8">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="brand">{facility.facility_type_label}</Badge>
              {maintenance ? (
                <Badge tone="orange">
                  <Wrench className="size-3" /> Under maintenance
                </Badge>
              ) : (
                <Badge tone="emerald">Available</Badge>
              )}
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              {facility.name}
            </h1>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-white/85">
              <MapPin className="size-4" aria-hidden /> {facility.location}
            </p>
          </div>
        </div>

        {/* CTAs */}
        <div className="flex flex-col gap-3 border-t border-line px-6 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="flex items-center gap-6 text-sm text-body">
            <span className="flex items-center gap-2">
              <Users className="size-4 text-muted" aria-hidden />
              Capacity <span className="font-semibold text-ink">{facility.capacity}</span>
            </span>
            <span className="flex items-center gap-2">
              <Clock className="size-4 text-muted" aria-hidden />
              Daily hours vary
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <Button variant="outline" icon={<CalendarDays className="size-4" />} onClick={() => navigate('/calendar')}>
              View calendar
            </Button>
            <Button
              disabled={maintenance}
              icon={<CalendarDays className="size-4" />}
              onClick={() => navigate(`/reservations/new?facility=${facility.id}`)}
            >
              Reserve this facility
            </Button>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="About this facility" />
            <p className="mt-3 text-[15px] leading-relaxed text-body">{facility.description}</p>

            {facility.rules.length > 0 && (
              <div className="mt-6">
                <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-muted">
                  Rules &amp; guidelines
                </h3>
                <ul className="mt-3 space-y-2.5">
                  {facility.rules.map((rule) => (
                    <li key={rule} className="flex items-start gap-2.5 text-sm text-body">
                      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Current & upcoming reservations"
              description="Approved and pending requests for this facility"
            />
            {upcoming.length === 0 ? (
              <EmptyState
                title="No upcoming reservations"
                description="This facility's calendar is clear for the coming days."
              />
            ) : (
              <ul className="mt-4 divide-y divide-line">
                {upcoming.slice(0, 8).map((reservation) => (
                  <li key={reservation.id}>
                    <Link
                      to={`/reservations/${reservation.id}`}
                      className="flex items-center gap-4 rounded-lg px-2 py-3 transition-colors hover:bg-soft"
                    >
                      <span className="flex size-10 shrink-0 flex-col items-center justify-center rounded-xl bg-soft leading-none">
                        <span className="text-[13px] font-bold text-ink">
                          {format(new Date(reservation.date), 'd')}
                        </span>
                        <span className="text-[9px] font-semibold uppercase text-muted">
                          {format(new Date(reservation.date), 'MMM')}
                        </span>
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">
                          {reservation.event_name}
                        </p>
                        <p className="truncate text-xs text-muted">
                          {formatTime(reservation.start_time)}–{formatTime(reservation.end_time)} ·{' '}
                          {reservation.requester}
                        </p>
                      </div>
                      <StatusBadge status={reservation.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Operating hours" />
            <ul className="mt-4 space-y-2">
              {(facility.operating_hours ?? []).map((hours) => (
                <li
                  key={hours.id}
                  className={cn(
                    'flex items-center justify-between rounded-lg px-3 py-2 text-sm',
                    hours.is_closed ? 'bg-soft text-muted' : 'bg-soft text-ink',
                  )}
                >
                  <span>{hours.day_label}</span>
                  <span className={cn('tabular-nums', hours.is_closed && 'text-muted')}>
                    {hours.is_closed ? 'Closed' : `${formatTime(hours.open_time!)} – ${formatTime(hours.close_time!)}`}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader
              title="Available equipment"
              action={
                <Link to="/equipment" className="text-sm font-medium text-brand hover:text-brand-dark">
                  View all
                </Link>
              }
            />
            {facilityEquipment.length === 0 ? (
              <p className="mt-4 text-sm text-muted">No equipment currently available.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {facilityEquipment.slice(0, 6).map((item) => (
                  <li key={item.id}>
                    <Link
                      to={`/equipment/${item.id}`}
                      className="flex items-center gap-3 rounded-lg border border-line p-3 transition-colors hover:border-line-strong hover:bg-soft"
                    >
                      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
                        <Package className="size-4" aria-hidden />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">{item.name}</p>
                        <p className="text-xs text-muted">{item.category.name}</p>
                      </div>
                      <span className="shrink-0 text-xs font-medium tabular-nums text-body">
                        {item.availability.available}/{item.total_quantity}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {maintenance && (
            <div className="rounded-xl border border-status-maintenance/25 bg-status-maintenance-bg p-4 text-sm text-status-maintenance">
              <p className="font-semibold">Facility under maintenance</p>
              <p className="mt-1 text-[13px]">
                Reservations are paused while maintenance is in progress. Please check back later
                or choose another facility.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}