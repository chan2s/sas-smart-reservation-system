import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * The install invitation must behave for browsers that never offer one, a
 * dismissal must stick across page loads (a polite invite, not a nag), and the
 * invitation must become eligible again after the seven-day cooldown.
 *
 * The module captures `beforeinstallprompt` at import time, so each test loads
 * a fresh copy via `vi.resetModules()`.
 */

const DISMISS_KEY = 'sas_pwa_install_dismissed_at'
const LEGACY_DISMISS_KEY = 'sas_pwa_install_dismissed'
const IOS_DISMISS_KEY = 'sas_pwa_ios_install_dismissed_at'
const SEVEN_DAYS = 7 * 24 * 60 * 60 * 1000

interface FakePromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

function fireInstallPrompt(outcome: 'accepted' | 'dismissed' = 'accepted'): FakePromptEvent {
  const event = new Event('beforeinstallprompt') as FakePromptEvent
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome, platform: 'web' })
  window.dispatchEvent(event)
  return event
}

async function loadInstallModule() {
  return import('./install')
}

beforeEach(() => {
  vi.resetModules()
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function stubNavigator(
  overrides: {
    userAgent?: string
    platform?: string
    standalone?: boolean
    maxTouchPoints?: number
  },
) {
  if (overrides.userAgent !== undefined) {
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue(overrides.userAgent)
  }
  if (overrides.platform !== undefined) {
    vi.spyOn(window.navigator, 'platform', 'get').mockReturnValue(overrides.platform)
  }
  for (const key of ['standalone', 'maxTouchPoints'] as const) {
    if (overrides[key] !== undefined) {
      // jsdom does not implement navigator.standalone/maxTouchPoints; define
      // them directly (configurable so later tests are unaffected).
      Object.defineProperty(window.navigator, key, {
        value: overrides[key],
        configurable: true,
      })
    }
  }
}

describe('install prompt capture', () => {
  it('offers nothing in browsers that never fire the event', async () => {
    const install = await loadInstallModule()
    expect(install.getInstallSnapshot()).toEqual({
      canPrompt: false,
      dismissed: false,
      installed: false,
      canShowIosInstructions: false,
    })
    // must degrade (not throw) for unsupported browsers
    await expect(install.promptInstall()).resolves.toBe('unavailable')
  })

  it('captures the deferred prompt when the browser offers one', async () => {
    const install = await loadInstallModule()
    fireInstallPrompt()
    expect(install.getInstallSnapshot().canPrompt).toBe(true)
  })

  it('notifies subscribers when the prompt becomes available', async () => {
    const install = await loadInstallModule()
    const listener = vi.fn()
    install.subscribeInstall(listener)
    fireInstallPrompt()
    expect(listener).toHaveBeenCalled()
  })

  it('routes the user choice back to the caller', async () => {
    const install = await loadInstallModule()
    fireInstallPrompt('dismissed')
    await expect(install.promptInstall()).resolves.toBe('dismissed')
  })

  it('stops offering the prompt once it has been used', async () => {
    const install = await loadInstallModule()
    fireInstallPrompt('accepted')
    await install.promptInstall()
    expect(install.getInstallSnapshot().canPrompt).toBe(false)
  })

  it('does not offer installation when the app already runs standalone', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({ matches: true }),
    )
    const install = await loadInstallModule()
    fireInstallPrompt()
    expect(install.getInstallSnapshot().installed).toBe(true)
    expect(install.getInstallSnapshot().canPrompt).toBe(false)
  })

  it('marks the app installed after the appinstalled event', async () => {
    const install = await loadInstallModule()
    fireInstallPrompt()
    window.dispatchEvent(new Event('appinstalled'))
    expect(install.getInstallSnapshot().installed).toBe(true)
    expect(install.getInstallSnapshot().canPrompt).toBe(false)
  })

  it('survives a browser that blocks localStorage', async () => {
    const setItem = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new Error('denied')
      })
    const install = await loadInstallModule()
    fireInstallPrompt()
    expect(() => install.dismissInstall()).not.toThrow()
    expect(install.getInstallSnapshot().canPrompt).toBe(false)
    setItem.mockRestore()
  })
})

