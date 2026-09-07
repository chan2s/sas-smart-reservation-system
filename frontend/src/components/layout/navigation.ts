import type { LucideIcon } from 'lucide-react'
import {
  BarChart3,
  Building2,
  CalendarCheck,
  CalendarDays,
  History,
  LayoutDashboard,
  LifeBuoy,
  Package,
  Settings,
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
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/reservations', label: 'Reservations', icon: CalendarCheck },
  { to: '/facilities', label: 'Facilities', icon: Building2 },
  { to: '/equipment', label: 'Equipment', icon: Package },
  { to: '/calendar', label: 'Calendar', icon: CalendarDays },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
]

/** Secondary pages, reachable from the user menu and mobile drawer. */
export const secondaryNavigation: NavigationItem[] = [
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/help', label: 'Help', icon: LifeBuoy },
]

/** Staff-only surfaces, appended to the user menu for administrators. */
export const staffNavigation: NavigationItem[] = [
  { to: '/audit-log', label: 'Audit log', icon: History },
]
