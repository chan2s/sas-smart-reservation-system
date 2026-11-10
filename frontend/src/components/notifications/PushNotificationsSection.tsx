import { useCallback, useEffect, useState } from 'react'
import { Bell, BellOff, MonitorSmartphone, Trash2 } from 'lucide-react'
import { endpoints } from '@/lib/api'
import { ensureBrowserPushSubscription } from '@/lib/pushSubscription'
import type { PushDevice } from '@/lib/types'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { useToast } from '@/components/ui/Toast'

type PermissionState = NotificationPermission | 'unsupported'

export function PushNotificationsSection() {
  const { toast } = useToast()
  const supported = typeof window !== 'undefined' && 'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window
  const isAppleMobile = typeof navigator !== 'undefined' && /iPhone|iPad|iPod/.test(navigator.userAgent)
  const installed = typeof window !== 'undefined' && (
    (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches) ||
    Boolean((navigator as Navigator & { standalone?: boolean }).standalone)
  )
  const [permission, setPermission] = useState<PermissionState>(supported ? Notification.permission : 'unsupported')
  const [devices, setDevices] = useState<PushDevice[]>([])
  const [currentSubscribed, setCurrentSubscribed] = useState(false)
  const [currentDevice, setCurrentDevice] = useState<PushDevice | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    if (!supported) return
    try {
      const [registered, registration] = await Promise.all([
        endpoints.pushSubscriptions(), navigator.serviceWorker.getRegistration('/'),
      ])
      setDevices(registered)
      const subscription = await registration?.pushManager.getSubscription()
      setCurrentSubscribed(Boolean(subscription))
      const fingerprint = subscription
        ? await crypto.subtle.digest('SHA-256', new TextEncoder().encode(subscription.endpoint)).then((bytes) =>
            Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, '0')).join(''),
          )
        : null
      setCurrentDevice(registered.find((device) => device.endpoint_fingerprint === fingerprint) ?? null)
      setPermission(Notification.permission)
    } catch {
      // Keep the settings page usable if push has not been configured yet.
    }
  }, [supported])

  useEffect(() => { void refresh() }, [refresh])

  async function enable() {
    if (!supported) return
    setBusy(true)
    try {
      const result = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission
      setPermission(result)
      if (result !== 'granted') return
      await ensureBrowserPushSubscription({ reactivate: true })
      await refresh()
      toast('Push notifications are enabled on this device.')
    } catch {
      toast('Unable to enable push notifications. Check your connection and try again.', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function disable() {
    if (!currentDevice) return
    setBusy(true)
    try {
      await endpoints.updatePushSubscription(currentDevice.id, false)
      await refresh()
      toast('Push notifications are disabled on this device.')
    } catch {
      toast('Unable to update push preferences.', 'error')
    } finally { setBusy(false) }
  }

  async function removeDevice(device: PushDevice) {
    try {
      await endpoints.removePushSubscription(device.id)
      if (currentDevice?.id === device.id) {
        const registration = await navigator.serviceWorker.getRegistration('/')
        const subscription = await registration?.pushManager.getSubscription()
        await subscription?.unsubscribe()
      }
      setDevices((current) => current.filter((item) => item.id !== device.id))
      await refresh()
      toast('Device removed.')
    } catch { toast('Unable to remove this device.', 'error') }
  }

  return (
    <Card className="mt-6">
      <CardHeader title="Push Notifications" description="Receive brief reservation and workflow updates on this browser or installed app." />
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-2 text-sm text-body">
          {permission === 'granted' ? <Bell className="size-4 text-status-approved" aria-hidden /> : <BellOff className="size-4 text-muted" aria-hidden />}
          Permission: <strong className="font-medium text-ink">{permission === 'unsupported' ? 'Not supported' : permission}</strong>
        </span>
        {supported && currentDevice?.active ? (
          <Button variant="outline" size="sm" loading={busy} onClick={() => void disable()}>Disable notifications</Button>
        ) : supported ? (
          <Button size="sm" loading={busy} onClick={() => void enable()}>Enable notifications</Button>
        ) : null}
      </div>
      {!supported && <p className="mt-3 text-sm text-body">This browser does not support Web Push. Try a current version of Chrome or Edge, or install SAS RESERVE on a supported device.</p>}
      {isAppleMobile && !installed && <p className="mt-3 text-sm text-body">On iPhone or iPad, Web Push is available from iOS/iPadOS 16.4 onward only after SAS RESERVE is added to the Home Screen. Open the installed app to enable notifications.</p>}
      {permission === 'denied' && <p className="mt-3 text-sm text-body">Notifications are blocked by your browser. Open this site’s browser settings, allow notifications, then return here and enable them. On iPhone or iPad, add SAS RESERVE to the Home Screen and enable notifications for the installed app.</p>}
      {supported && permission !== 'denied' && <p className="mt-3 text-xs text-muted">Current device: {currentSubscribed ? currentDevice ? currentDevice.active ? 'registered and enabled' : 'registered but disabled' : 'browser subscription is not linked to this account' : 'not registered'}. You can disable this device without affecting your other devices. Internet access and operating system notification settings are also required.</p>}
      {devices.length > 0 && <div className="mt-5 border-t border-line pt-4">
        <h4 className="text-sm font-semibold text-ink">Registered devices</h4>
        <ul className="mt-2 divide-y divide-line">
          {devices.map((device) => <li key={device.id} className="flex items-center justify-between gap-3 py-3">
            <div className="flex min-w-0 items-center gap-2.5"><MonitorSmartphone className="size-4 shrink-0 text-muted" aria-hidden /><div className="min-w-0"><p className="truncate text-sm font-medium text-ink">{device.device_name || 'Browser device'}</p><p className="text-xs text-muted">{device.active ? 'Active' : 'Inactive'} · Added {new Date(device.created_at).toLocaleDateString()}</p></div></div>
            <Button variant="ghost" size="sm" aria-label={`Remove ${device.device_name || 'device'}`} onClick={() => void removeDevice(device)} icon={<Trash2 className="size-4" />}>Remove</Button>
          </li>)}
        </ul>
      </div>}
      {permission === 'default' && <p className="mt-3 text-xs text-muted">Your browser will ask for permission only after you select Enable notifications.</p>}
    </Card>
  )
}
