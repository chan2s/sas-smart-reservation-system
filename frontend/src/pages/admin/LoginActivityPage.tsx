import { useEffect, useState } from 'react'
import { format } from 'date-fns'
import { Search } from 'lucide-react'
import { api } from '@/lib/api'
import type { LoginActivity } from '@/lib/types'
import { PageHeader } from '@/components/ui/Misc'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select } from '@/components/ui/Form'
import {
  CardField,
  ResponsiveTable,
  TableCell,
  TablePagination,
  TablePrimary,
  TableRow,
  TableSecondary,
  TableStatusBadge,
} from '@/components/ui/Table'

/** Human tone for the recorded authentication method. */
const METHOD_TONE: Record<string, 'brand' | 'sky'> = {
  GOOGLE: 'brand',
  PASSWORD: 'sky',
}

/**
 * Administrator login activity.
 *
 * Shows successful sign-ins, newest first, with the identity snapshot taken at
 * sign-in time (so the history survives account deletion). Rows are written
 * server-side; the frontend only reads them, and only an administrator can.
 */
export function LoginActivityPage() {
  const [rows, setRows] = useState<LoginActivity[] | null>(null)
  const [count, setCount] = useState(0)
  const [numPages, setNumPages] = useState(1)
  const [page, setPage] = useState(1)
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [method, setMethod] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  useEffect(() => {
    let cancelled = false
    setRows(null)
    setError(false)
    api
      .loginActivity({
        search: query || undefined,
        method: method || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
      })
      .then((data) => {
        if (cancelled) return
        setRows(data.results)
        setCount(data.count)
        setNumPages(Math.max(1, Math.ceil(data.count / 20)))
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [query, method, dateFrom, dateTo, page, reloadKey])

  function applySearch(value: string) {
    setQuery(value.trim())
    setPage(1)
  }

  const toolbar = (
    <div className="grid gap-3 border-b border-line bg-soft/60 px-5 py-4 sm:grid-cols-2 lg:grid-cols-4">
      <form
        className="relative lg:col-span-1"
        onSubmit={(event) => {
          event.preventDefault()
          applySearch(search)
        }}
      >
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          aria-hidden
        />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search name or email…"
          className="pl-9"
          aria-label="Search login activity"
        />
      </form>

      <Field label="Method" htmlFor="method-filter">
        <Select
          id="method-filter"
          value={method}
          onChange={(event) => {
            setMethod(event.target.value)
            setPage(1)
          }}
        >
          <option value="">All methods</option>
          <option value="PASSWORD">Email/Password</option>
          <option value="GOOGLE">Google OAuth</option>
        </Select>
      </Field>

      <Field label="From" htmlFor="date-from">
        <Input
          id="date-from"
          type="date"
          value={dateFrom}
          onChange={(event) => {
            setDateFrom(event.target.value)
            setPage(1)
          }}
        />
      </Field>

      <Field label="To" htmlFor="date-to">
        <Input
          id="date-to"
          type="date"
          value={dateTo}
          onChange={(event) => {
            setDateTo(event.target.value)
            setPage(1)
          }}
        />
      </Field>
    </div>
  )

  const columns = [
    { key: 'user', label: 'User' },
    { key: 'email', label: 'Email' },
    { key: 'role', label: 'Role' },
    { key: 'when', label: 'Login date & time' },
    { key: 'method', label: 'Method' },
    { key: 'status', label: 'Status' },
  ]

  // ``ResponsiveTable`` renders ``errorState`` whenever it is *set*, and hides
  // the table while it is. It must therefore only be passed once a request has
  // actually failed — passing it unconditionally replaces a loaded table (and
  // the loading skeleton) with the failure message.
  const errorPanel = (
    <div className="px-6 py-14 text-center">
      <p className="text-[15px] font-semibold text-ink">Unable to load login activity</p>
      <p className="mt-1 text-sm text-body">Please try again in a moment.</p>
      <Button
        variant="secondary"
        size="sm"
        className="mt-4"
        onClick={() => setReloadKey((value) => value + 1)}
      >
        Retry
      </Button>
    </div>
  )

  const timestamp = (value: string) =>
    value ? format(new Date(value), 'MMM d, yyyy · h:mm a') : '—'

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Administration"
        title="User login activity"
        description="Successful sign-ins across SAS RESERVE, most recent first."
      />

      <p className="mt-4 text-xs text-muted">
        {count} login event{count === 1 ? '' : 's'}
      </p>

      <ResponsiveTable<LoginActivity>
        containerClassName="mt-2"
        columns={columns}
        data={rows ?? []}
        rowKey={(item) => item.id}
        minWidthClassName="min-w-[820px]"
        isLoading={rows === null && !error}
        isEmpty={rows !== null && rows.length === 0}
        errorState={error ? errorPanel : undefined}
        emptyState={
          <div className="px-6 py-14 text-center">
            <p className="text-[15px] font-semibold text-ink">No login events</p>
            <p className="mt-1 text-sm text-body">
              Nothing recorded for this filter yet.
            </p>
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
              <TablePrimary>{item.user_name || 'Unknown user'}</TablePrimary>
              {item.user === null && <TableSecondary>Account deleted</TableSecondary>}
            </TableCell>
            <TableCell>
              <TablePrimary className="font-normal">{item.email || '—'}</TablePrimary>
            </TableCell>
            <TableCell>
              <TableSecondary>{item.role_label || '—'}</TableSecondary>
            </TableCell>
            <TableCell>
              <TableSecondary>{timestamp(item.created_at)}</TableSecondary>
            </TableCell>
            <TableCell>
              <TableStatusBadge
                status={item.method}
                label={item.method_label}
                tone={METHOD_TONE[item.method] ?? 'neutral'}
              />
            </TableCell>
            <TableCell>
              <TableStatusBadge
                status={item.status}
                label={item.status_label}
                tone={item.status === 'SUCCESS' ? 'emerald' : 'rose'}
              />
            </TableCell>
          </TableRow>
        )}
        renderMobileCard={(item) => (
          <div className="space-y-3 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <TablePrimary>{item.user_name || 'Unknown user'}</TablePrimary>
                <TableSecondary>{item.email || '—'}</TableSecondary>
              </div>
              <TableStatusBadge
                status={item.method}
                label={item.method_label}
                tone={METHOD_TONE[item.method] ?? 'neutral'}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <CardField label="Role">{item.role_label || '—'}</CardField>
              <CardField label="Status">
                <TableStatusBadge
                  status={item.status}
                  label={item.status_label}
                  tone={item.status === 'SUCCESS' ? 'emerald' : 'rose'}
                />
              </CardField>
              <CardField label="Login date & time" className="col-span-2">
                {timestamp(item.created_at)}
              </CardField>
            </div>
          </div>
        )}
      />
    </div>
  )
}
