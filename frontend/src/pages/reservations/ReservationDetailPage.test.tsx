import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { ApiError } from '@/lib/api'
import type { ReservationDetail } from '@/lib/types'

const state = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  toast: vi.fn(),
  reservation: null as unknown as ReservationDetail,
  isStaff: true,
  isViewOnly: false,
}))

vi.mock('react-router-dom', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: '7' }),
}))

vi.mock('@/hooks/queries', () => ({
  useReservation: () => ({ data: state.reservation, isLoading: false }),
  useReservationAction: () => ({
    mutateAsync: state.mutateAsync,
    mutate: vi.fn(),
    isPending: false,
  }),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, role: 'ADMIN' },
    isStaff: state.isStaff,
    isViewOnly: state.isViewOnly,
  }),
}))

vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: state.toast }),
}))

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
  apiErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error && error.message ? error.message : fallback,
}))

import { ReservationDetailPage } from './ReservationDetailPage'

/**
 * A reservation dated yesterday (the first eligible no-show day), exactly the
 * shape the backend returns for a staff viewer. `can_mark_no_show` is the
 * SERVER's decision — these tests never recompute it.
 */
function reservation(overrides: Partial<ReservationDetail> = {}): ReservationDetail {
  return {
    id: 7,
    reservation_id: 'SAS-2026-00007',
    event_name: 'Science Fair',
    event_type: 'ACADEMIC',
    event_type_label: 'Academic',
    requester_type: 'CAMPUS',
    requester_type_label: 'Campus User',
    organization: '',
    affiliation: '',
    affiliation_label: '',
    organization_code: '',
    organization_type: '',
    organization_type_label: '',
    expected_participants: 50,
    contact_person: '',
    contact_email: 'maria@school.edu',
    contact_phone: null,
    created_by_name: '',
    special_requirements: '',
    facility: 'Reminder Hall',
    facility_id: 1,
    facility_type: 'AVR',
    requester: 'Maria Santos',
    requester_id: 2,
    date: '2026-10-17',
    start_time: '09:00:00',
    end_time: '11:00:00',
    status: 'APPROVED',
    status_label: 'Approved',
    status_reason: '',
    rebooked_from: null,
    rebooked_from_reference: '',
    check_in_open_time: '2026-10-17T06:00:00+08:00',
    check_in_window_open: true,
    can_cancel: false,
    cancellation_reason: null,
    can_edit: false,
    can_mark_no_show: true,
    changes_requested: false,
    checked_in_at: null,
    checked_out_at: null,
    resources: [],
    estimated_total: '0.00',
    fees: [],
    approval_email_status: '',
    approval_email_status_label: '',
    created_at: '2026-10-10T09:00:00+08:00',
    description: '',
    purpose: '',
    notes: '',
    rejection_reason: '',
    checkin_code: '00000000-0000-0000-0000-000000000007',
    early_check_in_override: false,
    approved_by_name: 'Admin User',
    approved_at: '2026-10-10T09:00:00+08:00',
    no_show_marked_by_name: '',
    no_show_marked_at: null,
    reminder_sent_at: null,
    items: [],
    events: [],
    inspection: null,
    rescheduled_to: null,
    availability: {
      ok: true,
      facility: {
        id: 1,
        name: 'Reminder Hall',
        status: 'OPERATIONAL',
        available: true,
        operating_hours: null,
        conflicts: [],
      },
      items: [],
      problems: [],
    },
    ...overrides,
  }
}

function renderPage() {
  return render(<ReservationDetailPage />)
}

function noShowButton() {
  return screen.queryByRole('button', { name: /mark as no-show/i })
}

function cancelButton() {
  return screen.queryByRole('button', { name: /^cancel reservation$/i })
}

beforeEach(() => {
  state.mutateAsync = vi.fn()
  state.toast = vi.fn()
  state.isStaff = true
  state.isViewOnly = false
  state.reservation = reservation()
})

afterEach(cleanup)

