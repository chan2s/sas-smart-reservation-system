import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { AlertTriangle, CalendarDays, CheckCircle2, Info, Loader2, XCircle } from 'lucide-react'
import { endOfMonth, format, startOfMonth } from 'date-fns'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Select } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'
import { AvailabilityCheck } from '@/components/reservations/AvailabilityCheck'
import { ReservationEventsModal } from '@/components/reservations/ReservationEventsModal'
import { PricingBreakdown } from '@/components/reservations/PricingBreakdown'
import { CalendarHeader, MonthGrid } from '@/components/calendar/MonthGrid'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { cn, equipmentPrimaryImageUrl, facilityPrimaryImageUrl, formatTime } from '@/lib/utils'
import { useBookedDates } from '@/hooks/queries'
import type { ContactDraft, EventDetailsDraft } from '@/lib/reservationDraft'
import type {
  AlternativeSlot,
  AvailabilityCheck as AvailabilityCheckResult,
  BookedDateEvent,
  EventType,
  PricingQuote,
  ReservableResource,
} from '@/lib/types'

/**
 * Shared reservation workflow steps for the new-reservation wizard
 * (ReservationWizardPage): facility, schedule, the merged details & resources
 * step (see DetailsStep) and the review summary.
 */

/**
 * System-wide earliest bookable start time. Reservations may never start
 * before 8:00 AM, regardless of how early a facility opens. The backend
 * enforces the same minimum, so this is a convenience, not the source of
 * truth.
 */
export const EARLIEST_START_TIME = '08:00'
const EARLIEST_START_MINUTES = 8 * 60
const DAY_AVAILABILITY = {
  available: { label: 'Available', marker: 'bg-status-available' },
  partial: { label: 'Partially booked', marker: 'bg-status-pending' },
  full: { label: 'Fully booked', marker: 'bg-status-rejected' },
  unavailable: { label: 'Unavailable', marker: 'bg-faint' },
} as const
const EMPTY_BOOKED_EVENTS: BookedDateEvent[] = []

function minutesSinceMidnight(time: string): number {
  const [hours, minutes] = time.split(':').map(Number)
  return hours * 60 + minutes
}

/** Use the backend's half-open interval rule: end-to-start adjacency is free. */
function hasReservationConflict(events: BookedDateEvent[], requestedStart: number, requestedEnd: number): boolean {
  return events.some((event) =>
    minutesSinceMidnight(event.start_time) < requestedEnd &&
    minutesSinceMidnight(event.end_time) > requestedStart,
  )
}

export const EVENT_TYPE_OPTIONS: [EventType, string][] = [
  ['SEMINAR', 'Seminar'],
  ['MEETING', 'Meeting'],
  ['WORKSHOP', 'Workshop'],
  ['TRAINING', 'Training'],
  ['SPORTS', 'Sports Event'],
  ['CONFERENCE', 'Conference'],
  ['RECOGNITION', 'Recognition Program'],
  ['ORIENTATION', 'Orientation'],
  ['CULTURAL', 'Cultural Event'],
  ['ACADEMIC', 'Academic Event'],
  ['OTHER', 'Other'],
]

export function eventTypeLabel(type: EventType): string {
  const option = EVENT_TYPE_OPTIONS.find(([value]) => value === type)
  return option ? option[1] : type
}

// ---------------------------------------------------------------------------
// Availability state
// ---------------------------------------------------------------------------

/**
 * Explicit availability lifecycle. "Not yet checked" (IDLE) is deliberately
 * distinct from "checked and available" (AVAILABLE) so the wizard never treats
 * a filled-in form as a passed availability check.
 */
export type AvailabilityStatus = 'IDLE' | 'CHECKING' | 'AVAILABLE' | 'UNAVAILABLE' | 'ERROR'

export const AVAILABILITY_STATUS_MESSAGE: Record<AvailabilityStatus, string> = {
  IDLE: 'Check availability before continuing.',
  CHECKING: 'Checking availability…',
  AVAILABLE: 'Facility and selected resources are available.',
  UNAVAILABLE:
    'The selected facility or one or more resources are unavailable for this date and time.',
  ERROR: 'We could not check availability. Please try again.',
}

/**
 * Headline status for the availability check. Sits above the detailed report so
 * the exact state (idle / checking / available / unavailable / error) is always
 * spelled out, independent of whether a report has arrived yet.
 */
