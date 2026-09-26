import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowRight, IdCard, X } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

/**
 * A dismissible nudge for accounts that have never chosen an affiliation.
 *
 * Deliberately non-blocking: existing NORSU users keep working exactly as
 * before (a blank affiliation is treated as a campus user everywhere), so
 * this only invites them to complete the profile — it never gates access.
 */
export function AffiliationPrompt() {
  const { user } = useAuth()
  const location = useLocation()
  const [dismissed, setDismissed] = useState(false)

  if (!user || user.has_affiliation || dismissed) return null
  // The affiliation page itself has the full form — don't nag on top of it.
  if (location.pathname.startsWith('/onboarding/affiliation')) return null

  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-brand/25 bg-brand-soft/50 px-3.5 py-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand text-white">
        <IdCard className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-ink">
          Tell us how you&apos;re affiliated with NORSU
        </p>
        <p className="text-xs text-muted">
          Completing your affiliation keeps your reservations attributed correctly.
        </p>
      </div>
      <Link
        to="/onboarding/affiliation"
        className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-dark"
      >
        Complete profile
        <ArrowRight className="size-3.5" aria-hidden />
      </Link>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="rounded p-1 text-muted transition-colors hover:text-ink"
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  )
}
