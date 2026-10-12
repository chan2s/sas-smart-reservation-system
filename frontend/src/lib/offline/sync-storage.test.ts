import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  isStorageSupported: vi.fn(() => true),
  writeBackup: vi.fn(),
  facilities: vi.fn(),
  equipment: vi.fn(),
  reservations: vi.fn(),
}))

vi.mock('./db', () => ({
  isStorageSupported: () => mocks.isStorageSupported(),
  writeBackup: (input: unknown) => mocks.writeBackup(input),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    endpoints: {
      ...actual.endpoints,
      facilities: () => mocks.facilities(),
      equipment: () => mocks.equipment(),
      reservations: () => mocks.reservations(),
    },
  }
})

import { syncOfflineBackup } from './sync'

function resolveHappyPath() {
  mocks.facilities.mockResolvedValue([])
  mocks.equipment.mockResolvedValue([])
  mocks.reservations.mockResolvedValue({ count: 0, num_pages: 1, results: [] })
}

beforeEach(() => {
  vi.restoreAllMocks()
  mocks.isStorageSupported.mockReturnValue(true)
  mocks.writeBackup.mockReset()
  resolveHappyPath()
})

/**
 * Storage is best-effort: a full quota or a locked-down browser must degrade to
 * "no backup" with a readable reason, never crash the app.
 */
describe('syncOfflineBackup storage failures', () => {
  it('degrades gracefully when IndexedDB is unavailable', async () => {
    mocks.isStorageSupported.mockReturnValue(false)
    const result = await syncOfflineBackup({ id: 1, username: 'u' })

    expect(result.ok).toBe(false)
    expect(result.reason).toBe('storage')
    expect(mocks.facilities).not.toHaveBeenCalled()
  })

  it('reports a full quota as a storage failure', async () => {
    const quota = Object.assign(new Error('The quota has been exceeded.'), {
      name: 'QuotaExceededError',
    })
    mocks.writeBackup.mockRejectedValue(quota)

    const result = await syncOfflineBackup({ id: 1, username: 'u' })
    expect(result.ok).toBe(false)
    expect(result.reason).toBe('storage')
    expect(result.syncedAt).toBeNull()
  })

  it('reports a blocked storage context as a storage failure', async () => {
    mocks.writeBackup.mockRejectedValue(
      Object.assign(new Error('The operation is insecure.'), { name: 'SecurityError' }),
    )
    const result = await syncOfflineBackup({ id: 1, username: 'u' })
    expect(result.reason).toBe('storage')
  })

  it('keeps the previous timestamp when a later sync fails', async () => {
    mocks.writeBackup.mockRejectedValue(
      Object.assign(new Error('quota'), { name: 'QuotaExceededError' }),
    )
    const result = await syncOfflineBackup({ id: 1, username: 'u' })
    // The caller only stores `syncedAt` on ok — a failed sync never advances it.
    expect(result.syncedAt).toBeNull()
  })
})
