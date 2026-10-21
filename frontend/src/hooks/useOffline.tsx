import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/components/ui/Toast'
import {
  browserOnline,
  getApiReachable,
  isEffectivelyOnline,
  setApiReachable,
} from '@/lib/offline/connectivity'
import { getBackupMeta } from '@/lib/offline/db'
import { probeBackend } from '@/lib/offline/health'
import { syncOfflineBackup, type SyncResult } from '@/lib/offline/sync'

const OFFLINE_POLL_MS = 20000
/** Do not hammer the backend when several triggers fire close together. */
const MIN_PROBE_INTERVAL_MS = 5000
const SYNC_DEBOUNCE_MS = 4000

interface OfflineContextValue {
  /** Browser + backend agree the API is usable. */
  online: boolean
  /** navigator.onLine only (may be true while the API is down). */
  browserOnline: boolean
  /** Last reachability probe result; null until the first probe. */
  apiReachable: boolean | null
  /** A reachability probe is in flight. */
  checking: boolean
  /** ISO timestamp of the last successful backup sync (null when none). */
  lastSyncedAt: string | null
  /** True when a usable backup exists for the current user. */
  hasBackup: boolean
  /** Human-readable reason the last sync failed, if any. */
  backupError: string | null
  /** Probe the backend again now. */
  retryConnection: () => Promise<boolean>
  /** Force a backup refresh (no-op while offline). */
  syncNow: () => Promise<SyncResult | undefined>
}

const OfflineContext = createContext<OfflineContextValue | null>(null)

/**
 * Connectivity + offline-backup orchestration.
 *
 * Backend reachability is probed explicitly (`/api/health/`), never inferred
 * from `navigator.onLine`. The provider keeps the shared connectivity store in
 * sync so the API client can block offline writes, and it refreshes the
 * IndexedDB backup only after a successful sync.
 */
