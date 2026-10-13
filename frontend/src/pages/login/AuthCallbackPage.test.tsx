import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const state = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => state.current,
}))

import { AuthCallbackPage } from './AuthCallbackPage'

/**
 * The OAuth callback decides WHERE an authenticated user lands. Administrators
 * must go straight to the dashboard; only unfinished non-administrators are
 * routed to the affiliation step.
 */
function renderCallback(user: Record<string, unknown> | null, loading = false) {
  state.current = { user, loading }
  return render(
    <MemoryRouter initialEntries={['/auth/callback']}>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/dashboard" element={<div>Dashboard route</div>} />
        <Route
          path="/onboarding/affiliation"
          element={<div>Affiliation route</div>}
        />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe('AuthCallbackPage routing', () => {
  it('sends an unfinished regular user to the affiliation step', () => {
    renderCallback({ role: 'REQUESTER', has_affiliation: false })
    expect(screen.getByText('Affiliation route')).toBeInTheDocument()
  })

  it('sends an administrator to the dashboard, never to onboarding', () => {
    renderCallback({ role: 'ADMIN', has_affiliation: false })
    expect(screen.getByText('Dashboard route')).toBeInTheDocument()
  })

  it('sends an affiliated regular user to the dashboard', () => {
    renderCallback({ role: 'REQUESTER', has_affiliation: true })
    expect(screen.getByText('Dashboard route')).toBeInTheDocument()
  })
})
