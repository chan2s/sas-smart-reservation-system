import { useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { ensureBrowserPushSubscription } from '@/lib/pushSubscription'

/** Repair an authorized staff device subscription after sign-in without asking
 * for browser permission. Permission prompts remain an explicit Settings
 * action because browsers require a user gesture. */
export function PushSubscriptionInitializer() {
  const { user, isStaff, isViewOnly } = useAuth()

  useEffect(() => {
    if (!user || !isStaff || isViewOnly || typeof Notification === 'undefined') return
    if (Notification.permission !== 'granted') return

    void ensureBrowserPushSubscription().catch((error) => {
      console.warn('[push] automatic staff subscription setup failed', error)
    })
  }, [user?.id, isStaff, isViewOnly])

  return null
}