export function OfflineProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [browserOnlineState, setBrowserOnlineState] = useState(browserOnline)
  const [apiReachableState, setApiReachableState] = useState<boolean | null>(getApiReachable)
  const [checking, setChecking] = useState(false)
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null)
  const [hasBackup, setHasBackup] = useState(false)
  const [backupError, setBackupError] = useState<string | null>(null)

  const wasOffline = useRef(false)
  const syncDebounce = useRef<number | null>(null)

  // Probe bookkeeping: never run two probes at once, never hammer the backend
  // when several triggers fire together, and never write state after unmount.
  const mounted = useRef(true)
  const inFlightProbe = useRef<Promise<boolean> | null>(null)
  const inFlightController = useRef<AbortController | null>(null)
  const lastProbeAt = useRef(0)
  const lastKnownReachable = useRef<boolean | null>(getApiReachable())

  const applyReachability = useCallback((value: boolean | null) => {
    lastKnownReachable.current = value
    setApiReachableState(value)
    // Mirror into the store read synchronously by src/lib/api.ts.
    setApiReachable(value)
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      // Abort an outstanding probe so it cannot resolve into a dead tree.
      inFlightController.current?.abort()
      inFlightController.current = null
      inFlightProbe.current = null
    }
  }, [])

  const runProbe = useCallback(
    async ({ force = false }: { force?: boolean } = {}): Promise<boolean> => {
      if (!mounted.current) return false
      // Join the probe already in flight instead of starting a second one.
      if (inFlightProbe.current) return inFlightProbe.current
      // Scheduled triggers (mount, offline poll) are rate limited; an explicit
      // user retry or a browser 'online' recovery signal (force) always probes.
      if (!force && Date.now() - lastProbeAt.current < MIN_PROBE_INTERVAL_MS) {
        return lastKnownReachable.current !== false
      }

      const controller = new AbortController()
      inFlightController.current = controller
      setChecking(true)

      const probe = probeBackend(controller.signal)
        .then((reachable) => {
          lastProbeAt.current = Date.now()
          if (mounted.current) applyReachability(reachable)
          return reachable
        })
        .finally(() => {
          if (inFlightProbe.current === probe) inFlightProbe.current = null
          if (inFlightController.current === controller) inFlightController.current = null
          if (mounted.current) setChecking(false)
        })

      inFlightProbe.current = probe
      return probe
    },
    [applyReachability],
  )

  // First probe on mount.
  useEffect(() => {
    void runProbe()
  }, [runProbe])

  // Browser connectivity events.
  useEffect(() => {
    const onOnline = () => {
      setBrowserOnlineState(true)
      // The browser just regained a network: probe immediately instead of
      // waiting for the offline poll interval, so recovery is instant.
      void runProbe({ force: true })
    }
    const onOffline = () => {
      setBrowserOnlineState(false)
      applyReachability(false)
    }
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [runProbe, applyReachability])

  const online = browserOnlineState && apiReachableState !== false

  // While not effectively online, keep re-probing so recovery is detected even
  // when the browser still claims to be online.
  useEffect(() => {
    if (online) return
    const id = window.setInterval(() => {
      void runProbe()
    }, OFFLINE_POLL_MS)
    return () => window.clearInterval(id)
  }, [online, runProbe])

  // Reflect an existing backup on load / user change.
  useEffect(() => {
    let cancelled = false
    if (!user) {
      setLastSyncedAt(null)
      setHasBackup(false)
      return
    }
    void getBackupMeta()
      .then((meta) => {
        if (cancelled) return
        if (meta.ownerId === user.id && meta.syncedAt) {
          setLastSyncedAt(meta.syncedAt)
          setHasBackup(true)
        } else {
          setLastSyncedAt(null)
          setHasBackup(false)
        }
      })
      .catch(() => {
        /* storage unavailable — no backup */
      })
    return () => {
      cancelled = true
    }
  }, [user])

  const syncNow = useCallback(async (): Promise<SyncResult | undefined> => {
    if (!user) return undefined
    if (!isEffectivelyOnline()) return undefined
    const result = await syncOfflineBackup(user)
    if (result.ok) {
      setLastSyncedAt(result.syncedAt)
      setHasBackup(true)
      setBackupError(null)
    } else if (result.reason !== 'offline') {
      setBackupError(result.error ?? 'The offline backup could not be updated.')
    }
    return result
  }, [user])

  // Sync on login and whenever connectivity is (re)gained.
  useEffect(() => {
    if (!user || !online) return
    void syncNow()
  }, [user, online, syncNow])

  // Announce restoration, and remember that we were offline.
  useEffect(() => {
    if (!online) {
      wasOffline.current = true
      return
    }
    if (wasOffline.current && user) {
      wasOffline.current = false
      toast('Connection restored.', 'success')
    }
  }, [online, user, toast])

  // Refresh the backup after successful reads of the cached datasets.
  useEffect(() => {
    if (!user) return
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      const key = Array.isArray(event.query.queryKey) ? event.query.queryKey[0] : undefined
      if (
        event.query.state.status === 'success' &&
        (key === 'facilities' || key === 'equipment' || key === 'reservations')
      ) {
        if (syncDebounce.current) window.clearTimeout(syncDebounce.current)
        syncDebounce.current = window.setTimeout(() => {
          void syncNow()
        }, SYNC_DEBOUNCE_MS)
      }
    })
    return () => {
      unsubscribe()
      if (syncDebounce.current) window.clearTimeout(syncDebounce.current)
    }
  }, [queryClient, user, syncNow])

  const retryConnection = useCallback(async () => {
    const reachable = await runProbe({ force: true })
    if (reachable) void syncNow()
    return reachable
  }, [runProbe, syncNow])

  const value = useMemo<OfflineContextValue>(
    () => ({
      online,
      browserOnline: browserOnlineState,
      apiReachable: apiReachableState,
      checking,
      lastSyncedAt,
      hasBackup,
      backupError,
      retryConnection,
      syncNow,
    }),
    [
      online,
      browserOnlineState,
      apiReachableState,
      checking,
      lastSyncedAt,
      hasBackup,
      backupError,
      retryConnection,
      syncNow,
    ],
  )

  return <OfflineContext.Provider value={value}>{children}</OfflineContext.Provider>
}

export function useOffline(): OfflineContextValue {
  const context = useContext(OfflineContext)
  if (!context) throw new Error('useOffline must be used within OfflineProvider')
  return context
}
