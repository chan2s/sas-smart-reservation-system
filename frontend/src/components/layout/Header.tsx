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
import { NotificationCenter } from '@/components/notifications/NoShowAlerts'
import { Avatar } from '@/components/ui/Misc'
import { Dropdown, MenuItem } from '@/components/ui/Dropdown'
import { cn } from '@/lib/utils'
import {
  adminNavigation,
  primaryNavigationFor,
  secondaryNavigation,
  staffNavigation,
} from './navigation'

// ---------------------------------------------------------------------------
// Brand
// ---------------------------------------------------------------------------

export function Brand() {
  return (
    <Link to="/" className="flex min-w-0 items-center gap-2.5 rounded-lg focus-ring">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand text-white shadow-sm sm:size-10">
        <CalendarDays className="size-5" aria-hidden />
      </div>
      <div className="min-w-0 leading-tight">
        <p className="truncate text-sm font-bold tracking-tight text-ink sm:text-base">
          SAS RESERVE
        </p>
        <p className="hidden truncate text-[11px] font-medium uppercase tracking-[0.12em] text-muted sm:block">
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
  const { isStaff, isApprovalSignatory, isApprovalLettersOnly } = useAuth()
  return (
    <nav
      aria-label="Primary"
      className="hidden min-w-0 items-center gap-0.5 rounded-full border border-line bg-soft p-1 xl:inline-flex"
    >
      {primaryNavigationFor(isStaff, isApprovalSignatory, isApprovalLettersOnly).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap transition-colors duration-150',
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
  const { user, logout, isStaff, isApprovalSignatory, isApprovalLettersOnly } = useAuth()
  const { data: unread } = useUnreadCount(!isApprovalLettersOnly)
  const navigate = useNavigate()
  const isAdmin = user?.role === 'ADMIN'

  return (
    <div className="col-start-3 flex min-w-0 items-center justify-end gap-1 sm:gap-1.5">
      {/* Compact search field — never wide enough to push the pill off-center */}
      {!isApprovalLettersOnly && (
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
      )}
      {!isApprovalLettersOnly && (
        <button
          type="button"
          onClick={() => navigate('/reservations')}
          className="flex size-9 items-center justify-center rounded-full text-body transition-colors duration-150 hover:bg-soft hover:text-ink 2xl:hidden"
          aria-label="Search reservations, facilities, equipment"
        >
          <Search className="size-5" aria-hidden />
        </button>
      )}

      {/* Notifications */}
      {!isApprovalLettersOnly && (
        <Dropdown
          align="right"
          /*
           * Mobile: viewport-anchored sheet with 12px gutters on both sides, so
           * it can never overflow the left edge and stays clear of the fixed
           * bottom navigation (max height reserves header + nav + safe area).
           * From `sm` up it falls back to the original right-aligned panel.
           */
          panelClassName="fixed left-3 right-3 top-[4.25rem] flex max-h-[calc(100dvh_-_8.5rem_-_env(safe-area-inset-bottom))] w-auto max-w-[min(27rem,calc(100vw_-_24px))] flex-col overflow-hidden rounded-xl border border-line bg-surface p-1.5 shadow-pop animate-fade-up sm:absolute sm:top-full sm:left-auto sm:right-0 sm:mt-2 sm:max-h-[70vh] sm:w-[27rem]"
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
          {(close) => <NotificationCenter onNavigate={close} />}
        </Dropdown>
      )}

      {/* User menu */}
      <Dropdown
        align="right"
        trigger={
          <span className="flex items-center gap-2 rounded-full p-1 pr-2 transition-colors duration-150 hover:bg-soft">
            <Avatar name={user?.display_name ?? '?'} size="sm" />
            {/* The name block only appears once the pill nav and the actions
                both fit comfortably — below 2xl it collapses to the avatar. */}
            <span className="hidden text-left leading-tight 2xl:block">
              <span className="block text-[13px] font-semibold text-ink">
                {user?.display_name ?? 'Administrator'}
              </span>
              <span className="block text-[11px] text-muted">
                {isApprovalLettersOnly
                  ? 'Assistant Campus Director for Administration and Finance'
                  : user?.role === 'ADMIN'
                    ? 'SAS Administrator'
                    : user?.role === 'STAFF'
                      ? 'SAS Staff'
                      : user?.organization_ref?.display_name ||
                          user?.organization_ref?.organization_name ||
                          user?.affiliation_label ||
                          user?.organization ||
                          'Requester'}
              </span>
            </span>
            <ChevronDown className="hidden size-3.5 text-muted 2xl:block" aria-hidden />
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
                {isApprovalLettersOnly
                  ? 'Assistant Campus Director for Administration and Finance'
                  : user?.role === 'ADMIN'
                    ? 'SAS Administrator'
                    : user?.role === 'STAFF'
                      ? 'SAS Staff'
                      : user?.organization_ref?.display_name ||
                          user?.organization_ref?.organization_name ||
                          user?.affiliation_label ||
                          user?.organization ||
                          'Requester'}
              </p>
            </div>
            <div className="my-1 h-px bg-line md:hidden" aria-hidden />
            {primaryNavigationFor(isStaff, isApprovalSignatory, isApprovalLettersOnly).map((item) => (
              <MenuItem key={`m-${item.to}`} onClick={() => { close(); navigate(item.to) }}>
                <item.icon className="size-4" />
                {item.label}
              </MenuItem>
            ))}
            <div className="my-1 h-px bg-line" aria-hidden />
            {!isApprovalLettersOnly && secondaryNavigation.map((item) => (
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
            {isAdmin && (
              <>
                {adminNavigation.map((item) => (
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
  const { user, isStaff, isApprovalSignatory, isApprovalLettersOnly } = useAuth()
  const isAdmin = user?.role === 'ADMIN'
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
    <div id="app-mobile-navigation" className="fixed inset-0 z-40 xl:hidden">
      <div
        className="absolute inset-0 bg-ink/40"
        onClick={onClose}
        aria-hidden
      />
      <div className="absolute inset-x-3 top-3 max-h-[calc(100dvh-1.5rem)] overflow-y-auto rounded-2xl border border-line bg-surface p-3 shadow-float animate-fade-up">
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
          {primaryNavigationFor(isStaff, isApprovalSignatory, isApprovalLettersOnly).map((item) => (
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
          {!isApprovalLettersOnly && secondaryNavigation.map((item) => (
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
          {isStaff && (
            <>
              {staffNavigation.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={onClose}
                  className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-body transition-colors duration-150 hover:bg-soft hover:text-ink"
                >
                  <item.icon className="size-[18px]" aria-hidden />
                  {item.label}
                </NavLink>
              ))}
            </>
          )}
          {isAdmin && (
            <>
              {adminNavigation.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={onClose}
                  className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-body transition-colors duration-150 hover:bg-soft hover:text-ink"
                >
                  <item.icon className="size-[18px]" aria-hidden />
                  {item.label}
                </NavLink>
              ))}
            </>
          )}
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
 * Layout is a 3-column CSS grid (`minmax(0,1fr) auto minmax(0,1fr)`) so the
 * pill navigation sits at the exact viewport center regardless of the brand
 * and actions widths:
 *
 *   ┌─────────────┬──────────────────────────┬─────────────┐
 *   │ 1fr: Brand  │ auto: PillNavigation     │ 1fr: Actions│
 *   └─────────────┴──────────────────────────┴─────────────┘
 *
 * Responsive model: the pill navigation carries one entry per permitted route
 * (up to eight for a staff signatory), so it is only rendered from `xl` where
 * it genuinely fits. Below that, the header shows the brand, the actions and
 * the drawer trigger — the same navigation, in the existing mobile drawer.
 * The `minmax(0,1fr)` side columns (plus `min-w-0` descendants) are what keep
 * a long brand or a wide action group from widening the whole document and
 * producing a page-level horizontal scrollbar.
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
        <div className="mx-auto grid h-16 w-full max-w-[1600px] grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 px-4 sm:gap-3 sm:px-6 lg:h-[72px] lg:px-8">
          <div className="flex min-w-0 items-center gap-1">
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              className="-ml-1.5 shrink-0 rounded-lg p-2 text-body transition-colors hover:bg-soft hover:text-ink xl:hidden"
              aria-label="Open navigation"
              aria-expanded={mobileNavOpen}
              aria-controls="app-mobile-navigation"
            >
              <Menu className="size-5" aria-hidden />
            </button>
            <Brand />
          </div>

          <div className="hidden min-w-0 justify-center xl:flex">
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
  const { isStaff, isApprovalSignatory, isApprovalLettersOnly } = useAuth()
  return (
    <nav
      aria-label="Mobile"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
    >
      {primaryNavigationFor(isStaff, isApprovalSignatory, isApprovalLettersOnly).slice(0, 5).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              'flex min-w-0 flex-1 flex-col items-center gap-1 px-0.5 py-2.5 text-[10px] font-medium transition-colors',
              isActive ? 'text-brand' : 'text-muted',
            )
          }
        >
          <item.icon className="size-5 shrink-0" aria-hidden />
          <span className="w-full truncate text-center">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
