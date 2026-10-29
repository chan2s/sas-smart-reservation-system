import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { format } from 'date-fns'
import { KeyRound, Pencil, Power, Search, Trash2, UserCog, UserPlus } from 'lucide-react'
import { api, apiErrorMessage } from '@/lib/api'
import type {
  AdminUser,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  Role,
} from '@/lib/types'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/ui/Misc'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select } from '@/components/ui/Form'
import { Modal } from '@/components/ui/Modal'
import {
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from '@/components/organizations/OrganizationStatusNotice'
import {
  CardActions,
  CardField,
  ResponsiveTable,
  TableActions,
  TableCell,
  TablePagination,
  TablePrimary,
  TableRow,
  TableSecondary,
  TableStatusBadge,
} from '@/components/ui/Table'

const ROLE_TONE: Record<Role, 'brand' | 'sky' | 'neutral'> = {
  ADMIN: 'brand',
  STAFF: 'sky',
  REQUESTER: 'neutral',
  ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE: 'brand',
}

type StatusFilter = '' | 'active' | 'inactive'
type FormMode = 'create' | 'edit'

interface UserFormState {
  username: string
  email: string
  first_name: string
  last_name: string
  role: Role
  password: string
}

const EMPTY_FORM: UserFormState = {
  username: '',
  email: '',
  first_name: '',
  last_name: '',
  role: 'REQUESTER',
  password: '',
}

/** The API's `is_active` query value for a status filter choice. */
function statusParam(status: StatusFilter): 'true' | 'false' | undefined {
  if (status === 'active') return 'true'
  if (status === 'inactive') return 'false'
  return undefined
}

/**
 * Administrator user management.
 *
 * Lists every registered account with search, role and status filtering plus
 * pagination, and lets an administrator deactivate, reactivate, or delete an
 * eligible account after an explicit confirmation step. Every rule that
 * matters (administrator-only access, self-deactivation, protected system
 * accounts) is enforced by the Django API — this page only reflects it and
 * shows what the backend reports.
 */
export function UserManagementPage() {
  const { user: currentUser, isViewOnly } = useAuth()
  const { toast } = useToast()

  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [count, setCount] = useState(0)
  const [numPages, setNumPages] = useState(1)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [role, setRole] = useState<'' | Role>('')
  const [status, setStatus] = useState<StatusFilter>('')
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  const [pendingDelete, setPendingDelete] = useState<AdminUser | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [pendingStatus, setPendingStatus] = useState<{
    user: AdminUser
    nextActive: boolean
  } | null>(null)
  const [savingStatus, setSavingStatus] = useState(false)

  const [formMode, setFormMode] = useState<FormMode | null>(null)
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null)
  const [form, setForm] = useState<UserFormState>(EMPTY_FORM)
  const [formError, setFormError] = useState('')
  const [savingForm, setSavingForm] = useState(false)

  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [resetError, setResetError] = useState('')
  const [resettingPassword, setResettingPassword] = useState(false)
  const [credential, setCredential] = useState<{
    displayName: string
    username: string
    password: string
  } | null>(null)

  useEffect(() => {
    let cancelled = false
    setUsers(null)
    setError(false)
    api
      .adminUsers({
        search: query || undefined,
        role: role || undefined,
        is_active: statusParam(status),
        page,
      })
      .then((data) => {
        if (cancelled) return
        // A status change or deletion can empty the last page — step back so
        // the table is never blank while earlier results exist.
        if (data.results.length === 0 && data.count > 0 && page > 1) {
          setPage((value) => Math.max(1, value - 1))
          return
        }
        setUsers(data.results)
        setCount(data.count)
        setNumPages(Math.max(1, Math.ceil(data.count / 20)))
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [query, role, status, page, reloadKey])

  const refresh = useCallback(() => setReloadKey((value) => value + 1), [])

  function openCreate() {
    setEditingUser(null)
    setForm(EMPTY_FORM)
    setFormError('')
    setFormMode('create')
  }

  function openEdit(target: AdminUser) {
    setEditingUser(target)
    setForm({
      username: target.username,
      email: target.email,
      first_name: target.first_name,
      last_name: target.last_name,
      role: target.role,
      password: '',
    })
    setFormError('')
    setFormMode('edit')
  }

  function closeForm() {
    if (savingForm) return
    setFormMode(null)
    setEditingUser(null)
    setFormError('')
  }

  async function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!formMode) return
    setFormError('')

    const identity = {
      username: form.username.trim(),
      email: form.email.trim(),
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      role: form.role,
    }
    if (!identity.username || !identity.email) {
      setFormError('Username and email are required.')
      return
    }

    setSavingForm(true)
    try {
      if (formMode === 'create') {
        const payload: AdminUserCreatePayload = {
          ...identity,
          ...(form.password ? { password: form.password } : {}),
        }
        const created = await api.createUser(payload)
        toast(`Created ${created.display_name}.`)
        if (created.temporary_password) {
          setCredential({
            displayName: created.display_name,
            username: created.username,
            password: created.temporary_password,
          })
        }
        setFormMode(null)
        setEditingUser(null)
        refresh()
      } else if (editingUser) {
        const payload: AdminUserUpdatePayload = identity
        const updated = await api.updateUser(editingUser.id, payload)
        toast(`Updated ${updated.display_name}.`)
        setFormMode(null)
        setEditingUser(null)
        refresh()
      }
    } catch (err) {
      setFormError(
        apiErrorMessage(
          err,
          formMode === 'create'
            ? 'Unable to create this account.'
            : 'Unable to update this account.',
        ),
      )
    } finally {
      setSavingForm(false)
    }
  }

  function openPasswordReset(target: AdminUser) {
    setResetTarget(target)
    setResetPassword('')
    setResetError('')
  }

  function closePasswordReset() {
    if (resettingPassword) return
    setResetTarget(null)
    setResetPassword('')
    setResetError('')
  }

  async function submitPasswordReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!resetTarget) return
    setResetError('')
    setResettingPassword(true)
    try {
      const result = await api.resetUserPassword(
        resetTarget.id,
        resetPassword || undefined,
      )
      toast(result.detail)
      if (result.temporary_password) {
        setCredential({
          displayName: resetTarget.display_name,
          username: resetTarget.username,
          password: result.temporary_password,
        })
      }
      setResetTarget(null)
      setResetPassword('')
    } catch (err) {
      setResetError(
        apiErrorMessage(err, 'Unable to reset this account password.'),
      )
    } finally {
      setResettingPassword(false)
    }
  }

  const roleLocked = Boolean(
    formMode === 'edit' &&
      editingUser &&
      (editingUser.id === currentUser?.id || editingUser.is_superuser),
  )

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await api.deleteUser(pendingDelete.id)
      toast(`Deleted ${pendingDelete.display_name}.`)
      setPendingDelete(null)
      refresh()
    } catch (err) {
      toast(apiErrorMessage(err, 'Unable to delete this account.'), 'error')
    } finally {
      setDeleting(false)
    }
  }

  async function confirmStatusChange() {
    if (!pendingStatus) return
    const { user: target, nextActive } = pendingStatus
    setSavingStatus(true)
    try {
      const result = await api.setUserStatus(target.id, nextActive)
      toast(result.detail)
      setPendingStatus(null)
      // Re-read the list so the row, the active-count views, and the status
      // filter all reflect what the server stored.
      refresh()
    } catch (err) {
      toast(
        apiErrorMessage(
          err,
          nextActive
            ? 'Unable to activate this account.'
            : 'Unable to deactivate this account.',
        ),
        'error',
      )
    } finally {
      setSavingStatus(false)
    }
  }

  const toolbar = (
    <div className="flex flex-col gap-3 border-b border-line bg-soft/60 px-5 py-4 sm:flex-row sm:items-end sm:justify-between">
      <form
        className="relative flex-1 sm:max-w-xs"
        onSubmit={(event) => {
          event.preventDefault()
          setQuery(search.trim())
          setPage(1)
        }}
      >
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          aria-hidden
        />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search name, email, username…"
          className="pl-9"
          aria-label="Search users"
        />
      </form>
      <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-end">
        <div className="sm:w-44">
          <Field label="Role" htmlFor="role-filter">
            <Select
              id="role-filter"
              value={role}
              onChange={(event) => {
                setRole(event.target.value as '' | Role)
                setPage(1)
              }}
            >
              <option value="">All roles</option>
              <option value="ADMIN">Administrator</option>
              <option value="STAFF">SAS Staff</option>
              <option value="REQUESTER">Requester</option>
            </Select>
          </Field>
        </div>
        <div className="sm:w-40">
          <Field label="Status" htmlFor="status-filter">
            <Select
              id="status-filter"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as StatusFilter)
                setPage(1)
              }}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
          </Field>
        </div>
      </div>
    </div>
  )

  const columns = [
    { key: 'user', label: 'User' },
    { key: 'email', label: 'Email' },
    { key: 'role', label: 'Role' },
    { key: 'status', label: 'Account / organization' },
    { key: 'joined', label: 'Joined' },
    { key: 'actions', label: 'Actions', align: 'right' as const },
  ]

  // ``ResponsiveTable`` renders ``errorState`` whenever it is *set*, and hides
  // the table while it is. It must therefore only be passed once a request has
  // actually failed — passing it unconditionally replaces a loaded table (and
  // the loading skeleton) with the failure message.
  const errorPanel = (
    <div className="px-6 py-14 text-center">
      <p className="text-[15px] font-semibold text-ink">Unable to load users</p>
      <p className="mt-1 text-sm text-body">Please try again in a moment.</p>
      <Button variant="secondary" size="sm" className="mt-4" onClick={refresh}>
        Retry
      </Button>
    </div>
  )

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Administration"
        title="User management"
        description="Create accounts, assign roles, reset passwords, and control who can sign in."
        actions={
          !isViewOnly && (
            <Button icon={<UserPlus className="size-4" aria-hidden />} onClick={openCreate}>
              Add user
            </Button>
          )
        }
      />

      <p className="mt-4 text-xs text-muted">
        {count} user{count === 1 ? '' : 's'}
      </p>

      <ResponsiveTable<AdminUser>
        containerClassName="mt-2"
        columns={columns}
        data={users ?? []}
        rowKey={(item) => item.id}
        isLoading={users === null && !error}
        isEmpty={users !== null && users.length === 0}
        errorState={error ? errorPanel : undefined}
        emptyState={
          <div className="px-6 py-14 text-center">
            <p className="text-[15px] font-semibold text-ink">No users found</p>
            <p className="mt-1 text-sm text-body">Try a different search or filter.</p>
          </div>
        }
        toolbar={toolbar}
        footer={
          <TablePagination
            page={page}
            numPages={numPages}
            count={count}
            onPage={setPage}
          />
        }
        renderDesktopRow={(item) => (
          <TableRow key={item.id}>
            <TableCell>
              <TablePrimary>{item.display_name}</TablePrimary>
              <TableSecondary>@{item.username}</TableSecondary>
            </TableCell>
            <TableCell>
              <TablePrimary className="font-normal">{item.email || '—'}</TablePrimary>
            </TableCell>
            <TableCell>
              <Badge tone={ROLE_TONE[item.role] ?? 'neutral'}>{item.role_label}</Badge>
            </TableCell>
            <TableCell>
              <AccountStatusBadge user={item} />
            </TableCell>
            <TableCell>
              <TableSecondary>
                {item.date_joined ? format(new Date(item.date_joined), 'MMM d, yyyy') : '—'}
              </TableSecondary>
            </TableCell>
            <TableCell align="right">
              <TableActions>
                {!isViewOnly && (
                  <>
                    <EditButton item={item} onEdit={openEdit} />
                    <PasswordButton item={item} onReset={openPasswordReset} />
                    <StatusButton
                      item={item}
                      currentUserId={currentUser?.id}
                      onSelect={(target, nextActive) =>
                        setPendingStatus({ user: target, nextActive })
                      }
                    />
                    <DeleteButton
                      item={item}
                      currentUserId={currentUser?.id}
                      onDelete={setPendingDelete}
                    />
                  </>
                )}
              </TableActions>
            </TableCell>
          </TableRow>
        )}
        renderMobileCard={(item) => (
          <div className="space-y-3 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <TablePrimary>{item.display_name}</TablePrimary>
                <TableSecondary>@{item.username}</TableSecondary>
              </div>
              <Badge tone={ROLE_TONE[item.role] ?? 'neutral'}>{item.role_label}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <CardField label="Email">
                <span className="break-all">{item.email || '—'}</span>
              </CardField>
              <CardField label="Account / organization">
                <AccountStatusBadge user={item} />
              </CardField>
              <CardField label="Joined">
                {item.date_joined ? format(new Date(item.date_joined), 'MMM d, yyyy') : '—'}
              </CardField>
            </div>
            <CardActions>
              {!isViewOnly && (
                <>
                  <EditButton item={item} onEdit={openEdit} />
                  <PasswordButton item={item} onReset={openPasswordReset} />
                  <StatusButton
                    item={item}
                    currentUserId={currentUser?.id}
                    onSelect={(target, nextActive) =>
                      setPendingStatus({ user: target, nextActive })
                    }
                  />
                  <DeleteButton
                    item={item}
                    currentUserId={currentUser?.id}
                    onDelete={setPendingDelete}
                  />
                </>
              )}
            </CardActions>
          </div>
        )}
      />

      <Modal
        open={pendingStatus !== null}
        onClose={() => (savingStatus ? undefined : setPendingStatus(null))}
        title={pendingStatus?.nextActive ? 'Activate account' : 'Deactivate account'}
        size="sm"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setPendingStatus(null)}
              disabled={savingStatus}
            >
              Cancel
            </Button>
            <Button
              variant={pendingStatus?.nextActive ? 'primary' : 'danger'}
              onClick={confirmStatusChange}
              loading={savingStatus}
            >
              {pendingStatus?.nextActive ? 'Activate account' : 'Deactivate account'}
            </Button>
          </>
        }
      >
        {pendingStatus && (
          <div className="space-y-3 text-sm text-body">
            <p>
              You are about to {pendingStatus.nextActive ? 'reactivate' : 'deactivate'}{' '}
              <span className="font-semibold text-ink">
                {pendingStatus.user.display_name}
              </span>
              .
            </p>
            <div className="rounded-xl border border-line bg-soft p-3.5 text-[13px]">
              <p className="text-ink">
                <span className="font-medium">@{pendingStatus.user.username}</span>
              </p>
              <p className="text-muted">{pendingStatus.user.email || 'No email address'}</p>
              <p className="mt-1 text-muted">{pendingStatus.user.role_label}</p>
            </div>
            {pendingStatus.nextActive ? (
              <ul className="list-disc space-y-1.5 pl-5 text-[13px]">
                <li>They will be able to sign in again with their existing credentials.</li>
                <li>
                  Their role, profile, organization membership, and history are unchanged.
                </li>
                <li>Sessions that ended at deactivation are not restored — they sign in again.</li>
              </ul>
            ) : (
              <ul className="list-disc space-y-1.5 pl-5 text-[13px]">
                <li>
                  They can no longer sign in with email/password or with Google, and any
                  session they already have loses access immediately.
                </li>
                <li>
                  Their account is kept: role, profile, password, organization membership,
                  reservations, and history are all preserved.
                </li>
                <li>You can reactivate the account at any time.</li>
              </ul>
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={pendingDelete !== null}
        onClose={() => (deleting ? undefined : setPendingDelete(null))}
        title="Delete user account"
        size="sm"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setPendingDelete(null)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button variant="danger" onClick={confirmDelete} loading={deleting}>
              Delete account
            </Button>
          </>
        }
      >
        {pendingDelete && (
          <div className="space-y-3 text-sm text-body">
            <p>
              You are about to permanently delete{' '}
              <span className="font-semibold text-ink">{pendingDelete.display_name}</span>.
            </p>
            <div className="rounded-xl border border-line bg-soft p-3.5 text-[13px]">
              <p className="text-ink">
                <span className="font-medium">@{pendingDelete.username}</span>
              </p>
              <p className="text-muted">{pendingDelete.email || 'No email address'}</p>
              <p className="mt-1 text-muted">{pendingDelete.role_label}</p>
            </div>
            <p className="text-xs text-muted">
              Their reservation history is preserved (anonymized). This action cannot be
              undone. To block access without deleting anything, deactivate the account
              instead.
            </p>
          </div>
        )}
      </Modal>

      <Modal
        open={formMode !== null}
        onClose={closeForm}
        title={formMode === 'create' ? 'Add user' : 'Edit user'}
        description={
          formMode === 'create'
            ? 'Create an account and choose the role it should have in SAS RESERVE.'
            : 'Update the account profile or application role.'
        }
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={closeForm} disabled={savingForm}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="user-account-form"
              loading={savingForm}
            >
              {formMode === 'create' ? 'Create account' : 'Save changes'}
            </Button>
          </>
        }
      >
        <form id="user-account-form" className="space-y-4" onSubmit={submitForm}>
          {formError && (
            <div
              role="alert"
              className="rounded-lg border border-status-rejected/25 bg-status-rejected-bg px-3.5 py-2.5 text-[13px] text-status-rejected"
            >
              {formError}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Username" htmlFor="user-username" required>
              <Input
                id="user-username"
                value={form.username}
                onChange={(event) =>
                  setForm((current) => ({ ...current, username: event.target.value }))
                }
                autoComplete="off"
                required
              />
            </Field>
            <Field label="Email" htmlFor="user-email" required>
              <Input
                id="user-email"
                type="email"
                value={form.email}
                onChange={(event) =>
                  setForm((current) => ({ ...current, email: event.target.value }))
                }
                autoComplete="off"
                required
              />
            </Field>
            <Field label="First name" htmlFor="user-first-name">
              <Input
                id="user-first-name"
                value={form.first_name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, first_name: event.target.value }))
                }
                autoComplete="off"
              />
            </Field>
            <Field label="Last name" htmlFor="user-last-name">
              <Input
                id="user-last-name"
                value={form.last_name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, last_name: event.target.value }))
                }
                autoComplete="off"
              />
            </Field>
          </div>

          <Field
            label="Role"
            htmlFor="user-role"
            hint={
              roleLocked
                ? 'This account\u2019s role is protected and cannot be changed here.'
                : 'The active holder can review and approve reservation letters. Only one active account can hold this role.'
            }
          >
            <Select
              id="user-role"
              value={form.role}
              disabled={roleLocked}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  role: event.target.value as Role,
                }))
              }
            >
              <option value="REQUESTER">Requester</option>
              <option value="STAFF">SAS Staff</option>
              <option value="ADMIN">Administrator</option>
              <option value="ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE">
                Assistant Campus Director for Administration and Finance
              </option>
            </Select>
          </Field>

          {formMode === 'create' && (
            <Field
              label="Initial password"
              htmlFor="user-password"
              hint="Leave blank to generate a temporary password, shown once after creation."
            >
              <Input
                id="user-password"
                type="password"
                value={form.password}
                onChange={(event) =>
                  setForm((current) => ({ ...current, password: event.target.value }))
                }
                autoComplete="new-password"
              />
            </Field>
          )}
        </form>
      </Modal>

      <Modal
        open={resetTarget !== null}
        onClose={closePasswordReset}
        title="Reset password"
        description="Set a new password or generate a one-time temporary password."
        size="sm"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={closePasswordReset}
              disabled={resettingPassword}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              form="reset-password-form"
              loading={resettingPassword}
            >
              Reset password
            </Button>
          </>
        }
      >
        {resetTarget && (
          <form
            id="reset-password-form"
            className="space-y-4"
            onSubmit={submitPasswordReset}
          >
            {resetError && (
              <div
                role="alert"
                className="rounded-lg border border-status-rejected/25 bg-status-rejected-bg px-3.5 py-2.5 text-[13px] text-status-rejected"
              >
                {resetError}
              </div>
            )}
            <div className="rounded-xl border border-line bg-soft p-3.5 text-[13px]">
              <p className="font-medium text-ink">{resetTarget.display_name}</p>
              <p className="text-muted">
                @{resetTarget.username} · {resetTarget.email || 'No email address'}
              </p>
            </div>
            <Field
              label="New password"
              htmlFor="reset-password"
              hint="Leave blank to generate a temporary password, shown once after saving."
            >
              <Input
                id="reset-password"
                type="password"
                value={resetPassword}
                onChange={(event) => setResetPassword(event.target.value)}
                autoComplete="new-password"
              />
            </Field>
          </form>
        )}
      </Modal>

      <Modal
        open={credential !== null}
        onClose={() => setCredential(null)}
        title="Temporary password"
        size="sm"
        footer={<Button onClick={() => setCredential(null)}>Done</Button>}
      >
        {credential && (
          <div className="space-y-4 text-sm text-body">
            <p>
              Share these credentials with{' '}
              <span className="font-semibold text-ink">{credential.displayName}</span>.
              The temporary password is shown only once.
            </p>
            <div className="space-y-3 rounded-xl border border-line bg-soft p-3.5 text-[13px]">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                  Username
                </p>
                <code className="break-all text-ink">{credential.username}</code>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                  Temporary password
                </p>
                <code className="break-all text-ink">{credential.password}</code>
              </div>
            </div>
            <p className="text-xs text-muted">
              The account owner should change this password after signing in.
            </p>
          </div>
        )}
      </Modal>
    </div>
  )
}

