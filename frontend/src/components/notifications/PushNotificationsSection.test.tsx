import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  pushSubscriptions: vi.fn().mockResolvedValue([]),
  pushPublicKey: vi.fn(),
  registerPushSubscription: vi.fn(),
  updatePushSubscription: vi.fn(),
  removePushSubscription: vi.fn(),
  toast: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ endpoints: mocks }))
vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ toast: mocks.toast }) }))

import { PushNotificationsSection } from './PushNotificationsSection'

const notification = {
  permission: 'default' as NotificationPermission,
  requestPermission: vi.fn<() => Promise<NotificationPermission>>(),
}

beforeEach(() => {
  notification.permission = 'default'
  notification.requestPermission.mockReset()
  mocks.pushSubscriptions.mockReset().mockResolvedValue([])
  vi.stubGlobal('Notification', notification)
  vi.stubGlobal('PushManager', class {})
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: { getRegistration: vi.fn().mockResolvedValue(undefined) },
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('PushNotificationsSection', () => {
  it('does not request permission until the user explicitly enables push', async () => {
    render(<PushNotificationsSection />)
    await waitFor(() => expect(mocks.pushSubscriptions).toHaveBeenCalled())
    expect(notification.requestPermission).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Enable notifications' })).toBeInTheDocument()
  })

  it('explains when browser permission is denied', async () => {
    notification.permission = 'denied'
    render(<PushNotificationsSection />)
    expect(notification.requestPermission).not.toHaveBeenCalled()
    expect(screen.getByText(/browser settings, allow notifications/i)).toBeInTheDocument()
    expect(mocks.pushPublicKey).not.toHaveBeenCalled()
  })

  it('requests permission from the explicit enable action', async () => {
    notification.requestPermission.mockResolvedValue('denied')
    render(<PushNotificationsSection />)
    fireEvent.click(screen.getByRole('button', { name: 'Enable notifications' }))
    await waitFor(() => expect(notification.requestPermission).toHaveBeenCalledOnce())
    expect(mocks.pushPublicKey).not.toHaveBeenCalled()
  })
})
