import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { OfflineBanner } from '@/components/offline/OfflineBanner'
import { PwaNotices } from '@/components/pwa/PwaNotices'
import { ViewOnlyAccessDenied } from '@/components/auth/ViewOnlyNotice'
import { useAuth } from '@/hooks/useAuth'
import { Spinner } from '@/components/ui/Misc'

const LandingPage = lazy(() =>
  import('@/pages/public/LandingPage').then((module) => ({ default: module.LandingPage })),
)
const RegisterPage = lazy(() =>
  import('@/pages/public/RegisterPage').then((module) => ({ default: module.RegisterPage })),
)
const NotFoundPage = lazy(() =>
  import('@/pages/public/NotFoundPage').then((module) => ({ default: module.NotFoundPage })),
)
const LoginPage = lazy(() =>
  import('@/pages/login/LoginPage').then((module) => ({ default: module.LoginPage })),
)
const AuthCallbackPage = lazy(() =>
  import('@/pages/login/AuthCallbackPage').then((module) => ({
    default: module.AuthCallbackPage,
  })),
)
const DashboardPage = lazy(() =>
  import('@/pages/dashboard/DashboardPage').then((module) => ({ default: module.DashboardPage })),
)
const FacilitiesPage = lazy(() =>
  import('@/pages/facilities/FacilitiesPage').then((module) => ({ default: module.FacilitiesPage })),
)
const FacilityDetailPage = lazy(() =>
  import('@/pages/facilities/FacilityDetailPage').then((module) => ({ default: module.FacilityDetailPage })),
)
const ReservationsPage = lazy(() =>
  import('@/pages/reservations/ReservationsPage').then((module) => ({ default: module.ReservationsPage })),
)
const ReservationDetailPage = lazy(() =>
  import('@/pages/reservations/ReservationDetailPage').then((module) => ({ default: module.ReservationDetailPage })),
)
const ReservationWizardPage = lazy(() =>
  import('@/pages/reservations/ReservationWizardPage').then((module) => ({ default: module.ReservationWizardPage })),
)
const CheckInPage = lazy(() =>
  import('@/pages/checkin/CheckInPage').then((module) => ({ default: module.CheckInPage })),
)
const CheckOutPage = lazy(() =>
  import('@/pages/checkin/CheckOutPage').then((module) => ({ default: module.CheckOutPage })),
)
const CalendarPage = lazy(() =>
  import('@/pages/calendar/CalendarPage').then((module) => ({ default: module.CalendarPage })),
)
const EquipmentPage = lazy(() =>
  import('@/pages/equipment/EquipmentPage').then((module) => ({ default: module.EquipmentPage })),
)
const EquipmentDetailPage = lazy(() =>
  import('@/pages/equipment/EquipmentDetailPage').then((module) => ({ default: module.EquipmentDetailPage })),
)
const AnalyticsPage = lazy(() =>
  import('@/pages/analytics/AnalyticsPage').then((module) => ({ default: module.AnalyticsPage })),
)
const ReportsPage = lazy(() =>
  import('@/pages/reports/ReportsPage').then((module) => ({ default: module.ReportsPage })),
)
const NotificationsPage = lazy(() =>
  import('@/pages/notifications/NotificationsPage').then((module) => ({ default: module.NotificationsPage })),
)
const SettingsPage = lazy(() =>
  import('@/pages/settings/SettingsPage').then((module) => ({ default: module.SettingsPage })),
)
const HelpPage = lazy(() =>
  import('@/pages/help/HelpPage').then((module) => ({ default: module.HelpPage })),
)
const AuditLogPage = lazy(() =>
  import('@/pages/admin/AuditLogPage').then((module) => ({ default: module.AuditLogPage })),
)
const OrganizationsPage = lazy(() =>
  import('@/pages/admin/OrganizationsPage').then((module) => ({
    default: module.OrganizationsPage,
  })),
)
const UserManagementPage = lazy(() =>
  import('@/pages/admin/UserManagementPage').then((module) => ({
    default: module.UserManagementPage,
  })),
)
const LoginActivityPage = lazy(() =>
  import('@/pages/admin/LoginActivityPage').then((module) => ({
    default: module.LoginActivityPage,
  })),
)
const FacilityResourcesPage = lazy(() =>
  import('@/pages/admin/FacilityResourcesPage').then((module) => ({
    default: module.FacilityResourcesPage,
  })),
)
const AffiliationPage = lazy(() =>
  import('@/pages/onboarding/AffiliationPage').then((module) => ({
    default: module.AffiliationPage,
  })),
)
const OfflinePage = lazy(() =>
  import('@/pages/offline/OfflinePage').then((module) => ({ default: module.OfflinePage })),
)