describe('ReservationDetailPage no-show action', () => {
  it('hides the action when the backend says the reservation is not eligible', () => {
    state.reservation = reservation({ can_mark_no_show: false })
    renderPage()
    expect(noShowButton()).toBeNull()
  })

  it('replaces the check-in actions once the no-show window opens', () => {
    state.reservation = reservation({ can_mark_no_show: true })
    renderPage()

    expect(noShowButton()).toBeTruthy()
    expect(screen.queryByRole('button', { name: /^check in$/i })).toBeNull()
    expect(
      screen.queryByRole('button', { name: /view qr check-in/i }),
    ).toBeNull()
  })

  it('offers check-in instead of the no-show action on the event day', () => {
    state.reservation = reservation({ can_mark_no_show: false })
    renderPage()

    expect(screen.getByRole('button', { name: /^check in$/i })).toBeTruthy()
    expect(noShowButton()).toBeNull()
  })

  it('hides both actions for a reservation already marked no-show', () => {
    state.reservation = reservation({
      status: 'NO_SHOW',
      status_label: 'No-show',
      can_mark_no_show: false,
      no_show_marked_at: '2026-10-18T09:00:00+08:00',
      no_show_marked_by_name: 'Admin User',
    })
    renderPage()

    expect(noShowButton()).toBeNull()
    expect(screen.queryByRole('button', { name: /^check in$/i })).toBeNull()
  })

  it('never offers the action for an already checked-in reservation', () => {
    state.reservation = reservation({
      status: 'ACTIVE',
      can_mark_no_show: false,
      checked_in_at: '2026-10-17T08:55:00+08:00',
    })
    renderPage()
    expect(noShowButton()).toBeNull()
  })

  it('offers the action to staff only', () => {
    state.isStaff = false
    renderPage()
    expect(noShowButton()).toBeNull()
  })

  it('asks for explicit confirmation and does not submit on cancel', async () => {
    renderPage()
    fireEvent.click(noShowButton() as HTMLElement)

    expect(
      await screen.findByText('Mark Reservation as No-Show?'),
    ).toBeTruthy()
    expect(
      screen.getByText(
        'Are you sure you want to mark this reservation as a no-show? ' +
          'This action should only be performed if the requester did not ' +
          'attend the scheduled event.',
      ),
    ).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() =>
      expect(screen.queryByText('Confirm No-Show')).toBeNull(),
    )
    expect(state.mutateAsync).not.toHaveBeenCalled()
  })

  it('submits the confirmed action and reports success', async () => {
    state.mutateAsync.mockResolvedValue(undefined)
    renderPage()

    fireEvent.click(noShowButton() as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm No-Show' }))

    await waitFor(() =>
      expect(state.mutateAsync).toHaveBeenCalledWith({ action: 'mark-no-show' }),
    )
    expect(state.toast).toHaveBeenCalledWith('Reservation marked as no-show.')
    await waitFor(() =>
      expect(screen.queryByText('Confirm No-Show')).toBeNull(),
    )
  })

  it('keeps the dialog open and shows the backend error on failure', async () => {
    state.mutateAsync.mockRejectedValue(
      new Error(
        'This reservation can only be marked as a no-show on or after the ' +
          'day following the scheduled event date.',
      ),
    )
    renderPage()

    fireEvent.click(noShowButton() as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm No-Show' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('day following the scheduled event date')
    expect(screen.getByText('Confirm No-Show')).toBeTruthy()
    expect(state.toast).not.toHaveBeenCalled()
  })
})

describe('ReservationDetailPage cancel action visibility', () => {
  it('shows the button when the backend reports the reservation is cancellable', () => {
    state.reservation = reservation({ can_cancel: true, cancellation_reason: null })
    renderPage()
    expect(cancelButton()).toBeTruthy()
  })

  it('hides the button once the reservation is cancelled', () => {
    state.reservation = reservation({
      status: 'CANCELLED',
      status_label: 'Cancelled',
      can_cancel: false,
      cancellation_reason: 'This reservation can no longer be cancelled.',
    })
    renderPage()
    expect(cancelButton()).toBeNull()
  })

  it('hides the button for an already marked no-show reservation', () => {
    state.reservation = reservation({
      status: 'NO_SHOW',
      status_label: 'No-show',
      can_cancel: false,
      can_mark_no_show: false,
      cancellation_reason: 'This reservation can no longer be cancelled.',
    })
    renderPage()
    expect(cancelButton()).toBeNull()
    expect(noShowButton()).toBeNull()
    expect(screen.queryByRole('button', { name: /^check in$/i })).toBeNull()
  })

  it('hides the button for completed and otherwise finalized reservations', () => {
    state.reservation = reservation({
      status: 'COMPLETED',
      status_label: 'Completed',
      can_cancel: false,
      cancellation_reason: 'This reservation can no longer be cancelled.',
    })
    renderPage()
    expect(cancelButton()).toBeNull()
  })

  it('hides the button once the event has ended and explains why', () => {
    state.reservation = reservation({
      can_cancel: false,
      cancellation_reason:
        "This reservation's event has already ended and can no longer be cancelled.",
    })
    renderPage()
    expect(cancelButton()).toBeNull()
    expect(screen.getByText(/already ended/)).toBeTruthy()
  })

  it('keeps the two-day window restriction hidden with the policy reason', () => {
    state.reservation = reservation({
      can_cancel: false,
      cancellation_reason:
        'Reservations scheduled within the next 2 days cannot be cancelled.',
    })
    renderPage()
    expect(cancelButton()).toBeNull()
    expect(screen.getByText(/next 2 days/)).toBeTruthy()
  })

  it('cancels through the existing confirmation dialog and reports success', async () => {
    state.reservation = reservation({ can_cancel: true, cancellation_reason: null })
    state.mutateAsync.mockResolvedValue(undefined)
    renderPage()

    fireEvent.click(cancelButton() as HTMLElement)
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(
      within(dialog).getByRole('button', { name: /^cancel reservation$/i }),
    )

    await waitFor(() =>
      expect(state.mutateAsync).toHaveBeenCalledWith({
        action: 'cancel',
        body: { reason: '' },
      }),
    )
    expect(state.toast).toHaveBeenCalledWith('Reservation cancelled.')
  })

  it('shows the backend rejection message when the action is prohibited', async () => {
    state.reservation = reservation({ can_cancel: true, cancellation_reason: null })
    state.mutateAsync.mockRejectedValue(
      new ApiError(
        400,
        "This reservation's event has already ended and can no longer be cancelled.",
      ),
    )
    renderPage()

    fireEvent.click(cancelButton() as HTMLElement)
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(
      within(dialog).getByRole('button', { name: /^cancel reservation$/i }),
    )

    await waitFor(() =>
      expect(state.toast).toHaveBeenCalledWith(
        "This reservation's event has already ended and can no longer be cancelled.",
        'error',
      ),
    )
  })
})