/** Active / Inactive pill, driven purely by the backend's `is_active` flag. */
function AccountStatusBadge({ user }: { user: AdminUser }) {
  return (
    <div className="space-y-1">
      <TableStatusBadge
        status={user.is_active ? 'ACTIVE' : 'INACTIVE'}
        label={user.is_active ? 'Active' : 'Inactive'}
        tone={user.is_active ? 'emerald' : 'gray'}
      />
      {user.organization_ref && !user.organization_ref.is_internal && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted">Organization</span>
          <Badge tone={VERIFICATION_TONE[user.organization_ref.verification_status]}>
            {VERIFICATION_LABEL[user.organization_ref.verification_status]}
          </Badge>
        </div>
      )}
    </div>
  )
}

/** Edit profile / role. Role changes for self and superusers are locked. */
function EditButton({
  item,
  onEdit,
}: {
  item: AdminUser
  onEdit: (user: AdminUser) => void
}) {
  return (
    <Button
      variant="secondary"
      size="sm"
      icon={<Pencil className="size-4" aria-hidden />}
      aria-label={`Edit ${item.display_name}`}
      onClick={() => onEdit(item)}
    >
      Edit
    </Button>
  )
}

/** Password reset. The backend hashes the value and never returns it again. */
function PasswordButton({
  item,
  onReset,
}: {
  item: AdminUser
  onReset: (user: AdminUser) => void
}) {
  return (
    <Button
      variant="secondary"
      size="sm"
      icon={<KeyRound className="size-4" aria-hidden />}
      aria-label={`Reset password for ${item.display_name}`}
      onClick={() => onReset(item)}
    >
      Password
    </Button>
  )
}

