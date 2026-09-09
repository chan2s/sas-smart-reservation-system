import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
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
const VerifyOtpPage = lazy(() =>
  import('@/pages/login/VerifyOtpPage').then((module) => ({
    default: module.VerifyOtpPage,
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

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/auth/verify-otp" element={<VerifyOtpPage />} />
        <Route element={<Protected />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/facilities" element={<FacilitiesPage />} />
          <Route path="/facilities/:id" element={<FacilityDetailPage />} />
          <Route path="/reservations" element={<ReservationsPage />} />
          <Route path="/reservations/new" element={<ReservationWizardPage />} />
          <Route path="/reservations/:id" element={<ReservationDetailPage />} />
          <Route path="/reservations/:id/check-in" element={<CheckInPage />} />
          <Route path="/reservations/:id/check-out" element={<CheckOutPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/equipment/:id" element={<EquipmentDetailPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}