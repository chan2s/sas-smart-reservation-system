import type { CreateReservationPayload } from '@/lib/api'
import type { EventType } from '@/lib/types'

/**
 * Draft state + wire adapter for the "New reservation" wizard.
 *
 * The wizard collects a much smaller set of event details than the API has
 * historically accepted (see EventDetailsDraft). The draft below is the single
 * shape the wizard works with; {@link toCreateReservationPayload} adapts it to
 * the current backend contract so no backend change is required to ship this.
 */

// ---------------------------------------------------------------------------
// Draft shape
// ---------------------------------------------------------------------------

/** The five Event Details fields the wizard collects (Goal 1). */
export interface EventDetailsDraft {
  eventName: string
  /** '' until the requester picks a type — the select shows "Select type". */
  eventType: EventType | ''
  /** Raw input value — kept as a string so the field can be cleared while typing. */
  expectedParticipants: string
  /** Combines the old "Event purpose" and "Description" fields. */
  purpose: string
  /** Combines the old "Special requirements" and "Notes for SAS staff" fields. */
  staffNotes: string
}

/** Contact person — name plus a Philippine mobile number. */
export interface ContactDraft {
  name: string
  phone: string
}

export interface WizardDraft {
  facilityId: number | null
  /** ISO `yyyy-MM-dd`, or '' when no date is chosen yet. */
  dateISO: string
  startTime: string
  endTime: string
  details: EventDetailsDraft
  contact: ContactDraft
  items: Record<number, number>
  operatorSelections: Record<number, boolean>
  /** Equipment ids the requester touched — suggestions never overwrite these. */
  userEditedItems: number[]
  /** Step key, so a refresh restores the step too (indices differ for staff). */
  stepKey: string
}

export const EVENT_NAME_MAX = 80
export const PURPOSE_MAX = 150

export const EMPTY_DETAILS: EventDetailsDraft = {
  eventName: '',
  eventType: '',
  expectedParticipants: '',
  purpose: '',
  staffNotes: '',
}

export function emptyDraft(): WizardDraft {
  return {
    facilityId: null,
    dateISO: '',
    startTime: '',
    endTime: '',
    details: EMPTY_DETAILS,
    contact: { name: '', phone: '' },
    items: {},
    operatorSelections: {},
    userEditedItems: [],
    stepKey: 'facility',
  }
}

// ---------------------------------------------------------------------------
// sessionStorage persistence (survives a refresh mid-wizard)
// ---------------------------------------------------------------------------

const DRAFT_KEY = 'sas:reservation-wizard-draft:v1'

export function loadDraft(): WizardDraft | null {
  try {
    const raw = window.sessionStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<WizardDraft>
    // Merge over a fresh draft so a draft written by an older build (or a
    // partially-written one) can never leave a field undefined.
    const base = emptyDraft()
    return {
      ...base,
      ...parsed,
      details: { ...base.details, ...(parsed.details ?? {}) },
      contact: { ...base.contact, ...(parsed.contact ?? {}) },
      items: parsed.items ?? {},
      operatorSelections: parsed.operatorSelections ?? {},
      userEditedItems: parsed.userEditedItems ?? [],
    }
  } catch {
    return null
  }
}

export function saveDraft(draft: WizardDraft): void {
  try {
    window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // A full or disabled sessionStorage must never break the wizard.
  }
}

