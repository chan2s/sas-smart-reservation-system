import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const apiState = vi.hoisted(() => ({
  track: vi.fn(),
  legacyTrack: vi.fn(),
  upload: vi.fn(),
  editDetails: vi.fn(),
  requestRescheduleOTP: vi.fn(),
  verifyRescheduleOTP: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    endpoints: {
      ...actual.endpoints,
      trackReservationById: apiState.track,
      trackPublicReservation: apiState.legacyTrack,
      uploadPublicApprovalLetter: apiState.upload,
      publicReservationEditDetails: apiState.editDetails,
      requestPublicRescheduleOTP: apiState.requestRescheduleOTP,
      verifyPublicRescheduleOTP: apiState.verifyRescheduleOTP,
    },
  }
})

import { ApiError } from '@/lib/api'
import { ReservationTrackPage } from './ReservationTrackPage'

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/track-reservation?reservation_id=GSO-2026-00024']}>
        <Routes>
          <Route path="/track-reservation" element={<ReservationTrackPage />} />
          <Route path="/reserve/:organizationType" element={<p>public edit form route</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const result = {
  reservation_id: 'GSO-2026-00024',
  status: 'PENDING',
  status_label: 'Pending',
  event_name: 'Community Assembly',
  organization: 'Community Association',
  facility: 'Community Hall',
  date: '2026-12-14',
  start_time: '09:00:00',
  end_time: '11:00:00',
  created_at: '2026-11-08T09:00:00+08:00',
  approval_document_status: 'AWAITING' as const,
  approval_document_status_label: 'Awaiting Approval Letter',
  can_edit: true,
  reschedule: { can_request: false, request: null },
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  apiState.track.mockReset()
  apiState.legacyTrack.mockReset()
  apiState.upload.mockReset()
  apiState.editDetails.mockReset()
  apiState.requestRescheduleOTP.mockReset()
  apiState.verifyRescheduleOTP.mockReset()
})

const approvedForReschedule = {
  ...result,
  status: 'APPROVED',
  status_label: 'Approved',
  approval_document_status: 'NOT_REQUIRED' as const,
  approval_document_status_label: 'Not required for this reservation',
  can_edit: false,
  reschedule: { can_request: true, request: null },
}

async function openRescheduleForm() {
  apiState.track.mockResolvedValue(approvedForReschedule)
  renderPage()
  fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Request Reschedule' }))
}

function fillSchedule({
  start,
  end,
  reason = 'Conflict with another event.',
}: {
  start: string
  end: string
  reason?: string
}) {
  fireEvent.change(screen.getByLabelText('Requested new date'), {
    target: { value: '2026-12-15' },
  })
  fireEvent.change(screen.getByLabelText('Requested start time'), {
    target: { value: start },
  })
  fireEvent.change(screen.getByLabelText('Requested end time'), {
    target: { value: end },
  })
  fireEvent.change(screen.getByLabelText('Reason for the request'), {
    target: { value: reason },
  })
}

