import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { describe, expect, it, vi } from 'vitest'

function loadPushHandlers() {
  const listeners = new Map<string, (event: any) => void>()
  const self = {
    location: { origin: 'https://reserve.example.edu' },
    registration: { showNotification: vi.fn().mockResolvedValue(undefined) },
    clients: { matchAll: vi.fn(), openWindow: vi.fn() },
    addEventListener: (name: string, handler: (event: any) => void) => listeners.set(name, handler),
  }
  const source = readFileSync(resolve(process.cwd(), 'public/push-handler.js'), 'utf8')
  runInNewContext(source, { self, URL })
  return { listeners, self }
}

describe('service worker push handlers', () => {
  it('shows a notification while the app page is not required to be open', async () => {
    const { listeners, self } = loadPushHandlers()
    let completion: Promise<unknown> | undefined
    listeners.get('push')!({
      data: { json: () => ({ title: 'SAS RESERVE', body: 'New reservation', url: '/reservations/42' }) },
      waitUntil: (promise: Promise<unknown>) => { completion = promise },
    })

    await completion
    expect(self.registration.showNotification).toHaveBeenCalledWith('SAS RESERVE', expect.objectContaining({
      body: 'New reservation',
      data: { url: '/reservations/42' },
    }))
    expect([...listeners.keys()]).toEqual(['push', 'notificationclick'])
  })

  it('focuses an open app tab and navigates it to the notification route', async () => {
    const { listeners, self } = loadPushHandlers()
    const client = {
      url: 'https://reserve.example.edu/dashboard',
      navigate: vi.fn().mockResolvedValue(undefined),
      focus: vi.fn().mockResolvedValue(undefined),
    }
    self.clients.matchAll = vi.fn().mockResolvedValue([client])
    let completion: Promise<unknown> | undefined
    listeners.get('notificationclick')!({
      notification: { data: { url: '/reservations/42' }, close: vi.fn() },
      waitUntil: (promise: Promise<unknown>) => { completion = promise },
    })

    await completion
    expect(client.navigate).toHaveBeenCalledWith('https://reserve.example.edu/reservations/42')
    expect(client.focus).toHaveBeenCalledOnce()
  })
})
