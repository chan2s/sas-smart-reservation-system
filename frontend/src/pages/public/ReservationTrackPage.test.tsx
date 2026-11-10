import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const apiState = vi.hoisted(() => ({
  track: vi.fn(),
  legacyTrack: vi.fn(),
  upload: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  endpoints: {
    trackReservationById: apiState.track,
    trackPublicReservation: apiState.legacyTrack,
    uploadPublicApprovalLetter: apiState.upload,
  },
}))

import { ReservationTrackPage } from './ReservationTrackPage'

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/track-reservation?reservation_id=SAS-2026-00024']}>
        <Routes>
          <Route path="/track-reservation" element={<ReservationTrackPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const result = {
  reservation_id: 'SAS-2026-00024',
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
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  apiState.track.mockReset()
  apiState.legacyTrack.mockReset()
  apiState.upload.mockReset()
})

describe('ReservationTrackPage', () => {
  it('tracks a direct reservation ID without asking for representative email', async () => {
    apiState.track.mockResolvedValue(result)
    renderPage()

    expect(screen.getByText('Enter your reservation ID to check the current status of your reservation request.')).toBeTruthy()
    expect(screen.queryByLabelText(/representative email/i)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    await waitFor(() => {
      expect(apiState.track).toHaveBeenCalledWith('SAS-2026-00024')
    })
    expect(await screen.findByText('Community Assembly')).toBeTruthy()
  })

  it('shows a friendly message for an invalid reservation ID', async () => {
    apiState.track.mockRejectedValue(new Error('Not found'))
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "We couldn't find a reservation with that ID.",
    )
  })

  it('offers camera and file upload when the approval letter is missing', async () => {
    apiState.track.mockResolvedValue(result)
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    expect(await screen.findByText('This document is required before your reservation can be approved. Take a photo of your signed event approval letter or upload an image file.')).toBeTruthy()
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

    await waitFor(() => expect(apiState.upload).toHaveBeenCalledWith('SAS-2026-00024', file))
    expect(await screen.findByText('Approval Letter Submitted')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Take Photo' })).toBeNull()
  })
})
