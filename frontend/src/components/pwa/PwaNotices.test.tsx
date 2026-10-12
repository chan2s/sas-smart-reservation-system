import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const state = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}))

vi.mock('@/hooks/usePwa', () => ({
  usePwa: () => state.current,
}))

import { PwaNotices } from './PwaNotices'

/**
 * The install invitation is the one PWA surface most users ever see, so its
 * copy, controls, availability rules, and politeness delay are pinned here.
 */

const DESCRIPTION = 'Install SAS RESERVE for quick access from your home screen or desktop.'

function renderNotices(overrides: Record<string, unknown> = {}) {
  state.current = {
    offlineReady: false,
    updateAvailable: false,
    acceptUpdate: vi.fn(),
    dismissUpdate: vi.fn(),
    canInstall: false,
    installDismissed: false,
    isInstalled: false,
    canShowIosInstructions: false,
    promptInstall: vi.fn().mockResolvedValue(undefined),
    dismissInstall: vi.fn(),
    dismissIosInstructions: vi.fn(),
    ...overrides,
  }
  return render(
    <MemoryRouter>
      <PwaNotices />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  cleanup()
})

describe('PwaNotices install invitation (native prompt)', () => {
  it('waits politely before appearing', () => {
    renderNotices({ canInstall: true })
    expect(screen.queryByText('Install SAS RESERVE')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.getByText('Install SAS RESERVE')).toBeInTheDocument()
  })

  it('shows the app icon, the required description, and both actions', () => {
    renderNotices({ canInstall: true })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.getByText(DESCRIPTION)).toBeInTheDocument()
    expect(screen.getByAltText('SAS RESERVE app icon')).toHaveAttribute('src', '/pwa-192x192.png')
    expect(screen.getByRole('button', { name: 'Install App' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Not now' })).toBeInTheDocument()
  })

  it('triggers the native installation dialog from Install App', () => {
    const promptInstall = vi.fn().mockResolvedValue(undefined)
    renderNotices({ canInstall: true, promptInstall })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    screen.getByRole('button', { name: 'Install App' }).click()
    expect(promptInstall).toHaveBeenCalledTimes(1)
  })

  it('dismisses from Not now and from the close button', () => {
    const dismissInstall = vi.fn()
    renderNotices({ canInstall: true, dismissInstall })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    screen.getByRole('button', { name: 'Not now' }).click()
    expect(dismissInstall).toHaveBeenCalledTimes(1)
    screen.getByRole('button', { name: 'Dismiss installation notice' }).click()
    expect(dismissInstall).toHaveBeenCalledTimes(2)
  })

  it('renders nothing while the browser offers no prompt', () => {
    renderNotices({ canInstall: false })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.queryByText('Install SAS RESERVE')).toBeNull()
  })

  it('renders nothing for users who already installed the app', () => {
    renderNotices({ canInstall: true, isInstalled: true })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.queryByText('Install SAS RESERVE')).toBeNull()
  })
})

describe('PwaNotices iOS manual instructions', () => {
  it('shows concise Add to Home Screen steps on iOS', () => {
    renderNotices({ canShowIosInstructions: true })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.getByText(DESCRIPTION)).toBeInTheDocument()
    const steps = screen.getByRole('list')
    expect(steps.textContent).toMatch(/Share/)
    expect(steps.textContent).toMatch(/Add to Home Screen/i)
    expect(screen.queryByRole('button', { name: 'Install App' })).toBeNull()
  })

  it('dismisses the instructions', () => {
    const dismissIosInstructions = vi.fn()
    renderNotices({ canShowIosInstructions: true, dismissIosInstructions })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    screen.getByRole('button', { name: 'Got it' }).click()
    expect(dismissIosInstructions).toHaveBeenCalledTimes(1)
  })

  it('does not show native-prompt actions for iOS users', () => {
    renderNotices({ canShowIosInstructions: true })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.queryByRole('button', { name: 'Install App' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Not now' })).toBeNull()
  })
})

describe('PwaNotices update notice', () => {
  it('appears immediately, without the politeness delay', () => {
    renderNotices({ updateAvailable: true })
    expect(screen.getByText('A new version is available.')).toBeInTheDocument()
  })

  it('stays hidden while no service worker is waiting', () => {
    renderNotices({ updateAvailable: false })
    expect(screen.queryByText('A new version is available.')).toBeNull()
  })
})
