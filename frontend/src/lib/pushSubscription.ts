import { endpoints } from '@/lib/api'
import type { PushDevice } from '@/lib/types'

export type PushSetupResult = 'subscribed' | 'already-active' | 'unsupported' | 'permission-required' | 'disabled'

let setupInProgress: Promise<PushSetupResult> | null = null

function supported(): boolean {
  return typeof window !== 'undefined' &&
    'Notification' in window &&
    'serviceWorker' in navigator &&
    'PushManager' in window
}

function applicationServerKey(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (value.length % 4)) % 4)
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0)).buffer as ArrayBuffer
}

function deviceLabel(): string {
  const ua = navigator.userAgent
  const browser = /Edg\//.test(ua) ? 'Microsoft Edge' : /Chrome\//.test(ua) ? 'Google Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser'
  const os = /Windows/.test(ua) ? 'Windows' : /Android/.test(ua) ? 'Android' : /iPhone|iPad|iPod/.test(ua) ? 'iPhone/iPad' : /Mac OS/.test(ua) ? 'Mac' : 'Device'
  return `${browser} on ${os}`
}

async function endpointFingerprint(endpoint: string): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(endpoint))
  return Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, '0')).join('')
}

function base64UrlKey(subscription: PushSubscription, key: 'p256dh' | 'auth'): string {
  const value = subscription.getKey(key)
  if (!value) throw new Error(`The browser did not provide a ${key} push key.`)
  return btoa(String.fromCharCode(...new Uint8Array(value)))
}

async function ensureSubscription(reactivate: boolean): Promise<PushSetupResult> {
  if (!supported()) return 'unsupported'
  if (Notification.permission !== 'granted') return 'permission-required'

  const registration = await navigator.serviceWorker.getRegistration('/') ??
    await navigator.serviceWorker.register('/sw.js', { scope: '/' })
  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) {
    const key = await endpoints.pushPublicKey()
    const created = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: applicationServerKey(key.public_key),
    })
    await persistSubscription(created)
    return 'subscribed'
  }

  const fingerprint = await endpointFingerprint(subscription.endpoint)
  const devices: PushDevice[] = await endpoints.pushSubscriptions()
  const currentDevice = devices.find((device) => device.endpoint_fingerprint === fingerprint)
  if (currentDevice?.active) return 'already-active'
  if (currentDevice && !reactivate) return 'disabled'
  if (!currentDevice) {
    // A missing server row can mean the provider expired the old endpoint or
    // this browser was previously linked to another signed-in account. Rotate
    // the local endpoint before associating it with the current account.
    await subscription.unsubscribe()
    const key = await endpoints.pushPublicKey()
    const replacement = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: applicationServerKey(key.public_key),
    })
    await persistSubscription(replacement)
    return 'subscribed'
  }
  await persistSubscription(subscription)
  return 'subscribed'
}

async function persistSubscription(subscription: PushSubscription): Promise<void> {
  await endpoints.registerPushSubscription({
    device_name: deviceLabel(),
    endpoint: subscription.endpoint,
    keys: {
      p256dh: base64UrlKey(subscription, 'p256dh'),
      auth: base64UrlKey(subscription, 'auth'),
    },
  })
}

/**
 * Register and persist a browser subscription only after permission exists.
 * The optional flag is used by the explicit Settings action to re-enable a
 * device the user previously disabled.
 */
export function ensureBrowserPushSubscription({ reactivate = false } = {}): Promise<PushSetupResult> {
  if (!setupInProgress) {
    setupInProgress = ensureSubscription(reactivate).finally(() => {
      setupInProgress = null
    })
  }
  return setupInProgress
}
