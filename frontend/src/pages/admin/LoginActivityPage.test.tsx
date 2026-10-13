import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import type { LoginActivity } from '@/lib/types'

const apiState = vi.hoisted(() => ({
  loginActivity: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: { loginActivity: apiState.loginActivity },
  apiErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

import { LoginActivityPage } from './LoginActivityPage'
import { ToastProvider } from '@/components/ui/Toast'

/** A successful, paginated login-activity response, exactly as DRF sends it. */
const paginated = {
  count: 21,
  next: 'http://localhost/api/auth/login-activity/?page=2',
  previous: null,
  results: [
    {
      id: 1,
      user: 28,
      user_name: 'Maria Santos',
      email: 'maria@school.edu',
      role: 'REQUESTER',
      role_label: 'Requester',
      method: 'PASSWORD',
      method_label: 'Email/Password',
      status: 'SUCCESS',
      status_label: 'Success',
      ip_address: '127.0.0.1',
      created_at: '2026-10-11T16:57:21+0800',
    },
  ] as LoginActivity[],
}

function renderPage() {
  return render(
    <ToastProvider>
      <LoginActivityPage />
    </ToastProvider>,
  )
}

afterEach(() => {
  cleanup()
  apiState.loginActivity.mockReset()
})

describe('LoginActivityPage', () => {
  it('renders recorded sign-ins from a paginated response', async () => {
    apiState.loginActivity.mockResolvedValue(paginated)

    renderPage()

    await waitFor(() => expect(screen.getAllByText('Maria Santos').length).toBeGreaterThan(0))
    expect(screen.queryByText('Unable to load login activity')).not.toBeInTheDocument()
    expect(screen.getByText('21 login events')).toBeInTheDocument()
  })

  it('shows the failure state only when the request fails', async () => {
    apiState.loginActivity.mockRejectedValue(new Error('network down'))

    renderPage()

    await waitFor(() =>
      expect(screen.getByText('Unable to load login activity')).toBeInTheDocument(),
    )
  })
})
