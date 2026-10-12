import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  OfflineError,
  browserOnline,
  getApiReachable,
  isEffectivelyOnline,
  isMutationAllowed,
  setApiReachable,
  subscribeConnectivity,
} from './connectivity'

/**
 * The distinction that matters: `navigator.onLine` says the device has a
 * network; only a successful probe says the Django API is reachable. A browser
 * that is online while Render is down must still be treated as offline for
 * writes.
 */

function setBrowserOnline(value: boolean) {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(value)
}

afterEach(() => {
  vi.restoreAllMocks()
  setApiReachable(null)
})

describe('connectivity', () => {
  it('optimistically allows requests before the first probe', () => {
    setBrowserOnline(true)
    expect(getApiReachable()).toBeNull()
    expect(isEffectivelyOnline()).toBe(true)
  })

  it('reports offline when the browser has no network', () => {
    setBrowserOnline(false)
    expect(browserOnline()).toBe(false)
    expect(isEffectivelyOnline()).toBe(false)
    expect(isMutationAllowed()).toBe(false)
  })

  it('detects an unreachable backend even while the browser reports online', () => {
    setBrowserOnline(true)
    setApiReachable(false)
    expect(browserOnline()).toBe(true)
    expect(isEffectivelyOnline()).toBe(false)
    expect(isMutationAllowed()).toBe(false)
  })

  it('recovers once the backend answers again', () => {
    setBrowserOnline(true)
    setApiReachable(false)
    setApiReachable(true)
    expect(isEffectivelyOnline()).toBe(true)
    expect(isMutationAllowed()).toBe(true)
  })

  it('notifies subscribers when reachability changes, and stops after unsubscribe', () => {
    setBrowserOnline(true)
    const listener = vi.fn()
    const unsubscribe = subscribeConnectivity(listener)
    setApiReachable(false)
    expect(listener).toHaveBeenCalledTimes(1)
    // Setting the same value again must not re-notify.
    setApiReachable(false)
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
    setApiReachable(true)
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('OfflineError', () => {
  it('explains that nothing was changed', () => {
    const error = new OfflineError()
    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('OfflineError')
    expect(error.message).toMatch(/offline/i)
    expect(error.message).toMatch(/nothing was changed/i)
  })
})
