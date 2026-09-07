import { useEffect, useState } from 'react'
import { History, Search } from 'lucide-react'
import { format } from 'date-fns'
import { api, type AuditLogEntry } from '@/lib/api'
import { PageHeader, EmptyState, Skeleton } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Form'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

const ACTION_GROUPS: { label: string; actions: { value: string; label: string }[] }[] = [
  {
    label: 'All activity',
    actions: [{ value: '', label: 'All' }],
  },
  {
    label: 'Authentication',
    actions: [
      { value: 'LOGIN', label: 'Logins' },
      { value: 'LOGIN_2FA', label: '2FA logins' },
      { value: 'REGISTER', label: 'Registrations' },
    ],
  },
  {
    label: 'Reservations',
    actions: [
      { value: 'RESERVATION_CREATED', label: 'Created' },
      { value: 'RESERVATION_APPROVED', label: 'Approved' },
      { value: 'RESERVATION_REJECTED', label: 'Rejected' },
      { value: 'RESERVATION_CANCELLED', label: 'Cancelled' },
    ],
  },
  {
    label: 'Check-in',
    actions: [
      { value: 'CHECK_IN', label: 'Check-ins' },
      { value: 'EARLY_CHECK_IN', label: 'Early check-ins' },
      { value: 'CHECK_OUT', label: 'Check-outs' },
    ],
  },
  {
    label: 'Equipment',
    actions: [
      { value: 'EQUIPMENT_CREATED', label: 'Created' },
      { value: 'EQUIPMENT_EDITED', label: 'Edited' },
      { value: 'EQUIPMENT_REMOVED', label: 'Removed' },
      { value: 'EQUIPMENT_IMAGE', label: 'Image changes' },
    ],
  },
]

const TONE_BY_ACTION: Record<string, string> = {
  LOGIN: 'bg-status-available-bg text-status-available',
  LOGIN_2FA: 'bg-status-available-bg text-status-available',
  REGISTER: 'bg-brand-soft text-brand',
  RESERVATION_APPROVED: 'bg-status-available-bg text-status-available',
  RESERVATION_REJECTED: 'bg-status-rejected-bg text-status-rejected',
  RESERVATION_CANCELLED: 'bg-softer text-muted',
  RESERVATION_CREATED: 'bg-brand-soft text-brand',
  EARLY_CHECK_IN: 'bg-status-pending-bg text-status-pending',
  CHECK_IN: 'bg-status-available-bg text-status-available',
  CHECK_OUT: 'bg-softer text-muted',
  EQUIPMENT_REMOVED: 'bg-status-rejected-bg text-status-rejected',
  SETTINGS_CHANGED: 'bg-softer text-muted',
}

export function AuditLogPage() {
  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null)
  const [action, setAction] = useState('')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [count, setCount] = useState(0)
  const [numPages, setNumPages] = useState(1)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setEntries(null)
    api
      .auditLog({ action: action || undefined, search: query || undefined, page })
      .then((data) => {
        if (cancelled) return
        setEntries(data.results)
        setCount(data.count)
        setNumPages(data.num_pages)
        setError(false)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [action, query, page])

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="Administration"
        title="Audit log"
        description="Who changed what, and when — approvals, check-ins, equipment changes, and security events."
      />

      {/* Filters */}
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-1.5">
          {ACTION_GROUPS.flatMap((group) => group.actions).map((option) => (
            <button
              key={option.value || 'all'}
              type="button"
              onClick={() => {
                setAction(option.value)
                setPage(1)
              }}
              className={cn(
                'rounded-full px-3 py-1.5 text-xs font-medium transition-colors duration-150',
                action === option.value
                  ? 'bg-brand text-white shadow-sm'
                  : 'border border-line bg-surface text-body hover:bg-soft',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <form
          className="relative sm:w-64"
          onSubmit={(event) => {
            event.preventDefault()
            setQuery(search.trim())
            setPage(1)
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search entries…"
            className="pl-9"
          />
        </form>
      </div>

      <p className="mt-4 text-xs text-muted">
        {count} entr{count === 1 ? 'y' : 'ies'}
      </p>

      <Card className="mt-2">
        {error && (
          <EmptyState
            title="Unable to load the audit log"
            description="Please try again in a moment."
          />
        )}
        {!error && entries === null && <Skeleton className="h-64" />}
        {!error && entries !== null && entries.length === 0 && (
          <EmptyState
            title="No matching entries"
            description="Nothing recorded for this filter yet."
          />
        )}
        {!error && entries !== null && entries.length > 0 && (
          <ul className="divide-y divide-line">
            {entries.map((entry) => (
              <li key={entry.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-soft text-muted">
                  <History className="size-4" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{entry.actor_name}</span>
                    <span
                      className={cn(
                        'rounded-md px-1.5 py-0.5 text-[11px] font-semibold',
                        TONE_BY_ACTION[entry.action] ?? 'bg-softer text-muted',
                      )}
                    >
                      {entry.action_label}
                    </span>
                    <span className="text-xs text-muted">
                      {format(new Date(entry.created_at), 'MMM d, yyyy · h:mm a')}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate text-sm text-body">
                    {entry.object_repr || entry.object_type}
                    {entry.object_id && entry.action.startsWith('RESERVATION') ? ` (${entry.object_id})` : ''}
                  </p>
                  {entry.detail && <p className="mt-0.5 text-xs text-muted">{entry.detail}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Pagination */}
      {numPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <Button
            size="sm"
            variant="secondary"
            disabled={page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            Previous
          </Button>
          <span className="text-xs text-muted">
            Page {page} of {numPages}
          </span>
          <Button
            size="sm"
            variant="secondary"
            disabled={page >= numPages}
            onClick={() => setPage((value) => Math.min(numPages, value + 1))}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}
