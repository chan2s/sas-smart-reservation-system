/**
 * Connectivity state shared outside React.
 *
 * The API client (src/lib/api.ts) and the offline provider both need the same
 * answer to "may I talk to Django right now?". React context cannot be read
 * from the fetch layer, so the provider writes the latest backend-reachability
 * result here and the API client reads it synchronously.
 *
 * `navigator.onLine` is only one input: a browser can report online while the
 * Django API is unreachable. Effective connectivity requires BOTH.
 */

type Listener = () => void

/** Result of the last explicit reachability probe. null = not yet known. */
let apiReachable: boolean | null = null
const listeners = new Set<Listener>()

export function setApiReachable(value: boolean | null): void {
  if (apiReachable === value) return
  apiReachable = value
  listeners.forEach((listener) => listener())
}

export function getApiReachable(): boolean | null {
  return apiReachable
}

export function subscribeConnectivity(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** True when the browser believes it has a network connection. */
export function browserOnline(): boolean {
  if (typeof navigator === 'undefined') return true
  return navigator.onLine !== false
}

/**
 * Effective connectivity: the browser has a network AND we have not just
 * proven the backend unreachable. When reachability is still unknown (null) we
 * optimistically allow requests, so the app is never blocked before the first
 * probe completes.
 */
export function isEffectivelyOnline(): boolean {
  if (!browserOnline()) return false
  return apiReachable !== false
}

/** Mutations (anything that is not a safe read) require effective connectivity. */
export function isMutationAllowed(): boolean {
  return isEffectivelyOnline()
}

/** Thrown by the API client when a write is attempted with no backend. */
export class OfflineError extends Error {
  constructor(
    message = "You're offline — this action needs a connection. Nothing was changed.",
  ) {
    super(message)
    this.name = 'OfflineError'
  }
}
