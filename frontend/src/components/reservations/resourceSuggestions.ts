import type { EventType, SeatingType } from '@/lib/types'

/**
 * Resource suggestion rules for the reservation wizard.
 *
 * This is the single, editable place to teach the wizard which equipment an
 * event type usually needs. A rule matches the *facility's own* resources by
 * keyword (equipment names differ between facilities), so the wizard never
 * suggests an item the chosen facility cannot provide.
 *
 * What the facility already provides (see FacilitySeatingMetadata) is then
 * subtracted from the rule's need:
 *
 *     suggested = max(0, needed − builtIn)
 *
 * so a dining hall that already seats 300 never gets 109 folding chairs
 * suggested for a 109-person seminar.
 */
export interface ResourceSuggestionRule {
  /** Stable key, used for React keys and as a label fallback. */
  key: string
  /** Human label shown when the rule cannot be matched to a resource. */
  label: string
  /** Lower-case substrings matched against the resource name. */
  keywords: string[]
  /** Default quantity for `participants` attendees. */
  quantity: (participants: number) => number
  /**
   * Builds the row's explanation from the FINAL quantity, so the text can
   * never state a different number than the one suggested.
   */
  reasonFor: (quantity: number) => string
  /**
   * True for seating rules (chairs, tables). Their built-in allowance is the
   * facility's `built_in_seats` rather than a simple 0/1 token, and a facility
   * with no `seating_type` leaves them unverified (unchecked by default).
   */
  seating?: boolean
  /**
   * Facility `built_ins` tokens that make this rule unnecessary. When one is
   * listed, the item is not suggested at all and is shown as "included".
   */
  builtInTokens?: string[]
  /** Optional per-event-type quantity overrides. */
  perEvent?: Partial<
    Record<EventType, { quantity: (participants: number) => number; reasonFor: (quantity: number) => string }>
  >
}

const perParticipant = (participants: number) => participants
const perTenParticipants = (participants: number) => Math.max(1, Math.ceil(participants / 10))
const fixed = (count: number) => () => count

/** "1 unit" / "2 units" — never disagrees with the quantity it is given. */
const count = (quantity: number, singular: string, plural = `${singular}s`) =>
  `${quantity} ${quantity === 1 ? singular : plural}`

export const RESOURCE_SUGGESTION_RULES: ResourceSuggestionRule[] = [
  {
    key: 'chairs',
    label: 'Chairs',
    keywords: ['chair', 'monobloc', 'seat'],
    quantity: perParticipant,
    reasonFor: () => '1 per participant',
    seating: true,
  },
  {
    key: 'tables',
    label: 'Tables',
    keywords: ['table', 'desk'],
    quantity: perTenParticipants,
    reasonFor: () => '1 per 10 participants',
    seating: true,
  },
  {
    key: 'sound_system',
    label: 'Sound system',
    keywords: ['sound', 'speaker', 'pa system', 'amplifier'],
    quantity: fixed(1),
    reasonFor: (quantity) => `${count(quantity, 'system')} per event`,
    builtInTokens: ['sound_system'],
  },
  {
    key: 'projector',
    label: 'Projector',
    keywords: ['projector', 'lcd', 'screen'],
    quantity: fixed(1),
    reasonFor: (quantity) => `${count(quantity, 'unit')} per event`,
    builtInTokens: ['projector'],
  },
  {
    // Microphones are never treated as part of a built-in sound system: a
    // facility must list them explicitly for them to disappear.
    key: 'microphone',
    label: 'Microphone',
    keywords: ['microphone', 'mic'],
    quantity: fixed(2),
    reasonFor: (quantity) => `${count(quantity, 'unit')} per event`,
  },
  {
    key: 'extension_cord',
    label: 'Extension cord',
    keywords: ['extension', 'cord'],
    quantity: perTenParticipants,
    reasonFor: () => '1 per 10 participants',
  },
  {
    key: 'tent',
    label: 'Tent / canopy',
    keywords: ['tent', 'canopy', 'canopies'],
    quantity: fixed(1),
    reasonFor: (quantity) => `${count(quantity, 'tent')} per event`,
  },
  {
    key: 'court_equipment',
    label: 'Sports equipment',
    keywords: ['ball', 'net', 'scoreboard', 'goal', 'sports'],
    quantity: fixed(1),
    reasonFor: (quantity) => `${count(quantity, 'set')} per event`,
  },
]

/**
 * Rule keys suggested per event type, in display order. Add or reorder entries
 * here to change what the wizard pre-selects — no component changes needed.
 *
 * Sports events are contested on the floor itself: spectators use the
 * bleachers, so no seating is suggested.
 */
