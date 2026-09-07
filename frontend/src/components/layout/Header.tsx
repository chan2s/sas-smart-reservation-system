import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import {
  Bell,
  CalendarDays,
  ChevronDown,
  LogOut,
  Menu,
  Search,
  X,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useUnreadCount } from '@/hooks/queries'
import { Avatar } from '@/components/ui/Misc'
import { Dropdown, MenuItem } from '@/components/ui/Dropdown'
import { cn } from '@/lib/utils'
import { primaryNavigation, secondaryNavigation, staffNavigation } from './navigation'

// ---------------------------------------------------------------------------
// Brand
// ---------------------------------------------------------------------------

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5 focus-ring rounded-lg">
      <div className="flex size-10 items-center justify-center rounded-xl bg-brand text-white shadow-sm">
        <CalendarDays className="size-5" aria-hidden />
      </div>
      <div className="leading-tight">
        <p className="text-base font-bold tracking-tight text-ink">SAS RESERVE</p>
        <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
          Facility &amp; Resources
        </p>
      </div>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Pill navigation
// ---------------------------------------------------------------------------

export function PillNavigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav
      aria-label="Primary"
      className="hidden items-center rounded-full border border-line bg-soft p-1 lg:inline-flex"
    >
      {primaryNavigation.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13.5px] font-medium whitespace-nowrap transition-colors duration-150',
              isActive
                ? 'bg-brand text-white shadow-sm'
                : 'text-body hover:bg-softer hover:text-ink',
            )
          }
        >
          <item.icon className="size-4" aria-hidden />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Header actions: search, notifications, user menu
// ---------------------------------------------------------------------------

function HeaderActions() {
  const { user, logout, isStaff } = useAuth()
  const { data: unread } = useUnreadCount()
  const navigate = useNavigate()

  return (
    <div className="flex items-center gap-1.5 justify-self-end">
      {/* Compact search field — never wide enough to push the pill off-center */}
      <div className="relative hidden 2xl:block">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          aria-hidden
        />
        <input
          type="search"
          placeholder="Search…"
          className="h-9 w-44 rounded-full border border-line bg-soft pl-9 pr-4 text-sm text-ink placeholder:text-muted transition-colors duration-150 hover:border-line-strong focus:w-56 focus:border-brand focus:bg-surface focus:outline-none focus:ring-4 focus:ring-brand/10"
        />
      </div>
      <button
        type="button"
        onClick={() => navigate('/reservations')}
        className="flex size-9 items-center justify-center rounded-full text-body transition-colors duration-150 hover:bg-soft hover:text-ink 2xl:hidden"
        aria-label="Search reservations, facilities, equipment"
      >
        <Search className="size-5" aria-hidden />
      </button>

      {/* Notifications */}
      <Dropdown
        align="right"
        trigger={
          <span className="relative flex size-9 items-center justify-center rounded-full text-body transition-colors duration-150 hover:bg-soft hover:text-ink">
            <Bell className="size-5" aria-label="Notifications" />
            {(unread?.count ?? 0) > 0 && (
              <span className="absolute right-1 top-1 flex min-w-[17px] items-center justify-center rounded-full bg-brand px-1 py-px text-[10px] font-bold text-white ring-2 ring-surface">
                {unread?.count}
              </span>
            )}
          </span>
        }
      >
        {(close) => (
          <MenuItem onClick={() => { close(); navigate('/notifications') }}>
            <Bell className="size-4" />
            View notifications
          </MenuItem>
        )}
      </Dropdown>

      {/* User menu */}
      <Dropdown
        align="right"
        trigger={
          <span className="flex items-center gap-2 rounded-full p-1 pr-2 transition-colors duration-150 hover:bg-soft">
            <Avatar name={user?.display_name ?? '?'} size="sm" />
            <span className="hidden text-left leading-tight xl:block">
              <span className="block text-[13px] font-semibold text-ink">
                {user?.display_name ?? 'Administrator'}
              </span>
              <span className="block text-[11px] text-muted">
                {user?.role === 'ADMIN'
                  ? 'SAS Administrator'
                  : user?.role === 'STAFF'
                    ? 'SAS Staff'
                    : user?.organization || 'Requester'}
              </span>
            </span>
            <ChevronDown className="hidden size-3.5 text-muted xl:block" aria-hidden />
          </span>
        }
      >
        {(close) => (
          <>
            <div className="px-3 py-2 md:hidden">
              <p className="text-sm font-semibold text-ink">
                {user?.display_name ?? 'Administrator'}
              </p>
              <p className="text-xs text-muted">
                {user?.role === 'ADMIN'
                  ? 'SAS Administrator'
                  : user?.role === 'STAFF'
                    ? 'SAS Staff'
                    : user?.organization || 'Requester'}
              </p>
            </div>
            <div className="my-1 h-px bg-line md:hidden" aria-hidden />
            {primaryNavigation.map((item) => (
              <MenuItem key={`m-${item.to}`} onClick={() => { close(); navigate(item.to) }}>
                <item.icon className="size-4" />
                {item.label}
              </MenuItem>
            ))}
            <div className="my-1 h-px bg-line" aria-hidden />
            {secondaryNavigation.map((item) => (
              <MenuItem key={item.to} onClick={() => { close(); navigate(item.to) }}>
                <item.icon className="size-4" />
                {item.label}
              </MenuItem>
            ))}
            {isStaff && (
              <>
                {staffNavigation.map((item) => (
                  <MenuItem key={item.to} onClick={() => { close(); navigate(item.to) }}>
                    <item.icon className="size-4" />
                    {item.label}
                  </MenuItem>
                ))}
              </>
            )}
            <div className="my-1 h-px bg-line" aria-hidden />
            <MenuItem onClick={() => { close(); navigate('/notifications') }}>
              <Bell className="size-4" />
              Notifications
            </MenuItem>
            <MenuItem
              danger
              onClick={() => {
                close()
                logout()
                navigate('/login')
              }}
            >
              <LogOut className="size-4" />
              Sign out
            </MenuItem>
          </>
        )}
      </Dropdown>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mobile drawer navigation
// ---------------------------------------------------------------------------

function MobileMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <div
        className="absolute inset-0 bg-ink/40"
        onClick={onClose}
        aria-hidden
      />
      <div className="absolute inset-x-3 top-3 rounded-2xl border border-line bg-surface p-3 shadow-float animate-fade-up">
        <div className="flex items-center justify-between px-1 pb-2">
          <Brand />
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-muted transition-colors hover:bg-soft hover:text-ink"
            aria-label="Close navigation"
          >
            <X className="size-5" />
          </button>
        </div>
        <nav aria-label="Mobile" className="space-y-1 border-t border-line pt-3">
          {primaryNavigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onClose}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors duration-150',
                  isActive
                    ? 'bg-brand text-white'
                    : 'text-body hover:bg-soft hover:text-ink',
                )
              }
            >
              <item.icon className="size-[18px]" aria-hidden />
              {item.label}
            </NavLink>
          ))}
          <div className="my-2 h-px bg-line" aria-hidden />
          {secondaryNavigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={onClose}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors duration-150',
                  isActive
                    ? 'bg-brand-soft text-brand'
                    : 'text-body hover:bg-soft hover:text-ink',
                )
              }
            >
              <item.icon className="size-[18px]" aria-hidden />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

