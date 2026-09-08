import { useCallback, useMemo, useState } from 'react'
import {
  addDays,
  addMonths,
  addWeeks,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  isWeekend,
  parseISO,
  startOfMonth,
  startOfWeek,
} from 'date-fns'
import { CalendarDays, ChevronLeft, ChevronRight, Clock, MapPin, Shield, User } from 'lucide-react'
import { useCalendarEvents, useEquipment, useFacilities } from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { PageHeader } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Form'
import { cn, formatTime, STATUS_META } from '@/lib/utils'
import { Modal } from '@/components/ui/Modal'
import type { CalendarEvent, ReservationStatus } from '@/lib/types'

type View = 'month' | 'week' | 'day'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SelectedDateInfo {
  date: Date
  events: CalendarEvent[]
}

// ---------------------------------------------------------------------------
// Status colors
// ---------------------------------------------------------------------------

/** Compact tinted pill used inside calendar cells + modal status chips. */
const STATUS_PILL_CLASSES: Record<ReservationStatus, string> = {
  PENDING: 'bg-status-pending-bg text-status-pending',
  APPROVED: 'bg-status-approved-bg text-status-approved',
  ACTIVE: 'bg-status-active-bg text-status-active',
  COMPLETED: 'bg-status-completed-bg text-status-completed',
  REJECTED: 'bg-status-rejected-bg text-status-rejected',
  CANCELLED: 'bg-status-cancelled-bg text-status-cancelled',
}

const STATUS_DOT_CLASSES: Record<ReservationStatus, string> = {
  PENDING: 'bg-status-pending',
  APPROVED: 'bg-status-approved',
  ACTIVE: 'bg-status-active',
  COMPLETED: 'bg-status-completed',
  REJECTED: 'bg-status-rejected',
  CANCELLED: 'bg-status-cancelled',
}

/** Solid block used by the week/day timeline events. */
const STATUS_BLOCK_CLASSES: Record<ReservationStatus, string> = {
  PENDING: 'bg-status-pending text-white border-status-pending',
  APPROVED: 'bg-status-approved text-white border-status-approved',
  ACTIVE: 'bg-status-active text-white border-status-active',
  COMPLETED: 'bg-status-completed text-white border-status-completed',
  REJECTED: 'bg-status-rejected text-white border-status-rejected',
  CANCELLED: 'bg-status-cancelled text-white border-status-cancelled',
}

