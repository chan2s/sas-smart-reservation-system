import { Link } from 'react-router-dom'
import type { Facility } from '@/lib/types'
import {
  Building2,
  CalendarCheck,
  CheckCircle2,
  Clock,
  Database,
  Users,
  ArrowRight,
  ChevronRight,
  Video,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { useFacilities } from '@/hooks/queries'
import { useEquipmentCategories } from '@/hooks/queries'
import { useEquipmentStats } from '@/hooks/queries'
import { getEquipmentImageUrl } from '@/lib/utils'
import { cn } from '@/lib/utils'
import heroVideo from '@/assets/0625.mp4'

function LandingButton({
  variant = 'primary',
  size = 'md',
  href,
  className,
  children,
}: {
  variant?: 'primary' | 'secondary'
  size?: 'sm' | 'md' | 'lg'
  href: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <a
      href={href}
      className={cn(
        'inline-flex items-center justify-center font-medium whitespace-nowrap transition-colors duration-150',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        variant === 'primary'
          ? 'bg-brand text-white hover:bg-brand-dark shadow-lg'
          : 'border border-line bg-surface hover:bg-soft',
        size === 'lg' && 'h-11 px-5 text-sm gap-2 rounded-lg',
        className,
      )}
    >
      {children}
    </a>
  )
}

export function LandingPage() {
  const { data: facilities, isLoading: facilitiesLoading } = useFacilities()
  const { data: categories } = useEquipmentCategories()
  const { data: stats } = useEquipmentStats()

  const activeFacilities = (facilities ?? []).filter((facility) => facility.is_active)

  return (
    <div className="relative min-h-screen bg-soft pb-12">
      {/* Hero */}
      <section className="relative min-h-[85vh] overflow-hidden" aria-label="Introduction">
        {/* Video */}
        <div className="absolute inset-0 overflow-hidden rounded-none" aria-hidden>
          <video
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            className="h-full w-full object-cover"
          >
            <source src={heroVideo} type="video/mp4" />
          </video>
          {/* Gradient fallback when video cannot load */}
          <div className="absolute inset-0 bg-ink/60" />
        </div>

        {/* Dark translucent overlay with left-to-right gradient */}
        <div
          className="absolute inset-0 bg-gradient-to-r from-ink/80 via-ink/50 to-transparent"
          aria-hidden
        />

        {/* Nav */}
        <nav className="absolute inset-x-0 top-0 z-20 border-b border-white/10 bg-ink/40 backdrop-blur-lg" aria-label="Primary">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
            <Link to="/" className="flex items-center gap-2.5 focus-ring rounded-lg bg-white/10 px-3 py-1.5 hover:bg-white/20">
              <div className="flex size-9 items-center justify-center rounded-xl bg-brand text-white shadow-sm">
                <Video className="size-5" aria-hidden />
              </div>
              <span className="leading-tight select-none">
                <span className="block text-sm font-bold tracking-tight text-white">SAS RESERVE</span>
                <span className="block text-[10px] font-medium uppercase tracking-[0.14em] text-white/70">Facility &amp; Resources</span>
              </span>
            </Link>

            <div className="hidden items-center gap-6 sm:flex">
              <span className="text-sm font-medium text-white/90">Overview</span>
              <span className="text-sm font-medium text-white/90">Facilities</span>
              <span className="text-sm font-medium text-white/90">Equipment</span>
              <span className="text-sm font-medium text-white/90">About</span>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/login"
                className="rounded-lg px-3.5 py-2 text-sm font-medium text-white/90 transition-colors hover:bg-white/10"
              >
                Log In
              </Link>
              <Link
                to="/register"
                className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                Create Account
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          </div>
        </nav>

        {/* Hero text */}
        <div className="relative z-10 mx-auto max-w-6xl px-5 pt-28 sm:pt-32">
          <div className="max-w-2xl">
            <p className="animate-fade-up text-[11px] font-semibold uppercase tracking-[0.16em] text-brand">
              Smart Facility Management
            </p>
            <h1 className="animate-fade-up mt-4 text-4xl font-bold tracking-tight text-white sm:text-5xl lg:text-6xl">
              Reserve spaces.
              <br />
              Manage resources.
              <br />
              Simplify events.
            </h1>
            <p className="animate-fade-up mt-5 text-lg leading-relaxed text-white/80 sm:text-xl">
              Plan and manage campus events with a centralized reservation system for facilities, equipment, and shared resources.
            </p>

            <div className="animate-fade-up mt-8 flex flex-wrap gap-4 sm:gap-5">
              <LandingButton
                variant="primary"
                size="lg"
                href="/register"
                className="shadow-lg"
              >
                Create an Account
                <ArrowRight className="size-4" aria-hidden />
              </LandingButton>
              <LandingButton
                variant="secondary"
                size="lg"
                href="#facilities"
              >
                Explore Facilities
                <ChevronRight className="size-4" aria-hidden />
              </LandingButton>
            </div>

            <p className="animate-fade-up mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-white/70">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="size-4 text-brand" aria-hidden />
                Facility reservations
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="size-4 text-brand" aria-hidden />
                Equipment management
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="size-4 text-brand" aria-hidden />
                Real-time availability
              </span>
            </p>
          </div>
        </div>
      </section>

      {/* Stats / quick access */}
      <section className="relative bg-white border-y border-line" aria-label="What SAS Reserve manages">
        <div className="mx-auto max-w-6xl px-5 py-12 sm:py-16">
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              eyebrow="Manage"
              title="Facilities"
              description="Reserve campus spaces for events and activities."
              icon={<Building2 className="size-6 text-brand" aria-hidden />}
            />
            <StatCard
              eyebrow="Request"
              title="Equipment"
              description="Request shared equipment and resources."
              icon={<Database className="size-6 text-brand" aria-hidden />}
            />
            <StatCard
              eyebrow="Track"
              title="Reservations"
              description="Track and manage your reservations."
              icon={<CalendarCheck className="size-6 text-brand" aria-hidden />}
            />
            <StatCard
              eyebrow="See"
              title="Availability"
              description="View schedules and resource availability."
              icon={<Clock className="size-6 text-brand" aria-hidden />}
            />
          </div>
        </div>
      </section>

      {/* Facilities */}
      <section id="facilities" className="relative bg-soft py-20 sm:py-24" aria-labelledby="facilities-heading">
        <div className="mx-auto max-w-6xl px-5">
          <div className="mb-12 text-center sm:text-left">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand">Spaces</p>
            <h2 id="facilities-heading" className="mt-3 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
              Everything you need for your next event
            </h2>
            <p className="mt-3 max-w-xl text-body sm:mx-0">
              Explore the campus spaces available for reservation. View details and check availability before you create an account.
            </p>
          </div>

          {facilitiesLoading ? (
            <FacilityGridSkeleton />
          ) : activeFacilities.length === 0 ? (
            <p className="text-center text-sm text-muted">No facilities are published yet.</p>
          ) : (
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {activeFacilities.slice(0, 6).map((facility) => (
                <FacilityCard key={facility.id} facility={facility} />
              ))}
            </div>
          )}          <div className="mt-10 text-center">
            <LandingButton
              variant="secondary"
              size="lg"
              href="/facilities"
            >
              View all facilities
              <ArrowRight className="size-4" aria-hidden />
            </LandingButton>
          </div>
        </div>
      </section>

      {/* Equipment */}
      <section id="equipment" className="relative bg-white py-20 sm:py-24" aria-labelledby="equipment-heading">
        <div className="mx-auto max-w-6xl px-5">
          <div className="mb-12 text-center sm:text-left">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand">Resources</p>
            <h2 id="equipment-heading" className="mt-3 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
              Equipment inventory
            </h2>
            <p className="mt-3 max-w-xl text-body sm:mx-0">
              From sound systems to tables and chairs, reserve the resources you need from a single inventory.
            </p>
          </div>

          {stats ? (
            <div className="mb-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <EquipmentStatCard
                label="Equipment Types"
                value={stats.equipment_types}
                accent="text-brand"
                icon={<Database className="size-6" aria-hidden />}
              />
              <EquipmentStatCard
                label="Total Units"
                value={stats.total_units}
                accent="text-ink"
                icon={<Users className="size-6" aria-hidden />}
              />
              <EquipmentStatCard
                label="Available Now"
                value={stats.available_units}
                accent="text-status-available"
                icon={<CheckCircle2 className="size-6" aria-hidden />}
              />
              <EquipmentStatCard
                label="Reserved"
                value={stats.reserved_units}
                accent="text-status-approved"
                icon={<CalendarCheck className="size-6" aria-hidden />}
              />
            </div>
          ) : null}

          {categories && categories.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {categories.slice(0, 6).map((category) => (
                <EquipmentCategoryCard key={category.id} category={category} />
              ))}
            </div>
          ) : (
            <p className="text-center text-sm text-muted">Equipment categories are not configured yet.</p>
          )}

          <div className="mt-10 text-center">
            <LandingButton
              variant="secondary"
              size="lg"
              href="/equipment"
            >
              Browse equipment
              <ArrowRight className="size-4" aria-hidden />
            </LandingButton>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="relative bg-soft py-20 sm:py-24" aria-labelledby="how-heading">
        <div className="mx-auto max-w-6xl px-5">
          <div className="mb-14 text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand">Process</p>
            <h2 id="how-heading" className="mt-3 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
              How it works
            </h2>
            <p className="mt-3 max-w-xl mx-auto text-body">
              Three simple steps to reserve a facility and the resources you need.
            </p>
          </div>

          <ol className="grid gap-8 md:grid-cols-3">
            <HowCard
              number="01"
              title="Create your account"
              description="Sign up and sign in to access the reservation system. All reservations require an account."
            />
            <HowCard
              number="02"
              title="Choose a facility and resources"
              description="Browse facilities and equipment, then pick the combination that fits your event."
            />
            <HowCard
              number="03"
              title="Submit and track your reservation"
              description="Submit your request and track its status until the event is complete."
            />
          </ol>
        </div>
      </section>

      {/* CTA */}
      <section className="relative bg-ink py-20 sm:py-24" aria-labelledby="cta-heading">
        <div className="mx-auto max-w-3xl px-5 text-center">
          <h2 id="cta-heading" className="mx-auto text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Ready to plan your next event?
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-white/80">
            Reserve campus facilities and shared resources from one centralized system.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <Link
              to="/register"
              className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              Create Account
              <ArrowRight className="size-4" aria-hidden />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 rounded-lg border border-white/20 px-5 py-2.5 text-sm font-medium text-white/90 transition-colors hover:bg-white/10"
            >
              Sign In
            </Link>
          </div>
          <p className="mt-6 text-xs text-white/60">
            Reservations require an account. There is no guest reservation option.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line bg-soft py-10" aria-label="Site footer">
        <div className="mx-auto max-w-6xl px-5">
          <div className="grid gap-8 md:grid-cols-4">
            <div className="md:col-span-2">
              <div className="flex items-center gap-2.5">
                <div className="flex size-9 items-center justify-center rounded-xl bg-brand text-white shadow-sm">
                  <Video className="size-5" aria-hidden />
                </div>
                <span className="leading-tight">
                  <span className="block text-base font-bold tracking-tight text-ink">SAS RESERVE</span>
                  <span className="block text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
                    Smart Facility &amp; Resource Reservation System
                  </span>
                </span>
              </div>
              <p className="mt-4 max-w-sm text-sm text-body">
                A centralized reservation system for campus facilities, equipment, and shared resources.
              </p>
            </div>

            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Platform</p>
              <ul className="mt-3 space-y-2 text-sm">
                <li><a href="/#facilities" className="text-body hover:text-ink">Facilities</a></li>
                <li><a href="/#equipment" className="text-body hover:text-ink">Equipment</a></li>
                <li><a href="/login" className="text-body hover:text-ink">Sign In</a></li>
                <li><a href="/register" className="text-body hover:text-ink">Create Account</a></li>
              </ul>
            </div>

            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Account</p>
              <ul className="mt-3 space-y-2 text-sm">
                <li><a href="/login" className="text-body hover:text-ink">Sign In</a></li>
                <li><a href="/register" className="text-body hover:text-ink">Create Account</a></li>
              </ul>
            </div>
          </div>

          <div className="mt-10 border-t border-line pt-6 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
            <p>© {new Date().getFullYear()} SAS RESERVE. Managed by the SAS Office.</p>
            <p className="flex items-center gap-1.5">
              <CheckCircle2 className="size-3.5 text-status-available" aria-hidden />
              Account required for reservations
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

function StatCard({
  eyebrow,
  title,
  description,
  icon,
}: {
  eyebrow: string
  title: string
  description: string
  icon: React.ReactNode
}) {
  return (
    <Card className="card p-6 sm:p-7">
      <div className="text-brand">{icon}</div>
      <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">{eyebrow}</p>
      <h3 className="mt-1 text-xl font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm text-body">{description}</p>
    </Card>
  )
}

function FacilityGridSkeleton() {
  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="card overflow-hidden">
          <div className="skeleton h-44 w-full rounded-none" aria-hidden />
          <div className="space-y-3 p-5">
            <div className="skeleton h-5 w-2/5" aria-hidden />
            <div className="skeleton h-3 w-4/5" aria-hidden />
            <div className="skeleton h-10 w-full" aria-hidden />
          </div>
        </div>
      ))}
    </div>
  )
}

