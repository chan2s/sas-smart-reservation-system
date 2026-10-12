import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  facilities: vi.fn(),
  equipment: vi.fn(),
  reservations: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    endpoints: {
      ...actual.endpoints,
      facilities: (...args: unknown[]) => mocks.facilities(...args),
      equipment: (...args: unknown[]) => mocks.equipment(...args),
      reservations: (...args: unknown[]) => mocks.reservations(...args),
    },
  }
})

import { ApiError } from '@/lib/api'
import type { Equipment, Facility, ReservationSummary } from '@/lib/types'
import { clearBackup, readFacilities, readReservations } from './db'
import { syncOfflineBackup } from './sync'

const facilityRow = { id: 1, name: 'AVR', facility_type_label: 'AVR', description: '', capacity: 10, location: 'A', image: null, status_label: 'Available', is_active: true, availability: {} } as unknown as Facility
const equipmentRow = { id: 2, name: 'Chair', category: { id: 1, name: 'Furniture' }, total_quantity: 30, unit: 'pc', price: '0.00', condition_label: 'Good', status_label: 'Available', storage_location: 'B', image: null, is_active: true, availability: {} } as unknown as Equipment

const reservationRow = (id: number, requesterId: number | null) =>
  ({
    id,
    reservation_id: `RES-${id}`,
    event_name: `Event ${id}`,
    requester_id: requesterId,
    facility: 'AVR',
    facility_id: 1,
    date: '2026-11-01',
    start_time: '09:00:00',
    end_time: '10:00:00',
    status_label: 'Pending',
    created_at: `2026-10-0${Math.min(id, 9)}T00:00:00Z`,
  }) as unknown as ReservationSummary

function resolveHappyPath() {
  mocks.facilities.mockResolvedValue([facilityRow])
  mocks.equipment.mockResolvedValue([equipmentRow])
  mocks.reservations.mockResolvedValue({
    count: 2,
    num_pages: 1,
    results: [reservationRow(1, 7), reservationRow(2, 8)],
  })
}

function setBrowserOnline(value: boolean) {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(value)
}

beforeEach(() => {
  mocks.facilities.mockReset()
  mocks.equipment.mockReset()
  mocks.reservations.mockReset()
  setBrowserOnline(true)
})

afterEach(async () => {
  vi.restoreAllMocks()
  await clearBackup()
})

describe('syncOfflineBackup', () => {
  it('stores a minimal backup and records the sync time', async () => {
    resolveHappyPath()
    const result = await syncOfflineBackup({ id: 7, username: 'jane' })

    expect(result.ok).toBe(true)
    expect(result.syncedAt).toBeTruthy()
    expect(await readFacilities(7)).toHaveLength(1)
    // Only the signed-in user's own reservation is cached, even though the list
    // endpoint returned someone else's too.
    expect((await readReservations(7)).map((row) => row.id)).toEqual([1])
  })

  it('does not touch storage or the network while the browser is offline', async () => {
    setBrowserOnline(false)
    const result = await syncOfflineBackup({ id: 7, username: 'jane' })

    expect(result).toEqual({ ok: false, syncedAt: null, reason: 'offline' })
    // Nothing was queued for later replay: the endpoints were never called.
    expect(mocks.facilities).not.toHaveBeenCalled()
    expect(mocks.equipment).not.toHaveBeenCalled()
    expect(mocks.reservations).not.toHaveBeenCalled()
    expect(await readFacilities(7)).toEqual([])
  })

  it('reports an expired session without writing a partial backup', async () => {
    mocks.facilities.mockRejectedValue(new ApiError(401, 'Token is invalid or expired'))
    mocks.equipment.mockResolvedValue([])
    mocks.reservations.mockResolvedValue({ count: 0, num_pages: 1, results: [] })

    const result = await syncOfflineBackup({ id: 7, username: 'jane' })
    expect(result.ok).toBe(false)
    expect(result.reason).toBe('auth')
    expect(result.syncedAt).toBeNull()
    expect(await readFacilities(7)).toEqual([])
  })

  it('classifies a server error as a server problem', async () => {
    mocks.facilities.mockRejectedValue(new ApiError(500, 'Internal server error'))
    mocks.equipment.mockResolvedValue([])
    mocks.reservations.mockResolvedValue({ count: 0, num_pages: 1, results: [] })

    const result = await syncOfflineBackup({ id: 7, username: 'jane' })
    expect(result.reason).toBe('server')
  })

  it('classifies a network failure while nominally online as a server problem', async () => {
    mocks.facilities.mockRejectedValue(new TypeError('Failed to fetch'))
    mocks.equipment.mockResolvedValue([])
    mocks.reservations.mockResolvedValue({ count: 0, num_pages: 1, results: [] })

    const result = await syncOfflineBackup({ id: 7, username: 'jane' })
    expect(result.reason).toBe('server')
    expect(result.error).toContain('Failed to fetch')
  })
})
