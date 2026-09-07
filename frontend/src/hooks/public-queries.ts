import { useMutation, useQuery } from '@tanstack/react-query'
import { endpoints, type GuestReservationPayload } from '@/lib/api'
import type {
  AvailabilityCheck,
  Equipment,
  GuestReservationResult,
  PublicFacility,
  Recommendation,
  TrackResult,
} from '@/lib/types'

/**
 * Query hooks for the public (unauthenticated) reservation flow.
 * Kept separate from queries.ts so the public pages never accidentally
 * touch the authenticated token store.
 */

export function usePublicFacilities() {
  return useQuery({
    queryKey: ['public-facilities'],
    queryFn: () => endpoints.publicFacilities(),
    staleTime: 60_000,
  })
}

export function usePublicEquipment(params?: { date?: string; start?: string; end?: string }) {
  const key = params ?? {}
  return useQuery({
    queryKey: ['public-equipment', key],
    queryFn: () => endpoints.publicEquipment(params),
    staleTime: 30_000,
  })
}

export function usePublicAvailabilityCheck() {
  return useMutation({
    mutationFn: (payload: {
      facility_id: number
      date: string
      start_time: string
      end_time: string
      items: { equipment_id: number; quantity: number }[]
    }) => endpoints.publicCheckAvailability(payload),
  })
}

export function usePublicRecommendResources() {
  return useMutation({
    mutationFn: (payload: {
      event_type: string
      expected_participants: number
      facility_id?: number
      purpose?: string
      special_requirements?: string
      date?: string
      start_time?: string
      end_time?: string
    }) => endpoints.publicRecommendResources(payload),
  })
}

export function useCreateGuestReservation() {
  return useMutation({
    mutationFn: (payload: GuestReservationPayload): Promise<GuestReservationResult> =>
      endpoints.createGuestReservation(payload),
  })
}

export function useTrackReservation() {
  return useMutation({
    mutationFn: (payload: { reservation_code: string; email: string }): Promise<TrackResult> =>
      endpoints.trackReservation(payload),
  })
}

// Re-export types for page-level imports.
export type { AvailabilityCheck, Equipment, PublicFacility, Recommendation, TrackResult }