function PageLoader() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <Spinner />
    </div>
  )
}

function Protected() {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-soft">
        <Spinner />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <AppShell />
}

/**
 * Blocks a not-approved (view-only) account from a prohibited action form
 * reached directly by URL. Backend enforcement is authoritative; this keeps
 * the UI consistent and shows a clear access-denied message.
 */
function RequireApproved({
  children,
  title,
}: {
  children: ReactNode
  title: string
}) {
  const { user, loading, isViewOnly } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-soft">
        <Spinner />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (isViewOnly) return <ViewOnlyAccessDenied title={title} />
  return children
}

/** Blocks access for requesters; only administrators and SAS staff pass. */
function RequireStaff({ children }: { children: ReactNode }) {
  const { user, loading, isStaff } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-soft">
        <Spinner />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (!isStaff) return <Navigate to="/dashboard" replace />
  return children
}

/**
 * Administrator-only guard for user management and login activity. Mirrors the
 * backend's ``IsAdmin`` permission — SAS staff are redirected just like any
 * other non-administrator, so hiding the nav is never the only protection.
 */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-soft">
        <Spinner />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'ADMIN') return <Navigate to="/dashboard" replace />
  return children
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      {/*
       * Connectivity banner and the install/update notices are rendered ONCE
       * here, for every route — including the public landing/login pages, which
       * are exactly where a visitor notices an outage (they cannot sign in) and
       * where a first-time install happens. Rendering them per-shell instead
       * would duplicate them across route changes and miss those pages.
       */}
      <OfflineBanner />
      <PwaNotices />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route element={<Protected />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          {/* Read-only local backup view — reachable offline. */}
          <Route path="/offline" element={<OfflinePage />} />
          {/* Affiliation completion — reachable at any time from the profile. */}
          <Route
            path="/onboarding/affiliation"
            element={
              <RequireApproved title="Updating your affiliation">
                <AffiliationPage />
              </RequireApproved>
            }
          />
          <Route path="/facilities" element={<FacilitiesPage />} />
          <Route path="/facilities/:id" element={<FacilityDetailPage />} />
          <Route
            path="/facilities/:id/resources"
            element={
              <RequireApproved title="Editing this facility's resources">
                <RequireStaff>
                  <FacilityResourcesPage />
                </RequireStaff>
              </RequireApproved>
            }
          />
          <Route path="/reservations" element={<ReservationsPage />} />
          <Route
            path="/reservations/new"
            element={
              <RequireApproved title="Creating a reservation">
                <ReservationWizardPage />
              </RequireApproved>
            }
          />
          <Route path="/reservations/:id" element={<ReservationDetailPage />} />
          <Route
            path="/reservations/:id/check-in"
            element={
              <RequireApproved title="Check-in">
                <CheckInPage />
              </RequireApproved>
            }
          />
          <Route
            path="/reservations/:id/check-out"
            element={
              <RequireApproved title="Check-out">
                <CheckOutPage />
              </RequireApproved>
            }
          />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/equipment/:id" element={<EquipmentDetailPage />} />
          <Route path="/analytics" element={<RequireStaff><AnalyticsPage /></RequireStaff>} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
          <Route
            path="/organizations"
            element={
              <RequireStaff>
                <OrganizationsPage />
              </RequireStaff>
            }
          />
          {/* Administrator-only user management + login activity. */}
          <Route
            path="/admin/users"
            element={
              <RequireAdmin>
                <UserManagementPage />
              </RequireAdmin>
            }
          />
          <Route
            path="/admin/login-activity"
            element={
              <RequireAdmin>
                <LoginActivityPage />
              </RequireAdmin>
            }
          />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}