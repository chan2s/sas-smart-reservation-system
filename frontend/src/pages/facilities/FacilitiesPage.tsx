import { useState } from 'react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import { ArrowRight, CalendarDays, MapPin, Users } from 'lucide-react'
import { useFacilities } from '@/hooks/queries'
import { PageHeader, Skeleton } from '@/components/ui/Misc'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import { Badge } from '@/components/ui/Badge'
import { Backdrop } from '@/components/decor/Backdrop'
import { cn, formatTime } from '@/lib/utils'
import type { Facility } from '@/lib/types'

const nextSevenDays = Array.from({ length: 7 }, (_, index) => {
  const date = new Date(Date.now() + index * 86400_000)
  return date.toISOString().slice(0, 10)
})

export function FacilitiesPage() {
  const { data: facilities, isLoading } = useFacilities()
  const [selected, setSelected] = useState<string>('')

  const filtered = (facilities ?? []).filter(
    (facility) => !selected || facility.facility_type === selected,
  )

  return (
    <div className="relative">
      <Backdrop />

      <PageHeader
        eyebrow="SAS Facilities"
        title="Facilities"
        description="Find and reserve the right space for your next event."
      />

      {/* Type filter */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <FilterChip label="All facilities" active={selected === ''} onClick={() => setSelected('')} />
        {[...new Set((facilities ?? []).map((facility) => facility.facility_type))].map((type) => (
          <FilterChip
            key={type}
            label={facilityTypeLabel(type)}
            active={selected === type}
            onClick={() => setSelected(type)}
          />
        ))}
      </div>

      {/* Cards */}
      <div className="mt-6 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="card overflow-hidden">
              <Skeleton className="h-48 rounded-none" />
              <div className="space-y-3 p-5">
                <Skeleton className="h-5 w-1/2" />
                <Skeleton className="h-3 w-4/5" />
                <Skeleton className="h-10 w-full" />
              </div>
            </div>
          ))}

        {filtered.map((facility) => (
          <FacilityCard key={facility.id} facility={facility} />
        ))}
      </div>

      {!isLoading && filtered.length === 0 && (
        <div className="card mt-6 p-10 text-center text-sm text-muted">
          No facilities match this filter.
        </div>
      )}
    </div>
  )
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-lg border px-3.5 py-1.5 text-sm font-medium transition-colors duration-150',
        active
          ? 'border-brand bg-brand-soft text-brand'
          : 'border-line bg-surface text-body hover:border-line-strong hover:text-ink',
      )}
    >
      {label}
    </button>
  )
}

function facilityTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    GYMNASIUM: 'Gymnasium',
    CAFETERIA: 'Cafeteria',
    AVR: 'Audio-Visual Room',
    MULTI_PURPOSE: 'Multi-Purpose Hall',
    OUTDOOR: 'Outdoor',
    OTHER: 'Other',
  }
  return labels[type] ?? type
}

function FacilityCard({ facility }: { facility: Facility }) {
  const availability = facility.availability
  const maintenance = facility.status === 'MAINTENANCE'

  return (
    <article className="card card-hover flex flex-col overflow-hidden">
      <div className="relative h-48">
        <FacilityImage
          name={facility.name}
          facilityType={facility.facility_type}
          src={facility.image}
          rounded="rounded-none"
        />
        <div className="absolute left-4 top-4">
          {maintenance ? (
            <Badge tone="orange">Under maintenance</Badge>
          ) : (
            <Badge tone="emerald">Available</Badge>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col p-5">
        <h2 className="text-lg font-semibold text-ink">{facility.name}</h2>
        <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-body">
          {facility.description}
        </p>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
          <div className="flex items-center gap-2 text-body">
            <Users className="size-4 text-muted" aria-hidden />
            <span>
              <span className="font-medium text-ink">{facility.capacity}</span> capacity
            </span>
          </div>
          <div className="flex items-center gap-2 text-body">
            <MapPin className="size-4 text-muted" aria-hidden />
            <span className="truncate">{facility.location}</span>
          </div>
        </dl>

        <div className="mt-4 flex items-center gap-2 rounded-lg bg-soft px-3 py-2.5 text-[13px] text-body">
          <CalendarDays className="size-4 shrink-0 text-muted" aria-hidden />
          {maintenance ? (
            <span>Reservations paused during maintenance</span>
          ) : (
            <span>
              Next available —{' '}
              <span className="font-medium text-ink">
                {nextAvailableLabel(facility)}
              </span>
            </span>
          )}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
          <Link
            to={`/facilities/${facility.id}`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand transition-colors hover:text-brand-dark"
          >
            View facility <ArrowRight className="size-4" />
          </Link>
          {availability.is_operational && (
            <span className="flex items-center gap-1.5 text-xs text-status-available">
              <span className="size-1.5 rounded-full bg-status-available" aria-hidden />
              Open for reservations
            </span>
          )}
        </div>
      </div>
    </article>
  )
}

function nextAvailableLabel(facility: Facility): string {
  const date = new Date()
  const dayOfWeek = date.getDay() // 0 = Sunday
  const todayIndex = dayOfWeek === 0 ? 6 : dayOfWeek - 1

  // Look for an operating day at or after today; fall back to Monday.
  for (const offset of nextSevenDays) {
    const candidate = new Date(`${offset}T00:00:00`)
    const index = candidate.getDay() === 0 ? 6 : candidate.getDay() - 1
    if (index < todayIndex) continue
    const hours = facility.operating_hours?.find((hour) => hour.day_of_week === index)
    if (hours && !hours.is_closed) {
      const label = format(new Date(`${offset}T00:00:00`), 'EEE, MMM d')
      return hours.open_time ? `${label} · ${formatTime(hours.open_time)}` : label
    }
  }
  return 'Check operating hours'
}