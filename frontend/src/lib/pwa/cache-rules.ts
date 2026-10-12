/**
 * Service-worker runtime caching rules.
 *
 * Kept in a plain module (imported by vite.config.ts) so the policy is unit
 * testable without building the worker. The policy is intentionally narrow:
 *
 *  - public /media images may be cached (cache-first);
 *  - EVERYTHING under /api/ is NetworkOnly — including but not limited to auth,
 *    login, OAuth, OTP, refresh-token, reservation mutations, pricing/fees,
 *    analytics, audit-log and organizational endpoints. No authenticated API
 *    response is ever written to an HTTP cache, and no API response is ever
 *    replayed offline.
 *
 * IMPORTANT — the `urlPattern` callbacks must be SELF-CONTAINED. Workbox's
 * `generateSW` stringifies each callback into `dist/sw.js`, which does not
 * import this module: any identifier from this file (a helper function or a
 * shared constant) would be an undefined reference inside the worker. Literal
 * path prefixes are therefore repeated in the callbacks, and
 * `cache-rules.build.test.ts` asserts the generated worker contains no dangling
 * reference to them.
 */

export const MEDIA_CACHE_NAME = 'sas-public-media'

/** Documented policy: path families that must never be served from a cache. */
export const SENSITIVE_ENDPOINT_PREFIXES = [
  '/api/auth/',
  '/api/oauth/',
  '/api/reservations/',
  '/api/availability/',
  '/api/pricing/',
  '/api/analytics/',
  '/api/reports/',
  '/api/audit-log/',
  '/api/organizations/',
  '/api/equipment/',
  '/api/facilities/',
  '/api/health/',
] as const

/** The single prefix that makes a URL an API request. */
export const API_PATH_PREFIX = '/api/'

/** Public uploads; images here are the only cacheable response body. */
export const MEDIA_PATH_PREFIX = '/media/'

export const runtimeCaching = [
  {
    // Public, non-sensitive media (facility / equipment images). The only
    // network responses the worker is allowed to cache.
    urlPattern: ({ url, request }: { url: URL; request: Request }) =>
      url.pathname.startsWith('/media/') && request.destination === 'image',
    handler: 'CacheFirst' as const,
    options: {
      cacheName: MEDIA_CACHE_NAME,
      expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
      cacheableResponse: { statuses: [0, 200] },
    },
  },
  {
    // Every API call is network-only; offline reads come from the explicit
    // IndexedDB backup, never from an HTTP cache.
    urlPattern: ({ url }: { url: URL }) => url.pathname.startsWith('/api/'),
    handler: 'NetworkOnly' as const,
  },
]