export function clearDraft(): void {
  try {
    window.sessionStorage.removeItem(DRAFT_KEY)
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Field validation (no form library is used in this project — these are the
// lightweight schema the wizard renders and gates "Continue" on)
// ---------------------------------------------------------------------------

export type ReservationFieldKey =
  | 'eventName'
  | 'eventType'
  | 'expectedParticipants'
  | 'purpose'
  | 'contactName'
  | 'contactPhone'

/** Render + focus order of the validated fields. */
export const RESERVATION_FIELD_ORDER: ReservationFieldKey[] = [
  'eventName',
  'eventType',
  'expectedParticipants',
  'purpose',
  'contactName',
  'contactPhone',
]

/** DOM ids, shared by the inputs and the scroll-to-first-error behaviour. */
export const RESERVATION_FIELD_IDS: Record<ReservationFieldKey, string> = {
  eventName: 'event-name',
  eventType: 'event-type',
  expectedParticipants: 'expected-participants',
  purpose: 'event-purpose',
  contactName: 'contact-name',
  contactPhone: 'contact-phone',
}

/**
 * Normalise a Philippine mobile number for storage: spaces, dashes and
 * parentheses are removed and the `63…` form is rewritten as `+63…`.
 */
export function normalizePhone(value: string): string {
  const digits = value.replace(/[\s\-()]/g, '')
  if (/^639\d{9}$/.test(digits)) return `+${digits}`
  return digits
}

/** True for `09XXXXXXXXX` or `+639XXXXXXXXX` (after normalisation). */
export function isValidPhMobile(value: string): boolean {
  return /^09\d{9}$/.test(normalizePhone(value)) || /^\+639\d{9}$/.test(normalizePhone(value))
}

export function isPositiveInteger(value: string): boolean {
  return /^\d+$/.test(value.trim()) && Number(value) >= 1
}

export interface ReservationValidationInput {
  details: EventDetailsDraft
  contact: ContactDraft
  /** Capacity of the facility chosen in step 1 (0 when unknown). */
  capacity: number
  facilityName: string
}

/**
 * All field-level errors for the Details & Resources step. An empty object
 * means the step is valid; the wizard derives its Continue gate (and its
 * "what is missing" message) from this single source of truth.
 */
export function reservationFieldErrors({
  details,
  contact,
  capacity,
  facilityName,
}: ReservationValidationInput): Partial<Record<ReservationFieldKey, string>> {
  const errors: Partial<Record<ReservationFieldKey, string>> = {}

  if (!details.eventName.trim()) errors.eventName = 'Event name is required.'
  else if (details.eventName.length > EVENT_NAME_MAX)
    errors.eventName = `Keep the event name under ${EVENT_NAME_MAX} characters.`

  if (!details.eventType) errors.eventType = 'Select an event type.'

  const participants = details.expectedParticipants.trim()
  if (!participants) errors.expectedParticipants = 'Expected participants is required.'
  else if (!isPositiveInteger(participants))
    errors.expectedParticipants = 'Enter a whole number of at least 1.'
  else if (capacity > 0 && Number(participants) > capacity)
    // Deliberately an error, never a silent clamp: the requester must pick a
    // smaller number or a bigger facility.
    errors.expectedParticipants = `${facilityName || 'This facility'} seats ${capacity}. Choose a smaller number or another facility.`

  if (!details.purpose.trim()) errors.purpose = 'Purpose is required.'
  else if (details.purpose.length > PURPOSE_MAX)
    errors.purpose = `Keep the purpose under ${PURPOSE_MAX} characters.`

  if (!contact.name.trim()) errors.contactName = 'Contact name is required.'
  // The phone is required whenever the draft has none — i.e. the profile had
  // no number to prefill from (Goal 2).
  if (!contact.phone.trim()) errors.contactPhone = 'Phone number is required.'
  else if (!isValidPhMobile(contact.phone))
    errors.contactPhone = 'Use a PH mobile number: 09XXXXXXXXX or +639XXXXXXXXX.'

  return errors
}

/** Short labels used in the "complete these fields" summary message. */
const FIELD_LABELS: Record<ReservationFieldKey, string> = {
  eventName: 'Event name',
  eventType: 'Event type',
  expectedParticipants: 'Expected participants',
  purpose: 'Purpose',
  contactName: 'Contact name',
  contactPhone: 'Contact phone',
}

export function missingFieldLabels(
  errors: Partial<Record<ReservationFieldKey, string>>,
): string[] {
  return RESERVATION_FIELD_ORDER.filter((key) => errors[key]).map((key) => FIELD_LABELS[key])
}

// ---------------------------------------------------------------------------
// Wire adapter
// ---------------------------------------------------------------------------

export interface SubmitItems {
  equipment_id: number
  quantity: number
  operator?: boolean
}

/** Staff "reserve on behalf of an external organization" block. */
export interface ExternalRequesterDraft {
  organization: string
  organization_type: string
  contact_person: string
  contact_email: string
}

export interface SubmitReservationContext {
  /** Resolved items (operator opt-ins included). */
  items: SubmitItems[]
  /** Organization the reservation is for — derived from the account, never typed. */
  organization: string
  /** Staff-only: create on behalf of another campus user. */
  requesterId?: number
  /** Staff-only: external requester block (replaces the campus fields). */
  external?: ExternalRequesterDraft
}

/**
 * Maps the slim wizard draft onto the current API payload.
 *
 * TODO(backend-migration): the API still exposes the legacy `description` and
 * `special_requirements` columns and a `contact_person` string. The form no
 * longer collects separate values for them, so they are submitted empty (or,
 * for `contact_person`, from the contact row). Once the backend drops those
 * columns this adapter can go away and the draft can be sent as-is.
 */
export function toCreateReservationPayload(
  draft: WizardDraft,
  { items, organization, requesterId, external }: SubmitReservationContext,
): CreateReservationPayload {
  const base = {
    facility_id: draft.facilityId as number,
    date: draft.dateISO,
    start_time: draft.startTime,
    end_time: draft.endTime,
    event_name: draft.details.eventName.trim(),
    // Non-empty by the time Continue/Submit is enabled (see reservationFieldErrors).
    event_type: draft.details.eventType as EventType,
    // Merged into the single "Purpose" field — no duplicate value is sent.
    purpose: draft.details.purpose.trim(),
    description: '',
    expected_participants: Number(draft.details.expectedParticipants) || 0,
    // "Special requirements" was merged into "Notes for SAS staff".
    special_requirements: '',
    notes: draft.details.staffNotes.trim(),
    items,
  }

  if (external) {
    return {
      ...base,
      // The external block owns the organization + contact details; the phone
      // collected for campus requesters does not apply here.
      organization: external.organization,
      organization_type: external.organization_type,
      contact_person: external.contact_person,
      contact_email: external.contact_email,
      contact_phone: null,
      requester_type: 'EXTERNAL',
    }
  }

  return {
    ...base,
    organization,
    contact_person: draft.contact.name.trim(),
    contact_email: undefined,
    contact_phone: normalizePhone(draft.contact.phone) || null,
    ...(requesterId ? { requester_id: requesterId } : {}),
  }
}
