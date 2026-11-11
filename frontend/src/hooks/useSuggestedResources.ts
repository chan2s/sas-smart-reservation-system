import { useEffect, useMemo, useRef, useState } from 'react'
import { useRecommendResources } from '@/hooks/queries'
import type { EventType, Recommendation, RequesterType, ReservableResource } from '@/lib/types'

export interface SuggestedResource {
  equipmentId: number
  name: string
  category: string
  unit: string
  quantity: number
  available: number
  reason: string
}

export interface SuggestedResourcesState {
  suggestions: SuggestedResource[]
  loading: boolean
  error: boolean
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
  selectedItems: Record<number, number>
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
  selectedItems,
}: UseSuggestedResourcesArgs): SuggestedResourcesState {
  const recommendResources = useRecommendResources(publicReservation)
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null)
  const [fetchedFor, setFetchedFor] = useState<string | null>(null)
  const [errorFor, setErrorFor] = useState<string | null>(null)
  const [ignored, setIgnored] = useState<{ key: string; ids: Set<number> }>({ key: '', ids: new Set() })
  const requestRef = useRef<string | null>(null)

  const enabled = Boolean(
    active && eventType && facilityId != null && participants >= 1 && dateISO && startTime && endTime,
  )
  const requestKey = [
    eventType, eventName.trim(), participants, facilityId ?? '', purpose.trim(), staffNotes.trim(),
    dateISO, startTime, endTime, requesterType,
  ].join('|')

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
      const quantity = Math.min(recommendation.recommended, recommendation.available)
      if (
        !item || quantity < 1 || recommendation.available < recommendation.quantity ||
        selectedItems[item.id] > 0 || (ignored.key === requestKey && ignored.ids.has(item.id))
      ) return []
      return [{
        equipmentId: item.id,
        name: item.name,
        category: item.category.name,
        unit: item.unit,
        quantity,
        available: recommendation.available,
        reason: recommendation.reason,
      }]
    })
  }, [enabled, recommendations, equipment, selectedItems, ignored])

  return {
    suggestions,
    loading: Boolean(enabled && fetchedFor !== requestKey),
    error: errorFor === requestKey,
    ignore: (equipmentId) => setIgnored((current) => ({
      key: requestKey,
      ids: new Set(current.key === requestKey ? current.ids : []).add(equipmentId),
    })),
  }
}
