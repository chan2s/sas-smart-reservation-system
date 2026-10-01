import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { AlertTriangle, CheckCircle2, Pencil, Plus, Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Field, Input, Select, Textarea } from '@/components/ui/Form'
import { OtherEquipmentPicker, type OperatorConfig } from '@/components/reservations/OtherEquipmentPicker'
import { QuantityStepper } from '@/components/reservations/QuantityStepper'
import { EVENT_TYPE_OPTIONS } from '@/components/reservations/wizard-steps'
import {
  EVENT_NAME_MAX,
  PURPOSE_MAX,
  RESERVATION_FIELD_IDS,
  RESERVATION_FIELD_ORDER,
  isValidPhMobile,
  reservationFieldErrors,
  type ContactDraft,
  type EventDetailsDraft,
  type ReservationFieldKey,
} from '@/lib/reservationDraft'
import { cn } from '@/lib/utils'
import type { SuggestedResource } from '@/hooks/useSuggestedResources'
import type { EventType, ReservableResource } from '@/lib/types'

/**
 * Step 3 — "Details & Resources".
 *
 * The five-field event form, the read-only contact row, and the suggested
 * resources all live in ONE step so the wizard never asks for the same thing
 * twice (facility/date/time stay in steps 1–2 and reappear only as a read-only
 * summary on Review).
 *
 * TODO(conditional-fields): when Facility gains a `requires_approval_letter`
 * flag and an upload endpoint exists, render that upload here and only here —
 * i.e. gate it on `facility.requires_approval_letter`. Nothing in this
 * component reads facility metadata today.
 */
