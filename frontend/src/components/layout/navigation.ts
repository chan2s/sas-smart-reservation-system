import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BadgeCheck,
  BarChart3,
  Building2,
  CalendarCheck,
  CalendarDays,
  FileSignature,
  History,
  LayoutDashboard,
  LifeBuoy,
  Package,
  Settings,
  Users,
} from 'lucide-react'

/**
 * Centralized navigation configuration.
 *
 * Every navigation surface (top pill navigation, mobile drawer, mobile bottom
 * nav) renders from these arrays — never redefine routes/labels per component.
 */
export interface NavigationItem {
  to: string
  label: string
  icon: LucideIcon
  /** Match the route exactly (needed for the Overview root route). */
  end?: boolean
}

/** Primary pages shown in the centered pill navigation. */
export const primaryNavigation: NavigationItem[] = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/reservations', label: 'Reservations', icon: CalendarCheck },
  { to: '/facilities', label: 'Facilities', icon: Building2 },
  { to: '/equipment', label: 'Equipment', icon: Package },
  { to: '/calendar', label: 'Calendar', icon: CalendarDays },
]

/** Staff-only additions to the primary navigation (kept out of requester UI). */
export const staffPrimaryNavigation: NavigationItem[] = [
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/organizations', label: 'Organizations', icon: BadgeCheck },
]

/**
 * Primary navigation for a signed-in role. Only administrators and SAS staff
 * receive the Analytics entry — requesters never see it. The designated
 * approval-letter signatory additionally receives the Approval Letters entry
 * (the backend verifies the designation on every sign; this only shapes the
 * navigation).
 */
export function primaryNavigationFor(
  isStaff: boolean,
  isApprovalSignatory = false,
): NavigationItem[] {
  const items = isStaff
    ? [...primaryNavigation, ...staffPrimaryNavigation]
    : primaryNavigation
  if (isStaff && isApprovalSignatory) {
    return [
      ...items,
      { to: '/approval-letters', label: 'Approval Letters', icon: FileSignature },
    ]
  }
  return items
}

/** Secondary pages, reachable from the user menu and mobile drawer. */
export const secondaryNavigation: NavigationItem[] = [
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/help', label: 'Help', icon: LifeBuoy },
]

/** Staff-only surfaces, appended to the user menu for administrators. */
export const staffNavigation: NavigationItem[] = [
  { to: '/audit-log', label: 'Audit log', icon: History },
]

/**
 * Administrator-only surfaces. Rendered only for ``role === 'ADMIN'`` accounts
 * (the same rule the backend APIs enforce); SAS staff never see them.
 */
export const adminNavigation: NavigationItem[] = [
  { to: '/admin/users', label: 'User management', icon: Users },
  { to: '/admin/login-activity', label: 'Login activity', icon: Activity },
]
