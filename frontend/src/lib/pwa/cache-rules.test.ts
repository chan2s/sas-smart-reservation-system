import { describe, expect, it } from 'vitest'
import {
  API_PATH_PREFIX,
  MEDIA_PATH_PREFIX,
  SENSITIVE_ENDPOINT_PREFIXES,
  runtimeCaching,
} from './cache-rules'

/**
 * The service worker is the one place where a mistake could hand a stale or
 * sensitive API payload to the user. These tests drive the ACTUAL rules that
 * vite-plugin-pwa turns into the deployed worker, so a policy change cannot
 * silently disagree with its documentation.
 */

const rules = runtimeCaching as unknown as {
  urlPattern: (context: { url: URL; request: Request }) => boolean
  handler: string
}[]

const apiRule = rules.find((rule) => rule.handler === 'NetworkOnly')
const mediaRule = rules.find((rule) => rule.handler === 'CacheFirst')

// Workbox passes the real Request; jsdom's Request does not populate
// `destination`, so the predicate is given the same shape explicitly.
const context = (pathname: string, destination = '') => ({
  url: new URL(`https://sas-reserve-api.onrender.com${pathname}`),
  request: { destination } as Request,
})

describe('API rule', () => {
  it('is declared exactly once, as NetworkOnly', () => {
    expect(rules.filter((rule) => rule.handler === 'NetworkOnly')).toHaveLength(1)
    expect(apiRule).toBeDefined()
  })

  it('matches every sensitive endpoint family', () => {
    for (const prefix of SENSITIVE_ENDPOINT_PREFIXES) {
      expect(apiRule!.urlPattern(context(prefix)), prefix).toBe(true)
    }
  })

  it('matches the API paths the app actually calls', () => {
    for (const path of [
      '/api/',
      '/api/auth/login/',
      '/api/auth/refresh/',
      '/api/auth/2fa/verify-login/',
      '/api/reservations/',
      '/api/reservations/12/approve/',
      '/api/reservations/checkin/abc/',
      '/api/availability/check/',
      '/api/analytics/summary/',
      '/api/reports/utilization/export/csv/',
      '/api/health/',
    ]) {
      expect(apiRule!.urlPattern(context(path)), path).toBe(true)
    }
  })

  it('is not fooled by a path that merely starts with "api"', () => {
    expect(apiRule!.urlPattern(context('/apix/facilities/'))).toBe(false)
    expect(apiRule!.urlPattern(context('/media/facility.png', 'image'))).toBe(false)
  })

  it('documents the same prefix the rule hard-codes', () => {
    expect(API_PATH_PREFIX).toBe('/api/')
    expect(rules).toHaveLength(2)
  })
})

describe('media rule', () => {
  it('caches public media images', () => {
    expect(mediaRule!.urlPattern(context('/media/facilities/hall.png', 'image'))).toBe(true)
    expect(MEDIA_PATH_PREFIX).toBe('/media/')
  })

  it('ignores non-image responses and non-media paths', () => {
    expect(mediaRule!.urlPattern(context('/media/facilities/hall.png'))).toBe(false)
    expect(mediaRule!.urlPattern(context('/media/archive.zip', 'document'))).toBe(false)
    expect(mediaRule!.urlPattern(context('/assets/logo.png', 'image'))).toBe(false)
    expect(mediaRule!.urlPattern(context('/api/facilities/', 'image'))).toBe(false)
  })
})
