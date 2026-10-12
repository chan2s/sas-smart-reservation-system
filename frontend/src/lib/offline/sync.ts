/**
 * Offline backup synchronization.
 *
 * Runs only while the user is authenticated and the API is reachable, reads
 * through the existing API services, and persists a minimal projection to
 * IndexedDB. The timestamp is written only after a fully successful sync.
 */

import { ApiError, endpoints } from '@/lib/api'
import type { User } from '@/lib/types'
import { isStorageSupported, writeBackup } from './db'
import {
  projectEquipment,
  projectFacility,
  projectReservation,
  selectOwnReservations,
} from './projections'

export type SyncReason = 'offline' | 'auth' | 'server' | 'storage'

export interface SyncResult {
  ok: boolean
  syncedAt: string | null
  reason?: SyncReason
  error?: string
}

type SyncUser = Pick<User, 'id' | 'username'>

let inFlight: Promise<SyncResult> | null = null

/** Coalesce concurrent triggers into a single round-trip. */
export function syncOfflineBackup(user: SyncUser): Promise<SyncResult> {
  if (inFlight) return inFlight
  inFlight = runSync(user).finally(() => {
    inFlight = null
  })
  return inFlight
}

async function runSync(user: SyncUser): Promise<SyncResult> {
  if (!isStorageSupported()) {
    return { ok: false, syncedAt: null, reason: 'storage', error: 'IndexedDB is unavailable.' }
  }

  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return { ok: false, syncedAt: null, reason: 'offline' }
  }

  try {
    const [facilities, equipment, reservationsPage] = await Promise.all([
      endpoints.facilities(),
      endpoints.equipment(),
      endpoints.reservations({ page: 1 }),
    ])

    const reservations = selectOwnReservations(reservationsPage.results, user.id)
    const syncedAt = new Date().toISOString()

    await writeBackup({
      ownerId: user.id,
      username: user.username,
      syncedAt,
      facilities: facilities.map(projectFacility),
      equipment: equipment.map(projectEquipment),
      reservations: reservations.map(projectReservation),
    })

    return { ok: true, syncedAt }
  } catch (error) {
    return classifyError(error)
  }
}

function classifyError(error: unknown): SyncResult {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return { ok: false, syncedAt: null, reason: 'auth', error: error.message }
    }
    return { ok: false, syncedAt: null, reason: 'server', error: error.message }
  }

  if (error instanceof Error) {
    const storageErrors = ['QuotaExceededError', 'SecurityError', 'InvalidStateError', 'UnknownError']
    if (storageErrors.includes(error.name)) {
      return { ok: false, syncedAt: null, reason: 'storage', error: error.message }
    }
    // A fetch network failure surfaces as a TypeError; treat it as unreachable
    // when the browser also reports offline, otherwise as a server problem.
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false
    return { ok: false, syncedAt: null, reason: offline ? 'offline' : 'server', error: error.message }
  }

  return { ok: false, syncedAt: null, reason: 'server', error: String(error) }
}