export function DetailsStep({
  details,
  onDetailsChange,
  contact,
  onContactChange,
  reservingAs,
  capacity,
  facilityName,
  suggestions,
  suggestionsLoading,
  included,
  items,
  onQuantity,
  onToggleSuggestion,
  equipment,
  operatorConfig,
  operatorSelections,
  onOperatorChange,
  resourcesLoading,
  focusAttempt,
  showAllErrors,
}: {
  details: EventDetailsDraft
  onDetailsChange: (next: EventDetailsDraft) => void
  contact: ContactDraft
  onContactChange: (next: ContactDraft) => void
  /** Organization the reservation is for — derived from the account, never typed. */
  reservingAs: string
  capacity: number
  facilityName: string
  suggestions: SuggestedResource[]
  suggestionsLoading: boolean
  /** Items the facility already provides ("Cafeteria already provides Tables, Chairs."). */
  included: string[]
  items: Record<number, number>
  onQuantity: (equipmentId: number, quantity: number, available: number) => void
  onToggleSuggestion: (equipmentId: number, checked: boolean, suggestedQuantity: number) => void
  /** Facility resources that are NOT already listed as suggestions. */
  equipment: ReservableResource[]
  operatorConfig?: Record<number, OperatorConfig>
  operatorSelections?: Record<number, boolean>
  onOperatorChange?: (equipmentId: number, selected: boolean) => void
  resourcesLoading?: boolean
  /** Incremented by the wizard each time Continue was pressed while invalid. */
  focusAttempt: number
  /** True immediately after a failed Continue — reveals every error, not just touched ones. */
  showAllErrors: boolean
}) {
  const errors = useMemo(
    () => reservationFieldErrors({ details, contact, capacity, facilityName }),
    [details, contact, capacity, facilityName],
  )
  const [touched, setTouched] = useState<Partial<Record<ReservationFieldKey, boolean>>>({})
  // The contact row starts expanded when there is no number to prefill from.
  const [editingContact, setEditingContact] = useState(() => !contact.phone.trim())
  const [contactSnapshot, setContactSnapshot] = useState<ContactDraft>(contact)
  const [showPicker, setShowPicker] = useState(false)
  const contactTouched = useRef(false)
  const handledFocusAttempt = useRef(0)
  const formRef = useRef<HTMLDivElement>(null)
  const eventNameRef = useRef<HTMLInputElement>(null)

  const set = <K extends keyof EventDetailsDraft>(key: K, value: EventDetailsDraft[K]) =>
    onDetailsChange({ ...details, [key]: value })
  const markTouched = (key: ReservationFieldKey) =>
    setTouched((current) => (current[key] ? current : { ...current, [key]: true }))
  const visibleError = (key: ReservationFieldKey) =>
    touched[key] || showAllErrors ? errors[key] : undefined

  // Autofocus the first field on mount (but never steal focus from a draft the
  // requester already filled in).
  useEffect(() => {
    if (!details.eventName.trim()) eventNameRef.current?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The saved number prefills asynchronously; collapse the row when it lands,
  // unless the requester has already started editing the contact.
  useEffect(() => {
    if (!contactTouched.current && contact.phone.trim()) setEditingContact(false)
  }, [contact.phone])

  // "Enter" in a single-line field moves on instead of submitting the wizard.
  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Enter') return
    const target = event.target as HTMLElement
    if (target.tagName !== 'INPUT') return
    event.preventDefault()
    const fields = Array.from(
      formRef.current?.querySelectorAll<HTMLElement>('input, select, textarea') ?? [],
    ).filter((element) => !(element as HTMLInputElement).disabled)
    const index = fields.indexOf(target)
    fields[index + 1]?.focus()
  }

  // After a failed Continue: show every error, expand the contact row if that
  // is where the problem is, then scroll to and focus the first invalid field.
  const firstInvalid = RESERVATION_FIELD_ORDER.find((key) => errors[key])
  useEffect(() => {
    if (focusAttempt === handledFocusAttempt.current) return
    handledFocusAttempt.current = focusAttempt
    if (!firstInvalid) return
    if (firstInvalid === 'contactName' || firstInvalid === 'contactPhone') {
      setEditingContact(true)
    }
    const timer = window.setTimeout(() => {
      const element = document.getElementById(RESERVATION_FIELD_IDS[firstInvalid])
      element?.focus()
      element?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [focusAttempt, firstInvalid])

  // Additional (non-suggested) resources the requester picked — kept visible
  // even while the full picker is collapsed.
  const selectedExtras = equipment.filter((item) => (items[item.id] ?? 0) > 0)
  const unverifiedSeating = suggestions.some((suggestion) => suggestion.unverified)
  const showSuggestions = suggestionsLoading || suggestions.length > 0 || included.length > 0
  const contactComplete = Boolean(contact.name.trim()) && isValidPhMobile(contact.phone)

  return (
    <section aria-label="Event details and resources" className="mx-auto max-w-3xl">
      <h2 className="text-lg font-semibold text-ink">Details &amp; resources</h2>
      <p className="mt-1 text-sm text-body">
        Tell SAS about your event, then confirm the resources you need.
      </p>
      {/* Organization/Office is never typed: the reservation is made on behalf
          of the organization linked to the account (or, for staff, to the
          selected campus requester). */}
      <p className="mt-2 text-[13px] text-body">
        Reserving as:{' '}
        <span className="font-medium text-ink">{reservingAs || 'No organization linked yet'}</span>
        {!reservingAs && (
          <>
            {' '}
            — add one in your profile so SAS knows which college this is for.
          </>
        )}
      </p>

      <Card className="mt-4" padding="md">
        <div ref={formRef} onKeyDown={handleKeyDown} className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Event name"
            htmlFor={RESERVATION_FIELD_IDS.eventName}
            className="sm:col-span-2"
            error={visibleError('eventName')}
          >
            <Input
              id={RESERVATION_FIELD_IDS.eventName}
              ref={eventNameRef}
              value={details.eventName}
              maxLength={EVENT_NAME_MAX}
              onChange={(event) => set('eventName', event.target.value)}
              onBlur={() => markTouched('eventName')}
              placeholder="e.g. Student Leadership Seminar"
              aria-invalid={Boolean(visibleError('eventName'))}
              aria-describedby={
                visibleError('eventName') ? `${RESERVATION_FIELD_IDS.eventName}-error` : undefined
              }
            />
          </Field>

          <Field
            label="Event type"
            htmlFor={RESERVATION_FIELD_IDS.eventType}
            error={visibleError('eventType')}
          >
            <Select
              id={RESERVATION_FIELD_IDS.eventType}
              value={details.eventType}
              onChange={(event) => {
                set('eventType', event.target.value as EventType)
                markTouched('eventType')
              }}
              aria-invalid={Boolean(visibleError('eventType'))}
              aria-describedby={
                visibleError('eventType') ? `${RESERVATION_FIELD_IDS.eventType}-error` : undefined
              }
            >
              <option value="" disabled>
                Select type
              </option>
              {EVENT_TYPE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Expected participants"
            htmlFor={RESERVATION_FIELD_IDS.expectedParticipants}
            hint={capacity > 0 ? `Max ${capacity} for ${facilityName}` : undefined}
            error={visibleError('expectedParticipants')}
          >
            <Input
              id={RESERVATION_FIELD_IDS.expectedParticipants}
              type="number"
              min={1}
              max={capacity > 0 ? capacity : undefined}
              inputMode="numeric"
              value={details.expectedParticipants}
              onChange={(event) => set('expectedParticipants', event.target.value)}
              onBlur={() => markTouched('expectedParticipants')}
              placeholder="e.g. 150"
              aria-invalid={Boolean(visibleError('expectedParticipants'))}
              aria-describedby={
                visibleError('expectedParticipants')
                  ? `${RESERVATION_FIELD_IDS.expectedParticipants}-error`
                  : undefined
              }
            />
          </Field>

          <Field
            label="Purpose"
            htmlFor={RESERVATION_FIELD_IDS.purpose}
            className="sm:col-span-2"
            hint={`${details.purpose.length}/${PURPOSE_MAX}`}
            error={visibleError('purpose')}
          >
            <Textarea
              id={RESERVATION_FIELD_IDS.purpose}
              rows={2}
              maxLength={PURPOSE_MAX}
              value={details.purpose}
              onChange={(event) => set('purpose', event.target.value)}
              onBlur={() => markTouched('purpose')}
              placeholder="e.g. Recognition ceremony for graduating students"
              aria-invalid={Boolean(visibleError('purpose'))}
              aria-describedby={
                visibleError('purpose') ? `${RESERVATION_FIELD_IDS.purpose}-error` : undefined
              }
            />
          </Field>

          <div className="sm:col-span-2">
            {editingContact ? (
              <div className="rounded-xl border border-line bg-soft/60 p-3.5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field
                    label="Contact name"
                    htmlFor={RESERVATION_FIELD_IDS.contactName}
                    error={visibleError('contactName')}
                  >
                    <Input
                      id={RESERVATION_FIELD_IDS.contactName}
                      value={contact.name}
                      onChange={(event) => onContactChange({ ...contact, name: event.target.value })}
                      onBlur={() => markTouched('contactName')}
                      placeholder="e.g. Juan Dela Cruz"
                      aria-invalid={Boolean(visibleError('contactName'))}
                      aria-describedby={
                        visibleError('contactName')
                          ? `${RESERVATION_FIELD_IDS.contactName}-error`
                          : undefined
                      }
                    />
                  </Field>
                  <Field
                    label="Contact phone"
                    htmlFor={RESERVATION_FIELD_IDS.contactPhone}
                    hint="PH mobile: 09XXXXXXXXX or +639XXXXXXXXX"
                    error={visibleError('contactPhone')}
                  >
                    <Input
                      id={RESERVATION_FIELD_IDS.contactPhone}
                      type="tel"
                      inputMode="tel"
                      value={contact.phone}
                      onChange={(event) => onContactChange({ ...contact, phone: event.target.value })}
                      onBlur={() => markTouched('contactPhone')}
                      placeholder="e.g. 09171234567"
                      aria-invalid={Boolean(visibleError('contactPhone'))}
                      aria-describedby={
                        visibleError('contactPhone')
                          ? `${RESERVATION_FIELD_IDS.contactPhone}-error`
                          : undefined
                      }
                    />
                  </Field>
                </div>
                <div className="mt-3 flex items-center justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      contactTouched.current = false
                      onContactChange(contactSnapshot)
                      setEditingContact(false)
                      setTouched((current) => ({
                        ...current,
                        contactName: false,
                        contactPhone: false,
                      }))
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={!contactComplete}
                    onClick={() => {
                      contactTouched.current = true
                      setEditingContact(false)
                    }}
                  >
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-soft/60 px-3.5 py-2.5">
                <p className="min-w-0 truncate text-sm text-body">
                  <span className="font-medium text-ink">Contact:</span> {contact.name} ·{' '}
                  {contact.phone}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    contactTouched.current = true
                    setContactSnapshot(contact)
                    setEditingContact(true)
                  }}
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[13px] font-medium text-brand transition-colors hover:bg-brand-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                >
                  <Pencil className="size-3.5" aria-hidden /> Edit
                </button>
              </div>
            )}
          </div>

          <Field
            label="Notes for SAS staff (Optional)"
            htmlFor="event-staff-notes"
            className="sm:col-span-2"
          >
            <Textarea
              id="event-staff-notes"
              rows={2}
              value={details.staffNotes}
              onChange={(event) => set('staffNotes', event.target.value)}
              placeholder="Special setup, accessibility needs, or anything else we should know."
            />
          </Field>
        </div>
      </Card>

      {showSuggestions && (
        <Card className="mt-5" padding="md">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-[17px] font-semibold text-ink">Suggested resources</h3>
              <p className="mt-1 text-sm text-body">
                Based on your event type, participant count, and what
                {facilityName ? ` ${facilityName} ` : ' the facility '}already provides. Uncheck
                anything you don&apos;t need — your changes are kept if you edit the details again.
              </p>
            </div>
            <Sparkles className="mt-1 size-4 shrink-0 text-brand" aria-hidden />
          </div>

          {/* What the facility itself supplies is never offered as an extra:
              it is reported here, read-only. */}
          {included.length > 0 && (
            <p className="mt-4 flex items-start gap-2 rounded-xl border border-line bg-soft/70 px-3.5 py-2.5 text-[13px] text-body">
              <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-status-available" aria-hidden />
              <span>
                <span className="font-medium text-ink">Included:</span>{' '}
                {facilityName || 'This facility'} already provides {included.join(', ')}.
              </span>
            </p>
          )}

          {unverifiedSeating && (
            <p className="mt-3 text-[13px] text-muted">
              Seating for {facilityName || 'this facility'} has not been verified — Chairs and
              Tables are unchecked. Add the seating you actually need.
            </p>
          )}

          {suggestionsLoading && suggestions.length === 0 ? (
            <div className="mt-4 h-16 animate-pulse rounded-xl bg-soft" aria-hidden />
          ) : suggestions.length === 0 ? (
            included.length > 0 && (
              <p className="mt-4 text-sm text-muted">
                Everything this event needs is already provided by the facility. Add anything else
                from the equipment list below.
              </p>
            )
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {suggestions.map((suggestion) => {
                const quantity = items[suggestion.equipmentId] ?? 0
                const checked = quantity > 0
                const unavailable = suggestion.available <= 0
                // The badge must never claim one number while the row holds
                // another: an edited row says so, an untouched smart pick
                // states its suggested quantity. A checked-by-default row that
                // was unchecked counts as edited; an opt-in row left untouched
                // (or accepted as suggested) does not.
                const edited = checked ? quantity !== suggestion.quantity : suggestion.checkedByDefault
                return (
                  <li key={suggestion.equipmentId} className="flex items-start gap-3 py-3">
                    <input
                      id={`suggested-${suggestion.equipmentId}`}
                      type="checkbox"
                      className="mt-0.5 size-4 shrink-0 accent-[var(--color-brand)]"
                      checked={checked}
                      disabled={unavailable}
                      onChange={(event) =>
                        onToggleSuggestion(
                          suggestion.equipmentId,
                          event.target.checked,
                          suggestion.quantity,
                        )
                      }
                    />
                    <label
                      htmlFor={`suggested-${suggestion.equipmentId}`}
                      className="min-w-0 flex-1 cursor-pointer"
                    >
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="text-sm font-medium text-ink">{suggestion.name}</span>
                        {suggestion.unverified && <Badge tone="amber">Unverified</Badge>}
                        {edited ? (
                          <Badge tone="sky">Edited</Badge>
                        ) : suggestion.source === 'RECOMMENDER' ? (
                          <Badge tone="brand">
                            <Sparkles className="size-3" aria-hidden /> Smart pick ·{' '}
                            {suggestion.quantity}
                          </Badge>
                        ) : null}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted">
                        {suggestion.reason}
                        {suggestion.available > 0 && ` · ${suggestion.available} available`}
                        {suggestion.capped &&
                          suggestion.available > 0 &&
                          ` · capped at ${suggestion.available}`}
                        {unavailable && ' · not available for this date and time'}
                      </span>
                    </label>
                    <QuantityStepper
                      value={quantity}
                      max={suggestion.available}
                      disabled={unavailable}
                      label={suggestion.name}
                      onChange={(next) =>
                        onQuantity(suggestion.equipmentId, next, suggestion.available)
                      }
                    />
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      )}

      <Card className="mt-5" padding="md">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-[17px] font-semibold text-ink">Other equipment</h3>
            <p className="mt-1 text-sm text-body">
              Add anything the suggestions above missed. Quantities are limited by what is free for
              your date and time.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setShowPicker((open) => !open)}
            icon={<Plus className={cn('size-4 transition-transform', showPicker && 'rotate-45')} />}
            aria-expanded={showPicker}
            aria-controls="other-equipment-picker"
          >
            {showPicker ? 'Hide equipment list' : 'Add other equipment'}
          </Button>
        </div>

        {!showPicker && selectedExtras.length > 0 && (
          <ul className="mt-4 divide-y divide-line">
            {selectedExtras.map((item) => (
              <li key={item.id} className="flex items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{item.name}</p>
                  <p className="text-xs text-muted">
                    {item.availability.available} of {item.total_quantity} units available
                  </p>
                </div>
                <QuantityStepper
                  value={items[item.id] ?? 0}
                  max={item.availability.available}
                  label={item.name}
                  onChange={(next) => onQuantity(item.id, next, item.availability.available)}
                />
              </li>
            ))}
          </ul>
        )}

        {showPicker && (
          <div id="other-equipment-picker">
            <OtherEquipmentPicker
              equipment={equipment}
              items={items}
              onQuantity={onQuantity}
              operatorConfig={operatorConfig}
              operatorSelections={operatorSelections}
              onOperatorChange={onOperatorChange}
              loading={resourcesLoading}
            />
          </div>
        )}

        {operatorConfig && Object.keys(operatorConfig).length > 0 && (
          <p className="mt-4 flex items-start gap-1.5 text-xs text-muted">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            Operator/service fees are shown with each resource that offers one.
          </p>
        )}
      </Card>
    </section>
  )
}
