import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { FacilityResource } from '@/lib/types'

const hooksState = vi.hoisted(() => ({
  deleteResource: vi.fn(),
}))

vi.mock('@/hooks/queries', () => ({
  useFacility: () => ({ data: { name: 'Gymnasium' }, isLoading: false }),
  useFacilityResourceAssignments: () => ({
    data: [resourceFixture()],
    isLoading: false,
  }),
  useEquipment: () => ({ data: [], isLoading: false }),
  useCreateFacilityResource: () => ({ mutateAsync: vi.fn() }),
  useUpdateFacilityResource: () => ({ mutateAsync: vi.fn() }),
  useDeleteFacilityResource: () => ({ mutateAsync: hooksState.deleteResource }),
}))

// The real dialog and toast flow under test.
import { FacilityResourcesPage } from './FacilityResourcesPage'
import { ToastProvider } from '@/components/ui/Toast'

afterEach(cleanup)

/** Only the fields the page renders; the rest is irrelevant to this test. */
function resourceFixture(): FacilityResource {
  return {
    id: 7,
    name: 'Projector Set',
    category: { name: 'Audio Visual' },
    status: 'AVAILABLE',
    status_label: 'Available',
    quantity: 2,
    total_quantity: 5,
    operator_available: true,
    operator_required: false,
    operator_fee: '150.00',
    is_active: true,
  } as unknown as FacilityResource
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/facilities/3/resources']}>
      <ToastProvider>
        <Routes>
          <Route path="/facilities/:id/resources" element={<FacilityResourcesPage />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('FacilityResourcesPage — removing an assignment', () => {
  it('asks for confirmation and names the affected resource', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    // The resource is listed on the page *and* restated inside the dialog, so
    // scope the assertion to the dialog to prove it names the affected record.
    const dialog = await screen.findByRole('dialog', { name: 'Remove resource?' })
    expect(within(dialog).getByText('Projector Set')).toBeTruthy()
    // Nothing has been deleted yet.
    expect(hooksState.deleteResource).not.toHaveBeenCalled()
  })

  it('cancel keeps the assignment without calling the API', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    await waitFor(() =>
      expect(screen.queryByText('Remove resource?')).toBeNull(),
    )
    expect(hooksState.deleteResource).not.toHaveBeenCalled()
  })

  it('confirm removes the assignment exactly once', async () => {
    hooksState.deleteResource.mockResolvedValue(undefined)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove resource' }))
    await waitFor(() =>
      expect(hooksState.deleteResource).toHaveBeenCalledTimes(1),
    )
    expect(hooksState.deleteResource).toHaveBeenCalledWith(7)
    await waitFor(() =>
      expect(screen.queryByText('Remove resource?')).toBeNull(),
    )
  })

  it('a failed removal keeps the dialog open with the error inline', async () => {
    hooksState.deleteResource.mockRejectedValue(
      new Error('Could not remove the resource.'),
    )
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove resource' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Could not remove the resource.')
    expect(screen.getByText('Remove resource?')).toBeTruthy()
  })
})
