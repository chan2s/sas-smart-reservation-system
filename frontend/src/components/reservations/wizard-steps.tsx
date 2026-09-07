import { useMemo, useState, type ReactNode } from 'react'
import { CalendarDays, CheckCircle2, Minus, Plus } from 'lucide-react'
import { format } from 'date-fns'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Input, Select, Textarea } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'
import { AvailabilityCheck } from '@/components/reservations/AvailabilityCheck'
import { RecommendationCard } from '@/components/reservations/RecommendationCard'
import { MonthGrid } from '@/components/calendar/MonthGrid'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import { EmptyState } from '@/components/ui/Misc'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { cn, formatTime } from '@/lib/utils'
import type {
  AlternativeSlot,
  AvailabilityCheck as AvailabilityCheckResult,
  Equipment,
  EventType,
  Recommendation,
} from '@/lib/types'

/**
 * Shared reservation workflow steps.
 *
 * Used by both the authenticated wizard (ReservationWizardPage) and the
 * public guest wizard (ReservePage) so there is exactly ONE reservation
 * workflow — only requester identification and approval behavior differ.
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

export interface EventDetails {
  event_name: string
  event_type: EventType
  organization: string
  purpose: string
  description: string
  expected_participants: string
  contact_person: string
  special_requirements: string
  notes: string
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
  startTime: string
  endTime: string
  onStartTime: (value: string) => void
  onEndTime: (value: string) => void
  report: AvailabilityCheckResult | null
  checking: boolean
  onUseAlternative: (alternative: AlternativeSlot) => void
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
  onUseAlternative,
}: ScheduleProps) {
  const [month, setMonth] = useState(() => new Date())
  const today = new Date()

  const dayIndex = date ? (date.getDay() === 0 ? 6 : date.getDay() - 1) : -1
  const hours = facility?.operating_hours?.find((hour) => hour.day_of_week === dayIndex)
  const timeSlots = useMemo(() => {
    if (!hours || hours.is_closed || !hours.open_time || !hours.close_time) return []
    const slots: string[] = []
    const [openHour, openMinute] = hours.open_time.split(':').map(Number)
    const [closeHour, closeMinute] = hours.close_time.split(':').map(Number)
    let cursor = openHour * 60 + openMinute
    const close = closeHour * 60 + closeMinute
    while (cursor < close) {
      slots.push(`${String(Math.floor(cursor / 60)).padStart(2, '0')}:${String(cursor % 60).padStart(2, '0')}`)
      cursor += 30
    }
    return slots
  }, [hours])

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

        {date && date < today && (
          <div className="rounded-xl border border-status-rejected/25 bg-status-rejected-bg p-4 text-sm text-status-rejected">
            Please choose a future date.
          </div>
        )}

        {report && (
          <AvailabilityCheck report={report} onUseAlternative={onUseAlternative} />
        )}
        {checking && !report && <div className="h-24 animate-pulse rounded-xl bg-soft" aria-hidden />}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Step 3 — Event details
// ---------------------------------------------------------------------------

export function StepDetails({
  details,
  onChange,
  showErrors,
  missing,
}: {
  details: EventDetails
  onChange: (next: EventDetails) => void
  showErrors: boolean
  missing: string[]
}) {
  const set = <K extends keyof EventDetails>(key: K, value: EventDetails[K]) =>
    onChange({ ...details, [key]: value })

  const fieldError = (label: string) => (showErrors && missing.includes(label) ? `${label} is required.` : undefined)

  return (
    <section aria-label="Event details" className="mx-auto max-w-2xl">
      <h2 className="text-lg font-semibold text-ink">Event details</h2>
      <p className="mt-1 text-sm text-body">
        Tell SAS about your event — this lets us recommend the right resources.
      </p>

      <Card className="mt-5">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Event name" htmlFor="event-name" className="sm:col-span-2" error={fieldError('Event name')}>
            <Input
              id="event-name"
              value={details.event_name}
              onChange={(event) => set('event_name', event.target.value)}
              placeholder="e.g. Student Leadership Seminar"
            />
          </Field>
          <Field label="Event type" htmlFor="event-type" error={fieldError('Event type')}>
            <Select
              id="event-type"
              value={details.event_type}
              onChange={(event) => set('event_type', event.target.value as EventType)}
            >
              {EVENT_TYPE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Expected participants" htmlFor="participants" error={fieldError('Expected participants')}>
            <Input
              id="participants"
              type="number"
              min={1}
              value={details.expected_participants}
              onChange={(event) => set('expected_participants', event.target.value)}
              placeholder="e.g. 150"
            />
          </Field>
          <Field label="Event purpose" htmlFor="purpose" className="sm:col-span-2" error={fieldError('Event purpose')}>
            <Input
              id="purpose"
              value={details.purpose}
              onChange={(event) => set('purpose', event.target.value)}
              placeholder="e.g. Recognition ceremony for graduating students"
            />
          </Field>
          <Field label="Organization / Office" htmlFor="organization" className="sm:col-span-2">
            <Input
              id="organization"
              value={details.organization}
              onChange={(event) => set('organization', event.target.value)}
              placeholder="e.g. Student Affairs Office"
            />
          </Field>
          <Field label="Contact person" htmlFor="contact-person" className="sm:col-span-2">
            <Input
              id="contact-person"
              value={details.contact_person}
              onChange={(event) => set('contact_person', event.target.value)}
              placeholder="e.g. Juan Dela Cruz, ext. 1234"
            />
          </Field>
          <Field label="Description" htmlFor="description" className="sm:col-span-2">
            <Textarea
              id="description"
              value={details.description}
              onChange={(event) => set('description', event.target.value)}
              placeholder="Briefly describe the event."
            />
          </Field>
          <Field label="Special requirements" htmlFor="special-requirements" className="sm:col-span-2">
            <Textarea
              id="special-requirements"
              value={details.special_requirements}
              onChange={(event) => set('special_requirements', event.target.value)}
              placeholder="e.g. Stage setup, podium, table layout for 10 guests"
            />
          </Field>
          <Field label="Notes for SAS staff" htmlFor="notes" className="sm:col-span-2">
            <Textarea
              id="notes"
              value={details.notes}
              onChange={(event) => set('notes', event.target.value)}
              placeholder="Optional — setup needs, AV preferences, etc."
            />
          </Field>
        </div>
      </Card>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Step 4 — Resources
// ---------------------------------------------------------------------------

export function StepResources({
  equipment,
  items,
  onQuantity,
  recommendations,
  recommendationLoading,
  recommendationApplied,
  onAcceptRecommendations,
  onDismissRecommendations,
  eventContext,
}: {
  equipment: Equipment[]
  items: Record<number, number>
  onQuantity: (equipmentId: number, quantity: number, available: number) => void
  recommendations: Recommendation[] | null
  recommendationLoading: boolean
  recommendationApplied: boolean
  onAcceptRecommendations: () => void
  onDismissRecommendations: () => void
  eventContext: { eventName: string; participants: string; facilityName: string; schedule: string }
}) {
  const recommendedIds = useMemo(
    () => new Set((recommendations ?? []).map((recommendation) => recommendation.equipment_id)),
    [recommendations],
  )
  const otherEquipment = useMemo(() => equipment.filter((item) => !recommendedIds.has(item.id)), [equipment, recommendedIds])

  const byCategory = useMemo(() => {
    const groups = new Map<string, Equipment[]>()
    for (const item of otherEquipment) {
      const key = item.category.name
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(item)
    }
    return [...groups.entries()]
  }, [otherEquipment])

  return (
    <section aria-label="Choose resources">
      <h2 className="text-lg font-semibold text-ink">Resources</h2>
      <p className="mt-1 text-sm text-body">
        Based on your event details, we recommend the resources below. Adjust quantities as needed — they are capped by availability.
      </p>

      {recommendations && recommendations.length > 0 && (
        <div className="mt-5">
          <RecommendationCard
            recommendations={recommendations}
            equipment={equipment}
            items={items}
            onQuantity={onQuantity}
            eventContext={eventContext}
            loading={recommendationLoading}
            applied={recommendationApplied}
            onAccept={onAcceptRecommendations}
            onDismiss={onDismissRecommendations}
          />
        </div>
      )}
      {recommendationLoading && !recommendations && (
        <div className="mt-5 max-w-2xl">
          <RecommendationCard recommendations={[]} equipment={[]} items={{}} onQuantity={() => {}} loading />
        </div>
      )}

      {byCategory.length === 0 ? (
        <EmptyState
          title="No other equipment available"
          description="Everything you need is in the recommendations above. You can continue without additional resources."
        />
      ) : (
        <div className="mt-8 space-y-6">
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-muted">
            Other available resources
          </h3>
          {byCategory.map(([category, itemsInCategory]) => (
            <div key={category}>
              <h4 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-muted">
                {category}
              </h4>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {itemsInCategory.map((item) => {
                  const requested = items[item.id] ?? 0
                  const available = item.availability.available
                  return (
                    <div
                      key={item.id}
                      className={cn(
                        'flex items-center gap-4 rounded-xl border border-line bg-surface p-4 transition-colors',
                        requested > 0 && 'border-brand/40 bg-brand-soft/40',
                      )}
                    >
                      <EquipmentImage src={item.image} size="md" className="shrink-0 rounded-lg" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">{item.name}</p>
                        <p className="mt-0.5 text-xs text-body">
                          {available} of {item.total_quantity} units available
                          {item.availability.status !== 'AVAILABLE' && item.availability.status !== 'PARTIAL' && (
                            <span className="text-status-rejected"> · unavailable now</span>
                          )}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => onQuantity(item.id, requested - 1, available)}
                          disabled={requested === 0}
                          className="flex size-8 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
                          aria-label={`Decrease ${item.name} quantity`}
                        >
                          <Minus className="size-3.5" />
                        </button>
                        <span className="w-8 text-center text-sm font-semibold tabular-nums text-ink" aria-live="polite">
                          {requested}
                        </span>
                        <button
                          type="button"
                          onClick={() => onQuantity(item.id, requested + 1, available)}
                          disabled={requested >= available || available === 0}
                          className="flex size-8 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
                          aria-label={`Increase ${item.name} quantity`}
                        >
                          <Plus className="size-3.5" />
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Step 5 — Review
// ---------------------------------------------------------------------------

export function StepReview({
  facilityName,
  facilityType,
  dateISO,
  startTime,
  endTime,
  details,
  participants,
  equipment,
  items,
  report,
  checking,
  onUseAlternative,
  isAdmin,
  requesterSection,
}: {
  facilityName: string
  facilityType: string
  dateISO: string
  startTime: string
  endTime: string
  details: EventDetails
  participants: number
  equipment: Equipment[]
  items: Record<number, number>
  report: AvailabilityCheckResult | null
  checking: boolean
  onUseAlternative: (alternative: AlternativeSlot) => void
  isAdmin: boolean
  /** Requester identity block (campus summary or external contact details). */
  requesterSection?: ReactNode
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
      {checking && <div className="h-24 animate-pulse rounded-xl bg-soft" aria-hidden />}

      {requesterSection}

      <Card>
        <dl className="divide-y divide-line">
          <ReviewRow label="Facility" value={facilityName || '—'} sub={facilityType} />
          <ReviewRow
            label="Schedule"
            value={dateISO ? format(new Date(`${dateISO}T00:00:00`), 'EEEE, MMMM d, yyyy') : '—'}
            sub={startTime && endTime ? `${formatTime(startTime)} – ${formatTime(endTime)}` : undefined}
          />
          <ReviewRow label="Event" value={details.event_name || '—'} />
          <ReviewRow label="Event type" value={eventTypeLabel(details.event_type)} />
          <ReviewRow label="Purpose" value={details.purpose || '—'} />
          <ReviewRow label="Expected participants" value={participants ? participants.toLocaleString() : '—'} />
          <ReviewRow label="Organization" value={details.organization || '—'} />
          <ReviewRow label="Contact person" value={details.contact_person || '—'} />
          {details.special_requirements && (
            <ReviewRow label="Special requirements" value={details.special_requirements} />
          )}
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
                    <EquipmentImage src={entry.equipment.image} size="sm" className="shrink-0 rounded-lg" />
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
          {details.notes && <ReviewRow label="Notes" value={details.notes} />}
        </dl>
      </Card>

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

export function ReviewRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex items-start justify-between gap-6 py-3.5">
      <dt className="shrink-0 text-sm text-body">{label}</dt>
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
