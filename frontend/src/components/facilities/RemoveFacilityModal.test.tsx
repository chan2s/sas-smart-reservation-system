import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from '@/lib/api'
import type { Facility } from '@/lib/types'

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  onClose: vi.fn(),
}))

vi.mock('@/hooks/queries', () => ({
  useDeleteFacility: () => ({ mutate: state.mutate, isPending: false }),
}))

import { RemoveFacilityModal } from './RemoveFacilityModal'
import { ToastProvider } from '@/components/ui/Toast'

afterEach(cleanup)

beforeEach(() => {
  state.mutate.mockReset()
  state.onClose.mockReset()
})

/** Only the fields the modal reads; the rest is supplied by the API. */
function fixture(overrides: Partial<Facility> = {}): Facility {
  return {
    id: 7,
    name: 'AVR_DBG',
    has_history: false,
    reservation_count: 0,
    ...overrides,
  } as Facility
}

type MutationOptions = {
  /* undefined is the real payload for a 204 hard delete. */
  onSuccess: (result?: { archived?: boolean }) => void
  onError: (error: unknown) => void
}

function renderModal(facility = fixture()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RemoveFacilityModal facility={facility} onClose={state.onClose} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('RemoveFacilityModal', () => {
  it('sends only one DELETE when confirm is clicked twice', () => {
    renderModal()
    const confirm = screen.getByRole('button', { name: 'Delete Facility' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    expect(state.mutate).toHaveBeenCalledTimes(1)
  })

  it('closes after a 204 hard delete, whose body is empty', () => {
    state.mutate.mockImplementation(
      (_unused: undefined, options: MutationOptions) => options.onSuccess(undefined),
    )
    renderModal()
    fireEvent.click(screen.getByRole('button', { name: 'Delete Facility' }))
    expect(state.onClose).toHaveBeenCalledTimes(1)
    expect(screen.getByText('AVR_DBG deleted.')).toBeTruthy()
  })

  it('closes and explains an archived result for a facility with history', () => {
    state.mutate.mockImplementation(
      (_unused: undefined, options: MutationOptions) =>
        options.onSuccess({ archived: true }),
    )
    renderModal(fixture({ has_history: true, reservation_count: 3 }))
    fireEvent.click(screen.getByRole('button', { name: 'Archive Facility' }))
    expect(state.onClose).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText('AVR_DBG archived. Existing reservations remain intact.'),
    ).toBeTruthy()
  })

  it('stays open and shows the backend reason when deletion fails', () => {
    state.mutate.mockImplementation(
      (_unused: undefined, options: MutationOptions) =>
        options.onError(
          new ApiError(400, 'Bad request', {
            detail: 'AVR_DBG still has assigned equipment.',
          }),
        ),
    )
    renderModal()
    fireEvent.click(screen.getByRole('button', { name: 'Delete Facility' }))
    expect(
      screen.getByText('AVR_DBG still has assigned equipment.'),
    ).toBeTruthy()
    expect(state.onClose).not.toHaveBeenCalled()
  })
})
