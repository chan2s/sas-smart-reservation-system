/**
 * Backend reachability probe.
 *
 * Lives outside React so the offline provider stays a thin orchestrator and
 * the classification rules can be unit tested without a component tree. The
 * route is the unauthenticated Django view registered in config/urls.py; it is
 * reached through the same `/api` Vite proxy as every other API call, so a
 * probe result reflects exactly what real requests will experience.
 */

export const HEALTH_URL = '/api/health/'

/** Hard cap for one probe; a stalled connection must never hang the UI. */
export const HEALTH_TIMEOUT_MS = 6000

/**
 * Whether a health response proves the API is usable.
 *
 * 502/503/504 are gateway answers: the Vite dev proxy (or any reverse proxy)
 * could not reach Django at all, so the API really is unreachable.
 * Every other answer — including a plain 500, or a 404 from an older
 * deployment without the route — came FROM the service, so the backend is up
 * and the problem is application-level, not connectivity. Treating those as
 * "offline" would block writes and show the offline banner for a server that
 * is answering.
 */
export function isReachableHealthStatus(status: number): boolean {
  return status !== 502 && status !== 503 && status !== 504
}

/**
 * One connectivity probe.
 *
 * Resolves false only when the request produced no answer (DNS/connection
 * failure, timeout) or a gateway answer (502/503/504). An HTTP error from the
 * application itself is an answer and therefore counts as reachable.
 */
export async function probeBackend(signal?: AbortSignal): Promise<boolean> {
  if (typeof fetch !== 'function') return true
  if (signal?.aborted) return false

  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(abort, HEALTH_TIMEOUT_MS)
  try {
    const response = await fetch(HEALTH_URL, {
      method: 'GET',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    return isReachableHealthStatus(response.status)
  } catch {
    // Network error, opaque failure, or our own timeout.
    return false
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}
