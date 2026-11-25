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
  paymentMutate: vi.fn(),
  retryMutate: vi.fn(),
  refetch: vi.fn(),
  toast: vi.fn(),
  reservation: null as unknown as ReservationDetail,
  isError: false,
  error: null as unknown,
  routeId: '7',
  isStaff: true,
  isViewOnly: false,
}))

vi.mock('react-router-dom', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: state.routeId }),
}))

vi.mock('@/hooks/queries', () => ({
  useReservation: () => ({
    data: state.reservation,
    isLoading: false,
    isError: state.isError,
    error: state.error,
    refetch: state.refetch,
  }),
  useReservationAction: () => ({
    mutateAsync: state.mutateAsync,
    mutate: vi.fn(),
    isPending: false,
  }),
  useRetryApprovalEmail: () => ({
    mutate: state.retryMutate,
    isPending: false,
  }),
  useRetryApprovalDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useResendApprovalEmail: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateReservationPayment: () => ({ mutateAsync: state.paymentMutate, isPending: false }),
  useUploadApprovalLetterImage: () => ({ mutate: vi.fn(), isPending: false }),
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
    data: unknown
    constructor(status: number, message: string, data?: unknown) {
      super(message)
      this.status = status
      this.data = data
    }
  },
  api: { fileUrl: vi.fn(), downloadFile: vi.fn() },
  endpoints: { reservationApprovalLetterFile: vi.fn() },
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
    reservation_id: 'GSO-2026-00007',
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
    requester_email: 'maria@school.edu',
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
    generated_approval_status: 'NOT_STARTED',
    generated_approval_status_label: 'Not generated',
    generated_approval_error: '',
    generated_approval_at: null,
    approval_pdf_available: false,
    approval_docx_available: false,
    approval_email_sent_at: null,
    approval_email_attempts: 0,
    approval_email_last_error: '',
    approval_document_status: 'NOT_REQUIRED',
    approval_document_status_label: 'Not required for this reservation',
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

function paymentInfo(
  overrides: Partial<NonNullable<ReservationDetail['payment']>> = {},
): NonNullable<ReservationDetail['payment']> {
  return {
    payment_type: 'DOWN_PAYMENT',
    payment_type_label: 'Down Payment',
    total_amount: '10000.00',
    down_payment_amount: '5000.00',
    required_amount: '5000.00',
    amount_paid: '0.00',
    remaining_balance: '5000.00',
    status: 'UNPAID',
    status_label: 'Unpaid',
    is_configured: true,
    is_outstanding: true,
    approval_warning:
      'This external reservation has not received any payment yet. The required downpayment is 50% of the total reservation price.',
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
  state.paymentMutate = vi.fn()
  state.retryMutate = vi.fn()
  state.refetch = vi.fn(async () => ({ data: state.reservation }))
  state.toast = vi.fn()
  state.isStaff = true
  state.isViewOnly = false
  state.isError = false
  state.error = null
  state.routeId = '7'
  state.reservation = reservation()
})

afterEach(cleanup)

describe('ReservationDetailPage direct editing access', () => {
  it('offers the no-OTP edit form to authorized GSO staff for eligible reservations', () => {
    state.reservation = reservation({ status: 'PENDING', can_edit: true })
    renderPage()
    expect(screen.getByRole('button', { name: 'Edit reservation' })).toBeTruthy()
  })

  it('does not expose the admin edit action to a non-staff viewer', () => {
    state.isStaff = false
    state.reservation = reservation({ status: 'PENDING', can_edit: true })
    renderPage()
    expect(screen.queryByRole('button', { name: 'Edit reservation' })).toBeNull()
  })
})

describe('ReservationDetailPage approval email status', () => {
  it.each([
    ['NOT_SENT', 'Not sent'],
    ['SENT', 'Sent'],
    ['FAILED', 'Failed'],
  ])('shows the backend delivery state %s as %s', (status, label) => {
    state.reservation = reservation({
      approval_email_status: status,
      approval_email_status_label: label,
    })
    renderPage()

    expect(screen.getByText('Approval email')).toBeTruthy()
    expect(screen.getByText(label)).toBeTruthy()
  })

  it('offers a resend when the approval email was never sent', () => {
    state.reservation = reservation({
      approval_email_status: 'NOT_SENT',
      approval_email_status_label: 'Not sent',
    })
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /resend email/i }))
    expect(state.retryMutate).toHaveBeenCalled()
  })

  it('does not offer a resend once the email was sent', () => {
    state.reservation = reservation({
      approval_email_status: 'SENT',
      approval_email_status_label: 'Sent',
    })
    renderPage()

    expect(screen.queryByRole('button', { name: /resend email/i })).toBeNull()
  })
})

