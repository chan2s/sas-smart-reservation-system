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
  apiState.track.mockReset()
  apiState.legacyTrack.mockReset()
  apiState.upload.mockReset()
})

describe('ReservationTrackPage', () => {
  it('tracks a direct reservation ID URL after representative email verification', async () => {
    apiState.track.mockResolvedValue(result)
    renderPage()

    expect(screen.getByText('Enter your reservation ID to check the current status of your reservation request.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Representative email'), {
      target: { value: 'alex@example.org' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    await waitFor(() => {
      expect(apiState.track).toHaveBeenCalledWith('SAS-2026-00024', 'alex@example.org')
    })
    expect(await screen.findByText('Community Assembly')).toBeTruthy()
  })

  it('shows a friendly message for an invalid reservation ID/email pair', async () => {
    apiState.track.mockRejectedValue(new Error('Not found'))
    renderPage()
    fireEvent.change(screen.getByLabelText('Representative email'), {
      target: { value: 'wrong@example.org' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Track Reservation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "We couldn't find a reservation matching that ID and representative email.",
    )
  })
})