describe('dismissal cooldown', () => {
  it('writes a dismissal timestamp to localStorage', async () => {
    const install = await loadInstallModule()
    install.dismissInstall()
    const raw = window.localStorage.getItem(DISMISS_KEY)
    expect(raw).not.toBeNull()
    expect(Number(raw)).toBeGreaterThan(0)
  })

  it('never prompts again while the seven-day cooldown runs', async () => {
    const install = await loadInstallModule()
    fireInstallPrompt()
    install.dismissInstall()
    expect(install.getInstallSnapshot().canPrompt).toBe(false)
    expect(install.getInstallSnapshot().dismissed).toBe(true)

    // A later page load (within the cooldown) must still refuse to nag.
    vi.resetModules()
    const reloaded = await loadInstallModule()
    fireInstallPrompt()
    expect(reloaded.getInstallSnapshot().canPrompt).toBe(false)
  })

  it('becomes eligible again once the seven-day cooldown has elapsed', async () => {
    window.localStorage.setItem(DISMISS_KEY, String(Date.now() - SEVEN_DAYS - 1000))
    const install = await loadInstallModule()
    expect(install.getInstallSnapshot().dismissed).toBe(false)
    fireInstallPrompt()
    expect(install.getInstallSnapshot().canPrompt).toBe(true)
  })

  it('migrates the legacy permanent-dismissal flag to a timestamp', async () => {
    window.localStorage.setItem(LEGACY_DISMISS_KEY, '1')
    const install = await loadInstallModule()
    // Still dismissed now (migration writes the current time), and the legacy
    // key is gone.
    expect(install.getInstallSnapshot().dismissed).toBe(true)
    expect(window.localStorage.getItem(LEGACY_DISMISS_KEY)).toBeNull()
    expect(window.localStorage.getItem(DISMISS_KEY)).not.toBeNull()
  })

  it('ignores a corrupt dismissal timestamp', async () => {
    window.localStorage.setItem(DISMISS_KEY, 'not-a-number')
    const install = await loadInstallModule()
    fireInstallPrompt()
    expect(install.getInstallSnapshot().canPrompt).toBe(true)
  })
})

describe('iOS manual installation', () => {
  it('detects an iPhone and offers manual instructions', async () => {
    stubNavigator({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1' })
    const install = await loadInstallModule()
    expect(install.getInstallSnapshot().canShowIosInstructions).toBe(true)
  })

  it('detects iPadOS (Mac UA with touch) and offers manual instructions', async () => {
    stubNavigator({
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15',
      platform: 'MacIntel',
      maxTouchPoints: 5,
    })
    const install = await loadInstallModule()
    expect(install.getInstallSnapshot().canShowIosInstructions).toBe(true)
  })

  it('offers nothing on desktop browsers without the prompt event', async () => {
    stubNavigator({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0' })
    const install = await loadInstallModule()
    expect(install.getInstallSnapshot().canShowIosInstructions).toBe(false)
  })

  it('hides the instructions once the app is installed (standalone)', async () => {
    stubNavigator({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1' })
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    const install = await loadInstallModule()
    expect(install.getInstallSnapshot().canShowIosInstructions).toBe(false)
  })

  it('remembers a dismissal of the instructions for the cooldown period', async () => {
    stubNavigator({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1' })
    const install = await loadInstallModule()
    install.dismissIosInstructions()
    expect(window.localStorage.getItem(IOS_DISMISS_KEY)).not.toBeNull()

    vi.resetModules()
    const reloaded = await loadInstallModule()
    expect(reloaded.getInstallSnapshot().canShowIosInstructions).toBe(false)

    // …and they become eligible again after seven days.
    window.localStorage.setItem(IOS_DISMISS_KEY, String(Date.now() - SEVEN_DAYS - 1000))
    vi.resetModules()
    const later = await loadInstallModule()
    expect(later.getInstallSnapshot().canShowIosInstructions).toBe(true)
  })
})
