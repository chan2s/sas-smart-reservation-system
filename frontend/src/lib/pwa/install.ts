/**
 * Install-prompt state for the PWA.
 *
 * `beforeinstallprompt` can fire before React mounts, so the listener is
 * attached at module load (this module is imported from main.tsx) and the
 * deferred event is kept in a tiny observable store. Browsers that never fire
 * the event (iOS Safari, Firefox desktop, already-installed) simply leave
 * `canPrompt` false — callers must render nothing rather than a broken button.
 *
 * iOS/iPadOS never fires `beforeinstallprompt` (all iOS browsers use WebKit),
 * but they do support manual "Add to Home Screen". `canShowIosInstructions`
 * marks those devices so the UI can offer concise manual steps instead.
 *
 * A dismissal is remembered in localStorage but only for
 * {@link INSTALL_REPROMPT_AFTER_MS} (seven days): the invite politely goes
 * away, then becomes eligible again after a reasonable period.
 */

const DISMISS_KEY = 'sas_pwa_install_dismissed_at'
/** Pre-cooldown flag written by earlier versions; migrated on load. */
const LEGACY_DISMISS_KEY = 'sas_pwa_install_dismissed'
const IOS_DISMISS_KEY = 'sas_pwa_ios_install_dismissed_at'

/** How long a dismissal suppresses the invitation before it may reappear. */
export const INSTALL_REPROMPT_AFTER_MS = 7 * 24 * 60 * 60 * 1000

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[]
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

export interface InstallSnapshot {
  /** A deferred prompt is available and the user has not recently dismissed it. */
  canPrompt: boolean
  /** The user dismissed the install invitation, and the cooldown has not elapsed. */
  dismissed: boolean
  /** Running as an installed app (standalone), or already installed. */
  installed: boolean
  /** An iOS/iPadOS device that can install manually via Share → Add to Home Screen. */
  canShowIosInstructions: boolean
}

type Listener = () => void

let deferredPrompt: BeforeInstallPromptEvent | null = null
let sessionDismissed = false
let iosSessionDismissed = false
let installed = false
const listeners = new Set<Listener>()

function isStandalone(): boolean {
  if (typeof window === 'undefined') return false
  const standaloneDisplay = window.matchMedia?.('(display-mode: standalone)').matches ?? false
  // iOS Safari exposes navigator.standalone instead of the display-mode media
  // query.
  const iosStandalone = (window.navigator as { standalone?: boolean }).standalone === true
  return standaloneDisplay || iosStandalone
}

/**
 * iOS and iPadOS: every browser there is WebKit-based and never fires
 * `beforeinstallprompt`, but Share → "Add to Home Screen" installs the PWA.
 * The iPadOS check catches iPad Safari, which reports a Mac UA since iPadOS 13.
 */
function isIosDevice(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent
  const ios = /iPad|iPhone|iPod/.test(ua)
  const ipadOs = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1
  return ios || ipadOs
}

function readDismissedAt(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (raw === null) return null
    const value = Number(raw)
    return Number.isFinite(value) ? value : null
  } catch {
    // localStorage can throw in private mode / with cookies blocked — treat as
    // never dismissed rather than crashing.
    return null
  }
}

function writeDismissedAt(key: string): void {
  try {
    window.localStorage.setItem(key, String(Date.now()))
  } catch {
    // Ignore storage failures — the in-memory flag still suppresses this session.
  }
}

/** Migrate the old permanent flag so previously-dismissed users get the 7-day cooldown too. */
function migrateLegacyDismissal(): void {
  try {
    if (window.localStorage.getItem(LEGACY_DISMISS_KEY) === '1') {
      window.localStorage.setItem(DISMISS_KEY, String(Date.now()))
      window.localStorage.removeItem(LEGACY_DISMISS_KEY)
    }
  } catch {
    /* storage unavailable — nothing to migrate */
  }
}

function withinCooldown(key: string, sessionDismissal: boolean): boolean {
  if (sessionDismissal) return true
  const dismissedAt = readDismissedAt(key)
  return dismissedAt !== null && Date.now() - dismissedAt < INSTALL_REPROMPT_AFTER_MS
}

let snapshot: InstallSnapshot = {
  canPrompt: false,
  dismissed: false,
  installed: false,
  canShowIosInstructions: false,
}

function recompute(): void {
  const nowInstalled = installed || isStandalone()
  const dismissed = withinCooldown(DISMISS_KEY, sessionDismissed)
  snapshot = {
    canPrompt: deferredPrompt !== null && !dismissed && !nowInstalled,
    dismissed,
    installed: nowInstalled,
    canShowIosInstructions:
      isIosDevice() && !nowInstalled && !withinCooldown(IOS_DISMISS_KEY, iosSessionDismissed),
  }
}

function emit(): void {
  listeners.forEach((listener) => listener())
}

if (typeof window !== 'undefined') {
  migrateLegacyDismissal()
  installed = isStandalone()
  recompute()

  window.addEventListener('beforeinstallprompt', (event) => {
    // Suppress the browser's mini-infobar; the app shows its own invitation.
    event.preventDefault()
    deferredPrompt = event as BeforeInstallPromptEvent
    recompute()
    emit()
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null
    installed = true
    recompute()
    emit()
  })
}

export function subscribeInstall(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getInstallSnapshot(): InstallSnapshot {
  return snapshot
}

/** Fire the native install prompt. Returns what the user chose. */
export async function promptInstall(): Promise<'accepted' | 'dismissed' | 'unavailable'> {
  if (!deferredPrompt) return 'unavailable'
  const event = deferredPrompt
  deferredPrompt = null
  recompute()
  emit()
  try {
    await event.prompt()
    const choice = await event.userChoice
    if (choice.outcome === 'accepted') installed = true
    recompute()
    emit()
    return choice.outcome
  } catch {
    recompute()
    emit()
    return 'dismissed'
  }
}

/** Remember that the user declined; the invitation stays hidden for seven days. */
export function dismissInstall(): void {
  sessionDismissed = true
  writeDismissedAt(DISMISS_KEY)
  recompute()
  emit()
}

/** Dismiss the iOS manual-installation instructions for seven days. */
export function dismissIosInstructions(): void {
  iosSessionDismissed = true
  writeDismissedAt(IOS_DISMISS_KEY)
  recompute()
  emit()
}
