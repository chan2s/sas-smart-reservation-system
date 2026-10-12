import { useEffect, useState, type ReactNode } from 'react'
import { RefreshCw, Share, Sparkles, X } from 'lucide-react'
import { usePwa } from '@/hooks/usePwa'

/** The installable app icon ships in public/ and is precached with the shell. */
const APP_ICON_SRC = '/pwa-192x192.png'

/**
 * Install and iOS cards wait briefly before appearing so they never compete
 * with the initial render, the login form, or an OAuth/OTP redirect.
 */
const NOTICE_DELAY_MS = 1500

/**
 * Floating PWA notices: an install invitation (native prompt, or manual steps
 * on iOS) and a service-worker update prompt. Rendered once per app shell so
 * route changes never duplicate them.
 *
 * Each card degrades to nothing when its capability is unavailable (no
 * `beforeinstallprompt`; no iOS device; no waiting worker), so unsupported
 * browsers simply see no notices. Dismissals are remembered for seven days.
 */
export function PwaNotices() {
  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-4 z-[55] flex flex-col items-start gap-2 sm:inset-x-auto sm:left-4 sm:max-w-sm">
      <UpdateNotice />
      <DelayedAppearance delay={NOTICE_DELAY_MS}>
        <InstallNotice />
        <IosInstallNotice />
      </DelayedAppearance>
    </div>
  )
}

function DelayedAppearance({ delay, children }: { delay: number; children: ReactNode }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setReady(true), delay)
    return () => window.clearTimeout(timer)
  }, [delay])

  if (!ready) return null
  return <>{children}</>
}

function NoticeShell({
  children,
  onDismiss,
}: {
  children: ReactNode
  onDismiss: () => void
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-auto w-full rounded-xl border border-line bg-surface shadow-pop animate-fade-up"
    >
      <div className="flex items-start gap-3 p-3.5">
        <img
          src={APP_ICON_SRC}
          alt="SAS RESERVE app icon"
          width={44}
          height={44}
          className="size-11 shrink-0 rounded-xl border border-line"
        />
        <div className="min-w-0 flex-1">{children}</div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss installation notice"
          className="rounded p-0.5 text-muted transition-colors hover:text-ink focus-ring"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  )
}

function UpdateNotice() {
  const { updateAvailable, acceptUpdate, dismissUpdate } = usePwa()
  if (!updateAvailable) return null
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-auto w-full rounded-xl border border-brand/20 bg-surface p-3.5 shadow-pop animate-fade-up"
    >
      <div className="flex items-start gap-3">
        <Sparkles className="mt-0.5 size-4.5 shrink-0 text-brand" aria-hidden />
        <div className="flex-1">
          <p className="text-sm font-semibold text-ink">A new version is available.</p>
          <p className="mt-0.5 text-xs text-body">
            Reload to update. Your unsaved work stays until you choose to reload.
          </p>
          <div className="mt-2.5 flex items-center gap-2">
            <button
              type="button"
              onClick={acceptUpdate}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand px-3 text-[13px] font-medium text-white transition-opacity hover:opacity-90 focus-ring"
            >
              <RefreshCw className="size-3.5" aria-hidden />
              Reload
            </button>
            <button
              type="button"
              onClick={dismissUpdate}
              className="inline-flex h-8 items-center rounded-lg px-3 text-[13px] font-medium text-body transition-colors hover:bg-soft hover:text-ink focus-ring"
            >
              Later
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={dismissUpdate}
          aria-label="Dismiss update notice"
          className="rounded p-0.5 text-muted transition-colors hover:text-ink focus-ring"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  )
}

function InstallNotice() {
  const { canInstall, isInstalled, promptInstall, dismissInstall } = usePwa()
  const [working, setWorking] = useState(false)
  // `canInstall` already accounts for the installed state; the extra guard
  // keeps the card from ever surfacing for an installed app even if a stale
  // deferred prompt were still held.
  if (!canInstall || isInstalled) return null

  return (
    <NoticeShell onDismiss={dismissInstall}>
      <p className="text-sm font-semibold text-ink">Install SAS RESERVE</p>
      <p className="mt-0.5 text-xs text-body">
        Install SAS RESERVE for quick access from your home screen or desktop.
      </p>
      <div className="mt-2.5 flex items-center gap-2">
        <button
          type="button"
          disabled={working}
          onClick={() => {
            setWorking(true)
            void promptInstall().finally(() => setWorking(false))
          }}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand px-3 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60 focus-ring"
        >
          Install App
        </button>
        <button
          type="button"
          onClick={dismissInstall}
          className="inline-flex h-8 items-center rounded-lg px-3 text-[13px] font-medium text-body transition-colors hover:bg-soft hover:text-ink focus-ring"
        >
          Not now
        </button>
      </div>
    </NoticeShell>
  )
}

function IosInstallNotice() {
  const { canShowIosInstructions, dismissIosInstructions } = usePwa()
  if (!canShowIosInstructions) return null

  return (
    <NoticeShell onDismiss={dismissIosInstructions}>
      <p className="text-sm font-semibold text-ink">Install SAS RESERVE</p>
      <p className="mt-0.5 text-xs text-body">
        Install SAS RESERVE for quick access from your home screen or desktop.
      </p>
      <ol className="mt-2 list-decimal space-y-0.5 pl-4 text-xs text-body">
        <li>Tap the Share button in the browser toolbar.</li>
        <li>Choose &ldquo;Add to Home Screen&rdquo;.</li>
      </ol>
      <div className="mt-2.5 flex items-center gap-2">
        <button
          type="button"
          onClick={dismissIosInstructions}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-[13px] font-medium text-ink transition-colors hover:border-line-strong focus-ring"
        >
          <Share className="size-3.5" aria-hidden />
          Got it
        </button>
      </div>
    </NoticeShell>
  )
}
