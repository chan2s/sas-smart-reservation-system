import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addDays,
  addMonths,
  addWeeks,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from 'date-fns'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useCalendarEvents, useEquipment, useFacilities } from '@/hooks/queries'
import { PageHeader } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { MonthGrid } from '@/components/calendar/MonthGrid'
import { Select } from '@/components/ui/Form'
import { cn, formatTime, STATUS_META } from '@/lib/utils'
import type { CalendarEvent, ReservationStatus } from '@/lib/types'

type View = 'month' | 'week' | 'day'

const statusClasses: Record<ReservationStatus, string> = {
  PENDING: 'bg-status-pending-bg text-status-pending border-status-pending/25',
  APPROVED: 'bg-status-approved-bg text-status-approved border-status-approved/25',
  ACTIVE: 'bg-status-active-bg text-status-active border-status-active/25',
  COMPLETED: 'bg-status-completed-bg text-status-completed border-status-completed/25',
  REJECTED: 'bg-status-rejected-bg text-status-rejected border-status-rejected/25',
  CANCELLED: 'bg-status-cancelled-bg text-status-cancelled border-status-cancelled/25',
}

export function CalendarPage() {
  const [view, setView] = useState<View>('month')
  const [cursor, setCursor] = useState(() => new Date())
  const [facility, setFacility] = useState('')
  const [status, setStatus] = useState('')
  const [equipmentId, setEquipmentId] = useState('')

  const { data: facilities } = useFacilities()
  const { data: equipment } = useEquipment()

  const range = useMemo(() => {
    if (view === 'month') {
      return { start: startOfMonth(cursor), end: endOfMonth(cursor) }
    }
    if (view === 'week') {
      return { start: startOfWeek(cursor, { weekStartsOn: 1 }), end: endOfWeek(cursor, { weekStartsOn: 1 }) }
    }
    return { start: cursor, end: cursor }
  }, [view, cursor])

  const { data: events, isLoading } = useCalendarEvents({
    start: format(range.start, 'yyyy-MM-dd'),
    end: format(range.end, 'yyyy-MM-dd'),
    facility: facility || undefined,
    status: status || undefined,
    equipment: equipmentId || undefined,
  })

  const navigate = (direction: 1 | -1) => {
    if (view === 'month') setCursor((value) => addMonths(value, direction))
    else if (view === 'week') setCursor((value) => addWeeks(value, direction))
    else setCursor((value) => addDays(value, direction))
  }

  const title = useMemo(() => {
    if (view === 'month') return format(cursor, 'MMMM yyyy')
    if (view === 'week') {
      const start = startOfWeek(cursor, { weekStartsOn: 1 })
      const end = endOfWeek(cursor, { weekStartsOn: 1 })
      return `${format(start, 'MMM d')} – ${format(end, 'MMM d, yyyy')}`
    }
    return format(cursor, 'EEEE, MMMM d, yyyy')
  }, [view, cursor])

  return (
    <div>
      <PageHeader
        eyebrow="SAS Calendar"
        title="Calendar"
        description="See every reservation across all facilities at a glance."
      />

      {/* Toolbar */}
      <div className="mt-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-line bg-surface p-0.5">
            {(['month', 'week', 'day'] as View[]).map((item) => (
              <button
                key={item}
                onClick={() => setView(item)}
                className={cn(
                  'rounded-md px-3.5 py-1.5 text-sm font-medium capitalize transition-colors duration-150',
                  view === item ? 'bg-brand text-white shadow-sm' : 'text-body hover:text-ink',
                )}
                aria-pressed={view === item}
              >
                {item}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => navigate(-1)}
              className="flex size-9 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-surface hover:text-ink"
              aria-label="Previous period"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              onClick={() => setCursor(new Date())}
              className="rounded-lg border border-line px-3 py-2 text-sm font-medium text-body transition-colors hover:bg-surface hover:text-ink"
            >
              Today
            </button>
            <button
              onClick={() => navigate(1)}
              className="flex size-9 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-surface hover:text-ink"
              aria-label="Next period"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>

          <h2 className="ml-1 hidden text-lg font-semibold text-ink sm:block">{title}</h2>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <Select value={facility} onChange={(event) => setFacility(event.target.value)} aria-label="Filter by facility" className="w-full sm:w-44">
            <option value="">All facilities</option>
            {(facilities ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select value={equipmentId} onChange={(event) => setEquipmentId(event.target.value)} aria-label="Filter by equipment" className="w-full sm:w-44">
            <option value="">All equipment</option>
            {(equipment ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by status" className="w-full sm:w-40">
            <option value="">All statuses</option>
            {Object.entries(STATUS_META).map(([key, meta]) => (
              <option key={key} value={key}>
                {meta.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <h2 className="mb-4 mt-4 text-lg font-semibold text-ink lg:hidden">{title}</h2>

      {/* Views */}
      <Card className="mt-4 p-4 sm:p-5">
        {isLoading ? (
          <div className="h-96 animate-pulse rounded-lg bg-soft" aria-hidden />
        ) : view === 'month' ? (
          <MonthView month={cursor} events={events ?? []} />
        ) : view === 'week' ? (
          <WeekView days={weekDays(cursor)} events={events ?? []} />
        ) : (
          <WeekView days={[cursor]} events={events ?? []} />
        )}
      </Card>
    </div>
  )
}

function weekDays(cursor: Date): Date[] {
  const start = startOfWeek(cursor, { weekStartsOn: 1 })
  return Array.from({ length: 7 }, (_, index) => addDays(start, index))
}

// ---------------------------------------------------------------------------
// Month
// ---------------------------------------------------------------------------

function MonthView({ month, events }: { month: Date; events: CalendarEvent[] }) {
  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const event of events) {
      const key = event.start.slice(0, 10)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(event)
    }
    return map
  }, [events])

  return (
    <div>
      <MonthGrid
        month={month}
        renderDay={(day) => {
          const dayEvents = eventsByDay.get(format(day, 'yyyy-MM-dd')) ?? []
          if (dayEvents.length === 0) return null
          const shown = dayEvents.slice(0, 2)
          return (
            <span className="mt-1 w-full space-y-0.5 px-0.5" aria-hidden>
              {shown.map((event) => (
                <span
                  key={event.id}
                  className={cn(
                    'block truncate rounded px-1 py-px text-left text-[10px] font-medium leading-4',
                    statusClasses[event.status],
                  )}
                >
                  {event.title}
                </span>
              ))}
              {dayEvents.length > 2 && (
                <span className="block px-1 text-[10px] font-semibold text-muted">
                  +{dayEvents.length - 2} more
                </span>
              )}
            </span>
          )
        }}
      />
      <div className="mt-4 flex flex-wrap gap-4 border-t border-line pt-4 text-xs text-body">
        {Object.entries(STATUS_META).map(([key, meta]) => (
          <span key={key} className="flex items-center gap-1.5">
            <span className={cn('size-2 rounded-full', meta.dot)} aria-hidden />
            {meta.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Week / day
// ---------------------------------------------------------------------------

const HOURS = Array.from({ length: 17 }, (_, index) => index + 6) // 06:00–22:00

function WeekView({ days, events }: { days: Date[]; events: CalendarEvent[] }) {
  const today = new Date()
  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const event of events) {
      const key = event.start.slice(0, 10)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(event)
    }
    return map
  }, [events])

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[760px]">
        {/* Header */}
        <div className={cn('grid', days.length === 1 ? 'grid-cols-1' : 'grid-cols-[56px_1fr_1fr_1fr_1fr_1fr_1fr_1fr]')}>
          <div />
          {days.map((day) => {
            const isToday = isSameDay(day, today)
            return (
              <div key={day.toISOString()} className="px-1 pb-3 text-center">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                  {format(day, 'EEE')}
                </p>
                <p
                  className={cn(
                    'mx-auto mt-1 flex size-8 items-center justify-center rounded-full text-sm font-semibold',
                    isToday ? 'bg-brand text-white' : 'text-ink',
                  )}
                >
                  {format(day, 'd')}
                </p>
              </div>
            )
          })}
        </div>

        {/* Time grid */}
        <div
          className={cn('grid', days.length === 1 ? 'grid-cols-1' : 'grid-cols-[56px_1fr_1fr_1fr_1fr_1fr_1fr_1fr]')}
        >
          <div className="relative">
            {HOURS.map((hour) => (
              <div key={hour} className="relative h-12 -translate-y-1/2 pr-2 text-right text-[11px] tabular-nums text-muted">
                <span className="absolute right-2 top-1/2 -translate-y-1/2">{formatHour(hour)}</span>
              </div>
            ))}
          </div>

          {days.map((day) => {
            const dayEvents = (eventsByDay.get(format(day, 'yyyy-MM-dd')) ?? []).sort((a, b) =>
              a.start.localeCompare(b.start),
            )
            const isToday = isSameDay(day, today)
            return (
              <div key={day.toISOString()} className={cn('relative border-l border-line', isToday && 'bg-brand-soft/30')}>
                {HOURS.map((hour) => (
                  <div key={hour} className="h-12 border-b border-line/70" />
                ))}
                {dayEvents.map((event) => (
                  <EventBlock key={event.id} event={event} day={day} />
                ))}
                {dayEvents.length === 0 && (
                  <p className="absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-xs text-muted">
                    No events
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function EventBlock({ event, day }: { event: CalendarEvent; day: Date }) {
  const startMinutes = timeToMinutes(event.start.slice(11, 16))
  const endMinutes = timeToMinutes(event.end.slice(11, 16))
  const top = ((startMinutes - 6 * 60) / 60) * 48
  const height = Math.max(((endMinutes - startMinutes) / 60) * 48, 20)
  const outsideMonth = !isSameMonth(day, new Date(`${event.start.slice(0, 10)}T00:00:00`))

  if (outsideMonth) return null

  return (
    <Link
      to={`/reservations/${event.id}`}
      className={cn(
        'absolute inset-x-1 z-10 overflow-hidden rounded-lg border px-2 py-1.5 shadow-card transition-transform duration-150 hover:scale-[1.01]',
        statusClasses[event.status],
      )}
      style={{ top: `${top + 1}px`, height: `${height - 2}px` }}
    >
      <p className="truncate text-[11px] font-semibold leading-tight">{event.title}</p>
      <p className="truncate text-[10px] opacity-80">
        {formatTime(event.start.slice(11, 16))} – {formatTime(event.end.slice(11, 16))}
      </p>
      <p className="hidden truncate text-[10px] opacity-70 lg:block">{event.facility}</p>
    </Link>
  )
}

function timeToMinutes(value: string): number {
  const [hours, minutes] = value.split(':').map(Number)
  return hours * 60 + minutes
}

function formatHour(hour: number): string {
  const date = new Date()
  date.setHours(hour, 0, 0, 0)
  return format(date, 'ha')
}