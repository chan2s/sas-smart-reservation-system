import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  pushPublicKey: vi.fn(),
  pushSubscriptions: vi.fn(),
  registerPushSubscription: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ endpoints: mocks }))

import { ensureBrowserPushSubscription } from './pushSubscription'

const notification = { permission: 'granted' as NotificationPermission }

beforeEach(() => {
  notification.permission = 'granted'
  mocks.pushPublicKey.mockReset().mockResolvedValue({ public_key: 'AQID' })
  mocks.pushSubscriptions.mockReset().mockResolvedValue([])
  mocks.registerPushSubscription.mockReset().mockResolvedValue({})
  vi.stubGlobal('Notification', notification)
  vi.stubGlobal('PushManager', class {})
  const subscription = {
    endpoint: 'https://fcm.googleapis.com/test-device',
    getKey: (name: string) => name === 'p256dh' ? new Uint8Array(65).buffer : new Uint8Array(16).buffer,
  }
  const registration = {
    pushManager: {
      getSubscription: vi.fn().mockResolvedValue(null),
      subscribe: vi.fn().mockResolvedValue(subscription),
    },
  }
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      getRegistration: vi.fn().mockResolvedValue(registration),
      register: vi.fn(),
    },
  })
})

afterEach(() => vi.unstubAllGlobals())

describe('ensureBrowserPushSubscription', () => {
  it('does not prompt for browser permission or subscribe before it is granted', async () => {
    notification.permission = 'default'
    await expect(ensureBrowserPushSubscription()).resolves.toBe('permission-required')
    expect(mocks.pushPublicKey).not.toHaveBeenCalled()
    expect(mocks.registerPushSubscription).not.toHaveBeenCalled()
  })

  it('uses the configured VAPID public key and persists the browser subscription', async () => {
    await expect(ensureBrowserPushSubscription()).resolves.toBe('subscribed')
    expect(mocks.pushPublicKey).toHaveBeenCalledOnce()
    expect(mocks.registerPushSubscription).toHaveBeenCalledWith(expect.objectContaining({
      endpoint: 'https://fcm.googleapis.com/test-device',
      keys: expect.objectContaining({ p256dh: expect.any(String), auth: expect.any(String) }),
    }))
  })
})