describe('ReservationDetailPage external approval letter', () => {
  it('shows staff preview, PDF/DOCX downloads, generation state, and explicit resend', () => {
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      generated_approval_status: 'GENERATED',
      generated_approval_status_label: 'Generated',
      approval_pdf_available: true,
      approval_docx_available: true,
      approval_email_attempts: 1,
      approval_email_status: 'SENT',
      approval_email_status_label: 'Sent',
    })
    renderPage()

    expect(screen.getByRole('button', { name: 'Download Approval Letter' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Preview PDF' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Download DOCX' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Resend Approval Email' })).toBeTruthy()
    expect(screen.getByText('Generated')).toBeTruthy()
  })
})

describe('ReservationDetailPage revision request', () => {
  function revisionButton() {
    return screen.queryByRole('button', { name: /send revision request/i })
  }

  beforeEach(() => {
    state.reservation = reservation({ status: 'PENDING', status_label: 'Pending' })
  })

  it('renames the action and opens the revision dialog', () => {
    renderPage()

    expect(revisionButton()).toBeTruthy()
    expect(screen.queryByRole('button', { name: /request changes/i })).toBeNull()

    fireEvent.click(revisionButton() as HTMLElement)
    const dialog = screen.getByRole('dialog', { name: 'Send Revision Request' })
    expect(dialog).toBeTruthy()

    const email = within(dialog).getByLabelText(
      "Requester's email address",
    ) as HTMLInputElement
    expect(email.value).toBe('maria@school.edu')
    expect(email.readOnly).toBe(true)

    const subject = within(dialog).getByLabelText('Email subject') as HTMLInputElement
    expect(subject.value).toBe('Action Required: Reservation Revision – GSO-2026-00007')
    expect(within(dialog).getByLabelText('Message to the requester')).toBeTruthy()
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeTruthy()
    expect(
      (within(dialog).getByRole('button', { name: 'Send Email' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
  })

  it('sends the editable subject and message and reports success', async () => {
    state.mutateAsync.mockResolvedValue({
      revision_email_sent: true,
      revision_email_detail: 'Revision request email sent to maria@school.edu.',
    })
    renderPage()

    fireEvent.click(revisionButton() as HTMLElement)
    const dialog = screen.getByRole('dialog', { name: 'Send Revision Request' })

    fireEvent.change(within(dialog).getByLabelText('Email subject'), {
      target: { value: 'Room layout revision' },
    })
    fireEvent.change(within(dialog).getByLabelText('Message to the requester'), {
      target: { value: 'Please adjust the end time to 5:00 PM.' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send Email' }))

    await waitFor(() =>
      expect(state.mutateAsync).toHaveBeenCalledWith({
        action: 'request_changes',
        body: {
          subject: 'Room layout revision',
          message: 'Please adjust the end time to 5:00 PM.',
        },
      }),
    )
    await waitFor(() =>
      expect(state.toast).toHaveBeenCalledWith(
        'Revision request email sent to maria@school.edu.',
      ),
    )
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: 'Send Revision Request' }),
      ).toBeNull(),
    )
  })

  it('keeps the dialog open and reports a delivery failure', async () => {
    state.mutateAsync.mockResolvedValue({
      revision_email_sent: false,
      revision_email_detail:
        'Revision request recorded, but the email could not be sent. Please try again.',
    })
    renderPage()

    fireEvent.click(revisionButton() as HTMLElement)
    const dialog = screen.getByRole('dialog', { name: 'Send Revision Request' })
    fireEvent.change(within(dialog).getByLabelText('Message to the requester'), {
      target: { value: 'Please add two more tables.' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send Email' }))

    await waitFor(() =>
      expect(state.toast).toHaveBeenCalledWith(
        'Revision request recorded, but the email could not be sent. Please try again.',
        'error',
      ),
    )
    expect(
      screen.getByRole('dialog', { name: 'Send Revision Request' }),
    ).toBeTruthy()
  })

  it('shows the backend error and keeps the dialog open when sending fails', async () => {
    state.mutateAsync.mockRejectedValue(
      new ApiError(400, 'A revision request message is required.'),
    )
    renderPage()

    fireEvent.click(revisionButton() as HTMLElement)
    const dialog = screen.getByRole('dialog', { name: 'Send Revision Request' })
    fireEvent.change(within(dialog).getByLabelText('Message to the requester'), {
      target: { value: 'Please revise.' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send Email' }))

    await waitFor(() =>
      expect(state.toast).toHaveBeenCalledWith(
        'A revision request message is required.',
        'error',
      ),
    )
    expect(
      screen.getByRole('dialog', { name: 'Send Revision Request' }),
    ).toBeTruthy()
  })
})

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

describe('ReservationDetailPage payment calculation', () => {
  it('previews the automatic 50% downpayment and saves only type plus amount paid', async () => {
    state.paymentMutate.mockResolvedValue(undefined)
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      status: 'PENDING',
      estimated_total: '10000.00',
      payment: paymentInfo(),
    })
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /update payment information/i }))

    expect(screen.getAllByText('Total reservation price').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Required downpayment (50%)').length).toBeGreaterThan(0)
    expect(screen.getAllByText('₱5,000.00').length).toBeGreaterThan(0)

    fireEvent.change(screen.getByLabelText('Payment type'), {
      target: { value: 'FULL_PAYMENT' },
    })
    expect(screen.getAllByText('Required payment (100%)').length).toBeGreaterThan(0)
    expect(screen.getAllByText('₱10,000.00').length).toBeGreaterThan(0)

    fireEvent.change(screen.getByLabelText('Amount paid (₱)'), {
      target: { value: '7000.00' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save payment$/i }))

    await waitFor(() =>
      expect(state.paymentMutate).toHaveBeenCalledWith({
        payment_type: 'FULL_PAYMENT',
        amount_paid: '7000.00',
      }),
    )
  })
})

describe('ReservationDetailPage approval payment warning', () => {
  function approveButton() {
    return screen.getByRole('button', { name: /^approve$/i })
  }

  it('warns before approving an unpaid external reservation and only approves after acknowledgement', async () => {
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      status: 'PENDING',
      payment: paymentInfo(),
    })
    renderPage()

    fireEvent.click(approveButton())
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByText('Payment Required Before Approval')).toBeTruthy()
    expect(
      within(dialog).getByText(
        'This external reservation has not received any payment yet. The required downpayment is 50% of the total reservation price.',
      ),
    ).toBeTruthy()
    expect(within(dialog).getByText('Total Reservation Price')).toBeTruthy()
    expect(within(dialog).getByText('Required Downpayment (50%)')).toBeTruthy()
    expect(within(dialog).getByText('Remaining Downpayment')).toBeTruthy()
    expect(within(dialog).getByText('Payment Status')).toBeTruthy()
    expect(within(dialog).getByText('Unpaid')).toBeTruthy()
    expect(within(dialog).getByText('₱10,000.00')).toBeTruthy()
    expect(within(dialog).getAllByText('₱5,000.00')).toHaveLength(2)
    expect(state.mutateAsync).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByRole('button', { name: /^approve anyway$/i }))

    await waitFor(() =>
      expect(state.mutateAsync).toHaveBeenCalledWith({
        action: 'approve',
        body: { comment: '', acknowledge_payment_warning: true },
      }),
    )
  })

  it('keeps the reservation pending when the warning is cancelled', async () => {
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      status: 'PENDING',
      payment: paymentInfo(),
    })
    renderPage()

    fireEvent.click(approveButton())
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(
      within(dialog).getByRole('button', { name: /^wait for downpayment$/i }),
    )

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(state.mutateAsync).not.toHaveBeenCalled()
  })

  it('shows the outstanding balance for a partially paid reservation', async () => {
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      status: 'PENDING',
      payment: paymentInfo({
        status: 'PARTIALLY_PAID',
        status_label: 'Partially Paid',
        amount_paid: '2000.00',
        remaining_balance: '3000.00',
      }),
    })
    renderPage()

    fireEvent.click(approveButton())
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByText('Payment Required Before Approval')).toBeTruthy()
    expect(
      within(dialog).getByText(
        'This external reservation has not completed the required downpayment.',
      ),
    ).toBeTruthy()
    expect(
      within(dialog).getByText('This external reservation has only been partially paid.'),
    ).toBeTruthy()
    expect(within(dialog).getByText('₱3,000.00')).toBeTruthy()
  })

  it('approves a fully paid reservation without a warning', async () => {
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      status: 'PENDING',
      payment: paymentInfo({
        status: 'FULLY_PAID',
        status_label: 'Fully Paid',
        amount_paid: '5000.00',
        remaining_balance: '0.00',
        is_outstanding: false,
        approval_warning: null,
      }),
    })
    renderPage()

    fireEvent.click(approveButton())

    await waitFor(() =>
      expect(state.mutateAsync).toHaveBeenCalledWith({
        action: 'approve',
        body: { comment: '' },
      }),
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it("uses the backend's fresh payment data when a cached page says it is settled", async () => {
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      status: 'PENDING',
      payment: paymentInfo({
        status: 'FULLY_PAID',
        status_label: 'Fully Paid',
        amount_paid: '5000.00',
        remaining_balance: '0.00',
        is_outstanding: false,
        approval_warning: null,
      }),
    })
    state.mutateAsync.mockRejectedValue(
      new ApiError(409, 'Payment outstanding.', {
        code: 'PAYMENT_WARNING',
        payment: paymentInfo({
          status: 'PARTIALLY_PAID',
          status_label: 'Partially Paid',
          amount_paid: '2000.00',
          remaining_balance: '3000.00',
        }),
      }),
    )
    renderPage()

    fireEvent.click(approveButton())
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByText('Payment Required Before Approval')).toBeTruthy()
    expect(within(dialog).getByText('₱3,000.00')).toBeTruthy()
  })

  it('shows not found instead of cached data when the reservation was deleted', () => {
    state.isError = true
    state.error = new ApiError(404, 'Not found.')
    state.reservation = reservation()
    renderPage()

    expect(screen.getByText('Reservation not found')).toBeTruthy()
    expect(screen.queryByText('Science Fair')).toBeNull()
  })

  it('shows not found for an invalid reservation id without treating it as loading', () => {
    state.routeId = 'not-a-number'
    state.reservation = null as unknown as ReservationDetail
    renderPage()

    expect(screen.getByText('Reservation not found')).toBeTruthy()
  })

  it('still warns from the loaded reservation when the refresh fails', async () => {
    state.reservation = reservation({
      requester_type: 'EXTERNAL',
      status: 'PENDING',
      payment: paymentInfo(),
    })
    state.refetch.mockRejectedValue(new Error('offline'))
    renderPage()

    fireEvent.click(approveButton())
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByText('Payment Required Before Approval')).toBeTruthy()
    expect(state.mutateAsync).not.toHaveBeenCalled()
  })
})
