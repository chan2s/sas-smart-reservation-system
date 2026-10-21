import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: null }),
}))

vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

import { OfflineProvider, useOffline } from './useOffline'
import { setApiReachable } from '@/lib/offline/connectivity'

function Status() {
  const { online, checking, apiReachable } = useOffline()
  return (
    <>
      <p data-testid="online">{String(online)}</p>
      <p data-testid="checking">{String(checking)}</p>
      <p data-testid="reachable">{String(apiReachable)}</p>
    </>
  )
}

function renderProvider() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <OfflineProvider>{children}</OfflineProvider>
    </QueryClientProvider>
  )
  return render(<Status />, { wrapper })
}

function deferredResponse() {
  let resolve: (response: Response) => void = () => {}
  const promise = new Promise<Response>((r) => {
    resolve = r
  })
  return { promise, resolve: (status: number) => resolve(new Response('{}', { status })) }
}

beforeEach(() => {
  setApiReachable(null)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('OfflineProvider', () => {
  it('stays online when the health endpoint answers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"status":"ok"}', { status: 200 })))

    renderProvider()

    await waitFor(() => expect(screen.getByTestId('reachable').textContent).toBe('true'))
    expect(screen.getByTestId('online').textContent).toBe('true')
    expect(screen.getByTestId('checking').textContent).toBe('false')
  })

  it('goes offline on a 502 from the dev proxy and recovers on retry', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 502 }))
    vi.stubGlobal('fetch', fetchMock)

    renderProvider()

    await waitFor(() => expect(screen.getByTestId('online').textContent).toBe('false'))
    expect(screen.getByTestId('reachable').textContent).toBe('false')

    // Backend is reachable again; an explicit retry must clear the banner
    // without waiting for the 20s poll.
    fetchMock.mockResolvedValue(new Response('{"status":"ok"}', { status: 200 }))
    await act(async () => {
      await window.dispatchEvent(new Event('online'))
    })

    await waitFor(() => expect(screen.getByTestId('online').textContent).toBe('true'))
  })

  it('treats an application 500 as reachable instead of offline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 500 })))

    renderProvider()

    await waitFor(() => expect(screen.getByTestId('reachable').textContent).toBe('true'))
    expect(screen.getByTestId('online').textContent).toBe('true')
  })

  it('shares one probe between simultaneous triggers', async () => {
    const pending = deferredResponse()
    const fetchMock = vi.fn().mockReturnValue(pending.promise)
    vi.stubGlobal('fetch', fetchMock)

    renderProvider()
    // Mount probe is still in flight; the browser 'online' event must join it.
    act(() => {
      window.dispatchEvent(new Event('online'))
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      pending.resolve(200)
      await Promise.resolve()
    })

    await waitFor(() => expect(screen.getByTestId('online').textContent).toBe('true'))
  })
})