describe('ReservationTrackPage', () => {
  it('tracks a direct reservation ID without asking for representative email', async () => {
    apiState.track.mockResolvedValue(result)
    renderPage()

    expect(screen.getByText('Enter your reservation ID to check the current status of your reservation request.')).toBeTruthy()
    expect(screen.queryByLabelText(/representative email/i)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    await waitFor(() => {
      expect(apiState.track).toHaveBeenCalledWith('GSO-2026-00024')
    })
    expect(await screen.findByText('Community Assembly')).toBeTruthy()
    expect(await screen.findByRole('button', { name: 'Edit Reservation' })).toBeTruthy()
  })

  it('opens the shared public edit form without requesting an email address', async () => {
    apiState.track.mockResolvedValue(result)
    apiState.editDetails.mockResolvedValue({
      id: 24,
      requester_type: 'CAMPUS',
      organization: 'Community Association',
      facility_id: 1,
      date: '2026-12-14',
      start_time: '09:00:00',
      end_time: '11:00:00',
      event_name: 'Community Assembly',
      event_type: 'ACADEMIC',
      purpose: 'Meeting',
      description: '',
      expected_participants: 20,
      notes: '',
      contact_person: 'Requester',
      contact_phone: '',
      items: [],
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Reservation' }))
    await waitFor(() => expect(apiState.editDetails).toHaveBeenCalledWith('GSO-2026-00024'))
    expect(await screen.findByText('public edit form route')).toBeTruthy()
  })

  it('shows a friendly message for an invalid reservation ID', async () => {
    apiState.track.mockRejectedValue(new Error('Not found'))
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "We couldn't find a reservation with that ID.",
    )
  })

  it('offers camera and file upload when the optional approval letter is not attached yet', async () => {
    apiState.track.mockResolvedValue(result)
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    expect(
      await screen.findByText(
        'Optional. Upload your signed event approval letter now or provide it later — your reservation stays in the GSO review queue either way. Take a photo or upload an image file.',
      ),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Take Photo' })).toBeTruthy()
    expect(screen.getByLabelText('Upload approval letter image')).toBeTruthy()
  })

  it('hides the upload prompt when a letter is already submitted', async () => {
    apiState.track.mockResolvedValue({
      ...result,
      approval_document_status: 'SUBMITTED',
      approval_document_status_label: 'Approval Letter Submitted',
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    expect(await screen.findByText('Approval Letter Submitted')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Take Photo' })).toBeNull()
    expect(screen.queryByLabelText('Upload approval letter image')).toBeNull()
  })

  it('submits an OTP-verified reschedule request and shows its pending status', async () => {
    apiState.track.mockResolvedValue({
      ...result,
      status: 'APPROVED',
      status_label: 'Approved',
      approval_document_status: 'NOT_REQUIRED',
      approval_document_status_label: 'Not required for this reservation',
      can_edit: false,
      reschedule: { can_request: true, request: null },
    })
    apiState.requestRescheduleOTP.mockResolvedValue({
      verification_session: 'session-token',
      expires_at: '2026-11-21T10:05:00+08:00',
      resend_available_at: '2026-11-21T10:01:00+08:00',
      email_hint: 'r***@example.com',
    })
    apiState.verifyRescheduleOTP.mockResolvedValue({
      ...result,
      status: 'APPROVED',
      status_label: 'Approved',
      approval_document_status: 'NOT_REQUIRED',
      approval_document_status_label: 'Not required for this reservation',
      can_edit: false,
      reschedule: {
        can_request: false,
        request: {
          status: 'PENDING',
          status_label: 'Pending Admin Review',
          requested_date: '2026-12-15',
          requested_start_time: '13:00:00',
          requested_end_time: '15:00:00',
          reason: 'Conflict with another event.',
          submitted_at: '2026-11-21T10:00:00+08:00',
          rejection_reason: '',
          admin_message: '',
        },
      },
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Request Reschedule' }))

    fireEvent.change(screen.getByLabelText('Requested new date'), {
      target: { value: '2026-12-15' },
    })
    fireEvent.change(screen.getByLabelText('Requested start time'), {
      target: { value: '13:00' },
    })
    fireEvent.change(screen.getByLabelText('Requested end time'), {
      target: { value: '15:00' },
    })
    fireEvent.change(screen.getByLabelText('Reason for the request'), {
      target: { value: 'Conflict with another event.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request and send code' }))

    await waitFor(() =>
      expect(apiState.requestRescheduleOTP).toHaveBeenCalledWith('GSO-2026-00024', {
        requested_date: '2026-12-15',
        requested_start_time: '13:00',
        requested_end_time: '15:00',
        reason: 'Conflict with another event.',
      }),
    )

    fireEvent.change(await screen.findByLabelText('Email verification code'), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Verify and submit request' }))

    await waitFor(() =>
      expect(apiState.verifyRescheduleOTP).toHaveBeenCalledWith(
        'GSO-2026-00024',
        'session-token',
        '123456',
      ),
    )
    expect(await screen.findByText('Pending Admin Review')).toBeTruthy()
  })

  it('blocks the initial OTP request when the end time is not after the start time', async () => {
    await openRescheduleForm()

    fillSchedule({ start: '13:00', end: '13:00' })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request and send code' }))
    expect(
      await screen.findByText('The end time must be after the start time.'),
    ).toBeTruthy()

    fillSchedule({ start: '13:00', end: '12:00' })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request and send code' }))
    expect(
      await screen.findByText('The end time must be after the start time.'),
    ).toBeTruthy()

    expect(apiState.requestRescheduleOTP).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Requested end time')).toHaveValue('12:00')
    expect(screen.getByLabelText('Reason for the request')).toHaveValue(
      'Conflict with another event.',
    )
  })

  it('shows a backend field error beside its field without duplicating it as an alert', async () => {
    await openRescheduleForm()
    apiState.requestRescheduleOTP.mockRejectedValue(
      new ApiError(400, 'Request failed (400)', {
        requested_end_time: ['The end time must be after the start time.'],
      }),
    )

    fillSchedule({ start: '13:00', end: '15:00' })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request and send code' }))

    expect(
      await screen.findByText('The end time must be after the start time.'),
    ).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByLabelText('Requested start time')).toHaveValue('13:00')
    expect(screen.getByLabelText('Requested end time')).toHaveValue('15:00')
  })

  it('shows a non-field backend validation error as a form-level alert', async () => {
    await openRescheduleForm()
    apiState.requestRescheduleOTP.mockRejectedValue(
      new ApiError(400, 'Request failed (400)', {
        detail: 'A reschedule request for this reservation is already awaiting review.',
      }),
    )

    fillSchedule({ start: '13:00', end: '15:00' })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request and send code' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A reschedule request for this reservation is already awaiting review.',
    )
  })

  it('resends the OTP with the latest values and blocks an invalid range', async () => {
    apiState.requestRescheduleOTP.mockResolvedValue({
      verification_session: 'session-token',
      expires_at: '2026-11-21T10:05:00+08:00',
      resend_available_at: '2026-11-21T10:01:00+08:00',
      email_hint: 'r***@example.com',
    })
    await openRescheduleForm()

    fillSchedule({ start: '13:00', end: '15:00' })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request and send code' }))
    expect(await screen.findByLabelText('Email verification code')).toBeTruthy()
    expect(apiState.requestRescheduleOTP).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('Requested end time'), {
      target: { value: '12:00' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send a new code' }))
    expect(
      await screen.findByText('The end time must be after the start time.'),
    ).toBeTruthy()
    expect(apiState.requestRescheduleOTP).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('Requested end time'), {
      target: { value: '16:00' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send a new code' }))
    await waitFor(() =>
      expect(apiState.requestRescheduleOTP).toHaveBeenLastCalledWith(
        'GSO-2026-00024',
        {
          requested_date: '2026-12-15',
          requested_start_time: '13:00',
          requested_end_time: '16:00',
          reason: 'Conflict with another event.',
        },
      ),
    )
  })

  it('shows a backend field error on resend without losing the OTP session', async () => {
    apiState.requestRescheduleOTP.mockResolvedValue({
      verification_session: 'session-token',
      expires_at: '2026-11-21T10:05:00+08:00',
      resend_available_at: '2026-11-21T10:01:00+08:00',
      email_hint: 'r***@example.com',
    })
    await openRescheduleForm()

    fillSchedule({ start: '13:00', end: '15:00' })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request and send code' }))
    expect(await screen.findByLabelText('Email verification code')).toBeTruthy()

    apiState.requestRescheduleOTP.mockRejectedValue(
      new ApiError(400, 'Request failed (400)', {
        requested_end_time: ['The end time must be after the start time.'],
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Send a new code' }))

    expect(
      await screen.findByText('The end time must be after the start time.'),
    ).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByLabelText('Email verification code')).toBeTruthy()
    expect(apiState.requestRescheduleOTP).toHaveBeenCalledTimes(2)
  })

  it('uploads a selected image and refreshes the displayed status', async () => {
    class TestURL extends URL {}
    Object.assign(TestURL, {
      createObjectURL: vi.fn(() => 'blob:approval-preview'),
      revokeObjectURL: vi.fn(),
    })
    vi.stubGlobal('URL', TestURL)
    apiState.track.mockResolvedValue(result)
    apiState.upload.mockResolvedValue({
      ...result,
      approval_document_status: 'SUBMITTED',
      approval_document_status_label: 'Approval Letter Submitted',
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    const file = new File(['valid image bytes'], 'approval.png', { type: 'image/png' })
    fireEvent.change(await screen.findByLabelText('Upload approval letter image'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit approval letter' }))

    await waitFor(() => expect(apiState.upload).toHaveBeenCalledWith('GSO-2026-00024', file))
    expect(await screen.findByText('Approval Letter Submitted')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Take Photo' })).toBeNull()
  })
})
