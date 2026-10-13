import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const state = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => state.current,
}))

import { AffiliationPrompt } from './AffiliationPrompt'

/**
 * The prompt is driven by role + affiliation state, so every branch is pinned
 * here: regular users are nudged, administrators never are, and nothing is
 * shown before the session finishes loading.
 */
function renderPrompt(
  overrides: Record<string, unknown> = {},
  path = '/dashboard',
) {
  state.current = {
    user: { role: 'REQUESTER', has_affiliation: false },
    loading: false,
    ...overrides,
  }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AffiliationPrompt />
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe('AffiliationPrompt', () => {
  it('invites a regular user with no affiliation to complete it', () => {
    renderPrompt()
    expect(screen.getByText(/affiliated with NORSU/i)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /complete profile/i }).getAttribute('href'),
    ).toBe('/onboarding/affiliation')
  })

  it('never prompts an administrator, even with no affiliation', () => {
    const { container } = renderPrompt({
      user: { role: 'ADMIN', has_affiliation: false },
    })
    expect(container.textContent).toBe('')
  })

  it('stays hidden for a user who already completed affiliation', () => {
    const { container } = renderPrompt({
      user: { role: 'REQUESTER', has_affiliation: true },
    })
    expect(container.textContent).toBe('')
  })

  it('shows nothing while the session is still loading', () => {
    const { container } = renderPrompt({
      loading: true,
      user: { role: 'REQUESTER', has_affiliation: false },
    })
    expect(container.textContent).toBe('')
  })

  it('does not nag on the affiliation page itself', () => {
    const { container } = renderPrompt({}, '/onboarding/affiliation')
    expect(container.textContent).toBe('')
  })
})
