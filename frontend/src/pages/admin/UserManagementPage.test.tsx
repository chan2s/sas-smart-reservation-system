import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { AdminUser } from '@/lib/types'

const apiState = vi.hoisted(() => ({
  adminUsers: vi.fn(),
  setUserStatus: vi.fn(),
  deleteUser: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    adminUsers: apiState.adminUsers,
    setUserStatus: apiState.setUserStatus,
    deleteUser: apiState.deleteUser,
  },
  // The real helper only formats ApiError objects; these tests assert on the
  // fallback copy the page passes for each action.
  apiErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 99, role: 'ADMIN' }, loading: false }),
}))

import { UserManagementPage } from './UserManagementPage'
import { ToastProvider } from '@/components/ui/Toast'

function account(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 1,
    username: 'requester',
    first_name: 'Maria',
    last_name: 'Santos',
    display_name: 'Maria Santos',
    email: 'maria@school.edu',
    role: 'REQUESTER',
    role_label: 'Requester',
    affiliation: '',
    affiliation_label: '',
    organization_ref: null,
    is_active: true,
    is_staff: false,
    is_superuser: false,
    date_joined: '2026-10-11T16:57:21+0800',
    last_login: null,
    is_protected: false,
    ...overrides,
  }
}

const activeUser = account()
const inactiveUser = account({
  id: 2,
  username: 'retired',
  first_name: 'Rita',
  last_name: 'Reyes',
  display_name: 'Rita Reyes',
  email: 'rita@school.edu',
  is_active: false,
})

/** A DRF-shaped paginated user-list response. */
function respond(results: AdminUser[], count = results.length) {
  return {
    count,
    next: count > results.length ? 'http://localhost/api/auth/users/?page=2' : null,
    previous: null,
    results,
  }
}

function renderPage() {
  return render(
    <ToastProvider>
      <UserManagementPage />
    </ToastProvider>,
  )
}

/** The row's action button, rendered once per desktop row and mobile card. */
function rowAction(name: string) {
  const buttons = screen.getAllByRole('button', { name })
  expect(buttons.length).toBeGreaterThan(0)
  return buttons[0]
}

afterEach(() => {
  cleanup()
  apiState.adminUsers.mockReset()
  apiState.setUserStatus.mockReset()
  apiState.deleteUser.mockReset()
})

