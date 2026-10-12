import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { useOffline } from '@/hooks/useOffline'
import {
  readEquipment,
  readFacilities,
  readReservations,
  type OfflineEquipment,
  type OfflineFacility,
  type OfflineReservation,
} from '@/lib/offline'

/**
 * Read-only views over the local backup.
 *
 * The query key includes the user id and the last successful sync timestamp, so
 * switching accounts or completing a sync automatically re-reads the store. A
 * missing/foreign owner yields an empty list (never another user's data), and
 * storage failures surface as an error the UI renders as a plain empty state.
 */
function offlineKey(kind: string, userId: number | null, syncedAt: string | null) {
  return ['offline', kind, userId, syncedAt] as const
}

export function useOfflineFacilities() {
  const { user } = useAuth()
  const { lastSyncedAt } = useOffline()
  return useQuery<OfflineFacility[]>({
    queryKey: offlineKey('facilities', user?.id ?? null, lastSyncedAt),
    queryFn: () => readFacilities(user!.id),
    enabled: Boolean(user),
    staleTime: Infinity,
    retry: false,
  })
}

export function useOfflineEquipment() {
  const { user } = useAuth()
  const { lastSyncedAt } = useOffline()
  return useQuery<OfflineEquipment[]>({
    queryKey: offlineKey('equipment', user?.id ?? null, lastSyncedAt),
    queryFn: () => readEquipment(user!.id),
    enabled: Boolean(user),
    staleTime: Infinity,
    retry: false,
  })
}

export function useOfflineReservations() {
  const { user } = useAuth()
  const { lastSyncedAt } = useOffline()
  return useQuery<OfflineReservation[]>({
    queryKey: offlineKey('reservations', user?.id ?? null, lastSyncedAt),
    queryFn: () => readReservations(user!.id),
    enabled: Boolean(user),
    staleTime: Infinity,
    retry: false,
  })
}
