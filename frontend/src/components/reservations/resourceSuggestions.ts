import type { EventType } from '@/lib/types'

/**
 * Resource suggestion rules for the reservation wizard.
 *
 * This is the single, editable place to teach the wizard which equipment an
 * event type usually needs. A rule matches the *facility's own* resources by
 * keyword (equipment names differ between facilities), so the wizard never
 * suggests an item the chosen facility cannot provide.
 *
 * Quantities are capped by the facility's live stock for the chosen window
 * when the suggestion is applied (see useSuggestedResources).
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
  /** Human explanation of the arithmetic, shown under the row. */
  reason: string
  /** Optional per-event-type quantity overrides. */
  perEvent?: Partial<Record<EventType, (participants: number) => number>>
}

const perParticipant = (participants: number) => participants
const perTenParticipants = (participants: number) => Math.max(1, Math.ceil(participants / 10))
const fixed = (count: number) => () => count

export const RESOURCE_SUGGESTION_RULES: ResourceSuggestionRule[] = [
  {
    key: 'chairs',
    label: 'Chairs',
    keywords: ['chair', 'monobloc', 'seat'],
    quantity: perParticipant,
    reason: '1 per participant',
    perEvent: {
      MEETING: perParticipant,
      SPORTS: (participants) => Math.ceil(participants / 2),
    },
  },
  {
    key: 'tables',
    label: 'Tables',
    keywords: ['table', 'desk'],
    quantity: perTenParticipants,
    reason: '1 per 10 participants',
  },
  {
    key: 'sound_system',
    label: 'Sound system',
    keywords: ['sound', 'speaker', 'pa system', 'amplifier'],
    quantity: fixed(1),
    reason: '1 system per event',
  },
  {
    key: 'projector',
    label: 'Projector',
    keywords: ['projector', 'lcd', 'screen'],
    quantity: fixed(1),
    reason: '1 unit per event',
  },
  {
    key: 'microphone',
    label: 'Microphone',
    keywords: ['microphone', 'mic', 'wireless mic'],
    quantity: fixed(2),
    reason: '2 units per event',
  },
  {
    key: 'extension_cord',
    label: 'Extension cord',
    keywords: ['extension', 'cord'],
    quantity: perTenParticipants,
    reason: '1 per 10 participants',
  },
  {
    key: 'tent',
    label: 'Tent / canopy',
    keywords: ['tent', 'canopy', 'canopies'],
    quantity: fixed(1),
    reason: '1 per event',
  },
  {
    key: 'court_equipment',
    label: 'Sports equipment',
    keywords: ['ball', 'net', 'scoreboard', 'goal', 'sports'],
    quantity: fixed(1),
    reason: '1 set per event',
  },
]

/**
 * Rule keys suggested per event type, in display order. Add or reorder entries
 * here to change what the wizard pre-selects — no component changes needed.
 */
export const EVENT_TYPE_SUGGESTIONS: Record<EventType, string[]> = {
  SEMINAR: ['chairs', 'tables', 'sound_system', 'projector', 'microphone'],
  MEETING: ['chairs', 'tables', 'projector', 'sound_system'],
  WORKSHOP: ['chairs', 'tables', 'projector', 'extension_cord'],
  TRAINING: ['chairs', 'tables', 'projector', 'extension_cord', 'microphone'],
  SPORTS: ['chairs', 'court_equipment', 'sound_system', 'microphone'],
  CONFERENCE: ['chairs', 'tables', 'sound_system', 'projector', 'microphone'],
  RECOGNITION: ['chairs', 'tables', 'sound_system', 'microphone', 'tent'],
  ORIENTATION: ['chairs', 'sound_system', 'projector', 'microphone'],
  CULTURAL: ['chairs', 'sound_system', 'microphone', 'tent'],
  ACADEMIC: ['chairs', 'tables', 'projector', 'extension_cord'],
  OTHER: ['chairs', 'tables', 'sound_system'],
}

const RULES_BY_KEY = new Map(RESOURCE_SUGGESTION_RULES.map((rule) => [rule.key, rule]))

/** The rules (in order) that apply to an event type. */
export function suggestionRulesFor(eventType: EventType): ResourceSuggestionRule[] {
  const keys = EVENT_TYPE_SUGGESTIONS[eventType] ?? EVENT_TYPE_SUGGESTIONS.OTHER
  return keys
    .map((key) => RULES_BY_KEY.get(key))
    .filter((rule): rule is ResourceSuggestionRule => rule != null)
}

/** Quantity for one rule, honouring any per-event-type override. */
export function suggestionQuantity(
  rule: ResourceSuggestionRule,
  eventType: EventType,
  participants: number,
): number {
  const override = rule.perEvent?.[eventType]
  const quantity = (override ?? rule.quantity)(participants)
  return Number.isFinite(quantity) && quantity > 0 ? Math.floor(quantity) : 0
}
