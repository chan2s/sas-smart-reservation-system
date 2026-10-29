import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import type {
  AwaitingNoShowReview,
  NoShowAlert,
  NoShowAlertsResponse,
} from '@/lib/types'

const state = vi.hoisted(() => ({
  isStaff: true,
  alerts: null as unknown as NoShowAlertsResponse,
  alertsLoading: false,
  alertsError: false,
  summary: null as unknown as Record<string, unknown>,
}))

vi.mock('react-router-dom', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ isStaff: state.isStaff, isViewOnly: false }),
}))

vi.mock('@/hooks/queries', () => ({
  useDashboardSummary: () => ({
    data: state.summary,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    isFetching: false,
  }),
  useFacilities: () => ({ data: [] }),
  useUtilization: () => ({
    data: { facility: { facilities: [] } },
    isError: false,
  }),
  useNoShowAlerts: () => ({
    data: state.alerts,
    isLoading: state.alertsLoading,
    isError: state.alertsError,
    refetch: vi.fn(),
    isFetching: false,
  }),
}))

import { DashboardPage } from './DashboardPage'

function alert(overrides: Partial<NoShowAlert> = {}): NoShowAlert {
  return {
    id: 11,
    reservation: 42,
    reference: 'SAS-2026-00042',
    event_name: 'Leadership Summit',
    facility: 'Reminder Hall',
    facility_id: 3,
    requester: 'Maria Santos',
    requester_id: 7,
    date: '2026-10-23',
    start_time: '10:00',
    end_time: '12:00',
    status: 'APPROVED',
    status_label: 'Approved',
    stage: 'NO_SHOW_RISK',
    stage_label: 'Possible no-show — action required',
    acknowledged: false,
    acknowledged_at: null,
    detected_at: '2026-10-23T09:45:00+08:00',
    stage_changed_at: '2026-10-23T10:15:00+08:00',
    updated_at: '2026-10-23T10:15:00+08:00',
    link: '/reservations/42',
    minutes_until_start: null,
    minutes_since_start: 18,
    time_label: 'Started 18 minutes ago',
    no_check_in_label: 'No check-in recorded',
    ...overrides,
  }
}

function review(overrides: Partial<AwaitingNoShowReview> = {}): AwaitingNoShowReview {
  return {
    reservation: 84,
    reference: 'SAS-2026-00084',
    event_name: 'Alumni Homecoming',
    facility: 'Gymnasium',
    facility_id: 5,
    requester: 'Jose Rizal',
    requester_id: 9,
    date: '2026-10-22',
    start_time: '09:00',
    end_time: '11:00',
    status: 'APPROVED',
    status_label: 'Approved',
    link: '/reservations/84',
    time_label: 'Ended 1 day ago',
    minutes_since_end: 1520,
    no_check_in_label: 'No check-in recorded',
    can_mark_no_show: true,
    ...overrides,
  }
}

beforeEach(() => {
  state.isStaff = true
  state.alertsLoading = false
  state.alertsError = false
  state.summary = {
    total_reservations: 12,
    pending_requests: 2,
    facilities: 4,
    equipment: 30,
    today: [],
    pending: [],
    upcoming: [],
    today_date: '2026-10-23',
  }
  state.alerts = {
    count: 1,
    unread: 1,
    results: [alert()],
    review_count: 0,
    awaiting_review: [],
  }
})

afterEach(cleanup)

describe('DashboardPage possible no-show section', () => {
  it('renders the real alert returned by the API', () => {
    render(<DashboardPage />)

    expect(screen.getByText('Possible No-Show Alerts')).toBeTruthy()
    expect(
      screen.getByText('1 possible no-show · 1 unread · 0 awaiting review'),
    ).toBeTruthy()
    expect(screen.getByText('Possible No-Shows')).toBeTruthy()
    expect(screen.getByText('SAS-2026-00042')).toBeTruthy()
    expect(screen.getByText(/Reminder Hall · Maria Santos/)).toBeTruthy()
    expect(screen.getByText(/Possible no-show — action required/)).toBeTruthy()
    expect(screen.getByText(/Started 18 minutes ago/)).toBeTruthy()
    expect(screen.getByText(/No check-in recorded/)).toBeTruthy()

    const reviewLink = screen.getByRole('link', { name: /review reservation/i })
    expect(reviewLink.getAttribute('href')).toBe('/reservations/42')
  })

  it('shows a count for multiple alerts', () => {
    state.alerts = {
      ...state.alerts,
      count: 2,
      results: [
        alert(),
        alert({ id: 12, reservation: 43, reference: 'SAS-2026-00043', acknowledged: true }),
      ],
    }
    render(<DashboardPage />)

    expect(
      screen.getByText('2 possible no-shows · 1 unread · 0 awaiting review'),
    ).toBeTruthy()
  })

  it('renders overdue reservations awaiting review in their own group', () => {
    state.alerts = {
      ...state.alerts,
      review_count: 1,
      awaiting_review: [review()],
    }
    render(<DashboardPage />)

    expect(screen.getByText('Awaiting No-Show Review')).toBeTruthy()
    expect(
      screen.getByText('1 possible no-show · 1 unread · 1 awaiting review'),
    ).toBeTruthy()
    expect(screen.getByText('SAS-2026-00084')).toBeTruthy()
    expect(screen.getByText(/Alumni Homecoming · Gymnasium · Jose Rizal/)).toBeTruthy()
    expect(screen.getByText(/Oct 22, 2026 · 9:00 AM/)).toBeTruthy()
    expect(screen.getByText(/Ended 1 day ago/)).toBeTruthy()
    expect(screen.getByText('Awaiting no-show review')).toBeTruthy()

    const markLink = screen.getByRole('link', { name: /review & mark no-show/i })
    expect(markLink.getAttribute('href')).toBe('/reservations/84')

    // The possible no-show alert stays in its own group.
    expect(screen.getByText('SAS-2026-00042')).toBeTruthy()
  })

  it('explains when a review row can be marked as a no-show', () => {
    state.alerts = {
      ...state.alerts,
      results: [],
      count: 0,
      unread: 0,
      review_count: 1,
      awaiting_review: [review({ can_mark_no_show: false })],
    }
    render(<DashboardPage />)

    expect(
      screen.getByText(
        'Can be marked as a no-show from the day after the scheduled date.',
      ),
    ).toBeTruthy()
  })

  it('explains the empty state of each group instead of inventing records', () => {
    state.alerts = {
      count: 0,
      unread: 0,
      results: [],
      review_count: 0,
      awaiting_review: [],
    }
    render(<DashboardPage />)

    expect(
      screen.getByText(/No possible no-shows detected right now/),
    ).toBeTruthy()
    expect(
      screen.getByText('No overdue reservations are awaiting a no-show decision.'),
    ).toBeTruthy()
    expect(screen.queryByText('SAS-2026-00042')).toBeNull()
  })

  it('shows an error state and no fabricated rows when the request fails', () => {
    state.alertsError = true
    state.alerts = undefined as never
    render(<DashboardPage />)

    expect(screen.getByText("Couldn't load possible no-show alerts")).toBeTruthy()
    expect(screen.queryByText('SAS-2026-00042')).toBeNull()
  })

  it('is never shown to requesters', () => {
    state.isStaff = false
    render(<DashboardPage />)

    expect(screen.queryByText('Possible No-Show Alerts')).toBeNull()
  })
})
