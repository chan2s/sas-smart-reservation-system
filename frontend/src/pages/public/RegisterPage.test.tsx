import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const apiState = vi.hoisted(() => ({
  register: vi.fn(),
  googleStart: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: { ...actual.api, register: apiState.register, googleStart: apiState.googleStart },
  }
})

vi.mock('@/hooks/queries', () => ({
  useInternalOrganizations: () => ({ data: [] }),
}))

vi.mock('@/components/chatbot/ChatWidget', () => ({
  ChatWidget: () => null,
}))

import { ApiError } from '@/lib/api'
import { RegisterPage } from './RegisterPage'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function LoginProbe() {
  const location = useLocation()
  return <p>login reached {location.search}</p>
}

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<LoginProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

function fillRegistrationForm({ confirmPassword = 'pass12345' } = {}) {
  fireEvent.change(screen.getByLabelText('First name'), { target: { value: 'Juan' } })
  fireEvent.change(screen.getByLabelText('Last name'), { target: { value: 'Dela Cruz' } })
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'requester' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'juan@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pass12345' } })
  fireEvent.change(screen.getByLabelText('Confirm password'), {
    target: { value: confirmPassword },
  })
}

async function submitBasicRegistration() {
  fillRegistrationForm()
  fireEvent.click(screen.getByRole('button', { name: 'Create Account' }))
  await waitFor(() => expect(apiState.register).toHaveBeenCalled())
}

describe('RegisterPage', () => {
  it('shows backend field validation instead of a generic 400', async () => {
    apiState.register.mockRejectedValue(
      new ApiError(400, 'Request failed (400)', {
        username: ['A user with that username already exists.'],
      }),
    )

    renderRegister()
    await submitBasicRegistration()

    expect(
      await screen.findByText('A user with that username already exists.'),
    ).toBeTruthy()
    expect(screen.queryByText('Request failed (400)')).toBeNull()
  })

  it('redirects to login with a success notice code without logging the user in', async () => {
    apiState.register.mockResolvedValue({ id: 1 })

    renderRegister()
    await submitBasicRegistration()

    expect(await screen.findByText('login reached ?registered=success')).toBeTruthy()
    expect(apiState.register).toHaveBeenCalledWith(
      expect.objectContaining({
        username: 'requester',
        email: 'juan@example.com',
        password: 'pass12345',
      }),
    )
  })

  it('never sends the confirmation password to the backend', async () => {
    apiState.register.mockResolvedValue({ id: 1 })

    renderRegister()
    await submitBasicRegistration()

    expect(apiState.register).toHaveBeenCalledTimes(1)
    expect(apiState.register.mock.calls[0][0]).not.toHaveProperty('confirm_password')
  })

  it('blocks submission and reports a mismatch while the passwords differ', async () => {
    renderRegister()
    fillRegistrationForm({ confirmPassword: 'different99' })

    expect(await screen.findByText('Passwords do not match')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Create Account' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Create Account' }))
    expect(apiState.register).not.toHaveBeenCalled()
  })

  it('clears the mismatch error as soon as both passwords match', async () => {
    renderRegister()
    fillRegistrationForm({ confirmPassword: 'different99' })
    expect(await screen.findByText('Passwords do not match')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'pass12345' },
    })

    expect(screen.queryByText('Passwords do not match')).toBeNull()
    expect(screen.getByRole('button', { name: 'Create Account' })).toBeEnabled()
  })

  it('toggles each password field independently', () => {
    renderRegister()

    const password = screen.getByLabelText('Password') as HTMLInputElement
    const confirmPassword = screen.getByLabelText('Confirm password') as HTMLInputElement
    expect(password.type).toBe('password')
    expect(confirmPassword.type).toBe('password')

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password.type).toBe('text')
    expect(confirmPassword.type).toBe('password')

    fireEvent.click(screen.getByRole('button', { name: 'Show confirm password' }))
    expect(password.type).toBe('text')
    expect(confirmPassword.type).toBe('text')

    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(password.type).toBe('password')
    expect(confirmPassword.type).toBe('text')
  })

  it('shows a loading label and prevents duplicate submissions', async () => {
    let resolveRegister: (value: unknown) => void = () => {}
    apiState.register.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRegister = resolve
        }),
    )

    renderRegister()
    fillRegistrationForm()
    fireEvent.click(screen.getByRole('button', { name: 'Create Account' }))

    const submitting = await screen.findByRole('button', { name: 'Creating account...' })
    expect(submitting).toBeDisabled()

    fireEvent.click(submitting)
    expect(apiState.register).toHaveBeenCalledTimes(1)

    resolveRegister({ id: 1 })
    expect(await screen.findByText('login reached ?registered=success')).toBeTruthy()
  })

  it('starts the Google flow with the register intent, not the login intent', async () => {
    apiState.googleStart.mockResolvedValue({
      authorize_url: 'https://accounts.google.com/o/oauth2/v2/auth',
    })

    renderRegister()
    fireEvent.click(screen.getByRole('button', { name: /Continue with Google/i }))

    await waitFor(() =>
      expect(apiState.googleStart).toHaveBeenCalledWith(window.location.origin, 'register'),
    )
    // Starting the OAuth flow never submits the form itself.
    expect(apiState.register).not.toHaveBeenCalled()
  })

  it('marks password fields as required with new-password autocomplete', () => {
    renderRegister()

    const password = screen.getByLabelText('Password')
    const confirmPassword = screen.getByLabelText('Confirm password')

    expect(password).toBeRequired()
    expect(confirmPassword).toBeRequired()
    expect(password).toHaveAttribute('autocomplete', 'new-password')
    expect(confirmPassword).toHaveAttribute('autocomplete', 'new-password')
  })
})
