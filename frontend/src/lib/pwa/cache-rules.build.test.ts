import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Guards the generated worker, not the config source.
 *
 * Workbox's `generateSW` stringifies each `runtimeCaching.urlPattern` callback
 * into `dist/sw.js`, which never imports our config module. A callback that
 * referenced a helper function or a shared constant would compile, build, and
 * then throw a ReferenceError inside the worker on every GET — silently
 * disabling offline support. These assertions run against the real build
 * output and are skipped (not faked) when `dist/` has not been produced yet.
 *
 * Run `npm run build` first for these to be meaningful.
 */

const swPath = path.resolve(process.cwd(), 'dist/sw.js')
const hasBuild = existsSync(swPath)

describe.skipIf(!hasBuild)('generated service worker (dist/sw.js)', () => {
  const source = hasBuild ? readFileSync(swPath, 'utf8') : ''

  it('registers self-contained runtime caching callbacks', () => {
    // Identifiers from src/lib/pwa/cache-rules.ts must never leak into the
    // worker: the module is not bundled with it.
    for (const identifier of [
      'isApiNetworkOnly',
      'isPublicMediaImage',
      'SENSITIVE_ENDPOINT_PREFIXES',
      'API_PATH_PREFIX',
      'MEDIA_PATH_PREFIX',
      'MEDIA_CACHE_NAME',
      'runtimeCaching',
    ]) {
      expect(source, `dangling reference: ${identifier}`).not.toContain(identifier)
    }
  })

  it('still enforces both prefixes as literals', () => {
    expect(source).toContain('/api/')
    expect(source).toContain('/media/')
    expect(source).toContain('NetworkOnly')
    expect(source).toContain('CacheFirst')
    expect(source).toContain('sas-public-media')
  })

  it('precaches the app shell and precaches no API response', () => {
    const urls = [...source.matchAll(/url:"([^"]+)"/g)].map((match) => match[1])
    expect(urls).toContain('index.html')
    expect(urls).toContain('manifest.webmanifest')
    expect(urls.some((url) => url.startsWith('/api'))).toBe(false)
    expect(urls.some((url) => url.startsWith('api'))).toBe(false)
  })

  it('does not take over open pages without the user accepting the update', () => {
    // registerType is 'prompt': no clientsClaim, no skipWaiting at startup — an
    // update must never reload the page mid-reservation.
    expect(source).not.toContain('clientsClaim')
  })
})