export const EVENT_TYPE_SUGGESTIONS: Record<EventType, string[]> = {
  SEMINAR: ['chairs', 'tables', 'sound_system', 'projector', 'microphone'],
  MEETING: ['chairs', 'tables', 'projector', 'sound_system'],
  WORKSHOP: ['chairs', 'tables', 'projector', 'extension_cord'],
  TRAINING: ['chairs', 'tables', 'projector', 'extension_cord', 'microphone'],
  SPORTS: ['court_equipment', 'sound_system', 'microphone'],
  CONFERENCE: ['chairs', 'tables', 'sound_system', 'projector', 'microphone'],
  RECOGNITION: ['chairs', 'tables', 'sound_system', 'microphone', 'tent'],
  ORIENTATION: ['chairs', 'sound_system', 'projector', 'microphone'],
  CULTURAL: ['chairs', 'sound_system', 'microphone', 'tent'],
  ACADEMIC: ['chairs', 'tables', 'projector', 'extension_cord'],
  OTHER: ['chairs', 'tables', 'sound_system'],
}

// ---------------------------------------------------------------------------
// Facility metadata
// ---------------------------------------------------------------------------

/** The facility fields the suggestions depend on. */
export interface FacilitySeatingMetadata {
  /** Null means the space has not been verified yet. */
  seatingType: SeatingType | null
  /** Seats the space already provides at its own tables/fixed rows. */
  builtInSeats: number | null
  /** Tokens such as `tables`, `chairs`, `projector`, `sound_system`, `stage`. */
  builtIns: string[]
}

export const EMPTY_FACILITY_METADATA: FacilitySeatingMetadata = {
  seatingType: null,
  builtInSeats: null,
  builtIns: [],
}

/** Display labels for the known `built_ins` tokens (unknown ones are title-cased). */
export const BUILT_IN_LABELS: Record<string, string> = {
  tables: 'Tables',
  chairs: 'Chairs',
  projector: 'Projector',
  sound_system: 'Sound system',
  stage: 'Stage',
  podium: 'Podium',
  bleachers: 'Bleachers',
}

export function builtInLabel(token: string): string {
  return (
    BUILT_IN_LABELS[token] ??
    token
      .replace(/[_-]+/g, ' ')
      .trim()
      .replace(/\b\w/g, (character) => character.toUpperCase())
  )
}

/**
 * How many units of this rule the facility already provides.
 *
 * Seating rules use the facility's own seat count (only "tables and chairs"
 * and "fixed rows" imply seating; an open floor provides none). Everything
 * else is all-or-nothing: one token in `built_ins` covers the whole rule.
 */
export function builtInAllowance(
  rule: ResourceSuggestionRule,
  facility: FacilitySeatingMetadata,
): number {
  if (rule.seating) {
    if (facility.seatingType !== 'tables_and_chairs' && facility.seatingType !== 'fixed_rows') {
      return 0
    }
    return facility.builtInSeats ?? 0
  }
  if (!rule.builtInTokens?.length) return 0
  return rule.builtInTokens.some((token) => facility.builtIns.includes(token)) ? 1 : 0
}

/**
 * True when a seating rule cannot be trusted because the facility has no
 * recorded seating type: the row is offered unchecked (opt-in) instead.
 */
export function isUnverifiedSeating(
  rule: ResourceSuggestionRule,
  facility: FacilitySeatingMetadata,
): boolean {
  return Boolean(rule.seating) && facility.seatingType == null
}

const RULES_BY_KEY = new Map(RESOURCE_SUGGESTION_RULES.map((rule) => [rule.key, rule]))

/** The rules (in order) that apply to an event type. */
export function suggestionRulesFor(eventType: EventType): ResourceSuggestionRule[] {
  const keys = EVENT_TYPE_SUGGESTIONS[eventType] ?? EVENT_TYPE_SUGGESTIONS.OTHER
  return keys
    .map((key) => RULES_BY_KEY.get(key))
    .filter((rule): rule is ResourceSuggestionRule => rule != null)
}

/** How many units the event needs, ignoring what the facility provides. */
export function suggestionQuantity(
  rule: ResourceSuggestionRule,
  eventType: EventType,
  participants: number,
): number {
  const override = rule.perEvent?.[eventType]
  const quantity = (override?.quantity ?? rule.quantity)(participants)
  return Number.isFinite(quantity) && quantity > 0 ? Math.floor(quantity) : 0
}

/** Explanation for the quantity that was actually produced. */
export function suggestionReason(
  rule: ResourceSuggestionRule,
  eventType: EventType,
  quantity: number,
): string {
  const override = rule.perEvent?.[eventType]
  return (override?.reasonFor ?? rule.reasonFor)(quantity)
}
