import { Link } from 'react-router-dom'
import { Brand } from '@/components/layout/Header'
import { Backdrop } from '@/components/decor/Backdrop'

/**
 * Minimal public chrome for the external requester pages: brand header and
 * footer with no app navigation or authenticated controls.
 */
export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen bg-soft">
      <Backdrop />
      <header className="relative z-10 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-[72px] w-full max-w-5xl items-center justify-between px-4 sm:px-6">
          <Link to="/reserve">
            <Brand />
          </Link>
          <nav className="flex items-center gap-5">
            <Link
              to="/reserve"
              className="text-sm font-medium text-body transition-colors hover:text-ink"
            >
              Reserve
            </Link>
            <Link
              to="/track-reservation"
              className="text-sm font-medium text-brand transition-colors hover:text-brand-dark"
            >
              Track reservation
            </Link>
          </nav>
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
