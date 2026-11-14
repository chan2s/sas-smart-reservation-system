import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { User } from '@/lib/types'
import { api } from '@/lib/api'

const state = vi.hoisted(() => ({
  user: null as unknown as User,
  isViewOnly: false,
  toast: vi.fn(),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: state.user,
    updateUser: vi.fn(),
    isViewOnly: state.isViewOnly,
  }),
}))

vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: state.toast }),
}))

vi.mock('@/lib/api', () => ({
  api: {
    patch: vi.fn(),
    post: vi.fn(),
    postFileUrl: vi.fn().mockResolvedValue('blob:approval-preview'),
    get: vi.fn((path: string) => Promise.resolve(
      path.includes('/versions/')
        ? []
        : {
            authorized_signatory_name: 'Configured Signatory',
            credentials: 'Ph.D.',
            designation: 'Campus Director',
            approval_label: 'Approved by:',
            letter_title: 'RESERVATION APPROVAL LETTER',
            approval_message: 'Approved for {{event_name}} at {{facility_name}}.',
            introductory_paragraphs: '',
            instructions_template: '',
            additional_content: '',
            footer_disclaimer: '',
            version: 1,
          },
    )),
  },
  endpoints: {
    pushSubscriptions: vi.fn().mockResolvedValue([]),
    pushPublicKey: vi.fn(),
    registerPushSubscription: vi.fn(),
    updatePushSubscription: vi.fn(),
    removePushSubscription: vi.fn(),
  },
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
  vi.clearAllMocks()
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

  it('keeps approval letter configuration out of Account Settings', () => {
    state.user = { ...requester(), role: 'ADMIN' }
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('heading', { name: /approval letter/i })).not.toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalledWith('/api/admin/settings/approval-letter/')
  })
})
