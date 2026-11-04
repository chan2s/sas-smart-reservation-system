/* Imported into Workbox's generated service worker. Keep payloads generic. */
self.addEventListener('push', (event) => {
  let payload
  try {
    payload = event.data ? event.data.json() : {}
  } catch {
    payload = {}
  }
  if (!payload || typeof payload !== 'object') payload = {}
  const title = typeof payload.title === 'string' ? payload.title : 'SAS RESERVE'
  const options = {
    body: typeof payload.body === 'string' ? payload.body : 'You have an update. Sign in to view it.',
    icon: '/pwa-192x192.png',
    badge: '/pwa-192x192.png',
    tag: typeof payload.tag === 'string' ? payload.tag : 'sas-update',
    data: { url: typeof payload.url === 'string' ? payload.url : '/notifications' },
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const destination = event.notification.data?.url
  let target = new URL('/notifications', self.location.origin).href
  if (typeof destination === 'string' && destination.startsWith('/') && !destination.startsWith('//') && !destination.includes('\\')) {
    const candidate = new URL(destination, self.location.origin)
    if (candidate.origin === self.location.origin) target = candidate.href
  }
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(target)
        return client.focus()
      }
    }
    return self.clients.openWindow(target)
  })())
})
