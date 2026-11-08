import { ArrowRight, Building2, Landmark } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { PublicShell } from '@/components/layout/PublicShell'

export function OrganizationSelectionPage() {
  return (
    <PublicShell>
      <div className="mx-auto max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand">New reservation</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          Choose your organization
        </h1>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-body">
          Select the organization type that best describes your request. Both paths use the same reservation form.
        </p>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <Link to="/reserve/internal" className="group rounded-2xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">
            <Card className="flex h-full min-h-52 flex-col p-6 transition-shadow group-hover:shadow-float">
              <span className="flex size-12 items-center justify-center rounded-2xl bg-brand-soft text-brand">
                <Landmark className="size-6" aria-hidden />
              </span>
              <h2 className="mt-5 text-xl font-semibold text-ink">Internal Organization</h2>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-body">
                For NORSU colleges, offices, departments, and campus units.
              </p>
              <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand">
                Continue <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
              </span>
            </Card>
          </Link>

          <Link to="/reserve/external" className="group rounded-2xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">
            <Card className="flex h-full min-h-52 flex-col p-6 transition-shadow group-hover:shadow-float">
              <span className="flex size-12 items-center justify-center rounded-2xl bg-brand-soft text-brand">
                <Building2 className="size-6" aria-hidden />
              </span>
              <h2 className="mt-5 text-xl font-semibold text-ink">External Organization</h2>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-body">
                For schools, government agencies, businesses, community groups, and individuals.
              </p>
              <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand">
                Continue <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
              </span>
            </Card>
          </Link>
        </div>
      </div>
    </PublicShell>
  )
}
