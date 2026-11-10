import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, Menu, X } from 'lucide-react'
import { BrandMark } from '@/components/auth/AuthPanel'
import { cn } from '@/lib/utils'

/**
 * One navigation item can point at an in-page section (``id``), an
 * application route (``to``), or a landing section reached from another
 * public page (``href``). The landing page and the About page share this
 * header so both feel like the same site.
 */
export type LandingNavItem = {
  label: string
  id?: string
  to?: string
  href?: string
}

export const LANDING_NAV_ITEMS: LandingNavItem[] = [
  { label: 'Overview', id: 'overview' },
  { label: 'Facilities', id: 'facilities' },
  { label: 'Equipment', id: 'equipment' },
  { label: 'About Us', to: '/about' },
]

export const ABOUT_NAV_ITEMS: LandingNavItem[] = [
  { label: 'Overview', href: '/#overview' },
  { label: 'Facilities', href: '/#facilities' },
  { label: 'Equipment', href: '/#equipment' },
  { label: 'About Us', to: '/about' },
]

function isActive(item: LandingNavItem, activeSection?: string, activeTo?: string) {
  if (item.to) return activeTo === item.to
  if (item.id) return activeSection === item.id
  return false
}

export function LandingNav({
  items = LANDING_NAV_ITEMS,
  activeSection,
  activeTo,
  scrolled,
  onOpenMenu,
}: {
  items?: LandingNavItem[]
  activeSection?: string
  activeTo?: string
  scrolled: boolean
  onOpenMenu: () => void
}) {
  return (
    <header className="fixed inset-x-0 top-0 z-40">
      <div
        className={cn(
          'mx-auto max-w-[1400px] px-4 transition-all duration-300 ease-out sm:px-6',
          scrolled ? 'pt-2' : 'pt-4',
        )}
      >
        <nav
          aria-label="Primary"
          className={cn(
            'flex items-center justify-between gap-3 rounded-2xl border px-4 backdrop-blur-md transition-all duration-300 ease-out sm:px-6',
            scrolled
              ? 'h-16 border-[var(--nav-scrolled-border)] bg-[var(--nav-scrolled-background)] shadow-float backdrop-blur-lg'
              : 'h-[72px] bg-[var(--nav-background-applied)]',
          )}
        >
          <Link
            to="/"
            className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-faint"
            aria-label="SAS Reserve — back to top"
          >
            <BrandMark onDark />
          </Link>

          <div className="hidden items-center gap-8 lg:flex">
            {items.map((item) => {
              const active = isActive(item, activeSection, activeTo)
              const className = cn(
                'relative flex flex-col items-center gap-1 text-sm font-medium transition-colors',
                active
                  ? 'text-[var(--nav-foreground)]'
                  : 'text-[var(--nav-foreground-muted)] hover:text-[var(--nav-foreground)]',
              )
              const underline = (
                <span
                  aria-hidden
                  className={cn(
                    'h-0.5 rounded-full bg-[var(--nav-accent)] transition-all duration-300',
                    active ? 'w-5 opacity-100' : 'w-0 opacity-0',
                  )}
                />
              )

              if (item.to) {
                return (
                  <Link
                    key={item.label}
                    to={item.to}
                    aria-current={active ? 'page' : undefined}
                    className={className}
                  >
                    {item.label}
                    {underline}
                  </Link>
                )
              }

              return (
                <a
                  key={item.label}
                  href={item.href ?? `#${item.id}`}
                  aria-current={active ? 'true' : undefined}
                  className={className}
                >
                  {item.label}
                  {underline}
                </a>
              )
            })}
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2">
            <Link
              to="/login"
              className="hidden rounded-xl px-3.5 py-2 text-sm font-medium text-[var(--nav-foreground-muted)] transition-colors hover:bg-white/10 hover:text-[var(--nav-foreground)] sm:inline-flex"
            >
              Staff/Admin Login
            </Link>
            <Link
              to="/reserve"
              className="hidden h-10 items-center gap-1.5 rounded-full bg-[var(--nav-button-background)] px-4 text-sm font-semibold text-[var(--nav-button-foreground)] shadow-sm transition-colors hover:bg-brand-dark sm:inline-flex"
            >
              Create Reservation
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
            <button
              type="button"
              onClick={onOpenMenu}
              aria-label="Open menu"
              aria-expanded="false"
              className="ml-1 inline-flex size-9 items-center justify-center rounded-xl text-[var(--nav-foreground)] transition-colors hover:bg-white/10 lg:hidden"
            >
              <Menu className="size-5" aria-hidden />
            </button>
          </div>
        </nav>
      </div>
    </header>
  )
}

export function MobileMenu({
  open,
  onClose,
  items = LANDING_NAV_ITEMS,
}: {
  open: boolean
  onClose: () => void
  items?: LandingNavItem[]
}) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 lg:hidden"
      role="dialog"
      aria-modal="true"
      aria-label="Menu"
    >
      <div
        className="absolute inset-0 bg-[var(--nav-background)]/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div className="absolute inset-x-3 top-3 rounded-3xl border border-[var(--nav-border)] bg-[var(--nav-background)] p-6 shadow-float">
        <div className="flex items-center justify-between">
          <BrandMark onDark />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="inline-flex size-9 items-center justify-center rounded-xl text-[var(--nav-foreground)] transition-colors hover:bg-[var(--nav-background)]/10"
          >
            <X className="size-5" aria-hidden />
          </button>
        </div>

        <nav aria-label="Mobile" className="mt-8">
          <ul>
            {items.map((item) => {
              const className =
                'flex items-center justify-between border-t border-[var(--nav-border)] py-4 text-2xl font-semibold tracking-tight text-[var(--nav-foreground)] transition-colors hover:text-[var(--nav-foreground)]'
              const content = (
                <>
                  {item.label}
                  <ArrowUpRight className="size-5 text-[var(--nav-foreground)]/40" aria-hidden />
                </>
              )

              return (
                <li key={item.label}>
                  {item.to ? (
                    <Link to={item.to} onClick={onClose} className={className}>
                      {content}
                    </Link>
                  ) : (
                    <a
                      href={item.href ?? `#${item.id}`}
                      onClick={onClose}
                      className={className}
                    >
                      {content}
                    </a>
                  )}
                </li>
              )
            })}
          </ul>
        </nav>

        <div className="mt-8 flex flex-col gap-3">
          <Link
            to="/reserve"
            onClick={onClose}
            className="inline-flex h-11 items-center justify-center rounded-full bg-[var(--nav-accent)] text-sm font-semibold text-[var(--nav-button-foreground)] transition-colors hover:bg-brand-dark"
          >
            Create Reservation
          </Link>
          <Link
            to="/login"
            onClick={onClose}
            className="inline-flex h-11 items-center justify-center rounded-full border border-[var(--nav-border)] text-sm font-semibold text-[var(--nav-foreground)] transition-colors hover:bg-[var(--nav-background)]/10"
          >
            Staff/Admin Login
          </Link>
        </div>
      </div>
    </div>
  )
}