/**
 * Activate / deactivate action.
 *
 * The blocked cases mirror the server-side guards exactly (an administrator
 * cannot deactivate their own account, and superusers are protected system
 * accounts) so the UI never offers an action the API would refuse — but the
 * API remains the authority.
 */
function StatusButton({
  item,
  currentUserId,
  onSelect,
}: {
  item: AdminUser
  currentUserId?: number
  onSelect: (user: AdminUser, nextActive: boolean) => void
}) {
  const isSelf = currentUserId === item.id
  const blockedFromDeactivating =
    item.is_active && (isSelf || item.is_superuser)
  const nextActive = !item.is_active

  const blockedReason = isSelf
    ? 'You cannot deactivate your own account'
    : 'Protected system account'

  return (
    <Button
      variant="secondary"
      size="sm"
      icon={<Power className="size-4" aria-hidden />}
      disabled={blockedFromDeactivating}
      title={blockedFromDeactivating ? blockedReason : undefined}
      aria-label={
        blockedFromDeactivating
          ? blockedReason
          : `${nextActive ? 'Activate' : 'Deactivate'} ${item.display_name}`
      }
      onClick={() => onSelect(item, nextActive)}
    >
      {nextActive ? 'Activate' : 'Deactivate'}
    </Button>
  )
}

/** Delete action, disabled with an explanation for protected accounts. */
function DeleteButton({
  item,
  currentUserId,
  onDelete,
}: {
  item: AdminUser
  currentUserId?: number
  onDelete: (user: AdminUser) => void
}) {
  const isSelf = currentUserId === item.id
  const blocked = item.is_protected
  const title = isSelf
    ? 'You cannot delete your own account'
    : item.is_superuser
      ? 'Protected system account'
      : `Delete ${item.display_name}`

  return (
    <Button
      variant="danger"
      size="sm"
      icon={isSelf ? <UserCog className="size-4" aria-hidden /> : <Trash2 className="size-4" aria-hidden />}
      disabled={blocked}
      title={title}
      aria-label={title}
      onClick={() => onDelete(item)}
    >
      {isSelf ? 'Your account' : 'Delete'}
    </Button>
  )
}
