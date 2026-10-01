import { useEffect, useMemo, useRef, useState } from 'react'
import { useRecommendResources } from '@/hooks/queries'
import {
  builtInAllowance,
  builtInLabel,
  isUnverifiedSeating,
  suggestionQuantity,
  suggestionReason,
  suggestionRulesFor,
  type FacilitySeatingMetadata,
  type ResourceSuggestionRule,
} from '@/components/reservations/resourceSuggestions'
import type { EventType, Recommendation, RequesterType, ReservableResource } from '@/lib/types'

/**
 * One suggested resource row for the "Suggested resources" section.
 *
 * `quantity` is what we suggest for the current event type and participant
 * count, after subtracting what the facility already provides and after the
 * stock cap for the chosen window. The requester can uncheck the row or change
 * the quantity — their edits win.
 */
export interface SuggestedResource {
  equipmentId: number
  name: string
  category: string
  /** Suggested quantity (post-facility-allowance, post-stock-cap). */
  quantity: number
  /** Units free for the chosen date/time window. */
  available: number
  /** Where the suggestion came from. */
  source: 'RULES' | 'RECOMMENDER'
  /** Why this quantity — e.g. "1 per participant". */
  reason: string
  /** True when stock limited the suggested quantity. */
  capped: boolean
  /** False for rows the requester must opt into (unverified seating). */
  checkedByDefault: boolean
  /** True for seating on a facility with no verified seating type. */
  unverified: boolean
}

export interface SuggestedResourcesState {
  suggestions: SuggestedResource[]
  /** Items the facility already provides, labelled — shown read-only. */
  included: string[]
  /** True when the facility has no seating type recorded. */
  unverifiedSeating: boolean
  loading: boolean
}

export interface UseSuggestedResourcesArgs {
  /** True while the Details & Resources step is on screen — gates all fetching. */
  active: boolean
  /** '' until the requester picks an event type. */
  eventType: EventType | ''
  /** Expected participants, 0 when not yet valid. */
  participants: number
  /** Resources the chosen facility actually offers. */
  equipment: ReservableResource[]
  /** What the chosen facility already provides (drives the subtraction). */
  facility: FacilitySeatingMetadata
  facilityId: number | null
  dateISO: string
  startTime: string
  endTime: string
  purpose: string
  /** Free-text notes; sent to the recommender as extra context only. */
  staffNotes: string
  requesterType: RequesterType
}

/** First unmatched rule keyword wins; a resource is only suggested once. */
function matchResource(
  rule: ResourceSuggestionRule,
  equipment: ReservableResource[],
  used: Set<number>,
): ReservableResource | undefined {
  return equipment.find(
    (item) =>
      !used.has(item.id) &&
      rule.keywords.some((keyword) => item.name.toLowerCase().includes(keyword)),
  )
}

/** True when a resource belongs to a rule that already produced a row. */
function matchesAny(
  rules: Iterable<ResourceSuggestionRule>,
  item: ReservableResource,
): boolean {
  const name = item.name.toLowerCase()
  for (const rule of rules) {
    if (rule.keywords.some((keyword) => name.includes(keyword))) return true
  }
  return false
}

/**
 * Suggestion logic for the merged Details & Resources step.
 *
 * Two sources feed one list:
 *  1. the editable rule config ({@link RESOURCE_SUGGESTION_RULES}), which is
 *     instant and facility-aware, and
 *  2. the backend recommender, which adds anything the rules did not cover
 *     (the "smart recommendations" feature — kept intact).
 *
 * Every rule's need is reduced by what the facility already provides, so a
 * dining hall with 300 seats never gets 109 chairs suggested. Rows that end up
 * at zero are dropped, and the facility's built-ins are reported separately as
 * read-only "included" information.
 *
 * Rows are only produced once the event type and participant count are valid.
 */
