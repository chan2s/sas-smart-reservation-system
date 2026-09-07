import { Link, Navigate, useLocation } from 'react-router-dom'
import {
  ArrowRight,
  Building2,
  CalendarCheck2,
  Search,
  UserRound,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { PublicShell } from '@/components/layout/PublicShell'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Misc'

/**
 * Public reservation entry point: choose between the authenticated campus
 * flow and the no-account external requester flow. Both eventually use the
 * same shared reservation workflow — only requester identity differs.
 */
export function ReserveEntryPage() {
  const { user, loading } = useAuth()
  const location = useLocation()

  // Authenticated campus users (non-admin) go straight into the wizard —
  // their requester identity is already known.
  if (!loading && user && user.role === 'REQUESTER') {
    return <Navigate to="/reservations/new" state={{ from: location }} replace />
  }

  return (
    <PublicShell>
      <div className="mx-auto max-w-3xl">
        <div className="text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            SAS Reserve
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Reserve a Facility
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-[15px] text-body">
            Book SAS facilities and resources for your event. Choose the option
            that describes you — both paths use the same reservation process.
          </p>
        </div>

        {loading ? (
          <div className="mt-12 flex justify-center">
            <Spinner />
          </div>
        ) : (
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            <Card className="flex flex-col p-6">
              <span className="flex size-11 items-center justify-center rounded-xl bg-brand-soft text-brand">
                <UserRound className="size-5" aria-hidden />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-ink">Campus User</h2>
              <p className="mt-1.5 flex-1 text-sm text-body">
                Sign in to manage your reservations, track approval status, and
                check in when your event starts.
              </p>
              <ul className="mt-4 space-y-1.5 text-[13px] text-body">
                <li className="flex items-center gap-2">
                  <CalendarCheck2 className="size-3.5 text-brand" aria-hidden />
                  Your requesters details filled in automatically
                </li>
                <li className="flex items-center gap-2">
                  <CalendarCheck2 className="size-3.5 text-brand" aria-hidden />
                  Reservation history and status tracking
                </li>
              </ul>
              <Link to="/login" className="mt-6">
                <Button className="w-full">
                  Sign in to reserve <ArrowRight className="size-4" />
                </Button>
              </Link>
            </Card>

            <Card className="flex flex-col p-6">
              <span className="flex size-11 items-center justify-center rounded-xl bg-brand-soft text-brand">
                <Building2 className="size-5" aria-hidden />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-ink">External Organization</h2>
              <p className="mt-1.5 flex-1 text-sm text-body">
                Reserve without creating an account. Perfect for schools,
                companies, government offices, and community groups.
              </p>
              <ul className="mt-4 space-y-1.5 text-[13px] text-body">
                <li className="flex items-center gap-2">
                  <Search className="size-3.5 text-brand" aria-hidden />
                  No username or password required
                </li>
                <li className="flex items-center gap-2">
                  <Search className="size-3.5 text-brand" aria-hidden />
                  Track your request with code + email
                </li>
              </ul>
              <Link to="/reserve/guest" className="mt-6">
                <Button variant="secondary" className="w-full">
                  Continue as guest <ArrowRight className="size-4" />
                </Button>
              </Link>
            </Card>
          </div>
        )}

        <div className="mt-10 flex justify-center">
          <Link
            to="/track-reservation"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand transition-colors hover:text-brand-dark"
          >
            <Search className="size-4" aria-hidden />
            Already submitted? Track your reservation
          </Link>
        </div>
      </div>
    </PublicShell>
  )
}
