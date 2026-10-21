import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  HEALTH_URL,
  isReachableHealthStatus,
  probeBackend,
} from './health'

function respondWith(status: number) {
  return vi.fn().mockResolvedValue(new Response('{}', { status }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('isReachableHealthStatus', () => {
  it('treats application answers as reachable, including server errors', () => {
    expect(isReachableHealthStatus(200)).toBe(true)
    expect(isReachableHealthStatus(404)).toBe(true)
    // Django answered; the failure is application-level, not connectivity.
    expect(isReachableHealthStatus(500)).toBe(true)
  })

  it('treats gateway answers as unreachable', () => {
    expect(isReachableHealthStatus(502)).toBe(false)
    expect(isReachableHealthStatus(503)).toBe(false)
    expect(isReachableHealthStatus(504)).toBe(false)
  })
})

describe('probeBackend', () => {
  it('requests the proxied health route without caching', async () => {
    const fetchMock = respondWith(200)
    vi.stubGlobal('fetch', fetchMock)

    await expect(probeBackend()).resolves.toBe(true)

    expect(fetchMock).toHaveBeenCalledWith(
      HEALTH_URL,
      expect.objectContaining({ method: 'GET', cache: 'no-store' }),
    )
    expect(HEALTH_URL).toBe('/api/health/')
  })

  it('reports unreachable when the dev proxy answers 502', async () => {
    vi.stubGlobal('fetch', respondWith(502))
    await expect(probeBackend()).resolves.toBe(false)
  })

  it('reports unreachable when the connection fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(probeBackend()).resolves.toBe(false)
  })

  it('does not probe with an already-aborted signal', async () => {
    const fetchMock = respondWith(200)
    vi.stubGlobal('fetch', fetchMock)

    const controller = new AbortController()
    controller.abort()

    await expect(probeBackend(controller.signal)).resolves.toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('aborts the request when the provider unmounts', async () => {
    const fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const controller = new AbortController()
    const probe = probeBackend(controller.signal)
    controller.abort()

    await expect(probe).resolves.toBe(false)
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
})
