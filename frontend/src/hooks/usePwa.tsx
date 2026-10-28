import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { useToast } from '@/components/ui/Toast'
import {
  dismissInstall as dismissInstallStore,
  dismissIosInstructions as dismissIosInstructionsStore,
  getInstallSnapshot,
  promptInstall as triggerInstallPrompt,
  subscribeInstall,
} from '@/lib/pwa/install'

/** What the user chose in the browser's install dialog, or that none was open. */
export type InstallOutcome = 'accepted' | 'dismissed' | 'unavailable'

interface PwaContextValue {
  /** The shell has been precached and can open offline. */
  offlineReady: boolean
  /** A new service worker is waiting; the user chooses when to update. */
  updateAvailable: boolean
  acceptUpdate: () => void
  dismissUpdate: () => void
  /** A native install prompt is available and the polite invitation may show. */
  canInstall: boolean
  /** A native install prompt is available, even after an earlier "not now". */
  promptAvailable: boolean
  /** The native prompt was opened and closed unused in this session. */
  promptDismissed: boolean
  installDismissed: boolean
  isInstalled: boolean
  /** An iOS/iPadOS device: manual "Add to Home Screen" instructions apply. */
  canShowIosInstructions: boolean
  promptInstall: () => Promise<InstallOutcome>
  dismissInstall: () => void
  dismissIosInstructions: () => void
}

const PwaContext = createContext<PwaContextValue | null>(null)

/**
 * PWA runtime state: service-worker lifecycle + install availability.
 *
 * The service worker is registered here (with `registerType: 'prompt'`), so an
 * update is offered to the user rather than forced — an auto-reload must never
 * interrupt an in-progress reservation workflow.
 */
export function PwaProvider({ children }: { children: ReactNode }) {
  const { toast } = useToast()
  const install = useSyncExternalStore(subscribeInstall, getInstallSnapshot, getInstallSnapshot)

  const {
    offlineReady: [offlineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    immediate: true,
    onRegisterError: (error) => {
      // A failed registration must never take the app down; it only means the
      // enhanced offline shell is unavailable.
      console.warn('[pwa] service worker registration failed', error)
    },
  })

  useEffect(() => {
    // The dev service worker registers without precaching anything, so the
    // "opens offline" claim is only true for production builds.
    if (offlineReady && !import.meta.env.DEV) {
      toast('SAS RESERVE is ready to open without a connection.', 'info')
    }
  }, [offlineReady, toast])

  const acceptUpdate = useCallback(() => {
    void updateServiceWorker()
  }, [updateServiceWorker])

  const dismissUpdate = useCallback(() => setNeedRefresh(false), [setNeedRefresh])

  const promptInstall = useCallback(async () => {
    const outcome = await triggerInstallPrompt()
    if (outcome === 'accepted') toast('Installing SAS RESERVE…', 'success')
    return outcome
  }, [toast])

  const value = useMemo<PwaContextValue>(
    () => ({
      offlineReady,
      updateAvailable: needRefresh,
      acceptUpdate,
      dismissUpdate,
      canInstall: install.canPrompt,
      promptAvailable: install.promptAvailable,
      promptDismissed: install.promptDismissed,
      installDismissed: install.dismissed,
      isInstalled: install.installed,
      canShowIosInstructions: install.canShowIosInstructions,
      promptInstall,
      dismissInstall: dismissInstallStore,
      dismissIosInstructions: dismissIosInstructionsStore,
    }),
    [offlineReady, needRefresh, acceptUpdate, dismissUpdate, install, promptInstall],
  )

  return <PwaContext.Provider value={value}>{children}</PwaContext.Provider>
}

export function usePwa(): PwaContextValue {
  const context = useContext(PwaContext)
  if (!context) throw new Error('usePwa must be used within PwaProvider')
  return context
}
