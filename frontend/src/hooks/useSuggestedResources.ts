import { useEffect, useMemo, useRef, useState } from 'react'
import { useRecommendResources } from '@/hooks/queries'
import type { EventType, Recommendation, RequesterType, ReservableResource } from '@/lib/types'

export interface SuggestedResource {
  equipmentId: number
  name: string
  category: string
  unit: string
  /** Units the configured rule says the event needs (never inventory). */
  quantity: number
  /** Availability-capped quantity safe to add: min(quantity, available). */
  recommended: number
  /** Units free during the selected schedule. */
  available: number
  status: 'AVAILABLE' | 'PARTIAL' | 'UNAVAILABLE'
  /** Only set when the rule quantity exceeds what the schedule can provide. */
  warning: string | null
  reason: string
  calculation: string
  /** Configured rate for this item, or null when it is unpriced. */
  unitPrice: string | null
  /** Payable estimate for the selected requester type. */
  estimatedCost: string | null
  feeApplies: boolean
}

export interface SuggestedResourcesState {
  suggestions: SuggestedResource[]
  loading: boolean
  error: boolean
  /**
   * Event details the recommender still needs (event type, participants,
   * facility, schedule). Empty when a request could be made.
   */
  missingDetails: string[]
  /**
   * Facility equipment ids owned by the latest recommendation response. The
   * Other equipment list filters on this set, NOT on the rendered suggestions:
   * an item that is temporarily unavailable (or ignored) must not reappear in
   * the catalog while the recommender still claims it.
   */
  recommendedIds: Set<number>
  ignore: (equipmentId: number) => void
}

export interface UseSuggestedResourcesArgs {
  active: boolean
  eventType: EventType | ''
  eventName: string
  participants: number
  equipment: ReservableResource[]
  facilityId: number | null
  dateISO: string
  startTime: string
  endTime: string
  purpose: string
  staffNotes: string
  requesterType: RequesterType
  publicReservation?: boolean
}

/** Recommendations are shown only when the backend checked this exact facility and window. */
export function useSuggestedResources({
  active,
  eventType,
  eventName,
  participants,
  equipment,
  facilityId,
  dateISO,
  startTime,
  endTime,
  purpose,
  staffNotes,
  requesterType,
  publicReservation = false,
}: UseSuggestedResourcesArgs): SuggestedResourcesState {
  const recommendResources = useRecommendResources(publicReservation)
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null)
  const [fetchedFor, setFetchedFor] = useState<string | null>(null)
  const [errorFor, setErrorFor] = useState<string | null>(null)
  // Ignoring a suggestion is the requester's decision, so it must survive the
  // edits that keep recalculating the recommendation. It only resets when the
  // facility changes, because that replaces the whole resource list.
  const [ignored, setIgnored] = useState<Set<number>>(() => new Set())
  const requestRef = useRef<string | null>(null)

  const missingDetails = useMemo(() => {
    const missing: string[] = []
    if (!eventType) missing.push('event type')
    if (participants < 1) missing.push('expected participants')
    if (facilityId == null) missing.push('facility')
    if (!dateISO) missing.push('reservation date')
    if (!startTime || !endTime) missing.push('reservation start and end time')
    return missing
  }, [eventType, participants, facilityId, dateISO, startTime, endTime])

  const enabled = active && missingDetails.length === 0
  // Every input the backend reads is part of the key, so any change supersedes
  // the last request (and any response still in flight for it).
  const requestKey = [
    eventType, eventName.trim(), participants, facilityId ?? '', purpose.trim(), staffNotes.trim(),
    dateISO, startTime, endTime, requesterType,
  ].join('|')

  useEffect(() => {
    setIgnored(new Set())
  }, [facilityId])

  useEffect(() => {
    if (!enabled) {
      requestRef.current = null
      setRecommendations(null)
      setFetchedFor(null)
      setErrorFor(null)
      return
    }
    if (fetchedFor === requestKey) return
    requestRef.current = requestKey
    const timer = window.setTimeout(() => {
      recommendResources.mutate(
        {
          event_type: eventType,
          event_name: eventName,
          expected_participants: participants,
          facility_id: facilityId ?? undefined,
          purpose,
          special_requirements: staffNotes,
          date: dateISO,
          start_time: startTime,
          end_time: endTime,
          requester_type: requesterType,
        },
        {
          onSuccess: (data) => {
            // A response for an older form state must never replace the
            // recommendations for the current one.
            if (requestRef.current !== requestKey) return
            setRecommendations(data.recommendations)
            setErrorFor(null)
            setFetchedFor(requestKey)
          },
          onError: () => {
            if (requestRef.current !== requestKey) return
            setRecommendations(null)
            setErrorFor(requestKey)
            setFetchedFor(requestKey)
          },
        },
      )
    }, 350)
    return () => window.clearTimeout(timer)
    // Mutation identity is stable for the mounted hook; the request key carries all inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, requestKey])

  const suggestions = useMemo(() => {
    if (!enabled || !recommendations) return []
    const byId = new Map(equipment.map((item) => [item.id, item]))
    return recommendations.flatMap((recommendation) => {
      const item = byId.get(recommendation.equipment_id)
      // Not offered at this facility, or nothing free during this schedule:
      // such a row could never be added, so it is not shown as available.
      // PARTIAL rows stay visible with the shortage called out below.
      if (!item || recommendation.available < 1 || ignored.has(item.id)) return []
      return [{
        equipmentId: item.id,
        name: item.name,
        category: item.category.name,
        unit: item.unit,
        quantity: recommendation.quantity,
        recommended: Math.min(recommendation.quantity, recommendation.available),
        available: recommendation.available,
        status: recommendation.status,
        warning: recommendation.warning,
        reason: recommendation.reason,
        calculation: recommendation.calculation,
        unitPrice: recommendation.unit_price ?? null,
        estimatedCost: recommendation.estimated_cost ?? null,
        feeApplies: Boolean(recommendation.fee_applies),
      }]
    })
  }, [enabled, recommendations, equipment, ignored])

  const recommendedIds = useMemo(() => {
    const ids = new Set<number>()
    if (!recommendations) return ids
    const offered = new Set(equipment.map((item) => item.id))
    for (const recommendation of recommendations) {
      if (offered.has(recommendation.equipment_id) && !ignored.has(recommendation.equipment_id)) {
        ids.add(recommendation.equipment_id)
      }
    }
    return ids
  }, [recommendations, equipment, ignored])

  return {
    suggestions,
    loading: Boolean(enabled && fetchedFor !== requestKey),
    error: errorFor === requestKey,
    missingDetails,
    recommendedIds,
    ignore: (equipmentId) => setIgnored((current) => new Set(current).add(equipmentId)),
  }
}