export function useSuggestedResources({
  active,
  eventType,
  participants,
  equipment,
  facility,
  facilityId,
  dateISO,
  startTime,
  endTime,
  purpose,
  staffNotes,
  requesterType,
}: UseSuggestedResourcesArgs): SuggestedResourcesState {
  const recommendResources = useRecommendResources()
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null)
  const [fetchedFor, setFetchedFor] = useState<string | null>(null)
  // Stable handle to the latest request so a superseded response is discarded.
  const requestRef = useRef<string | null>(null)

  const enabled = active && facilityId != null && participants >= 1 && Boolean(eventType)

  // Everything the recommender's answer depends on. Any change invalidates the
  // previous answer and triggers exactly one new request.
  const requestKey = `${eventType}|${participants}|${facilityId ?? ''}|${purpose.trim()}|${staffNotes.trim()}|${dateISO}|${startTime}|${endTime}|${requesterType}`

  useEffect(() => {
    if (!enabled) {
      requestRef.current = null
      setRecommendations(null)
      setFetchedFor(null)
      return
    }
    if (fetchedFor === requestKey) return
    requestRef.current = requestKey
    // Debounced: the key includes the free-text purpose/notes, so without this
    // every keystroke would fire a request. The rule-based rows below update
    // instantly and do not wait for this call.
    const timer = window.setTimeout(() => {
      recommendResources.mutate(
        {
          event_type: eventType,
          expected_participants: participants,
          facility_id: facilityId ?? undefined,
          purpose,
          // The form no longer has a separate "special requirements" field; the
          // merged staff notes are useful context for the recommender's rules.
          special_requirements: staffNotes,
          date: dateISO || undefined,
          start_time: startTime || undefined,
          end_time: endTime || undefined,
          requester_type: requesterType,
        },
        {
          onSuccess: (data) => {
            if (requestRef.current !== requestKey) return
            setRecommendations(data.recommendations)
            setFetchedFor(requestKey)
          },
          // A failed recommender call must not block the step — the rule-based
          // suggestions stand on their own.
          onError: () => {
            if (requestRef.current !== requestKey) return
            setRecommendations(null)
            setFetchedFor(requestKey)
          },
        },
      )
    }, 400)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey, enabled])

  const suggestions = useMemo(() => {
    if (!enabled) return []
    const used = new Set<number>()
    const claimedRules: ResourceSuggestionRule[] = []
    const rows: SuggestedResource[] = []

    for (const rule of suggestionRulesFor(eventType as EventType)) {
      const item = matchResource(rule, equipment, used)
      if (!item) continue
      used.add(item.id)
      claimedRules.push(rule)

      const available = item.availability.available
      const needed = suggestionQuantity(rule, eventType as EventType, participants)
      // What the facility already provides is subtracted from the need.
      const builtIn = builtInAllowance(rule, facility)
      const suggested = Math.max(0, needed - builtIn)
      const unverified = isUnverifiedSeating(rule, facility)

      // A resource the facility already supplies in full is not a suggestion —
      // it is reported as "included" instead (see `included` below).
      if (suggested <= 0 && !unverified) continue

      const quantity = Math.min(suggested, available)
      rows.push({
        equipmentId: item.id,
        name: item.name,
        category: item.category.name,
        quantity,
        available,
        source: 'RULES',
        reason: suggestionReason(rule, eventType as EventType, suggested),
        capped: suggested > available,
        // Unverified seating must be explicitly opted into.
        checkedByDefault: !unverified && quantity > 0,
        unverified,
      })
    }

    // Backend recommendations for anything the rules did not cover. Equipment
    // ids that no longer belong to the facility are simply dropped, and a
    // recommendation for a category a rule already covered (say a second
    // microphone model) is dropped too, so a rule never double-counts.
    const byId = new Map(equipment.map((item) => [item.id, item]))
    for (const recommendation of recommendations ?? []) {
      if (used.has(recommendation.equipment_id)) continue
      const item = byId.get(recommendation.equipment_id)
      if (!item) continue
      if (matchesAny(claimedRules, item)) continue
      used.add(item.id)
      rows.push({
        equipmentId: item.id,
        name: item.name,
        category: item.category.name,
        quantity: Math.max(0, recommendation.recommended),
        available: recommendation.available,
        source: 'RECOMMENDER',
        reason: recommendation.reason || 'Suggested for this kind of event',
        capped: Boolean(recommendation.warning),
        checkedByDefault: recommendation.recommended > 0,
        unverified: false,
      })
    }

    return rows
  }, [enabled, eventType, participants, equipment, recommendations, facility])

  const included = useMemo(
    () => facility.builtIns.map((token) => builtInLabel(token)),
    [facility.builtIns],
  )

  return {
    suggestions,
    included,
    unverifiedSeating: facility.seatingType == null,
    loading: recommendResources.isPending,
  }
}
