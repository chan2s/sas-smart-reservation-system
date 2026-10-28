import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

const state = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}))

vi.mock('@/hooks/usePwa', () => ({
  usePwa: () => state.current,
}))

import { INSTALL_DESCRIPTION, InstallAppSection } from './InstallAppSection'

/**
 * The Settings install section is the explicit counterpart to the floating
 * invitation: it must show the real prompt whenever one is held, explain the
 * manual routes when the browser offers none, and never render a dead button.
 */

function renderSection(overrides: Record<string, unknown> = {}) {
  state.current = {
    promptAvailable: false,
    promptDismissed: false,
    isInstalled: false,
    canShowIosInstructions: false,
    promptInstall: vi.fn().mockResolvedValue('accepted'),
    ...overrides,
  }
  return render(<InstallAppSection />)
}

const installButton = () => screen.queryByRole('button', { name: 'Install App' })

afterEach(() => {
  cleanup()
})

describe('InstallAppSection (prompt available)', () => {
  it('shows the section title, app icon, description, and install button', () => {
    renderSection({ promptAvailable: true })
    expect(screen.getByRole('heading', { name: 'Install SAS RESERVE App' })).toBeInTheDocument()
    expect(screen.getByText(INSTALL_DESCRIPTION)).toBeInTheDocument()
    expect(document.querySelector('img[src="/pwa-192x192.png"]')).not.toBeNull()
    expect(installButton()).toBeInTheDocument()
  })

  it('invokes the native prompt when Install App is clicked', async () => {
    const promptInstall = vi.fn().mockResolvedValue('accepted')
    renderSection({ promptAvailable: true, promptInstall })
    await act(async () => {
      fireEvent.click(installButton()!)
    })
    expect(promptInstall).toHaveBeenCalledTimes(1)
  })

  it('stays available after an earlier dismissal (no cooldown here)', () => {
    // `promptAvailable` ignores the seven-day cooldown that hides the floating
    // invitation, so an explicit visit to Settings still offers installation.
    renderSection({ promptAvailable: true, promptDismissed: false })
    expect(installButton()).toBeInTheDocument()
  })

  it('explains how to retry after the prompt was cancelled', async () => {
    const promptInstall = vi.fn().mockResolvedValue('dismissed')
    const view = renderSection({ promptAvailable: true, promptInstall })
    await act(async () => {
      fireEvent.click(installButton()!)
    })
    state.current = { ...state.current, promptAvailable: false, promptDismissed: true }
    view.rerender(<InstallAppSection />)
    expect(screen.getByText('The installation prompt was closed.')).toBeInTheDocument()
    expect(screen.getByText(/Reload this page to try again if your browser offers a fresh prompt/i)).toBeInTheDocument()
    expect(installButton()).toBeNull()
  })

  it('shows the button again if the browser offers a fresh prompt after dismissal', async () => {
    const promptInstall = vi.fn().mockResolvedValue('dismissed')
    const view = renderSection({ promptAvailable: true, promptInstall })
    await act(async () => {
      fireEvent.click(installButton()!)
    })
    state.current = { ...state.current, promptAvailable: false, promptDismissed: true }
    view.rerender(<InstallAppSection />)
    expect(installButton()).toBeNull()

    state.current = { ...state.current, promptAvailable: true, promptDismissed: false }
    view.rerender(<InstallAppSection />)
    expect(installButton()).toBeInTheDocument()
  })

  it('degrades gracefully when the prompt has already been consumed', async () => {
    const promptInstall = vi.fn().mockResolvedValue('unavailable')
    const view = renderSection({ promptAvailable: true, promptInstall })
    await act(async () => {
      fireEvent.click(installButton()!)
    })
    state.current = { ...state.current, promptAvailable: false }
    view.rerender(<InstallAppSection />)
    expect(screen.getByText('This browser cannot install the app automatically.')).toBeInTheDocument()
    expect(installButton()).toBeNull()
  })

  it('survives a prompt that throws', async () => {
    const promptInstall = vi.fn().mockRejectedValue(new Error('NotAllowedError'))
    const view = renderSection({ promptAvailable: true, promptInstall })
    await act(async () => {
      fireEvent.click(installButton()!)
    })
    state.current = { ...state.current, promptAvailable: false, promptDismissed: true }
    view.rerender(<InstallAppSection />)
    expect(screen.getByText(/Reload this page to try again if your browser offers a fresh prompt/i)).toBeInTheDocument()
  })
})

describe('InstallAppSection (installed)', () => {
  it('reports the installed state and shows no button, even in standalone', () => {
    renderSection({ isInstalled: true, promptAvailable: true })
    expect(screen.getByText('SAS RESERVE is installed on this device.')).toBeInTheDocument()
    expect(screen.getByText('Installed')).toBeInTheDocument()
    expect(installButton()).toBeNull()
  })
})

describe('InstallAppSection (manual installation)', () => {
  it('gives iOS Safari Share → Add to Home Screen steps', () => {
    renderSection({ canShowIosInstructions: true })
    expect(screen.getByText('Add SAS RESERVE to your Home Screen')).toBeInTheDocument()
    expect(screen.getByText(/Share button/i)).toBeInTheDocument()
    expect(screen.getByText(/Add to Home Screen/i)).toBeInTheDocument()
    expect(installButton()).toBeNull()
  })

  it('points unsupported desktop browsers at the browser menu', () => {
    renderSection()
    expect(screen.getByText('This browser cannot install the app automatically.')).toBeInTheDocument()
    expect(screen.getByText(/Install app/)).toBeInTheDocument()
    expect(screen.getByText(/browser menu/i)).toBeInTheDocument()
    expect(installButton()).toBeNull()
  })

  it('never blocks the website on installation', () => {
    renderSection()
    expect(screen.getByText(/You can keep using SAS RESERVE in the browser/)).toBeInTheDocument()
  })
})
