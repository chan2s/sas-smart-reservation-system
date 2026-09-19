import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { CalendarDays } from 'lucide-react'
import { Spinner } from '@/components/ui/Misc'
import { useAuth } from '@/hooks/useAuth'

/**
 * Landing point of the Google OAuth flow. The backend redirects here with
 * the SAS RESERVE JWT pair in the URL fragment. The AuthProvider bootstrap
 * consumes the fragment on mount and loads the authenticated user; this page
 * shows progress and then routes to the correct dashboard for the user's
 * existing role (requesters and staff both land on /dashboard, which renders
 * role-scoped content; staff additionally get Analytics in the nav).
 */
export function AuthCallbackPage() {
  const navigate = useNavigate()
  const { user, loading } = useAuth()

  // Once the OAuth session materializes, route to the role-aware dashboard.
  useEffect(() => {
    if (!loading && user) {
      // Both roles use /dashboard; the dashboard renders role-scoped content.
      // Staff see additional Analytics nav (see components/layout/navigation.ts).
      navigate('/dashboard', { replace: true })
    }
  }, [loading, user, navigate])

  // Fallback: if the session never materializes, go to login with a
  // friendly error instead of leaving the user on a spinner.
  useEffect(() => {
    const timer = setTimeout(() => {
      window.location.replace('/login?google_error=token_exchange_failed')
    }, 8000)
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
