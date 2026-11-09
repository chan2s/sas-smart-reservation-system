import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { BrandMark } from '@/components/auth/AuthPanel'
import { Backdrop } from '@/components/decor/Backdrop'

/**
 * Minimal public chrome for the external requester pages: brand header and
 * footer with no app navigation or authenticated controls.
 */
export function PublicShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()
  // /reserve and its nested routes (e.g. /reserve/external) are the
  // reservation flow itself, so a link back into it would be redundant.
  const isReservationRoute =
    location.pathname === '/reserve' || location.pathname.startsWith('/reserve/')

  const goBack = () => {
    // React Router marks a direct/tab entry as "default" (and index 0); only
    // then is there no previous internal page to return to.
    const canGoBack =
      location.key !== 'default' && (window.history.state?.idx ?? 0) > 0
    if (canGoBack) {
      navigate(-1)
    } else {
      navigate('/')
    }
  }

  return (
    <div className="relative min-h-screen bg-soft">
      <Backdrop />
      <header className="relative z-10">
        <div className="mx-auto max-w-[1400px] px-3 pt-3 sm:px-6 sm:pt-4">
        <div className="flex h-[64px] w-full items-center justify-between gap-3 rounded-2xl border border-[var(--nav-scrolled-border)] bg-[var(--nav-scrolled-background)] px-4 shadow-float backdrop-blur-lg sm:h-[72px] sm:px-6">
          <Link to="/" className="rounded-lg focus-ring" aria-label="SAS Reserve home">
            <BrandMark onDark />
          </Link>
          <nav aria-label="Primary" className="flex items-center gap-4 sm:gap-7">
            {isReservationRoute ? (
              <button
                type="button"
                onClick={goBack}
                className="relative inline-flex items-center gap-1.5 text-xs font-medium text-white/75 transition-colors hover:text-white sm:text-sm"
              >
                <ArrowLeft className="size-3.5 sm:size-4" aria-hidden />
                Back
              </button>
            ) : (
              <Link
                to="/reserve"
                className="relative text-xs font-medium text-white/75 transition-colors hover:text-white sm:text-sm"
              >
                Reserve
              </Link>
            )}
            <Link
              to="/track-reservation"
              className="relative text-xs font-medium text-white/75 transition-colors hover:text-white sm:text-sm"
            >
              Track reservation
            </Link>
          </nav>
        </div>
        </div>
      </header>
      <main className="relative z-10 mx-auto w-full max-w-5xl px-4 py-10 sm:px-6">{children}</main>
      <footer className="relative z-10 border-t border-line bg-surface py-6">
        <p className="text-center text-xs text-muted">
          Reservations are reviewed by the SAS Office. Submission does not guarantee approval.
        </p>
      </footer>
    </div>
  )
}
