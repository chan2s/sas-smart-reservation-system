import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { User } from '@/lib/types'

const state = vi.hoisted(() => ({
  user: null as unknown as User,
  isViewOnly: false,
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: state.user,
    updateUser: vi.fn(),
    isViewOnly: state.isViewOnly,
  }),
}))

vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('@/lib/api', () => ({
  api: { patch: vi.fn() },
}))

vi.mock('@/hooks/usePwa', () => ({
  usePwa: () => ({
    promptAvailable: false,
    promptDismissed: false,
    isInstalled: false,
    canShowIosInstructions: false,
    promptInstall: vi.fn().mockResolvedValue('accepted'),
  }),
}))

import { SettingsPage } from './SettingsPage'

function requester(): User {
  return {
    id: 7,
    username: 'maria',
    first_name: 'Maria',
    last_name: 'Santos',
    display_name: 'Maria Santos',
    email: 'maria@campus.edu',
    role: 'REQUESTER',
    organization: '',
    affiliation_label: 'Student',
    has_affiliation: true,
  } as unknown as User
}

afterEach(() => {
  cleanup()
})

describe('SettingsPage', () => {
  it('offers the Install SAS RESERVE App section to signed-in users', () => {
    state.user = requester()
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Install SAS RESERVE App' })).toBeInTheDocument()
    expect(
      screen.getByText(
        'Install SAS RESERVE on your device for quicker access and an app-like experience.',
      ),
    ).toBeInTheDocument()
  })
})
