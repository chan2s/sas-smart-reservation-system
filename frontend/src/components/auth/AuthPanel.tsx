import { Link } from 'react-router-dom'
import { ArrowLeft, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import sasLogo from '@/assets/sas1.jpg'

/** SAS RESERVE brand lockup (icon + wordmark + descriptor). */
export function BrandMark({
  onDark = false,
  className,
}: {
  onDark?: boolean
  className?: string
}) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <span
        className={cn(
          'flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white p-0.5 shadow-sm sm:size-10',
          !onDark && 'ring-1 ring-line',
        )}
      >
        <img src={sasLogo} alt="SAS Reserve" className="h-full w-full object-contain" />
      </span>
      <span className="leading-tight select-none">
        <span
          className={cn(
            'block text-[15px] font-bold tracking-tight',
            onDark ? 'text-white' : 'text-ink',
          )}
        >
          SAS RESERVE
        </span>
        <span
          className={cn(
            'block text-[9px] font-semibold uppercase tracking-[0.2em]',
            onDark ? 'text-white/60' : 'text-muted',
          )}
        >
          Facility &amp; Resources
        </span>
      </span>
    </span>
  )
}

/** Subtle "← Back to Home" link used at the top of the auth pages. */
export function BackHomeLink({ className }: { className?: string }) {
  return (
    <Link
      to="/"
      className={cn(
        'inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm font-medium text-body',
        'transition-colors hover:bg-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        className,
      )}
    >
      <ArrowLeft className="size-4" aria-hidden />
      Back to Home
    </Link>
  )
}

const DEFAULT_BENEFITS = [
  'Facility reservations',
  'Equipment management',
  'Real-time availability',
]

/**
 * Dark editorial panel that anchors the left side of the auth pages.
 * Echoes the landing hero typography so the whole flow shares one design.
 */
export function AuthVisualPanel({
  headline,
  benefits = DEFAULT_BENEFITS,
  footnote = 'Managed by the SAS Office',
}: {
  headline: string
  benefits?: string[]
  footnote?: string
}) {
  return (
    <aside
      className="relative hidden overflow-hidden bg-navy text-white lg:flex lg:flex-col lg:justify-between"
      aria-label="SAS Reserve overview"
    >
      {/* Decorative washes + grid — kept subtle, aria-hidden */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div className="absolute -right-48 -top-48 size-[560px] rounded-full bg-brand/25 blur-3xl" />
        <div className="absolute -bottom-56 -left-40 size-[480px] rounded-full bg-brand/15 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)',
            backgroundSize: '64px 64px',
          }}
        />
      </div>

      <div className="relative z-10 flex h-full flex-col justify-between p-12 xl:p-16">
        <BrandMark onDark />

        <div className="max-w-md">
          <p className="flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-brand-faint">
            <span className="h-px w-8 bg-brand" aria-hidden />
            Smart Facility Management
          </p>
          <h2 className="mt-5 text-4xl font-bold leading-[1.06] tracking-tight text-white xl:text-[2.75rem]">
            {headline}
          </h2>

          <ul className="mt-8 space-y-2.5">
            {benefits.map((benefit) => (
              <li
                key={benefit}
                className="flex items-center gap-2.5 text-sm text-white/75"
              >
                <span className="flex size-5 items-center justify-center rounded-full bg-white/10">
                  <Check className="size-3 text-brand-faint" aria-hidden />
                </span>
                {benefit}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-white/50">{footnote}</p>
      </div>
    </aside>
  )
}