import { Lock, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

/** The one sentence every view-only surface repeats. */
export const VIEW_ONLY_MESSAGE =
  'Your account is pending administrator approval. You currently have view-only access to SAS RESERVE.'

/**
 * Global, non-blocking banner for a not-approved account.
 *
 * Rendered once in the app shell so it appears on every authenticated page.
 * Purely informational: the backend refuses each prohibited action with a
 * 403, so this is a usability aid, never the enforcement point.
 */
export function ViewOnlyBanner({ className }: { className?: string }) {
  return (
    <div
      role="status"
      className={cn(
        'flex items-start gap-3 rounded-2xl border border-status-pending/30 bg-status-pending-bg px-4 py-3.5 text-status-pending',
        className,
      )}
    >
      <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0">
        <p className="text-sm font-semibold">View-only access</p>
        <p className="mt-0.5 text-[13px] leading-relaxed opacity-90">
          {VIEW_ONLY_MESSAGE}
        </p>
      </div>
    </div>
  )
}

/**
 * Inline notice shown where a specific action is unavailable to a
 * not-approved account (an alternative to hiding the whole form).
 */
export function ViewOnlyNotice({
  action,
  className,
}: {
  action?: string
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2.5 rounded-xl border border-status-pending/30 bg-status-pending-bg px-3.5 py-3 text-[13px] text-status-pending',
        className,
      )}
    >
      <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0">
        <span className="font-semibold">Action unavailable.</span>{' '}
        {action ?? 'You cannot perform this action'} while your account is
        pending administrator approval.
      </p>
    </div>
  )
}

/**
 * Full-page access-denied view for a prohibited route a not-approved account
 * reached directly (for example by typing ``/reservations/new``).
 */
export function ViewOnlyAccessDenied({ title }: { title: string }) {
  return (
    <div className="mx-auto max-w-lg">
      <div className="flex flex-col items-center rounded-2xl border border-line bg-surface px-6 py-12 text-center shadow-sm">
        <span className="flex size-12 items-center justify-center rounded-full bg-status-pending-bg text-status-pending">
          <Lock className="size-6" aria-hidden />
        </span>
        <h1 className="mt-4 text-xl font-bold tracking-tight text-ink">
          {title} is unavailable
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-body">
          {VIEW_ONLY_MESSAGE}
        </p>
        <Link
          to="/dashboard"
          className="mt-6 inline-flex items-center rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-brand-dark focus-ring"
        >
          Back to dashboard
        </Link>
      </div>
    </div>
  )
}
