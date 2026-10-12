/**
 * IndexedDB backing store for the safe offline backup.
 *
 * Scope and safety rules (see src/lib/offline/sync.ts for what is written):
 *  - Every read is scoped to the currently authenticated user id; a mismatch
 *    returns nothing, so one account can never read another's cached data.
 *  - Auth material (tokens, OTP secrets, passwords) is never stored here.
 *  - All operations are wrapped by callers so quota/permission failures degrade
 *    to "no backup" instead of crashing the app.
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb'

const DB_NAME = 'sas-reserve-offline'
const DB_VERSION = 1

/** Minimal, non-sensitive projections (mirrors src/lib/offline/projections.ts). */
export interface OfflineFacility {
  id: number
  name: string
  facility_type_label: string
  description: string
  capacity: number
  location: string
  image: string | null
  status_label: string
  is_active: boolean
}

export interface OfflineEquipment {
  id: number
  name: string
  category_name: string
  total_quantity: number
  unit: string
  condition_label: string
  status_label: string
  storage_location: string
  image: string | null
  is_active: boolean
}

export interface OfflineReservation {
  id: number
  reservation_id: string
  event_name: string
  facility: string
  facility_id: number
  date: string
  start_time: string
  end_time: string
  status_label: string
}

interface MetaRecord {
  key: 'owner' | 'sync'
  ownerId?: number
  username?: string
  syncedAt?: string
}

export interface BackupMeta {
  ownerId: number | null
  username: string
  syncedAt: string | null
}

interface OfflineSchema extends DBSchema {
  facilities: { key: number; value: OfflineFacility }
  equipment: { key: number; value: OfflineEquipment }
  reservations: { key: number; value: OfflineReservation }
  meta: { key: MetaRecord['key']; value: MetaRecord }
}

let dbPromise: Promise<IDBPDatabase<OfflineSchema>> | null = null

function getDb(): Promise<IDBPDatabase<OfflineSchema>> {
  if (!dbPromise) {
    dbPromise = openDB<OfflineSchema>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('facilities')) {
          db.createObjectStore('facilities', { keyPath: 'id' })
        }
        if (!db.objectStoreNames.contains('equipment')) {
          db.createObjectStore('equipment', { keyPath: 'id' })
        }
        if (!db.objectStoreNames.contains('reservations')) {
          db.createObjectStore('reservations', { keyPath: 'id' })
        }
        if (!db.objectStoreNames.contains('meta')) {
          db.createObjectStore('meta', { keyPath: 'key' })
        }
      },
    })
  }
  return dbPromise
}

/** True when IndexedDB exists (it does not in some private/embedded contexts). */
export function isStorageSupported(): boolean {
  return typeof indexedDB !== 'undefined'
}

/**
 * Persist a complete snapshot atomically, with its owner and timestamp. The
 * three data stores are replaced (not appended) so a backup always reflects the
 * last successful sync.
 */
export async function writeBackup(input: {
  ownerId: number
  username: string
  syncedAt: string
  facilities: OfflineFacility[]
  equipment: OfflineEquipment[]
  reservations: OfflineReservation[]
}): Promise<void> {
  const db = await getDb()
  const tx = db.transaction(['facilities', 'equipment', 'reservations', 'meta'], 'readwrite')
  await Promise.all([
    tx.objectStore('facilities').clear(),
    tx.objectStore('equipment').clear(),
    tx.objectStore('reservations').clear(),
  ])
  for (const facility of input.facilities) {
    void tx.objectStore('facilities').put(facility)
  }
  for (const item of input.equipment) {
    void tx.objectStore('equipment').put(item)
  }
  for (const reservation of input.reservations) {
    void tx.objectStore('reservations').put(reservation)
  }
  void tx.objectStore('meta').put({
    key: 'owner',
    ownerId: input.ownerId,
    username: input.username,
  })
  void tx.objectStore('meta').put({ key: 'sync', syncedAt: input.syncedAt })
  await tx.done
}

async function readMeta(): Promise<BackupMeta> {
  const db = await getDb()
  const [owner, sync] = await Promise.all([
    db.get('meta', 'owner'),
    db.get('meta', 'sync'),
  ])
  return {
    ownerId: owner?.ownerId ?? null,
    username: owner?.username ?? '',
    syncedAt: sync?.syncedAt ?? null,
  }
}

/** Owner/timestamp of the current backup, or nulls when none exists. */
export async function getBackupMeta(): Promise<BackupMeta> {
  return readMeta()
}

/**
 * Read a store, but only when it belongs to `ownerId`. A different (or absent)
 * owner yields an empty list — cached data is never shown across accounts.
 */
async function readOwned<T>(
  store: 'facilities' | 'equipment' | 'reservations',
  ownerId: number,
): Promise<T[]> {
  const meta = await readMeta()
  if (meta.ownerId !== ownerId) return []
  const db = await getDb()
  const rows = await db.getAll(store)
  return rows as unknown as T[]
}

export function readFacilities(ownerId: number): Promise<OfflineFacility[]> {
  return readOwned<OfflineFacility>('facilities', ownerId)
}

export function readEquipment(ownerId: number): Promise<OfflineEquipment[]> {
  return readOwned<OfflineEquipment>('equipment', ownerId)
}

export function readReservations(ownerId: number): Promise<OfflineReservation[]> {
  return readOwned<OfflineReservation>('reservations', ownerId)
}

/** Remove every cached record. Used on logout / account change. */
export async function clearBackup(): Promise<void> {
  const db = await getDb()
  const tx = db.transaction(['facilities', 'equipment', 'reservations', 'meta'], 'readwrite')
  await Promise.all([
    tx.objectStore('facilities').clear(),
    tx.objectStore('equipment').clear(),
    tx.objectStore('reservations').clear(),
    tx.objectStore('meta').clear(),
  ])
  await tx.done
}
