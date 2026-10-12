import { afterEach, describe, expect, it, vi } from 'vitest'
import { OfflineError, setApiReachable } from './offline/connectivity'
import { api, apiErrorMessage, endpoints } from './api'

/**
 * Reservation integrity. When the backend cannot be reached, every
 * server-dependent action must fail loudly and locally — never be sent, never
 * queued for a silent replay after reconnection, never reported as success.
 */

function stubFetch(payload: unknown = []) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function setBrowserOnline(value: boolean) {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(value)
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  setApiReachable(null)
})

describe('offline mutation guard', () => {
  it('blocks a reservation submission without touching the network', async () => {
    setBrowserOnline(true)
    setApiReachable(false)
    const fetchMock = stubFetch()

    await expect(endpoints.createReservation({} as never)).rejects.toBeInstanceOf(OfflineError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('blocks availability checks, approvals and check-in offline', async () => {
    setBrowserOnline(true)
    setApiReachable(false)
    const fetchMock = stubFetch()

    await expect(endpoints.checkAvailability({} as never)).rejects.toBeInstanceOf(OfflineError)
    await expect(endpoints.reservationAction(1, 'approve')).rejects.toBeInstanceOf(OfflineError)
    await expect(endpoints.reservationAction(1, 'check_in')).rejects.toBeInstanceOf(OfflineError)
    await expect(endpoints.reservationAction(1, 'cancel')).rejects.toBeInstanceOf(OfflineError)
    await expect(api.delete('/api/reservations/1/')).rejects.toBeInstanceOf(OfflineError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('blocks writes when the browser is offline even before any probe', async () => {
    setBrowserOnline(false)
    setApiReachable(null)
    const fetchMock = stubFetch()

    await expect(api.post('/api/reservations/', {})).rejects.toBeInstanceOf(OfflineError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('still allows reads, so the UI can fall back to the local backup', async () => {
    setBrowserOnline(true)
    setApiReachable(false)
    const fetchMock = stubFetch([])

    await expect(endpoints.facilities()).resolves.toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('allows the write again once the backend is reachable', async () => {
    setBrowserOnline(true)
    setApiReachable(true)
    const fetchMock = stubFetch({ id: 1 })

    await expect(api.post('/api/reservations/', {})).resolves.toEqual({ id: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('surfaces the offline reason instead of a generic fallback message', () => {
    const message = apiErrorMessage(new OfflineError(), 'Something went wrong.')
    expect(message).not.toBe('Something went wrong.')
    expect(message).toMatch(/offline/i)
  })
})
