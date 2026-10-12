import 'fake-indexeddb/auto'
import { afterEach, describe, expect, it } from 'vitest'
import {
  clearBackup,
  getBackupMeta,
  readEquipment,
  readFacilities,
  readReservations,
  writeBackup,
} from './db'

/**
 * The backup must be per-user: a shared device where one account signs out and
 * another signs in is exactly the case this store has to survive.
 */

const facility = (id: number) => ({
  id,
  name: `Facility ${id}`,
  facility_type_label: 'AVR',
  description: '',
  capacity: 50,
  location: 'Main',
  image: null,
  status_label: 'Available',
  is_active: true,
})

const equipment = (id: number) => ({
  id,
  name: `Item ${id}`,
  category_name: 'AV',
  total_quantity: 2,
  unit: 'unit',
  condition_label: 'Good',
  status_label: 'Available',
  storage_location: 'Office',
  image: null,
  is_active: true,
})

const reservation = (id: number) => ({
  id,
  reservation_id: `RES-${id}`,
  event_name: `Event ${id}`,
  facility: 'AVR',
  facility_id: 1,
  date: '2026-11-01',
  start_time: '09:00:00',
  end_time: '10:00:00',
  status_label: 'Pending',
})

async function seed(ownerId: number, syncedAt = '2026-10-01T00:00:00.000Z') {
  await writeBackup({
    ownerId,
    username: `user-${ownerId}`,
    syncedAt,
    facilities: [facility(1)],
    equipment: [equipment(1)],
    reservations: [reservation(1)],
  })
}

afterEach(async () => {
  await clearBackup()
})

describe('offline backup store', () => {
  it('writes and reads back a snapshot for its owner', async () => {
    await seed(7)
    expect(await readFacilities(7)).toHaveLength(1)
    expect(await readEquipment(7)).toHaveLength(1)
    expect(await readReservations(7)).toHaveLength(1)
  })

  it('reports the owner and the last successful sync time', async () => {
    await seed(7, '2026-10-05T12:30:00.000Z')
    const meta = await getBackupMeta()
    expect(meta.ownerId).toBe(7)
    expect(meta.username).toBe('user-7')
    expect(meta.syncedAt).toBe('2026-10-05T12:30:00.000Z')
  })

  it('returns nothing to a different account (no cross-account leak)', async () => {
    await seed(7)
    expect(await readFacilities(8)).toEqual([])
    expect(await readEquipment(8)).toEqual([])
    expect(await readReservations(8)).toEqual([])
  })

  it('replaces the previous snapshot instead of appending to it', async () => {
    await seed(7)
    await writeBackup({
      ownerId: 7,
      username: 'user-7',
      syncedAt: '2026-10-02T00:00:00.000Z',
      facilities: [facility(1), facility(2)],
      equipment: [],
      reservations: [],
    })
    expect((await readFacilities(7)).map((row) => row.id).sort()).toEqual([1, 2])
    expect(await readEquipment(7)).toEqual([])
  })

  it('hands the backup over when the device changes account', async () => {
    await seed(7)
    await seed(9)
    // The new owner sees its own snapshot; the previous owner sees nothing.
    expect(await readFacilities(9)).toHaveLength(1)
    expect(await readFacilities(7)).toEqual([])
    expect((await getBackupMeta()).ownerId).toBe(9)
  })

  it('clears every store on logout', async () => {
    await seed(7)
    await clearBackup()
    expect(await readFacilities(7)).toEqual([])
    expect(await readEquipment(7)).toEqual([])
    expect(await readReservations(7)).toEqual([])
    expect(await getBackupMeta()).toEqual({ ownerId: null, username: '', syncedAt: null })
  })

  it('treats an empty device as "no backup" rather than an error', async () => {
    expect(await getBackupMeta()).toEqual({ ownerId: null, username: '', syncedAt: null })
    expect(await readFacilities(7)).toEqual([])
  })
})