/**
 * Sticky top header.
 *
 * Layout is a 3-column CSS grid (`1fr auto 1fr`) so the pill navigation sits
 * at the exact viewport center regardless of brand/actions widths:
 *
 *   ┌─────────────┬──────────────────────────┬─────────────┐
 *   │ 1fr: Brand  │ auto: PillNavigation     │ 1fr: Actions│
 *   └─────────────┴──────────────────────────┴─────────────┘
 *
 * Scroll model: the document itself scrolls (the shell no longer pins the
 * viewport), so `sticky top-0` works naturally and page content can scroll
 * beneath the header edge.
 */
export function Header() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
        {/* One row on desktop (grid centers the pill); stacked rows on mobile */}
        <div className="mx-auto grid h-[72px] w-full max-w-[1600px] grid-cols-[1fr_auto_1fr] items-center gap-3 px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setMobileNavOpen(true)}
              className="rounded-lg p-2 text-body transition-colors hover:bg-soft hover:text-ink lg:hidden"
              aria-label="Open navigation"
            >
              <Menu className="size-5" />
            </button>
            <div className="hidden min-[480px]:block">
              <Brand />
            </div>
          </div>

          <div className="flex justify-center">
            <PillNavigation />
          </div>

          <HeaderActions />
        </div>
      </header>

      <MobileMenu open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Mobile bottom navigation (kept from the previous design)
// ---------------------------------------------------------------------------

export function MobileBottomNav() {
  return (
    <nav
      aria-label="Mobile"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
    >
      {primaryNavigation.slice(0, 5).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              'flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px] font-medium transition-colors',
              isActive ? 'text-brand' : 'text-muted',
            )
          }
        >
          <item.icon className="size-5" aria-hidden />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
