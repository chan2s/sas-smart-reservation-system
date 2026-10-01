import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { AlertTriangle, CalendarDays, CheckCircle2, Info, Loader2, XCircle } from 'lucide-react'
import { format } from 'date-fns'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Select } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'
import { AvailabilityCheck } from '@/components/reservations/AvailabilityCheck'
import { PricingBreakdown } from '@/components/reservations/PricingBreakdown'
import { MonthGrid } from '@/components/calendar/MonthGrid'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { cn, equipmentPrimaryImageUrl, formatTime } from '@/lib/utils'
import type { ContactDraft, EventDetailsDraft } from '@/lib/reservationDraft'
import type {
  AlternativeSlot,
  AvailabilityCheck as AvailabilityCheckResult,
  EventType,
  PricingQuote,
  ReservableResource,
} from '@/lib/types'

/**
 * Shared reservation workflow steps for the new-reservation wizard
 * (ReservationWizardPage): facility, schedule, the merged details & resources
 * step (see DetailsStep) and the review summary.
 */

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
  facilities: { id: number; name: string; facility_type: string; facility_type_label: string; description: string; capacity: number; location: string; image: string | null; status: string }[]
  selected: number | null
  onSelect: (id: number) => void
}) {
  return (
    <section aria-label="Choose facility">
      <h2 className="text-lg font-semibold text-ink">Choose facility</h2>
      <p className="mt-1 text-sm text-body">Select the space you need for your event.</p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {facilities.map((facility) => {
          const isSelected = selected === facility.id
          const maintenance = facility.status === 'MAINTENANCE'
          return (
            <button
              key={facility.id}
              type="button"
              onClick={() => !maintenance && onSelect(facility.id)}
              aria-pressed={isSelected}
              className={cn(
                'card card-hover overflow-hidden text-left transition-shadow',
                isSelected && 'ring-2 ring-brand ring-offset-2',
                maintenance && 'cursor-not-allowed opacity-60',
              )}
            >
              <div className="relative h-28">
                <FacilityImage
                  name={facility.name}
                  facilityType={facility.facility_type as never}
                  src={facility.image}
                  rounded="rounded-none"
                />
                <div className="absolute left-3 top-3">
                  {maintenance ? (
                    <Badge tone="orange">Maintenance</Badge>
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
  facility?: { id: number; name: string; status: string; operating_hours?: { day_of_week: number; open_time: string | null; close_time: string | null; is_closed: boolean }[] }
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
  const [month, setMonth] = useState(() => new Date())
  const [nowMinutes, setNowMinutes] = useState(() => manilaNowMinutes())

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
    const [openHour, openMinute] = hours.open_time.split(':').map(Number)
    const [closeHour, closeMinute] = hours.close_time.split(':').map(Number)
    let cursor = openHour * 60 + openMinute
    const close = closeHour * 60 + closeMinute
    while (cursor < close) {
      if (!isToday || cursor > nowMinutes) {
        slots.push(`${String(Math.floor(cursor / 60)).padStart(2, '0')}:${String(cursor % 60).padStart(2, '0')}`)
      }
      cursor += 30
    }
    return slots
  }, [hours, isToday, nowMinutes])

  const endSlots = useMemo(() => {
    if (!startTime) return []
    const [hour, minute] = startTime.split(':').map(Number)
    let cursor = hour * 60 + minute + 30
    const close = hours && !hours.is_closed && hours.close_time ? Number(hours.close_time.split(':')[0]) * 60 + Number(hours.close_time.split(':')[1]) : 24 * 60
    const slots: string[] = []
    while (cursor <= close) {
      slots.push(`${String(Math.floor(cursor / 60)).padStart(2, '0')}:${String(cursor % 60).padStart(2, '0')}`)
      cursor += 30
    }
    return slots
  }, [startTime, hours])

  useEffect(() => {
    if (startTime) {
      if (!timeSlots.includes(startTime)) {
        onStartTime('')
        onEndTime('')
        return
      }
    }
    if (endTime && !endSlots.includes(endTime)) {
      onEndTime('')
    }
  }, [timeSlots, endSlots, startTime, endTime, onStartTime, onEndTime])

  return (
    <section aria-label="Choose schedule" className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="Choose date"
          description={facility ? `${facility.name} — select an available day` : 'Select a facility first'}
        />
        <div className="mt-4">
          <MonthGrid
            month={month}
            selected={date}
            onSelect={(day) => {
              onDateChange(day)
              setMonth(day)
            }}
          />
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
          <Button variant="outline" size="sm" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>
            Previous month
          </Button>
          <Button variant="outline" size="sm" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>
            Next month
          </Button>
        </div>
      </Card>

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
                disabled={timeSlots.length === 0}
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
                disabled={!startTime}
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
