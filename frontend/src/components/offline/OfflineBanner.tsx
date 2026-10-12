import { Link } from 'react-router-dom'
import { CloudOff, Database, RefreshCw, WifiOff } from 'lucide-react'
import { useOffline } from '@/hooks/useOffline'
import { formatDateTime } from '@/lib/utils'

/**
 * Persistent, unobtrusive connectivity banner.
 *
 * Rendered once in the app shells (never per-route) so it cannot duplicate as
 * the user navigates. It is intentionally informational: the app stays usable,
 * but every server-dependent action is blocked elsewhere.
 */
export function OfflineBanner() {
  const { online, browserOnline, checking, lastSyncedAt, hasBackup, backupError, retryConnection } =
    useOffline()

  if (online) return null

  const heading = browserOnline
    ? "Can't reach SAS RESERVE — showing saved information."
    : "You're offline — showing saved information."

  const backupLabel = hasBackup && lastSyncedAt
    ? `Local backup · Updated ${formatDateTime(lastSyncedAt)}`
    : 'No saved information on this device yet.'

  return (
    <div
      role="status"
      aria-live="polite"
      className="border-b border-status-pending/30 bg-status-pending-bg"
    >
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-2 px-4 py-2.5 sm:flex-row sm:items-center sm:gap-4 sm:px-6 lg:px-10">
        <div className="flex min-w-0 items-start gap-2.5 sm:items-center">
          <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-status-pending/15 text-status-pending sm:mt-0">
            {browserOnline ? <CloudOff className="size-4" /> : <WifiOff className="size-4" />}
          </span>
          <div className="min-w-0">
            <p className="text-[13.5px] font-semibold text-ink">{heading}</p>
            <p className="flex items-center gap-1.5 text-xs text-body">
              <Database className="size-3.5 shrink-0 text-muted" aria-hidden />
              <span className="truncate">{backupLabel}</span>
            </p>
            {backupError && (
              <p className="mt-0.5 text-xs text-status-rejected">
                Backup not updated: {backupError}
              </p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:ml-auto">
          <Link
            to="/offline"
            className="inline-flex h-8 items-center rounded-lg border border-line bg-surface px-3 text-[13px] font-medium text-ink transition-colors hover:border-line-strong"
          >
            View saved info
          </Link>
          <button
            type="button"
            onClick={() => void retryConnection()}
            disabled={checking}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand px-3 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            <RefreshCw className={checking ? 'size-3.5 animate-spin' : 'size-3.5'} aria-hidden />
            {checking ? 'Checking…' : 'Retry'}
          </button>
        </div>
      </div>
    </div>
  )
}
