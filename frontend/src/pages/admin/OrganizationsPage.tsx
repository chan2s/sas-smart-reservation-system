import { useState, type ReactNode } from 'react'
import {
  Building2,
  Check,
  Mail,
  MapPin,
  Phone,
  RotateCcw,
  Search,
  ShieldOff,
  Users,
  X,
} from 'lucide-react'
import { format } from 'date-fns'
import { useOrganization, useOrganizations, useVerifyOrganization } from '@/hooks/queries'
import type { OrganizationVerificationAction, OrganizationFilters } from '@/lib/api'
import type { Organization, VerificationStatus } from '@/lib/types'
import { PageHeader, EmptyState, Skeleton } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { Input, Textarea } from '@/components/ui/Form'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { useToast } from '@/components/ui/Toast'
import {
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from '@/components/organizations/OrganizationStatusNotice'
import { cn } from '@/lib/utils'

const ACTION_PAST: Record<OrganizationVerificationAction, string> = {
  approve: 'approved',
  reject: 'rejected',
  suspend: 'suspended',
  reactivate: 'reactivated',
}

const STATUS_FILTERS: { value: VerificationStatus | ''; label: string }[] = [
  { value: 'PENDING', label: 'Pending' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'SUSPENDED', label: 'Suspended' },
  { value: '', label: 'All' },
]

function rows(payload: { results?: Organization[] } | Organization[] | undefined) {
  if (!payload) return []
  if (Array.isArray(payload)) return payload
  return payload.results ?? []
}

/**
 * Administrator verification workflow for external organizations.
 *
 * Staff can see what each organization submitted, who belongs to it, and
 * approve / reject / suspend / reactivate it. Members of an organization that
 * is not Approved cannot submit facility reservations.
 */
export function OrganizationsPage() {
  const { toast } = useToast()
  const [status, setStatus] = useState<VerificationStatus | ''>('PENDING')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [notes, setNotes] = useState('')

  const filters: OrganizationFilters = {
    status: status || undefined,
    search: query || undefined,
  }
  const list = useOrganizations(filters)
  const detail = useOrganization(selectedId)
  const verify = useVerifyOrganization()

  const organizations = rows(list.data)

  function select(organization: Organization) {
    setSelectedId(organization.id)
    setNotes('')
  }

  async function decide(action: OrganizationVerificationAction) {
    if (selectedId == null) return
    try {
      await verify.mutateAsync({ id: selectedId, action, notes: notes.trim() })
      toast(`Organization ${ACTION_PAST[action]}.`)
      setNotes('')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Unable to update the organization.', 'error')
    }
  }

  const organization = detail.data ?? null

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Administration"
        title="External organizations"
        description="Review registrations from organizations outside NORSU. Only approved organizations may submit facility reservations."
      />

      {/* Filters */}
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-1.5">
          {STATUS_FILTERS.map((option) => (
            <button
              key={option.value || 'all'}
              type="button"
              onClick={() => {
                setStatus(option.value)
                setSelectedId(null)
              }}
              className={cn(
                'rounded-full px-3 py-1.5 text-xs font-medium transition-colors duration-150',
                status === option.value
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
          }}
        >
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search code, name, contact…"
            className="pl-9"
          />
        </form>
      </div>

      <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        {/* Queue */}
        <Card className="self-start">
          {list.isError && (
            <EmptyState
              title="Unable to load organizations"
              description="Please try again in a moment."
            />
          )}
          {list.isLoading && <Skeleton className="h-64" />}
          {!list.isLoading && !list.isError && organizations.length === 0 && (
            <EmptyState
              title="Nothing here"
              description="No organizations match this filter."
            />
          )}
          {organizations.length > 0 && (
            <ul className="divide-y divide-line">
              {organizations.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    onClick={() => select(row)}
                    className={cn(
                      'flex w-full items-start gap-3 py-3 text-left transition-colors first:pt-0 last:pb-0',
                      selectedId === row.id ? 'text-brand' : 'text-ink hover:text-brand',
                    )}
                  >
                    <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-soft text-muted">
                      <Building2 className="size-4" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium">
                          {row.organization_name}
                        </span>
                        <Badge tone={VERIFICATION_TONE[row.verification_status]}>
                          {VERIFICATION_LABEL[row.verification_status]}
                        </Badge>
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-muted">
                        {row.organization_code} · {row.organization_type_label}
                      </span>
                      <span className="mt-0.5 flex items-center gap-3 text-xs text-muted">
                        <span className="inline-flex items-center gap-1">
                          <Users className="size-3" aria-hidden />
                          {row.member_count ?? 0}
                        </span>
                        {row.created_at && (
                          <span>{format(new Date(row.created_at), 'MMM d, yyyy')}</span>
                        )}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Detail + decision */}
        <div>
          {selectedId == null && (
            <Card>
              <EmptyState
                title="Select an organization"
                description="Choose an organization to review its registration and decide on verification."
              />
            </Card>
          )}

          {selectedId != null && detail.isLoading && (
            <Card>
              <Skeleton className="h-80" />
            </Card>
          )}

          {selectedId != null && detail.isError && (
            <Card>
              <EmptyState
                title="Unable to load this organization"
                description="It may have been removed."
              />
            </Card>
          )}

          {organization && (
            <>
              <Card>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted">
                      {organization.organization_code}
                    </p>
                    <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
                      {organization.organization_name}
                    </h2>
                    <p className="mt-0.5 text-sm text-body">
                      {organization.organization_type_label}
                    </p>
                  </div>
                  <Badge tone={VERIFICATION_TONE[organization.verification_status]}>
                    {VERIFICATION_LABEL[organization.verification_status]}
                  </Badge>
                </div>

                <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
                  <Detail icon={Users} label="Representative">
                    {organization.contact_person || '—'}
                  </Detail>
                  <Detail icon={Phone} label="Contact number">
                    {organization.contact_number || '—'}
                  </Detail>
                  <Detail icon={Mail} label="Organization email">
                    {organization.contact_email || '—'}
                  </Detail>
                  <Detail icon={MapPin} label="Address">
                    {organization.address || '—'}
                  </Detail>
                </dl>

                {organization.purpose && (
                  <div className="mt-5 rounded-xl border border-line p-3.5">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted">
                      Purpose of requesting NORSU facilities
                    </p>
                    <p className="mt-1 text-sm text-body">{organization.purpose}</p>
                  </div>
                )}

                <div className="mt-5 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
                  {organization.created_by_name && (
                    <span>Registered by {organization.created_by_name}</span>
                  )}
                  {organization.created_at && (
                    <span>Submitted {format(new Date(organization.created_at), 'MMM d, yyyy · h:mm a')}</span>
                  )}
                  {organization.reviewed_by_name && organization.reviewed_at && (
                    <span>
                      Reviewed by {organization.reviewed_by_name} on{' '}
                      {format(new Date(organization.reviewed_at), 'MMM d, yyyy')}
                    </span>
                  )}
                </div>

                {organization.review_notes && (
                  <p className="mt-3 rounded-lg bg-soft px-3 py-2 text-xs text-body">
                    Last review note: {organization.review_notes}
                  </p>
                )}
              </Card>

              {/* Members */}
              <Card className="mt-6">
                <CardHeader
                  title="Members"
                  description="Users who authenticate with their own Google account and belong to this organization."
                />
                {(organization.members ?? []).length === 0 ? (
                  <p className="mt-3 text-sm text-muted">No members yet.</p>
                ) : (
                  <ul className="mt-3 divide-y divide-line">
                    {(organization.members ?? []).map((member) => (
                      <li
                        key={member.id}
                        className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-ink">
                            {member.display_name}
                          </p>
                          <p className="truncate text-xs text-muted">
                            {member.email || `@${member.username}`}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge tone="neutral">{member.role.toLowerCase()}</Badge>
                          {!member.is_active && <Badge tone="rose">disabled</Badge>}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              {/* Decision */}
              <Card className="mt-6">
                <CardHeader
                  title="Verification decision"
                  description="Approve to allow reservations. Suspending or rejecting blocks all reservations for these members."
                />
                <div className="mt-4">
                  <label
                    htmlFor="review-notes"
                    className="block text-[13px] font-medium text-ink"
                  >
                    Review notes (optional)
                  </label>
                  <Textarea
                    id="review-notes"
                    rows={3}
                    className="mt-1.5"
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Recorded in the audit log and shown to the organization."
                  />
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {organization.verification_status !== 'APPROVED' && (
                    <Button
                      size="sm"
                      loading={verify.isPending}
                      onClick={() => decide('approve')}
                      icon={<Check className="size-4" />}
                    >
                      Approve
                    </Button>
                  )}
                  {organization.verification_status === 'SUSPENDED' && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={verify.isPending}
                      onClick={() => decide('reactivate')}
                      icon={<RotateCcw className="size-4" />}
                    >
                      Reactivate
                    </Button>
                  )}
                  {organization.verification_status !== 'REJECTED' && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={verify.isPending}
                      onClick={() => decide('reject')}
                      icon={<X className="size-4" />}
                    >
                      Reject
                    </Button>
                  )}
                  {organization.verification_status === 'APPROVED' && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={verify.isPending}
                      onClick={() => decide('suspend')}
                      icon={<ShieldOff className="size-4" />}
                    >
                      Suspend
                    </Button>
                  )}
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Detail({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Users
  label: string
  children: ReactNode
}) {
  return (
    <div className="rounded-xl border border-line p-3.5">
      <dt className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted">
        <Icon className="size-3.5" aria-hidden />
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm text-ink">{children}</dd>
    </div>
  )
}
