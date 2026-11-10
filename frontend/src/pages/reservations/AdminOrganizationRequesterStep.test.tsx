import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const queryState = vi.hoisted(() => ({
  internal: { data: [] as unknown[], isLoading: false, isError: false },
  external: { data: { results: [] as unknown[] }, isFetching: false, isError: false },
}))

vi.mock('@/hooks/queries', () => ({
  useInternalOrganizations: () => queryState.internal,
  useOrganizations: () => queryState.external,
}))

import { AdminOrganizationRequesterStep } from './ReservationWizardPage'

afterEach(() => {
  cleanup()
  queryState.internal.data = []
  queryState.external.data = { results: [] }
})

function renderStep(requesterType: 'CAMPUS' | 'EXTERNAL', onSelectOrganization = vi.fn()) {
  return {
    onSelectOrganization,
    ...render(
      <MemoryRouter>
        <AdminOrganizationRequesterStep
          requesterType={requesterType}
          onRequesterType={vi.fn()}
          selectedOrganizationId=""
          onSelectOrganization={onSelectOrganization}
          search=""
          onSearch={vi.fn()}
          showErrors={false}
        />
      </MemoryRouter>,
    ),
  }
}

describe('AdminOrganizationRequesterStep', () => {
  it('searches registered internal organizations and removes campus account search', () => {
    const cas = {
      id: 5,
      organization_code: 'CAS',
      acronym: 'CAS',
      organization_name: 'College of Arts and Sciences',
      display_name: 'CAS — College of Arts and Sciences',
      organization_type: 'INTERNAL' as const,
      organization_type_label: 'Internal Organization',
      is_internal: true as const,
      is_active: true,
      verification_status: 'APPROVED' as const,
      verification_status_label: 'Approved',
      status_label: 'Approved',
    }
    queryState.internal.data = [cas]
    const { onSelectOrganization } = renderStep('CAMPUS')

    expect(screen.getByRole('heading', { name: 'Who is this reservation for?' })).toBeTruthy()
    expect(screen.getByText('Select the organization requesting this reservation. You can create reservations on behalf of internal or external organizations.')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /Internal Organization/ }).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /External Organization/ })).toBeTruthy()
    expect(screen.getByLabelText('Search internal organizations')).toBeTruthy()
    expect(screen.queryByText('Campus User')).toBeNull()
    expect(screen.queryByLabelText(/Search campus users/i)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /CAS.*College of Arts and Sciences/ }))
    expect(onSelectOrganization).toHaveBeenCalledWith(cas)
  })

  it('searches approved external organizations from the existing organization directory', () => {
    const externalOrg = {
      id: 12,
      organization_code: 'EXT-0012',
      organization_name: 'ABC National High School',
      organization_type: 'SCHOOL_UNIVERSITY' as const,
      organization_type_label: 'School/University',
      is_internal: false,
      is_active: true,
      verification_status: 'APPROVED' as const,
      verification_status_label: 'Approved',
      contact_person: 'School Principal',
      contact_email: 'principal@example.edu',
    }
    queryState.external.data = { results: [externalOrg] }
    const { onSelectOrganization } = renderStep('EXTERNAL')

    expect(screen.getByLabelText('Search external organizations')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /ABC National High School/ }))
    expect(onSelectOrganization).toHaveBeenCalledWith(externalOrg)
    expect(screen.getByRole('link', { name: 'Manage organizations' })).toHaveAttribute('href', '/organizations')
  })
})
