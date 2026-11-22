import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from '@/lib/api'
import type { Equipment } from '@/lib/types'

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  onClose: vi.fn(),
}))

vi.mock('@/hooks/queries', () => ({
  useDeleteEquipment: () => ({ mutate: state.mutate, isPending: false }),
  useEquipmentHistory: () => ({ data: [] }),
}))

import { RemoveEquipmentModal } from './RemoveEquipmentModal'
import { ToastProvider } from '@/components/ui/Toast'

afterEach(cleanup)

beforeEach(() => {
  state.mutate.mockReset()
  state.onClose.mockReset()
})

/** Only the fields the modal reads; the rest is supplied by the API. */
function fixture(overrides: Partial<Equipment> = {}): Equipment {
  return {
    id: 42,
    name: 'Folding Chair ApiV',
    has_history: false,
    ...overrides,
  } as Equipment
}

type MutationOptions = {
  /* undefined is the real payload for a 204 hard delete. */
  onSuccess: (result?: { archived?: boolean }) => void
  onError: (error: unknown) => void
}

function renderModal(equipment = fixture()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RemoveEquipmentModal equipment={equipment} onClose={state.onClose} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function confirmDelete() {
  fireEvent.click(screen.getByRole('button', { name: 'Delete Equipment' }))
}

describe('RemoveEquipmentModal', () => {
  it('sends only one DELETE when confirm is clicked twice', () => {
    renderModal()
    const confirm = screen.getByRole('button', { name: 'Delete Equipment' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    expect(state.mutate).toHaveBeenCalledTimes(1)
  })

  it('closes after a 204 hard delete, whose body is empty', () => {
    state.mutate.mockImplementation(
      (_unused: undefined, options: MutationOptions) => options.onSuccess(undefined),
    )
    renderModal()
    confirmDelete()
    expect(state.onClose).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Folding Chair ApiV deleted.')).toBeTruthy()
  })

  it('closes and explains an archived result for equipment with history', () => {
    state.mutate.mockImplementation(
      (_unused: undefined, options: MutationOptions) =>
        options.onSuccess({ archived: true }),
    )
    renderModal(fixture({ has_history: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Archive Equipment' }))
    expect(state.onClose).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText('Folding Chair ApiV archived. Existing records remain intact.'),
    ).toBeTruthy()
  })

  it('refreshes the list and closes when the item no longer exists (404)', async () => {
    state.mutate.mockImplementation(
      (_variables: undefined, options: MutationOptions) =>
        options.onError(new ApiError(404, 'Not found')),
    )
    renderModal()

    confirmDelete()

    expect(
      await screen.findByText(
        'Folding Chair ApiV no longer exists. The equipment list has been refreshed.',
      ),
    ).toBeTruthy()
    await waitFor(() => expect(state.onClose).toHaveBeenCalledTimes(1))
  })

  it('shows the backend reason and keeps the dialog open on other failures', async () => {
    state.mutate.mockImplementation(
      (_variables: undefined, options: MutationOptions) =>
        options.onError(
          new ApiError(500, 'Server error', { detail: 'Database unavailable.' }),
        ),
    )
    renderModal()

    confirmDelete()

    expect(await screen.findByText('Database unavailable.')).toBeTruthy()
    expect(state.onClose).not.toHaveBeenCalled()
  })
})
