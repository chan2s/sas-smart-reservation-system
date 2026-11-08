import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { OrganizationSelectionPage } from './OrganizationSelectionPage'

afterEach(cleanup)

describe('OrganizationSelectionPage', () => {
  it('offers both account-free organization flows', () => {
    render(
      <MemoryRouter initialEntries={['/reserve']}>
        <OrganizationSelectionPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Choose your organization' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Internal Organization/ }).getAttribute('href')).toBe('/reserve/internal')
    expect(screen.getByRole('link', { name: /External Organization/ }).getAttribute('href')).toBe('/reserve/external')
    expect(screen.queryByRole('link', { name: /login|register/i })).toBeNull()
  })
})
