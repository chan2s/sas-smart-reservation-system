import { useState } from 'react'
import { CheckCircle2, Download, Share } from 'lucide-react'
import { usePwa } from '@/hooks/usePwa'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { cn } from '@/lib/utils'

/** The installable app icon ships in public/ and is precached with the shell. */
const APP_ICON_SRC = '/pwa-192x192.png'

export const INSTALL_DESCRIPTION =
  'Install SAS RESERVE on your device for quicker access and an app-like experience.'

/**
 * "Install SAS RESERVE App" section for the user's Settings page.
 *
 * The floating invitation in {@link PwaNotices} is polite: it disappears for
 * seven days once dismissed. This is the explicit, always-available counterpart
 * — a user who opens Settings is asking to install, so it ignores the dismissal
 * cooldown and instead reports exactly where installation stands:
 *
 * * installed (standalone or `appinstalled`) — status only, never a button,
 * * a deferred `beforeinstallprompt` is held — the real install button,
 * * iOS/iPadOS (WebKit never fires the event) — Share → "Add to Home Screen",
 * * anything else — the browser-menu route, plainly labelled as such,
 * * the prompt was cancelled — how to try again.
 */
export function InstallAppSection({ className }: { className?: string }) {
  const { promptAvailable, promptDismissed, isInstalled, canShowIosInstructions, promptInstall } =
    usePwa()
  const [working, setWorking] = useState(false)

  // beforeinstallprompt events are single-use. The store drops the event as
  // soon as it is invoked, then publishes a fresh available event if the
  // browser offers another later in this session.
  const showPrompt = promptAvailable
  const promptClosed = promptDismissed

  async function install() {
    setWorking(true)
    try {
      await promptInstall()
    } catch {
      // A refused or crashed prompt must never break the Settings page.
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card className={cn('mt-6', className)}>
      <div className="flex items-start gap-4">
        <img
          src={APP_ICON_SRC}
          alt=""
          aria-hidden
          width={48}
          height={48}
          className="size-12 shrink-0 rounded-xl border border-line"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[17px] font-semibold text-ink">Install SAS RESERVE App</h2>
            {isInstalled && (
              <Badge tone="emerald">
                <CheckCircle2 className="size-3.5" aria-hidden />
                Installed
              </Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-body">{INSTALL_DESCRIPTION}</p>
        </div>
      </div>

      <div
        aria-live="polite"
        className="mt-5 rounded-xl border border-line bg-soft/60 p-4 text-sm text-body"
      >
        {isInstalled ? (
          <div className="flex items-start gap-2.5">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-status-available" aria-hidden />
            <div>
              <p className="font-medium text-ink">SAS RESERVE is installed on this device.</p>
              <p className="mt-0.5 text-xs text-muted">
                Open it from your home screen, dock, or app list — no browser address bar needed.
              </p>
            </div>
          </div>
        ) : showPrompt ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="min-w-0">
              Add SAS RESERVE to your home screen or desktop for one-tap access.
            </p>
            <Button
              className="shrink-0 self-start sm:self-auto"
              onClick={() => void install()}
              loading={working}
              icon={<Download className="size-4" aria-hidden />}
            >
              Install App
            </Button>
          </div>
        ) : canShowIosInstructions ? (
          <div>
            <p className="flex items-center gap-1.5 font-medium text-ink">
              <Share className="size-4 shrink-0 text-brand" aria-hidden />
              Add SAS RESERVE to your Home Screen
            </p>
            <p className="mt-0.5 text-xs text-muted">
              Safari on iPhone and iPad installs web apps from the Share menu.
            </p>
            <ol className="mt-2.5 list-decimal space-y-1 pl-4 text-xs text-body">
              <li>Tap the Share button in Safari&apos;s toolbar.</li>
              <li>Scroll the share sheet and choose &ldquo;Add to Home Screen&rdquo;.</li>
              <li>Tap &ldquo;Add&rdquo; to finish. The app icon appears on your Home Screen.</li>
            </ol>
          </div>
        ) : (
          <div>
            <p className="font-medium text-ink">
              {promptClosed
                ? 'The installation prompt was closed.'
                : 'This browser cannot install the app automatically.'}
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {promptClosed
                ? 'The browser prompt can only be used once. Reload this page to try again if your browser offers a fresh prompt.'
                : 'Installation may still be available through your browser menu — for example “Install app” in Chrome, or Apps → “Install this site as an app” in Edge.'}{' '}
              You can keep using SAS RESERVE in the browser; the app is optional.
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}