function FacilityCard({ facility }: { facility: Facility }) {
  const imageUrl = facility.image ? getEquipmentImageUrl(facility.image) : null
  const operational = facility.status === 'OPERATIONAL'

  return (
    <article className="card card-hover overflow-hidden">
      {/* Image */}
      <div className="relative h-44">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center rounded-none bg-soft text-muted">
            <Building2 className="size-10" aria-hidden />
          </div>
        )}
        <div className="absolute left-4 top-4">
          <Badge tone={operational ? 'emerald' : 'orange'}>
            {operational ? 'Available' : 'Under maintenance'}
          </Badge>
        </div>
      </div>

      <div className="p-5">
        <h3 className="text-lg font-semibold text-ink">{facility.name}</h3>
        <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-body">{facility.description}</p>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
          <div className="flex items-center gap-2 text-body">
            <Users className="size-4 text-muted" aria-hidden />
            <span>
              <span className="font-medium text-ink">{facility.capacity}</span> capacity
            </span>
          </div>
          <div className="flex items-center gap-2 text-body">
            <Building2 className="size-4 text-muted" aria-hidden />
            <span className="truncate">{facility.location || '—'}</span>
          </div>
        </dl>

        <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
          <Link
            to={`/facilities/${facility.id}`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand transition-colors hover:text-brand-dark"
          >
            View Facility
            <ArrowRight className="size-4" aria-hidden />
          </Link>
          {operational && (
            <span className="flex items-center gap-1.5 text-xs text-status-available">
              <CheckCircle2 className="size-3.5" aria-hidden />
              Open for reservations
            </span>
          )}
        </div>
      </div>
    </article>
  )
}

