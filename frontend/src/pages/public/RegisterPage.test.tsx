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

async function submitBasicRegistration() {
  fireEvent.change(screen.getByLabelText('First name'), { target: { value: 'Juan' } })
  fireEvent.change(screen.getByLabelText('Last name'), { target: { value: 'Dela Cruz' } })
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'requester' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'juan@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pass12345' } })
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
})
