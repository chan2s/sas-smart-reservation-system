import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Real ApiError + isDeactivatedAccountError: the test constructs the exact
// 403 body the Django login endpoint now returns for a deactivated account.
const apiState = vi.hoisted(() => ({
  login: vi.fn(),
  googleStart: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: { ...actual.api, login: apiState.login, googleStart: apiState.googleStart },
  }
})

const authState = vi.hoisted(() => ({
  login: vi.fn(),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: authState.login,
    // The page reads nothing else from the context.
  }),
}))

vi.mock('@/components/chatbot/ChatWidget', () => ({
  ChatWidget: () => null,
}))

import { LoginPage } from './LoginPage'

const DEACTIVATED_MESSAGE =
  'This account has been deactivated. Please contact the SAS Office to restore access.'

afterEach(cleanup)

function renderLogin(initialEntries?: string[]) {
  return render(
    <MemoryRouter initialEntries={initialEntries ?? ['/login']}>
      <LoginPage />
    </MemoryRouter>,
  )
}

async function submitCredentials(username: string, password: string) {
  fireEvent.change(screen.getByLabelText('Username'), {
    target: { value: username },
  })
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: password },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(authState.login).toHaveBeenCalled())
}

describe('LoginPage — deactivated account modal', () => {
  it('a deactivated password login opens the modal, not the inline error', async () => {
    authState.login.mockRejectedValue(
      new (await import('@/lib/api')).ApiError(
        403,
        DEACTIVATED_MESSAGE,
        { detail: DEACTIVATED_MESSAGE, code: 'account_deactivated' },
      ),
    )
    renderLogin()
    await submitCredentials('req', 'pass1234!')

    // Modal with the required heading and the exact message.
    expect(await screen.findByText('Account Deactivated')).toBeTruthy()
    expect(screen.getByText(DEACTIVATED_MESSAGE)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'OK' })).toBeTruthy()

    // The condition must not also appear as the inline form error.
    const inlineAlerts = screen.queryAllByRole('alert')
    for (const alert of inlineAlerts) {
      expect(alert.textContent).not.toContain('deactivated')
    }
  })

  it('invalid credentials keep the existing inline error and show no modal', async () => {
    authState.login.mockRejectedValue(
      new (await import('@/lib/api')).ApiError(
        401,
        'No active account found with the given credentials',
      ),
    )
    renderLogin()
    await submitCredentials('req', 'wrong-pass!')
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(
      'No active account found with the given credentials',
    )
    expect(screen.queryByText('Account Deactivated')).toBeNull()
  })

  it('the Google OAuth deactivated redirect (?google_error=…) opens the modal', () => {
    renderLogin(['/login?google_error=account_deactivated'])
    expect(screen.getByText('Account Deactivated')).toBeTruthy()
    expect(screen.getByText(DEACTIVATED_MESSAGE)).toBeTruthy()
  })

  it('OK dismisses the modal and scrubs the google_error parameter', async () => {
    const { container } = renderLogin([
      '/login?google_error=account_deactivated',
    ])
    fireEvent.click(screen.getByRole('button', { name: 'OK' }))
    await waitFor(() =>
      expect(screen.queryByText('Account Deactivated')).toBeNull(),
    )
    expect(container.textContent).not.toContain('deactivated')
  })
})
