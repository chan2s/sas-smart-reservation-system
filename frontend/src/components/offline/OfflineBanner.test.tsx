import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const state = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}))

vi.mock('@/hooks/useOffline', () => ({
  useOffline: () => state.current,
}))

import { OfflineBanner } from './OfflineBanner'

function renderBanner(overrides: Record<string, unknown> = {}) {
  state.current = {
    online: false,
    browserOnline: false,
    checking: false,
    lastSyncedAt: '2026-10-01T09:30:00.000Z',
    hasBackup: true,
    backupError: null,
    retryConnection: vi.fn(),
    ...overrides,
  }
  return render(
    <MemoryRouter>
      <OfflineBanner />
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe('OfflineBanner', () => {
  it('renders nothing while the app is online', () => {
    const { container } = renderBanner({ online: true, browserOnline: true })
    expect(container.textContent).toBe('')
  })

  it('announces the offline state politely', () => {
    renderBanner()
    const banner = screen.getByRole('status')
    expect(banner.textContent).toContain("You're offline")
    expect(banner.getAttribute('aria-live')).toBe('polite')
  })

  it('says the backend is unreachable even when the browser reports online', () => {
    renderBanner({ browserOnline: true })
    expect(screen.getByRole('status').textContent).toContain("Can't reach SAS RESERVE")
  })

  it('labels the data as a local backup with its last update time', () => {
    renderBanner()
    const text = screen.getByRole('status').textContent ?? ''
    expect(text).toMatch(/local backup/i)
    expect(text).toMatch(/updated/i)
  })

  it('shows an empty state instead of a timestamp when nothing was saved', () => {
    renderBanner({ hasBackup: false, lastSyncedAt: null })
    expect(screen.getByRole('status').textContent).toMatch(/no saved information/i)
  })

  it('surfaces a failed backup sync', () => {
    renderBanner({ backupError: 'IndexedDB is unavailable.' })
    expect(screen.getByRole('status').textContent).toContain('IndexedDB is unavailable.')
  })

  it('offers a link to the saved information and a retry control', () => {
    const retryConnection = vi.fn()
    renderBanner({ retryConnection })
    expect(screen.getByRole('link', { name: /view saved info/i }).getAttribute('href')).toBe(
      '/offline',
    )
    screen.getByRole('button', { name: /retry/i }).click()
    expect(retryConnection).toHaveBeenCalledTimes(1)
  })

  it('disables the retry control while a probe is running', () => {
    renderBanner({ checking: true })
    expect(screen.getByRole('button', { name: /checking/i })).toHaveProperty('disabled', true)
  })
})