export function CalendarPage() {
  const { user } = useAuth()
  const [view, setView] = useState<View>('month')
  const [cursor, setCursor] = useState(() => new Date())
  const [facility, setFacility] = useState('')
  const [status, setStatus] = useState('APPROVED')
  const [equipmentId, setEquipmentId] = useState('')
  const [selectedDate, setSelectedDate] = useState<SelectedDateInfo | null>(null)

  const isAdmin = user?.role === 'ADMIN' || user?.role === 'STAFF'

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

  const { data: events, isLoading, isError, error } = useCalendarEvents({
    start: format(range.start, 'yyyy-MM-dd'),
    end: format(range.end, 'yyyy-MM-dd'),
    // Empty filter values are omitted entirely — never facility=undefined.
    ...(facility ? { facility } : {}),
    ...(status ? { status } : {}),
    ...(equipmentId ? { equipment: equipmentId } : {}),
  })

  const navigate = (direction: 1 | -1) => {
    if (view === 'month') setCursor((v) => addMonths(v, direction))
    else if (view === 'week') setCursor((v) => addWeeks(v, direction))
    else setCursor((v) => addDays(v, direction))
  }

  const goToToday = () => setCursor(new Date())

  const title = useMemo(() => {
    if (view === 'month') return format(cursor, 'MMMM yyyy')
    if (view === 'week') {
      const start = startOfWeek(cursor, { weekStartsOn: 1 })
      const end = endOfWeek(cursor, { weekStartsOn: 1 })
      return `${format(start, 'MMM d')} – ${format(end, 'MMM d, yyyy')}`
    }
    return format(cursor, 'EEEE, MMMM d, yyyy')
  }, [view, cursor])

  // Group events by day (date string from the API — no UTC re-parsing, so a
  // reservation never shifts to the wrong calendar day).
  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const event of events ?? []) {
      const key = event.start.slice(0, 10)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(event)
    }
    return map
  }, [events])

  const handleDateClick = useCallback((day: Date, dayEvents: CalendarEvent[]) => {
    if (dayEvents.length === 0) return
    setSelectedDate({ date: day, events: dayEvents })
  }, [])

  const closeModal = useCallback(() => setSelectedDate(null), [])

  return (
    <div>
      <PageHeader
        eyebrow="SAS Calendar"
        title="Calendar"
        description="View facility reservations at a glance. Click any date with bookings to see details."
      />

      {/* ------------------------------------------------------------------ */}
      {/* Toolbar                                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
        {/* View toggle */}
        <div
          className="flex items-center gap-1 rounded-lg border border-line bg-surface p-1 shadow-sm"
          role="group"
          aria-label="Calendar view"
        >
          {(['month', 'week', 'day'] as View[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setView(item)}
              className={cn(
                'rounded-md px-4 py-2 text-[13px] font-semibold capitalize transition-colors duration-150',
                view === item
                  ? 'bg-brand text-white shadow-sm'
                  : 'text-body hover:bg-soft hover:text-ink',
              )}
              aria-pressed={view === item}
            >
              {item}
            </button>
          ))}
        </div>

        {/* Navigation + month title */}
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="flex size-10 items-center justify-center rounded-lg border border-line bg-surface text-body transition-colors duration-150 hover:bg-soft hover:text-ink"
              aria-label="Previous period"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              onClick={goToToday}
              className="h-10 rounded-lg border border-line bg-surface px-4 text-sm font-medium text-ink transition-colors duration-150 hover:bg-soft"
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => navigate(1)}
              className="flex size-10 items-center justify-center rounded-lg border border-line bg-surface text-body transition-colors duration-150 hover:bg-soft hover:text-ink"
              aria-label="Next period"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>

          <h2 className="text-2xl font-bold tracking-tight text-ink sm:text-[26px]">{title}</h2>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          <Select
            value={facility}
            onChange={(e) => setFacility(e.target.value)}
            aria-label="Filter by facility"
            className="w-full sm:w-44"
          >
            <option value="">All facilities</option>
            {(facilities ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select
            value={equipmentId}
            onChange={(e) => setEquipmentId(e.target.value)}
            aria-label="Filter by equipment"
            className="w-full sm:w-44"
          >
            <option value="">All equipment</option>
            {(equipment ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Filter by status"
            className="w-full sm:w-40"
          >
            <option value="APPROVED">Approved</option>
            <option value="PENDING">Pending</option>
            <option value="ACTIVE">Active</option>
            <option value="COMPLETED">Completed</option>
            <option value="REJECTED">Rejected</option>
            <option value="CANCELLED">Cancelled</option>
            <option value="">All statuses</option>
          </Select>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Calendar container                                                  */}
      {/* ------------------------------------------------------------------ */}
      <Card padding="none" className="mt-6 overflow-hidden">
        {isLoading ? (
          <CalendarSkeleton />
        ) : isError ? (
          <div className="flex flex-col items-start gap-3 p-6">
            <div className="flex items-center gap-3">
              <svg className="shrink-0 size-5 text-status-rejected" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <div>
                <p className="text-sm font-semibold text-status-rejected">Unable to load calendar</p>
                <p className="text-xs text-status-rejected/80">
                  We couldn't load reservations right now. Please try again.
                </p>
              </div>
            </div>
            {error instanceof Error && <p className="text-xs text-status-rejected/60">{error.message}</p>}
            <button
              type="button"
              onClick={() => setCursor((d) => new Date(d.getTime()))}
              className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand/90"
            >
              Try again
            </button>
          </div>
        ) : view === 'month' ? (
          <MonthView month={cursor} events={events ?? []} onDateClick={handleDateClick} />
        ) : view === 'week' ? (
          <WeekView days={weekDays(cursor)} events={events ?? []} onDateClick={handleDateClick} />
        ) : (
          <DayView
            day={cursor}
            events={(eventsByDay.get(format(cursor, 'yyyy-MM-dd')) ?? []).sort((a, b) =>
              a.start.localeCompare(b.start),
            )}
          />
        )}

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line bg-soft/60 px-5 py-3.5">
          {Object.entries(STATUS_META).map(([key, meta]) => (
            <span
              key={key}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
                meta.bg,
                meta.text,
              )}
            >
              <span className={cn('size-2 rounded-full', meta.dot)} aria-hidden />
              {meta.label}
            </span>
          ))}
        </div>
      </Card>

      {/* Date detail modal */}
      <Modal
        open={selectedDate !== null}
        onClose={closeModal}
        title={format(selectedDate?.date ?? new Date(), 'MMMM d, yyyy')}
        description={
          selectedDate
            ? `${selectedDate.events.length} reservation${selectedDate.events.length !== 1 ? 's' : ''}`
            : undefined
        }
        size="md"
        footer={
          <button
            type="button"
            onClick={closeModal}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand/90"
          >
            Close
          </button>
        }
      >
        {selectedDate && <DateDetailModal date={selectedDate} isAdmin={isAdmin} />}
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function weekDays(cursor: Date): Date[] {
  const start = startOfWeek(cursor, { weekStartsOn: 1 })
  return Array.from({ length: 7 }, (_, i) => addDays(start, i))
}

/** Group reservation counts by status, most frequent first. */
function groupByStatus(events: CalendarEvent[]): [ReservationStatus, number][] {
  const counts = events.reduce<Record<ReservationStatus, number>>(
    (acc, e) => {
      acc[e.status] = (acc[e.status] ?? 0) + 1
      return acc
    },
    {} as Record<ReservationStatus, number>,
  )
  return (Object.entries(counts) as [ReservationStatus, number][]).sort((a, b) => b[1] - a[1])
}

/** Human text for a status pill inside a calendar cell. */
function indicatorLabel(status: ReservationStatus, count: number, multipleGroups: boolean): string {
  const label = STATUS_META[status].label.toLowerCase()
  if (!multipleGroups && count === 1) return '1 reservation'
  return `${count} ${label}`
}

function statusSummary(groups: [ReservationStatus, number][]): string {
  return groups.map(([s, c]) => `${c} ${STATUS_META[s].label.toLowerCase()}`).join(', ')
}

// ---------------------------------------------------------------------------
// Month view — one unified grid
// ---------------------------------------------------------------------------

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Soft day-header tints: weekday indigo, Saturday cool gray, Sunday warm gray. */
const DAY_HEADER_TINTS = [
  'bg-indigo-50/80 text-indigo-900/80',
  'bg-indigo-50/80 text-indigo-900/80',
  'bg-indigo-50/80 text-indigo-900/80',
  'bg-indigo-50/80 text-indigo-900/80',
  'bg-indigo-50/80 text-indigo-900/80',
  'bg-slate-100/80 text-slate-600',
  'bg-stone-100/80 text-stone-600',
]

function MonthView({
  month,
  events,
  onDateClick,
}: {
  month: Date
  events: CalendarEvent[]
  onDateClick: (day: Date, dayEvents: CalendarEvent[]) => void
}) {
  const today = new Date()

  // 42 cells: leading/lagging days of adjacent months included as secondary.
  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 })
    return Array.from({ length: 42 }, (_, i) => addDays(start, i))
  }, [month])

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
      <div className="min-w-[576px]">
        {/* Day-of-week header */}
        <div className="grid grid-cols-7 border-b border-line">
          {DAY_LABELS.map((label, i) => (
            <div
              key={label}
              className={cn(
                'flex items-center justify-center py-2.5 text-[11px] font-bold uppercase tracking-[0.08em]',
                DAY_HEADER_TINTS[i],
              )}
            >
              {label}
            </div>
          ))}
        </div>

        {/* Date grid — visually connected, no per-cell cards */}
        <div className="grid grid-cols-7 border-t border-line">
          {days.map((day) => (
            <MonthCell
              key={day.toISOString()}
              day={day}
              month={month}
              today={today}
              events={eventsByDay.get(format(day, 'yyyy-MM-dd')) ?? []}
              onDateClick={onDateClick}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function MonthCell({
  day,
  month,
  today,
  events,
  onDateClick,
}: {
  day: Date
  month: Date
  today: Date
  events: CalendarEvent[]
  onDateClick: (day: Date, dayEvents: CalendarEvent[]) => void
}) {
  const isToday = isSameDay(day, today)
  const isCurrentMonth = isSameMonth(day, month)
  const isWeekendDay = isWeekend(day)
  const hasReservations = events.length > 0
  const groups = useMemo(() => groupByStatus(events), [events])

  const background = !isCurrentMonth
    ? 'bg-neutral-50/60'
    : isToday
      ? 'bg-brand-soft/40'
      : isWeekendDay
        ? day.getDay() === 6
          ? 'bg-slate-50/60'
          : 'bg-stone-50/60'
        : 'bg-surface'

  const ariaLabel = hasReservations
    ? `${format(day, 'MMMM d, yyyy')} — ${events.length} reservation${events.length > 1 ? 's' : ''} (${statusSummary(groups)}). Click to view details.`
    : format(day, 'MMMM d, yyyy')

  const content = (
    <>
      {/* Date number — top-left, never centered */}
      <span
        className={cn(
          'inline-flex size-7 items-center justify-center rounded-full text-[13px] font-semibold tabular-nums transition-colors duration-150',
          isToday
            ? 'bg-brand text-white shadow-sm'
            : isCurrentMonth
              ? isWeekendDay
                ? 'text-neutral-500'
                : 'text-ink'
              : 'text-neutral-400',
        )}
      >
        {format(day, 'd')}
      </span>

      {/* Compact reservation indicators — pinned to the bottom, never expand the row */}
      {hasReservations && (
        <div className="mt-auto flex flex-col items-start gap-1">
          {groups.slice(0, 2).map(([status, count]) => (
            <span
              key={status}
              className={cn(
                'inline-flex max-w-full items-center gap-1 truncate rounded-full px-1.5 py-1 text-[10px] font-semibold leading-none',
                STATUS_PILL_CLASSES[status],
              )}
              title={`${count} ${STATUS_META[status].label.toLowerCase()} reservation${count > 1 ? 's' : ''}`}
            >
              <span className={cn('size-1.5 shrink-0 rounded-full', STATUS_DOT_CLASSES[status])} aria-hidden />
              <span className="truncate">{indicatorLabel(status, count, groups.length > 1)}</span>
            </span>
          ))}
          {groups.length > 2 && (
            <span className="pl-1 text-[10px] font-semibold text-body">
              +{groups.length - 2} more
            </span>
          )}
        </div>
      )}
    </>
  )

  const cellBase = cn(
    'relative flex min-h-[84px] flex-col items-start gap-1 overflow-hidden border-r border-b border-line/80 p-1.5 text-left sm:min-h-[108px] sm:p-2',
    background,
  )

  if (hasReservations) {
    return (
      <button
        type="button"
        onClick={() => onDateClick(day, events)}
        title={`View ${events.length} reservation${events.length > 1 ? 's' : ''}`}
        aria-label={ariaLabel}
        aria-haspopup="dialog"
        className={cn(
          cellBase,
          'cursor-pointer transition-colors duration-150 hover:bg-brand-soft/70 focus-visible:bg-brand-soft/70',
        )}
      >
        {content}
      </button>
    )
  }

  return (
    <div className={cellBase} aria-label={ariaLabel}>
      {content}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Week view
// ---------------------------------------------------------------------------

function WeekView({
  days,
  events,
  onDateClick,
}: {
  days: Date[]
  events: CalendarEvent[]
  onDateClick: (day: Date, dayEvents: CalendarEvent[]) => void
}) {
  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const event of events) {
      const key = event.start.slice(0, 10)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(event)
    }
    return map
  }, [events])

  const today = new Date()
  const HOURS = Array.from({ length: 17 }, (_, i) => i + 6) // 06:00–22:00
  const gridCols = 'grid-cols-[56px_1fr_1fr_1fr_1fr_1fr_1fr_1fr]'

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[760px]">
        {/* Header */}
        <div className={cn('grid border-b border-line', gridCols)}>
          <div />
          {days.map((day) => {
            const isToday = isSameDay(day, today)
            const isWeekendDay = isWeekend(day)
            return (
              <div
                key={day.toISOString()}
                className={cn(
                  'flex flex-col items-center justify-center gap-1 py-2.5 text-center',
                  isToday
                    ? 'bg-brand-soft/50'
                    : isWeekendDay
                      ? day.getDay() === 6
                        ? 'bg-slate-100/70'
                        : 'bg-stone-100/70'
                      : 'bg-indigo-50/50',
                )}
              >
                <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-indigo-900/70">
                  {format(day, 'EEE')}
                </p>
                <p
                  className={cn(
                    'flex size-7 items-center justify-center rounded-full text-[13px] font-semibold tabular-nums',
                    isToday ? 'bg-brand text-white shadow-sm' : isWeekendDay ? 'text-neutral-500' : 'text-ink',
                  )}
                >
                  {format(day, 'd')}
                </p>
              </div>
            )
          })}
        </div>

        {/* Time grid */}
        <div className={cn('grid', gridCols)}>
          <div className="flex flex-col gap-px">
            {HOURS.map((hour) => (
              <div key={hour} className="flex h-12 items-start justify-end pr-2 pt-0.5 text-right text-[11px] text-muted">
                {formatHour(hour)}
              </div>
            ))}
          </div>

          {days.map((day) => {
            const dayEvents = (eventsByDay.get(format(day, 'yyyy-MM-dd')) ?? []).sort((a, b) =>
              a.start.localeCompare(b.start),
            )
            const isToday = isSameDay(day, today)
            const isWeekendDay = isWeekend(day)

            return (
              <div
                key={day.toISOString()}
                className={cn(
                  'relative flex flex-col border-l border-line/70',
                  isToday ? 'bg-brand-soft/20' : isWeekendDay ? 'bg-neutral-50/40' : 'bg-surface',
                )}
              >
                {HOURS.map((hour) => (
                  <div key={hour} className="h-12 border-b border-line/60" />
                ))}
                {dayEvents.map((event) => (
                  <WeekEventBlock key={event.id} event={event} day={day} onDateClick={onDateClick} />
                ))}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function WeekEventBlock({
  event,
  day,
  onDateClick,
}: {
  event: CalendarEvent
  day: Date
  onDateClick: (day: Date, dayEvents: CalendarEvent[]) => void
}) {
  const startMinutes = timeToMinutes(event.start.slice(11, 16))
  const endMinutes = timeToMinutes(event.end.slice(11, 16))
  const top = ((startMinutes - 6 * 60) / 60) * 48
  const height = Math.max(((endMinutes - startMinutes) / 60) * 48, 20)
  const dayDate = format(day, 'yyyy-MM-dd')
  const eventDate = event.start.slice(0, 10)

  if (dayDate !== eventDate) return null

  return (
    <button
      type="button"
      onClick={() => onDateClick(day, [event])}
      className={cn(
        'absolute left-1 right-1 rounded-md border-l-2 px-2 py-1 text-left shadow-sm transition-shadow duration-150 hover:shadow-md',
        STATUS_BLOCK_CLASSES[event.status],
      )}
      style={{ top: `${top + 1}px`, height: `${height - 2}px` }}
      title={`View ${event.title}`}
    >
      <p className="truncate text-[11px] font-semibold leading-tight">{event.title}</p>
      <p className="mt-0.5 truncate text-[10px] opacity-80">
        {formatTime(event.start.slice(11, 16))} – {formatTime(event.end.slice(11, 16))}
      </p>
      <p className="mt-0.5 truncate text-[10px] opacity-70">{event.facility}</p>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Day view
// ---------------------------------------------------------------------------

function DayView({ day, events: dayEvents }: { day: Date; events: CalendarEvent[] }) {
  const HOURS = Array.from({ length: 17 }, (_, i) => i + 6)
  const today = new Date()
  const isToday = isSameDay(day, today)

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[480px]">
        {/* Header */}
        <div
          className={cn(
            'flex items-center justify-center gap-3 border-b border-line px-4 py-4',
            isToday ? 'bg-brand-soft/40' : 'bg-soft/60',
          )}
        >
          <CalendarDays className="size-5 text-brand" />
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-indigo-900/70">
              {format(day, 'EEEE')}
            </p>
            <p className={cn('text-xl font-semibold', isToday ? 'text-brand' : 'text-ink')}>
              {format(day, 'MMMM d, yyyy')}
            </p>
          </div>
        </div>

        {/* Timeline */}
        <div className="flex flex-col border-l border-line/70">
          {HOURS.map((hour) => (
            <div key={hour} className="flex h-12 border-b border-line/60">
              <div className="flex w-12 shrink-0 items-start justify-end pr-3 pt-0.5 text-right text-[11px] text-muted">
                {formatHour(hour)}
              </div>
              <div className="flex-1">
                {dayEvents
                  .filter(
                    (e) =>
                      timeToMinutes(e.start.slice(11, 16)) <= hour * 60 &&
                      timeToMinutes(e.end.slice(11, 16)) > hour * 60,
                  )
                  .map((event) => (
                    <div
                      key={event.id}
                      className={cn(
                        'mb-1 rounded-md border-l-2 px-3 py-1.5 text-left shadow-sm',
                        STATUS_BLOCK_CLASSES[event.status],
                      )}
                    >
                      <p className="truncate text-[12px] font-semibold">{event.title}</p>
                      <p className="mt-0.5 text-[11px] opacity-80">
                        {formatTime(event.start.slice(11, 16))} – {formatTime(event.end.slice(11, 16))}
                      </p>
                      <p className="mt-0.5 text-[10px] opacity-70">{event.facility}</p>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function CalendarSkeleton() {
  return (
    <div className="p-6" aria-hidden>
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="skeleton h-5 rounded" />
        ))}
      </div>
      <div className="mt-2 grid grid-cols-7 border-t border-line">
        {Array.from({ length: 42 }).map((_, i) => (
          <div key={i} className="skeleton h-24 rounded-none border-r border-b border-line/40" />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Date detail modal content
// ---------------------------------------------------------------------------

function DateDetailModal({ date, isAdmin }: { date: SelectedDateInfo; isAdmin: boolean }) {
  const { events } = date
  const sortedEvents = [...events].sort((a, b) => a.start.localeCompare(b.start))

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 overflow-y-auto pr-1" style={{ maxHeight: 'calc(90vh - 300px)' }}>
        {sortedEvents.map((event) => (
          <ReservationCard key={event.id} event={event} isAdmin={isAdmin} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Reservation card (role-aware)
// ---------------------------------------------------------------------------

function ReservationCard({ event, isAdmin }: { event: CalendarEvent; isAdmin: boolean }) {
  const statusMeta = STATUS_META[event.status]

  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-line/60 bg-surface p-4 shadow-sm transition-shadow duration-150 hover:shadow-md">
      {/* Status badge */}
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold',
            STATUS_PILL_CLASSES[event.status],
          )}
        >
          <span className={cn('size-1.5 rounded-full', statusMeta.dot)} aria-hidden />
          {statusMeta.label}
        </span>
      </div>

      {/* Event name */}
      <p className="text-sm font-semibold leading-snug text-ink">{event.title}</p>

      {/* Facility + time + date */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-body">
        <span className="flex items-center gap-1.5">
          <MapPin className="size-3.5 text-brand/70" aria-hidden />
          {event.facility}
        </span>
        <span className="flex items-center gap-1.5">
          <Clock className="size-3.5 text-brand/70" aria-hidden />
          {formatTime(event.start.slice(11, 16))} – {formatTime(event.end.slice(11, 16))}
        </span>
        <span className="flex items-center gap-1.5">
          <CalendarDays className="size-3.5 text-brand/70" aria-hidden />
          {format(parseISO(event.start.slice(0, 10)), 'MMM d, yyyy')}
        </span>
      </div>

      {/* Reservation reference */}
      <div className="flex items-center gap-1.5 rounded-lg bg-soft px-2.5 py-1 text-xs font-mono text-muted">
        <User className="size-3 text-brand/50" aria-hidden />
        {event.reservation_id}
      </div>

      {/* Admin-only extra info — the backend only sends these fields to SAS staff */}
      {isAdmin && event.is_sas_staff && (
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 border-t border-line/60 pt-2.5 text-xs text-neutral-500">
          {event.requester_type && event.requester_type !== 'CAMPUS' && (
            <span className="flex items-center gap-1.5">
              <Shield className="size-3.5 text-neutral-400" aria-hidden />
              {event.requester_type === 'EXTERNAL' ? 'External' : event.requester_type}
            </span>
          )}
          {event.organization && (
            <span className="flex items-center gap-1.5">
              <User className="size-3.5 text-neutral-400" aria-hidden />
              {event.organization}
            </span>
          )}
          {event.contact_person && (
            <span className="flex items-center gap-1.5">
              <span className="text-neutral-400">Contact:</span> {event.contact_person}
            </span>
          )}
          {event.created_by && (
            <span className="flex items-center gap-1.5">
              <span className="text-neutral-400">Created by:</span> {event.created_by}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeToMinutes(value: string): number {
  const [hours, minutes] = value.split(':').map(Number)
  return hours * 60 + minutes
}

function formatHour(hour: number): string {
  const date = new Date('2026-01-01T00:00:00+08:00')
  date.setHours(hour, 0, 0, 0)
  return format(date, 'ha')
}