import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { Notification } from '@/lib/types'

const state = vi.hoisted(() => ({
  isStaff: true,
  unread: 2,
  markRead: vi.fn(),
  markAll: vi.fn(),
  notifications: null as unknown as { count: number; next: string | null; previous: string | null; results: Notification[] },
  loading: false,
  error: false,
}))

vi.mock('react-router-dom', () => ({
  Link: ({ children, to, onClick }: { children: React.ReactNode; to: string; onClick?: () => void }) => (
    <a href={to} onClick={(event) => { event.preventDefault(); onClick?.() }}>{children}</a>
  ),
  NavLink: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => vi.fn(),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, role: state.isStaff ? 'ADMIN' : 'REQUESTER', display_name: 'Admin User' },
    logout: vi.fn(),
    isStaff: state.isStaff,
    isViewOnly: false,
  }),
}))

vi.mock('@/hooks/queries', () => ({
  useUnreadCount: () => ({ data: { count: state.unread } }),
  useNotifications: () => ({
    data: state.notifications,
    isLoading: state.loading,
    isError: state.error,
    isFetching: false,
    refetch: vi.fn(),
  }),
  useMarkNotificationRead: () => ({ mutate: state.markRead, isPending: false }),
  useMarkAllNotificationsRead: () => ({ mutate: state.markAll, isPending: false }),
}))

import { Header } from './Header'

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 11,
    source: 'notification',
    type: 'RESERVATION',
    type_label: 'Reservation',
    title: 'Reservation submitted',
    message: 'SAS-2026-00042 is awaiting approval.',
    link: '/reservations/42',
    read: false,
    created_at: '2026-10-23T10:00:00+08:00',
    time_ago: '5 minutes ago',
    ...overrides,
  }
}

function openBell() {
  fireEvent.click(screen.getByRole('button', { name: /notifications/i }))
}

beforeEach(() => {
  state.isStaff = true
  state.unread = 2
  state.loading = false
  state.error = false
  state.markRead = vi.fn()
  state.markAll = vi.fn()
  state.notifications = {
    count: 2,
    next: null,
    previous: null,
    results: [
      notification(),
      notification({
        id: 19,
        source: 'possible_no_show',
        title: 'Possible no-show: SAS-2026-00019',
        message: 'Leadership Summit at Alert Hall; requester: Maria Santos; Started 18 minutes ago. No check-in recorded.',
        type_label: 'Possible no-show — action required',
        stage: 'NO_SHOW_RISK',
        stage_label: 'Possible no-show — action required',
        reference: 'SAS-2026-00019',
        read: true,
        link: '/reservations/19',
      }),
    ],
  }
})

afterEach(cleanup)

describe('Header notification center', () => {
  it('shows the persisted unread count and opens the complete notification feed directly', () => {
    render(<Header />)
    expect(screen.getByText('2')).toBeTruthy()
    openBell()
    expect(screen.getByText('Notifications')).toBeTruthy()
    expect(screen.getByText('Reservation submitted')).toBeTruthy()
    expect(screen.getByText('Possible no-show: SAS-2026-00019')).toBeTruthy()
    expect(screen.getByText('Unread')).toBeTruthy()
    expect(screen.getByText('Read')).toBeTruthy()
    const unreadRow = screen.getByText('Reservation submitted').closest('li')!
    const readRow = screen.getByText('Possible no-show: SAS-2026-00019').closest('li')!
    expect(unreadRow.compareDocumentPosition(readRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('links a notification to its reservation and marks it read when opened', () => {
    render(<Header />)
    openBell()
    const notificationLink = screen.getByRole('link', { name: /Reservation submitted/ })
    expect(notificationLink.getAttribute('href')).toBe('/reservations/42')
    fireEvent.click(notificationLink)
    expect(state.markRead).toHaveBeenCalledWith(state.notifications.results[0])
  })

  it('marks all notifications read from the panel', () => {
    render(<Header />)
    openBell()
    fireEvent.click(screen.getByRole('button', { name: /mark all as read/i }))
    expect(state.markAll).toHaveBeenCalled()
  })

  it('offers the complete paginated notification page', () => {
    render(<Header />)
    openBell()
    expect(screen.getByRole('link', { name: /all notifications/i }).getAttribute('href')).toBe('/notifications')
  })

  it('shows useful empty and request-error states', () => {
    state.notifications = { count: 0, next: null, previous: null, results: [] }
    state.unread = 0
    render(<Header />)
    openBell()
    expect(screen.getByText("You're all caught up")).toBeTruthy()
    cleanup()

    state.error = true
    state.notifications = undefined as never
    render(<Header />)
    openBell()
    expect(screen.getByText("Couldn't load notifications")).toBeTruthy()
  })
})