describe('UserManagementPage', () => {
  it('renders the user table from a paginated response', async () => {
    apiState.adminUsers.mockResolvedValue(respond([activeUser, inactiveUser], 21))

    renderPage()

    await waitFor(() => expect(screen.getAllByText('Maria Santos').length).toBeGreaterThan(0))
    // The success path must never show the failure state.
    expect(screen.queryByText('Unable to load users')).not.toBeInTheDocument()
    expect(screen.queryByText('Please try again in a moment.')).not.toBeInTheDocument()
    expect(screen.getAllByText('Rita Reyes').length).toBeGreaterThan(0)
    expect(screen.getByText('21 users')).toBeInTheDocument()
    // 21 records over DRF's 20-per-page size means a second page exists.
    expect(screen.getAllByRole('button', { name: '2' }).length).toBeGreaterThan(0)
  })

  it('shows each account status as Active or Inactive', async () => {
    apiState.adminUsers.mockResolvedValue(respond([activeUser, inactiveUser]))

    renderPage()

    await waitFor(() => expect(screen.getAllByText('Maria Santos').length).toBeGreaterThan(0))
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Inactive').length).toBeGreaterThan(0)
  })

  it('requests the page number and reports count metadata', async () => {
    apiState.adminUsers.mockResolvedValue(respond([activeUser]))

    renderPage()

    await waitFor(() => expect(apiState.adminUsers).toHaveBeenCalled())
    expect(apiState.adminUsers).toHaveBeenCalledWith({
      search: undefined,
      role: undefined,
      is_active: undefined,
      page: 1,
    })
  })

  it('filters by account status', async () => {
    apiState.adminUsers.mockResolvedValue(respond([activeUser, inactiveUser]))

    renderPage()
    await waitFor(() => expect(apiState.adminUsers).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'inactive' } })
    await waitFor(() =>
      expect(apiState.adminUsers).toHaveBeenLastCalledWith({
        search: undefined,
        role: undefined,
        is_active: 'false',
        page: 1,
      }),
    )

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'active' } })
    await waitFor(() =>
      expect(apiState.adminUsers).toHaveBeenLastCalledWith({
        search: undefined,
        role: undefined,
        is_active: 'true',
        page: 1,
      }),
    )

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: '' } })
    await waitFor(() =>
      expect(apiState.adminUsers).toHaveBeenLastCalledWith({
        search: undefined,
        role: undefined,
        is_active: undefined,
        page: 1,
      }),
    )
  })

  it('confirms before deactivating and explains the consequences', async () => {
    apiState.adminUsers.mockResolvedValue(respond([activeUser]))
    apiState.setUserStatus.mockResolvedValue({
      detail: 'Account deactivated.',
      user: { ...activeUser, is_active: false },
    })

    renderPage()
    await waitFor(() => expect(screen.getAllByText('Maria Santos').length).toBeGreaterThan(0))

    fireEvent.click(rowAction('Deactivate Maria Santos'))

    // Nothing happens until the administrator confirms.
    expect(apiState.setUserStatus).not.toHaveBeenCalled()
    expect(screen.getByText(/can no longer sign in with email\/password or with Google/i)).toBeInTheDocument()
    expect(screen.getByText(/their account is kept/i)).toBeInTheDocument()
    expect(screen.getByText('You can reactivate the account at any time.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Deactivate account' }))

    await waitFor(() =>
      expect(apiState.setUserStatus).toHaveBeenCalledWith(activeUser.id, false),
    )
    // Success message + list refresh.
    await waitFor(() => expect(screen.getByText('Account deactivated.')).toBeInTheDocument())
    await waitFor(() => expect(apiState.adminUsers.mock.calls.length).toBeGreaterThanOrEqual(2))
  })

  it('confirms before reactivating an inactive account', async () => {
    apiState.adminUsers.mockResolvedValue(respond([inactiveUser]))
    apiState.setUserStatus.mockResolvedValue({
      detail: 'Account activated.',
      user: { ...inactiveUser, is_active: true },
    })

    renderPage()
    await waitFor(() => expect(screen.getAllByText('Rita Reyes').length).toBeGreaterThan(0))

    fireEvent.click(rowAction('Activate Rita Reyes'))

    expect(apiState.setUserStatus).not.toHaveBeenCalled()
    expect(
      screen.getByText(/they will be able to sign in again with their existing credentials/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Activate account' }))

    await waitFor(() =>
      expect(apiState.setUserStatus).toHaveBeenCalledWith(inactiveUser.id, true),
    )
    await waitFor(() => expect(screen.getByText('Account activated.')).toBeInTheDocument())
  })

  it('reports a failed status change without changing the row', async () => {
    apiState.adminUsers.mockResolvedValue(respond([activeUser]))
    apiState.setUserStatus.mockRejectedValue(new Error('nope'))

    renderPage()
    await waitFor(() => expect(screen.getAllByText('Maria Santos').length).toBeGreaterThan(0))

    fireEvent.click(rowAction('Deactivate Maria Santos'))
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate account' }))

    await waitFor(() =>
      expect(screen.getByText('Unable to deactivate this account.')).toBeInTheDocument(),
    )
    // The dialog stays open so the administrator can retry or cancel.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('does not offer deactivation for the signed-in administrator', async () => {
    apiState.adminUsers.mockResolvedValue(
      respond([account({ id: 99, username: 'me', display_name: 'SAS Admin', role: 'ADMIN', role_label: 'Administrator', is_protected: true })]),
    )

    renderPage()
    await waitFor(() => expect(screen.getAllByText('SAS Admin').length).toBeGreaterThan(0))

    const button = rowAction('You cannot deactivate your own account')
    expect(button).toBeDisabled()
  })

  it('shows the failure state only when the request fails', async () => {
    apiState.adminUsers.mockRejectedValue(new Error('network down'))

    renderPage()

    await waitFor(() => expect(screen.getByText('Unable to load users')).toBeInTheDocument())
  })
})
