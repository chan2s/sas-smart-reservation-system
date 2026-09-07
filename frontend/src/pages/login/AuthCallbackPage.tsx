import { useEffect } from 'react'
import { CalendarDays } from 'lucide-react'
import { Spinner } from '@/components/ui/Misc'

/**
 * Landing point of the Google OAuth flow. The backend redirects here with
 * the SAS RESERVE JWT pair in the URL fragment. The AuthProvider bootstrap
 * consumes the fragment on mount; this page only shows progress while the
 * session is established, then the router takes over.
 */
export function AuthCallbackPage() {
  // Fallback: if the session never materializes, go to login with a
  // friendly error instead of leaving the user on a spinner.
  useEffect(() => {
    const timer = setTimeout(() => {
      window.location.replace('/login?google_error=token_exchange_failed')
    }, 4000)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-soft">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-brand text-white shadow-card-hover">
        <CalendarDays className="size-6" aria-hidden />
      </div>
      <p className="text-sm text-body">Completing Google sign-in…</p>
      <Spinner />
    </div>
  )
}