export function AvailabilityStatusNotice({ status }: { status: AvailabilityStatus }) {
  const message = AVAILABILITY_STATUS_MESSAGE[status]
  const tone = {
    IDLE: 'border-line bg-soft text-body',
    CHECKING: 'border-line bg-soft text-body',
    AVAILABLE: 'border-status-available/25 bg-status-available-bg text-status-available',
    UNAVAILABLE: 'border-status-rejected/25 bg-status-rejected-bg text-status-rejected',
    ERROR: 'border-status-pending/25 bg-status-pending-bg text-status-pending',
  }[status]

  const icon = {
    IDLE: <Info className="size-4 shrink-0" aria-hidden />,
    CHECKING: <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />,
    AVAILABLE: <CheckCircle2 className="size-4 shrink-0" aria-hidden />,
    UNAVAILABLE: <XCircle className="size-4 shrink-0" aria-hidden />,
    ERROR: <AlertTriangle className="size-4 shrink-0" aria-hidden />,
  }[status]

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('flex items-start gap-2.5 rounded-xl border px-4 py-3', tone)}
    >
      <span className="mt-0.5">{icon}</span>
      <p className="text-sm font-medium leading-relaxed">{message}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 1 — Facility
// ---------------------------------------------------------------------------

export function StepFacility({
  facilities,
  selected,
  onSelect,
}: {
  facilities: { id: number; name: string; facility_type: string; facility_type_label: string; description: string; capacity: number; location: string; image: string | null; images?: { id: number | null; url: string; is_primary: boolean; order: number }[]; is_active: boolean; status: string }[]
  selected: number | null
  onSelect: (id: number) => void
}) {
  return (
    <section aria-label="Choose facility">
      <h2 className="text-lg font-semibold text-ink">Choose facility</h2>
      <p className="mt-1 text-sm text-body">Select the space you need for your event.</p>

      {/* Disabled/archived facilities are already excluded by the backend, so
          this list only ever contains reservable spaces. */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {facilities.map((facility) => {
          const isSelected = selected === facility.id
          const unavailable = facility.status === 'MAINTENANCE' || facility.is_active === false
          return (
            <button
              key={facility.id}
              type="button"
              onClick={() => !unavailable && onSelect(facility.id)}
              aria-pressed={isSelected}
              disabled={unavailable}
              className={cn(
                'card card-hover overflow-hidden text-left transition-shadow',
                isSelected && 'ring-2 ring-brand ring-offset-2',
                unavailable && 'cursor-not-allowed opacity-60',
              )}
            >
              <div className="relative h-28">
                <FacilityImage
                  name={facility.name}
                  facilityType={facility.facility_type as never}
                  src={facilityPrimaryImageUrl(facility)}
                  rounded="rounded-none"
                />
                <div className="absolute left-3 top-3">
                  {unavailable ? (
                    <Badge tone="orange">Unavailable</Badge>
                  ) : isSelected ? (
                    <Badge tone="brand">Selected</Badge>
                  ) : (
                    <Badge tone="emerald">Available</Badge>
                  )}
                </div>
              </div>
              <div className="p-4">
                <p className="text-[15px] font-semibold text-ink">{facility.name}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {facility.facility_type_label} · Capacity {facility.capacity}
                </p>
                <p className="mt-2 line-clamp-2 text-[13px] text-body">{facility.description}</p>
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Step 2 — Schedule
// ---------------------------------------------------------------------------

export interface ScheduleProps {
  facility?: { id: number; name: string; status: string; is_active?: boolean; operating_hours?: { day_of_week: number; open_time: string | null; close_time: string | null; is_closed: boolean }[] }
  excludeReservationId?: number | null
  date: Date | null
  onDateChange: (date: Date) => void
  /** When true, the caller still considers this schedule slot valid for
   *  availability purposes (used to clear stale availability state on the
   *  parent when the date becomes invalid). */
  dateInvalid?: boolean
  /** True when the selected date is within the 2-day cancellation window
   *  (today/tomorrow) — shows the policy notice (such reservations cannot
   *  be cancelled once submitted). */
  isCancellationRestricted?: boolean
  startTime: string
  endTime: string
  onStartTime: (value: string) => void
  onEndTime: (value: string) => void
  report: AvailabilityCheckResult | null
  checking: boolean
  /** Explicit availability state — drives the headline notice and, in the
   *  parent wizard, whether Continue is enabled. */
  availabilityStatus?: AvailabilityStatus
  onUseAlternative: (alternative: AlternativeSlot) => void
}

/**
 * Calendar-date comparison in Asia/Manila so "today" matches the backend's
 * notion of today (the server rejects past/today reservations using its local
 * Asia/Manila clock).
 */
export function manilaCalendarDate(): Date {
  const now = new Date()
  const tz = Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Manila',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  const [y, m, d] = tz.formatToParts(now).filter((p) => p.type !== 'literal').map((p) => p.value)
  return new Date(Number(y), Number(m) - 1, Number(d))
}

/** Current wall-clock time in Asia/Manila as minutes since midnight. */
function manilaNowMinutes(): number {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Manila',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(new Date())
  const hour = Number(parts.find((part) => part.type === 'hour')?.value ?? '0')
  const minute = Number(parts.find((part) => part.type === 'minute')?.value ?? '0')
  return hour * 60 + minute
}

export function StepSchedule({
  facility,
  excludeReservationId,
  date,
  onDateChange,
  startTime,
  endTime,
  onStartTime,
  onEndTime,
  report,
  checking,
  availabilityStatus = 'IDLE',
  onUseAlternative,
  dateInvalid,
  isCancellationRestricted,
}: ScheduleProps) {
  const [month, setMonth] = useState(() => date ?? new Date())
  // Two deliberately separate views: the calendar only picks a reservation
  // date; the booked-dates view only inspects existing reservations.
  const [view, setView] = useState<'calendar' | 'booked'>('calendar')
  const [selectedBookedDate, setSelectedBookedDate] = useState<string | null>(null)
  const [eventsModalOpen, setEventsModalOpen] = useState(false)
  const [nowMinutes, setNowMinutes] = useState(() => manilaNowMinutes())
  const monthStart = format(startOfMonth(month), 'yyyy-MM-dd')
  const monthEnd = format(endOfMonth(month), 'yyyy-MM-dd')
  const selectedDateKey = date ? format(date, 'yyyy-MM-dd') : null
  const bookedDatesQuery = useBookedDates({
    facilityId: facility?.id ?? null,
    start: monthStart,
    end: monthEnd,
  })
  // Pull a fresh, date-scoped reservation set for slot filtering. The monthly
  // query continues to power only the separate Booked Dates View.
  const selectedDateReservationsQuery = useBookedDates({
    facilityId: date ? facility?.id ?? null : null,
    start: selectedDateKey ?? monthStart,
    end: selectedDateKey ?? monthEnd,
    excludeId: excludeReservationId,
  })
  const bookedDates = bookedDatesQuery.data ?? []
  const eventsByDate = useMemo(() => {
    const grouped = new Map<string, BookedDateEvent[]>()
    for (const event of bookedDates) {
      const events = grouped.get(event.date) ?? []
      events.push(event)
      grouped.set(event.date, events)
    }
    return grouped
  }, [bookedDates])
  const reservationsForSelectedDate = useMemo(() => {
    if (!selectedDateKey) return EMPTY_BOOKED_EVENTS
    const events = selectedDateReservationsQuery.data ?? (
      bookedDatesQuery.isSuccess
        ? eventsByDate.get(selectedDateKey) ?? EMPTY_BOOKED_EVENTS
        : EMPTY_BOOKED_EVENTS
    )
    return events.filter((event) => event.status === 'APPROVED')
  }, [selectedDateKey, selectedDateReservationsQuery.data, bookedDatesQuery.isSuccess, eventsByDate])
  const selectedReservationsPending = Boolean(
    date && facility && selectedDateReservationsQuery.isPending &&
      (!bookedDatesQuery.isSuccess || excludeReservationId != null),
  )
  const selectedReservationsError = Boolean(
    date && facility && selectedDateReservationsQuery.isError &&
      (!bookedDatesQuery.isSuccess || excludeReservationId != null),
  )

  // Keep the existing Booked Dates View availability legend unchanged.
  const bookedDateAvailability = (day: Date): 'available' | 'partial' | 'full' | 'unavailable' | null => {
    if (!facility) return null
    if (day.getFullYear() !== month.getFullYear() || day.getMonth() !== month.getMonth()) return null
    const today = manilaCalendarDate()
    if (day < today || facility.is_active === false || facility.status !== 'OPERATIONAL') return 'unavailable'
    const dayIndex = day.getDay() === 0 ? 6 : day.getDay() - 1
    const operatingHours = facility.operating_hours?.find((hours) => hours.day_of_week === dayIndex)
    if (!operatingHours || operatingHours.is_closed || !operatingHours.open_time || !operatingHours.close_time) return 'unavailable'
    const events = eventsByDate.get(format(day, 'yyyy-MM-dd')) ?? []
    if (bookedDatesQuery.isPending || bookedDatesQuery.isError) return null
    if (events.length === 0) return 'available'
    const [openHour, openMinute] = operatingHours.open_time.split(':').map(Number)
    const [closeHour, closeMinute] = operatingHours.close_time.split(':').map(Number)
    const open = Math.max(openHour * 60 + openMinute, EARLIEST_START_MINUTES)
    const close = closeHour * 60 + closeMinute
    if (close - open < 30) return 'unavailable'
    const isToday = day.toDateString() === today.toDateString()
    const candidateStarts = Array.from({ length: Math.floor((close - open) / 30) }, (_, index) => open + index * 30)
      .filter((slotStart) => !isToday || slotStart > nowMinutes)
    if (candidateStarts.length === 0) return 'unavailable'
    const hasFreeSlot = candidateStarts.some((slotStart) =>
      !hasReservationConflict(events, slotStart, slotStart + 30),
    )
    return hasFreeSlot ? 'partial' : 'full'
  }

  // Calendar View's date state uses the same 30-minute intervals as its time
  // selectors and excludes the reservation being edited when authorized.
  const calendarDayAvailability = (day: Date): 'available' | 'partial' | 'full' | 'unavailable' | null => {
    if (!facility) return null
    if (day.getFullYear() !== month.getFullYear() || day.getMonth() !== month.getMonth()) return null
    const today = manilaCalendarDate()
    if (day < today || facility.is_active === false || facility.status !== 'OPERATIONAL') return 'unavailable'
    const dayIndex = day.getDay() === 0 ? 6 : day.getDay() - 1
    const operatingHours = facility.operating_hours?.find((hours) => hours.day_of_week === dayIndex)
    if (!operatingHours || operatingHours.is_closed || !operatingHours.open_time || !operatingHours.close_time) return 'unavailable'
    const dayKey = format(day, 'yyyy-MM-dd')
    const editingCurrentDate = excludeReservationId != null && dayKey === selectedDateKey
    if (editingCurrentDate && (selectedDateReservationsQuery.isPending || selectedDateReservationsQuery.isError)) return null
    const events = editingCurrentDate && selectedDateReservationsQuery.data
      ? selectedDateReservationsQuery.data
      : eventsByDate.get(dayKey) ?? EMPTY_BOOKED_EVENTS
    if (bookedDatesQuery.isPending || bookedDatesQuery.isError) return null
    const approvedEvents = events.filter((event) => event.status === 'APPROVED')
    const open = Math.max(minutesSinceMidnight(operatingHours.open_time), EARLIEST_START_MINUTES)
    const close = minutesSinceMidnight(operatingHours.close_time)
    if (close - open < 30) return 'unavailable'
    const isToday = day.toDateString() === today.toDateString()
    const candidateStarts = Array.from({ length: Math.floor((close - open) / 30) }, (_, index) => open + index * 30)
      .filter((slotStart) => !isToday || slotStart > nowMinutes)
    if (candidateStarts.length === 0) return 'unavailable'
    if (approvedEvents.length === 0) return 'available'
    const hasFreeSlot = candidateStarts.some((slotStart) =>
      !hasReservationConflict(approvedEvents, slotStart, slotStart + 30),
    )
    return hasFreeSlot ? 'partial' : 'full'
  }

  const renderAvailability = (day: Date) => {
    const availability = bookedDateAvailability(day)
    if (!availability) return null
    const details = DAY_AVAILABILITY[availability]
    return (
      <span className="mt-1 flex items-center justify-center gap-1" aria-label={details.label} title={details.label}>
        <span aria-hidden className={cn('size-1.5 rounded-full', details.marker)} />
        <span className="sr-only">{details.label}</span>
      </span>
    )
  }

  const renderCalendarAvailability = (day: Date) => {
    const availability = calendarDayAvailability(day)
    if (!availability) return null
    const details = DAY_AVAILABILITY[availability]
    return (
      <span className="mt-1 flex items-center justify-center gap-1" aria-label={details.label} title={details.label}>
        <span aria-hidden className={cn('size-1.5 rounded-full', details.marker)} />
        <span className="sr-only">{details.label}</span>
      </span>
    )
  }

  useEffect(() => {
    const id = window.setInterval(() => setNowMinutes(manilaNowMinutes()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  const dayIndex = date ? (date.getDay() === 0 ? 6 : date.getDay() - 1) : -1
  const hours = facility?.operating_hours?.find((hour) => hour.day_of_week === dayIndex)
  const isToday = date != null && date.toDateString() === manilaCalendarDate().toDateString()
  const timeSlots = useMemo(() => {
    if (!hours || hours.is_closed || !hours.open_time || !hours.close_time) return []
    const slots: string[] = []
    const openTime = minutesSinceMidnight(hours.open_time)
    const closeTime = minutesSinceMidnight(hours.close_time)
    // The first bookable slot is the later of the facility's opening time and
    // the system-wide 8:00 AM minimum, so no earlier option is ever offered.
    let cursor = Math.max(openTime, EARLIEST_START_MINUTES)
    while (cursor + 30 <= closeTime) {
      if ((!isToday || cursor > nowMinutes) && !hasReservationConflict(reservationsForSelectedDate, cursor, cursor + 30)) {
        slots.push(`${String(Math.floor(cursor / 60)).padStart(2, '0')}:${String(cursor % 60).padStart(2, '0')}`)
      }
      cursor += 30
    }
    return slots
  }, [hours, isToday, nowMinutes, reservationsForSelectedDate])

  const endSlots = useMemo(() => {
    if (!startTime) return []
    const start = minutesSinceMidnight(startTime)
    let cursor = start + 30
    const close = hours && !hours.is_closed && hours.close_time ? minutesSinceMidnight(hours.close_time) : 24 * 60
    const slots: string[] = []
    while (cursor <= close) {
      if (!hasReservationConflict(reservationsForSelectedDate, start, cursor)) {
        slots.push(`${String(Math.floor(cursor / 60)).padStart(2, '0')}:${String(cursor % 60).padStart(2, '0')}`)
      }
      cursor += 30
    }
    return slots
  }, [startTime, hours, reservationsForSelectedDate])

  useEffect(() => {
    // Leave the default (and any restored selection) untouched until a
    // facility and date are chosen and its slots are known. Once they are, a
    // selection that is no longer valid (including one before 8:00 AM) is
    // cleared so it can never be submitted.
    if (!facility || !date) return
    if (selectedReservationsPending || selectedReservationsError) return
    if (startTime && !timeSlots.includes(startTime)) {
      onStartTime('')
      onEndTime('')
      return
    }
    if (endTime && !endSlots.includes(endTime)) {
      onEndTime('')
    }
  }, [facility, date, timeSlots, endSlots, startTime, endTime, onStartTime, onEndTime, selectedReservationsPending, selectedReservationsError])

  /** Calendar View: the only effect of a click is choosing the reservation date. */
  const selectDate = (day: Date) => {
    onDateChange(day)
    setMonth(day)
  }
  /** Booked Dates View: inspect existing reservations — never touch the form. */
  const openBookedDate = (day: Date) => {
    const dateKey = format(day, 'yyyy-MM-dd')
    setSelectedBookedDate(dateKey)
    setEventsModalOpen((eventsByDate.get(dateKey) ?? []).length > 0)
  }
  const changeMonth = (offset: number) => {
    setMonth((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1))
    setSelectedBookedDate(null)
    setEventsModalOpen(false)
  }
  /** Switching views must not reset the facility, date, or any other form state. */
  const changeView = (next: 'calendar' | 'booked') => {
    setEventsModalOpen(false)
    setView(next)
  }
  const selectedBookedDateValue = selectedBookedDate
    ? new Date(`${selectedBookedDate}T12:00:00`)
    : null
  const selectedEvents = selectedBookedDate ? eventsByDate.get(selectedBookedDate) ?? [] : []
  const legend = (
    <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 border-t border-line pt-4 text-xs text-body" aria-label="Date availability legend">
      {[
        ['bg-status-available', 'Available'],
        ['bg-status-pending', 'Partially booked'],
        ['bg-status-rejected', 'Fully booked'],
        ['bg-faint', 'Unavailable'],
      ].map(([color, label]) => (
        <span key={label} className="inline-flex items-center gap-2">
          <span className={cn('size-2 rounded-full', color)} aria-hidden />{label}
        </span>
      ))}
    </div>
  )
  // Calendar View shows aggregate availability only. Reservation event names
  // and details stay exclusive to the Booked Dates View and its modal.
  const calendarMonth = (
    <MonthGrid
      month={month}
      selected={date}
      onSelect={selectDate}
      disabledDate={(day) => {
        const availability = calendarDayAvailability(day)
        return day < manilaCalendarDate() || availability === 'full' || availability === 'unavailable'
      }}
      renderDay={renderCalendarAvailability}
      getDayLabel={(day) => {
        const availability = calendarDayAvailability(day)
        return availability ? DAY_AVAILABILITY[availability].label : ''
      }}
    />
  )
  // Booked Dates View: the same grid, showing actual backend reservation data.
  const bookedMonth = (
    <MonthGrid
      month={month}
      selected={selectedBookedDateValue}
      onSelect={openBookedDate}
      renderDay={renderAvailability}
      getDayLabel={(day) => {
        const availability = bookedDateAvailability(day)
        return availability ? DAY_AVAILABILITY[availability].label : ''
      }}
    />
  )
  return (
    <section aria-label="Choose schedule" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">Reservation dates</h2>
          <p className="mt-0.5 text-sm text-body">
            {view === 'calendar'
              ? `Select a date to reserve at ${facility?.name ?? 'your facility'}.`
              : `Existing reservations at ${facility?.name ?? 'your facility'}.`}
          </p>
        </div>
        <div className="inline-flex rounded-xl border border-line bg-softer p-1" role="group" aria-label="Reservation date view">
          <button
            type="button"
            aria-pressed={view === 'calendar'}
            onClick={() => changeView('calendar')}
            className={cn('min-h-10 rounded-lg px-3 text-sm font-semibold transition-colors sm:px-4', view === 'calendar' ? 'bg-surface text-ink shadow-sm' : 'text-body hover:text-ink')}
          >
            Calendar View
          </button>
          <button
            type="button"
            aria-pressed={view === 'booked'}
            disabled={!facility}
            onClick={() => changeView('booked')}
            className={cn('min-h-10 rounded-lg px-3 text-sm font-semibold transition-colors sm:px-4', view === 'booked' ? 'bg-surface text-ink shadow-sm' : 'text-body hover:text-ink', !facility && 'cursor-not-allowed opacity-50')}
          >
            View Booked Dates
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
      <Card>
        <CardHeader
          title={view === 'booked' ? 'Booked dates' : 'Choose date'}
          description={facility ? `${facility.name} · ${view === 'booked' ? 'select a marked date to see reservation details' : 'select a date for your reservation'}` : 'Select a facility first'}
        />
        <div className="mt-4">
          <CalendarHeader month={month} onPrev={() => changeMonth(-1)} onNext={() => changeMonth(1)} />
          <div className="mt-4 overflow-hidden">
            <div
              className="flex w-[200%] transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none"
              style={{ transform: view === 'booked' ? 'translateX(-50%)' : 'translateX(0)' }}
            >
              {/* Calendar View — reservation creation only: date selection, no
                  booking markers, no event names, no event modal. */}
              <div className="w-1/2 shrink-0" inert={view === 'booked'} aria-hidden={view === 'booked'}>
                {calendarMonth}
                {legend}
              </div>
              {/* Booked Dates View — existing reservations only: availability
                  markers, monthly list, and event detail modal. Inspecting a
                  date here never changes the reservation form. */}
              <div className="w-1/2 shrink-0" inert={view !== 'booked'} aria-hidden={view !== 'booked'}>
                <div className="space-y-4">
                  {bookedMonth}
                  {legend}
                  <aside className="rounded-xl border border-line bg-soft p-3 sm:p-4" aria-label="Booked reservation dates">
                    <h3 className="text-sm font-semibold text-ink">Reservations this month</h3>
                    {!facility && <p className="mt-3 text-sm text-body">Select a facility to view booked dates.</p>}
                    {facility && bookedDatesQuery.isPending && <p className="mt-3 text-sm text-body">Loading reservation dates…</p>}
                    {facility && bookedDatesQuery.isError && <p role="alert" className="mt-3 text-sm text-status-rejected">Booked dates could not be loaded. Try another month or refresh this view.</p>}
                    {facility && !bookedDatesQuery.isPending && !bookedDatesQuery.isError && bookedDates.length === 0 && (
                      <p className="mt-3 text-sm leading-relaxed text-body">No reservations are scheduled at this facility this month.</p>
                    )}
                    {facility && selectedBookedDateValue && selectedEvents.length === 0 && (
                      <p role="status" className="mt-3 rounded-lg bg-surface px-3 py-2 text-xs text-body">
                        No reservations on {format(selectedBookedDateValue, 'MMMM d, yyyy')}.
                      </p>
                    )}
                    {facility && bookedDates.length > 0 && (
                      <ul className="mt-3 max-h-48 space-y-2 overflow-y-auto">
                        {[...eventsByDate.entries()].map(([eventDate, events]) => (
                          <li key={eventDate}>
                            <button
                              type="button"
                              aria-pressed={selectedBookedDate === eventDate}
                              onClick={() => openBookedDate(new Date(`${eventDate}T12:00:00`))}
                              className={cn('w-full rounded-lg border px-3 py-2.5 text-left transition-colors hover:border-brand/40 hover:bg-brand-soft/50', selectedBookedDate === eventDate ? 'border-brand/40 bg-brand-soft/50' : 'border-line bg-surface')}
                            >
                              <span className="block text-sm font-semibold text-ink">{format(new Date(`${eventDate}T12:00:00`), 'EEE, MMM d')}</span>
                              <span className="mt-0.5 block text-xs text-body">{events.length} reservation{events.length === 1 ? '' : 's'}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </aside>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader title="Choose time" description="Slots follow the facility's operating hours" />
          <div className="mt-5 grid grid-cols-2 gap-4">
            <Field label="Start time" htmlFor="start-time">
              <Select
                id="start-time"
                value={startTime}
                onChange={(event) => {
                  onStartTime(event.target.value)
                  onEndTime('')
                }}
                disabled={timeSlots.length === 0 || selectedReservationsPending || selectedReservationsError}
              >
                <option value="">Select…</option>
                {timeSlots.map((slot) => (
                  <option key={slot} value={slot}>
                    {formatTime(slot)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="End time" htmlFor="end-time">
              <Select
                id="end-time"
                value={endTime}
                onChange={(event) => onEndTime(event.target.value)}
                disabled={!startTime || selectedReservationsPending || selectedReservationsError}
              >
                <option value="">Select…</option>
                {endSlots.map((slot) => (
                  <option key={slot} value={slot}>
                    {formatTime(slot)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {selectedReservationsPending && (
            <p role="status" className="mt-3 text-sm text-body">Checking existing reservations for this date…</p>
          )}
          {selectedReservationsError && (
            <div role="alert" className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-status-pending-bg px-3 py-2 text-sm text-status-pending">
              <span>Existing reservations could not be loaded. Time selection is paused.</span>
              <button type="button" className="font-semibold underline" onClick={() => void selectedDateReservationsQuery.refetch()}>
                Retry
              </button>
            </div>
          )}
          {isToday && (
            <p className="mt-3 text-[13px] text-muted">
              Only future time slots are shown for today.
            </p>
          )}
          {date && hours?.is_closed && (
            <p className="mt-4 rounded-lg bg-status-rejected-bg px-3 py-2 text-[13px] text-status-rejected">
              {facility?.name} is closed on {format(date, 'EEEE')}.
            </p>
          )}
          {date && !hours?.is_closed && (
            <p className="mt-4 flex items-center gap-2 text-[13px] text-muted">
              <CalendarDays className="size-4" aria-hidden />
              Operating hours: {hours?.open_time ? formatTime(hours.open_time) : '—'} –{' '}
              {hours?.close_time ? formatTime(hours.close_time) : '—'}
            </p>
          )}
        </Card>

        {dateInvalid && (
          <div className="rounded-xl border border-status-rejected/25 bg-status-rejected-bg p-4 text-sm text-status-rejected">
            Please choose a future date.
          </div>
        )}

        {isCancellationRestricted && !dateInvalid && (
          <div
            role="alert"
            className="rounded-xl border border-status-maintenance/30 bg-status-maintenance-bg p-4"
          >
            <p className="flex items-center gap-2 text-sm font-semibold text-status-maintenance">
              <AlertTriangle className="size-4 shrink-0" aria-hidden />
              Cancellation Policy Notice
            </p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-status-maintenance">
              Reservations scheduled within the next <strong>2 days cannot be cancelled once submitted.</strong>{' '}
              Please make sure that all reservation details are correct before submitting.
            </p>
          </div>
        )}

        {!dateInvalid && <AvailabilityStatusNotice status={availabilityStatus} />}
        {report && !dateInvalid && (
          <AvailabilityCheck report={report} onUseAlternative={onUseAlternative} />
        )}
        {checking && !dateInvalid && !report && (
          <div className="h-24 animate-pulse rounded-xl bg-soft" aria-hidden />
        )}
      </div>
      </div>
      {/* The modal exists only for the Booked Dates View, so closing it always
          leaves the user there — the selected view is never changed. */}
      <ReservationEventsModal
        open={eventsModalOpen && selectedEvents.length > 0}
        date={selectedBookedDateValue}
        events={selectedEvents}
        onClose={() => setEventsModalOpen(false)}
      />
    </section>
  )
}

// ---------------------------------------------------------------------------
// Step 4 — Review
// ---------------------------------------------------------------------------

export function StepReview({
  facilityName,
  facilityType,
  dateISO,
  startTime,
  endTime,
  details,
  contact,
  reservingAs,
  participants,
  equipment,
  items,
  report,
  checking,
  onUseAlternative,
  isAdmin,
  requesterSection,
  isCancellationRestricted,
  pricing,
  onEditStep,
}: {
  facilityName: string
  facilityType: string
  dateISO: string
  startTime: string
  endTime: string
  details: EventDetailsDraft
  /** Contact person shown as a compact read-only row. */
  contact: ContactDraft
  /** Organization the reservation is for — derived from the account. */
  reservingAs: string
  participants: number
  equipment: ReservableResource[]
  items: Record<number, number>
  report: AvailabilityCheckResult | null
  checking: boolean
  onUseAlternative: (alternative: AlternativeSlot) => void
  isAdmin: boolean
  /** Estimated external-organization cost for the final selected resources. */
  pricing?: PricingQuote | null
  /** Requester identity block (campus summary or external contact details). */
  requesterSection?: ReactNode
  /** True when the event date falls within the 2-day cancellation window
   *  (today/tomorrow) — such reservations cannot be cancelled once
   *  submitted. */
  isCancellationRestricted?: boolean
  /** Jump back to an earlier step to edit what is shown here (Goal 4). */
  onEditStep?: (step: 'facility' | 'schedule') => void
}) {
  const reviewItems = Object.entries(items)
    .map(([equipmentId, quantity]) => ({
      equipment: equipment.find((item) => item.id === Number(equipmentId)),
      quantity,
    }))
    .filter((entry) => entry.equipment)

  return (
    <section aria-label="Review reservation" className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-ink">Review your reservation</h2>
        <p className="mt-1 text-sm text-body">
          Confirm everything looks right before{' '}
          {isAdmin ? 'creating the approved reservation' : 'submitting for approval'}.
        </p>
      </div>

      {report && <AvailabilityCheck report={report} onUseAlternative={onUseAlternative} />}
      {checking && !report && <div className="h-24 animate-pulse rounded-xl bg-soft" aria-hidden />}

      <PricingBreakdown pricing={pricing} loading={checking && !pricing} title="Estimated cost" />

      {requesterSection}

      <Card>
        <dl className="divide-y divide-line">
          {/* Facility and schedule are captured in earlier steps: they are
              shown read-only here, with a link back to the step that owns them. */}
          <ReviewRow
            label="Facility"
            value={facilityName || '—'}
            sub={facilityType}
            onEdit={onEditStep ? () => onEditStep('facility') : undefined}
          />
          <ReviewRow
            label="Schedule"
            value={dateISO ? format(new Date(`${dateISO}T00:00:00`), 'EEEE, MMMM d, yyyy') : '—'}
            sub={startTime && endTime ? `${formatTime(startTime)} – ${formatTime(endTime)}` : undefined}
            onEdit={onEditStep ? () => onEditStep('schedule') : undefined}
          />
          <ReviewRow label="Event" value={details.eventName || '—'} />
          <ReviewRow
            label="Event type"
            value={details.eventType ? eventTypeLabel(details.eventType) : '—'}
          />
          <ReviewRow label="Purpose" value={details.purpose || '—'} />
          <ReviewRow label="Expected participants" value={participants ? participants.toLocaleString() : '—'} />
          <ReviewRow label="Organization" value={reservingAs || '—'} />
          <ReviewRow
            label="Contact"
            value={contact.name || '—'}
            sub={contact.phone || undefined}
          />
          <ReviewRow
            label="Resources"
            value={
              reviewItems.length
                ? reviewItems.map((entry) => `${entry.quantity}× ${entry.equipment?.name}`).join(', ')
                : 'None requested'
            }
          />
          {reviewItems.length > 0 && (
            <div className="divide-y divide-line py-3.5">
              {reviewItems.map((entry) => {
                if (!entry.equipment) return null
                return (
                  <div key={entry.equipment.id} className="flex items-center gap-4 py-3">
                    <EquipmentImage
                      src={equipmentPrimaryImageUrl(entry.equipment)}
                      size="sm"
                      className="shrink-0 rounded-lg"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-ink">{entry.equipment.name}</p>
                      <p className="text-xs text-body">{entry.equipment.category.name}</p>
                    </div>
                    <span className="shrink-0 rounded-lg bg-soft px-2.5 py-1 text-xs font-semibold tabular-nums text-ink">
                      ×{entry.quantity}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
          {details.staffNotes && (
            <ReviewRow label="Notes for SAS staff" value={details.staffNotes} />
          )}
        </dl>
      </Card>

      {isCancellationRestricted && !isAdmin && (
        <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-status-maintenance/30 bg-status-maintenance-bg px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-status-maintenance" aria-hidden />
          <p className="leading-relaxed text-status-maintenance">
            <span className="font-semibold">Cancellation Policy Notice.</span> Reservations scheduled
            within the next <strong>2 days cannot be cancelled once submitted.</strong>{' '}
            Please make sure all details are correct before submitting.
          </p>
        </div>
      )}

      {isAdmin && (
        <div className="flex items-start gap-2.5 rounded-xl border border-brand/20 bg-brand-soft/50 px-4 py-3 text-sm text-brand">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <span className="font-semibold">Administrator reservation.</span> Submitting will create this
            reservation with status <span className="font-semibold">Approved</span> — no pending review needed.
          </p>
        </div>
      )}
    </section>
  )
}

export function ReviewRow({
  label,
  value,
  sub,
  onEdit,
}: {
  label: string
  value: string
  sub?: string
  /** When provided, renders an "Edit" link that jumps back to the owning step. */
  onEdit?: (() => void) | false
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-3.5">
      <dt className="shrink-0 text-sm text-body">
        {label}
        {onEdit ? (
          <button
            type="button"
            onClick={onEdit}
            className="ml-2 rounded px-1 text-[13px] font-medium text-brand transition-colors hover:bg-brand-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            Edit
          </button>
        ) : null}
      </dt>
      <dd className="min-w-0 text-right">
        <p className="text-sm font-medium text-ink">{value}</p>
        {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
      </dd>
    </div>
  )
}

export function ConfirmationRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-6 py-3">
      <dt className="shrink-0 text-[13px] text-body">{label}</dt>
      <dd className="min-w-0 text-right text-sm font-medium text-ink">{value}</dd>
    </div>
  )
}