function EquipmentStatCard({
  label,
  value,
  accent,
  icon,
}: {
  label: string
  value: number
  accent: string
  icon: React.ReactNode
}) {
  return (
    <Card className="flex items-center gap-4 p-4">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
        {icon}
      </span>
      <div>
        <p className={cn('text-2xl font-semibold leading-none tabular-nums', accent)}>{value}</p>
        <p className="mt-1 truncate text-xs text-muted">{label}</p>
      </div>
    </Card>
  )
}

function EquipmentCategoryCard({ category }: { category: NonNullable<ReturnType<typeof useEquipmentCategories>['data']>[number] }) {
  return (
    <Link
      to="/equipment"
      className="card card-hover p-5"
    >
      <div className="flex items-center gap-4">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
          {category.icon ? <span className="size-5" dangerouslySetInnerHTML={{ __html: category.icon }} /> : <Database className="size-5" aria-hidden />}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{category.name}</p>
          <p className="mt-1 truncate text-xs text-body">{category.description || 'Equipment available for reservation'}</p>
        </div>
        <ArrowRight className="ml-auto size-4 shrink-0 text-muted" aria-hidden />
      </div>
    </Link>
  )
}

function HowCard({
  number,
  title,
  description,
}: {
  number: string
  title: string
  description: string
}) {
  return (
    <Card className="card p-6 sm:p-7 text-center">
      <span className="text-3xl font-bold text-brand tracking-tight">{number}</span>
      <h3 className="mt-4 text-lg font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm text-body">{description}</p>
    </Card>
  )
}
