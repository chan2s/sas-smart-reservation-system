import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  History,
  Pencil,
  RotateCcw,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  Wrench,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  useEquipmentCategories,
  useEquipmentHistory,
  useEquipmentItem,
  useEquipmentMaintenance,
  useReportEquipmentIssue,
  useResolveMaintenance,
  useRestoreEquipment,
  useSetEquipmentMaintenance,
  useUpdateEquipment,
} from '@/hooks/queries'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import { Field, Select, Textarea } from '@/components/ui/Form'
import { Skeleton, EmptyState } from '@/components/ui/Misc'
import { EquipmentFormModal } from '@/components/equipment/EquipmentFormModal'
import { MaintenanceModal } from '@/components/equipment/MaintenanceModal'
import { RemoveEquipmentModal } from '@/components/equipment/RemoveEquipmentModal'
import { ConditionBadge, EquipmentStatusBadge } from '@/components/equipment/EquipmentBadges'
import { cn, formatDateTime } from '@/lib/utils'

const ISSUE_TYPES = [
  { value: 'DAMAGE', label: 'Damage' },
  { value: 'MISSING', label: 'Missing item' },
  { value: 'MALFUNCTION', label: 'Malfunction' },
  { value: 'MAINTENANCE', label: 'Maintenance required' },
]

export function EquipmentDetailPage() {
  const { id } = useParams()
  const equipmentId = Number(id)
  const { toast } = useToast()
  const { isStaff } = useAuth()
  const { data: item, isLoading } = useEquipmentItem(equipmentId)
  const { data: maintenance } = useEquipmentMaintenance(equipmentId)
  const { data: history } = useEquipmentHistory(equipmentId)
  const { data: categories } = useEquipmentCategories()
  const reportIssue = useReportEquipmentIssue(equipmentId)
  const updateEquipment = useUpdateEquipment(equipmentId)
  const setMaintenance = useSetEquipmentMaintenance(equipmentId)
  const restoreEquipment = useRestoreEquipment(equipmentId)

  const [issueOpen, setIssueOpen] = useState(false)
  const [issueType, setIssueType] = useState('DAMAGE')
  const [description, setDescription] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)

  const [editOpen, setEditOpen] = useState(false)
  const [maintenanceOpen, setMaintenanceOpen] = useState(false)
  const [removeOpen, setRemoveOpen] = useState(false)

  if (isLoading || !item) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-1/3" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-72 lg:col-span-2" />
          <Skeleton className="h-72" />
        </div>
      </div>
    )
  }

  const currentItem = item
  const availability = item.availability

  function submitIssue() {
    const form = new FormData()
    form.append('equipment', String(currentItem.id))
    form.append('issue_type', issueType)
    form.append('quantity', '1')
    form.append('description', description)
    if (photo) form.append('photo', photo)
    reportIssue.mutate(form, {
      onSuccess: () => {
        toast('Issue reported to the maintenance queue.')
        setIssueOpen(false)
        setDescription('')
        setPhoto(null)
      },
      onError: () => toast('Unable to report the issue.', 'error'),
    })
  }

  return (
    <div>
      <Link
        to="/equipment"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> Equipment inventory
      </Link>

      {/* Header */}
      <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
              {item.asset_code ? `Asset ${item.asset_code}` : `Equipment #${item.id}`}
            </p>
            <EquipmentStatusBadge item={item} />
            <ConditionBadge condition={item.condition} />
            {!item.is_active && <Badge tone="gray">Archived</Badge>}
          </div>
          <h1 className="mt-1.5 text-3xl font-semibold tracking-tight text-ink sm:text-[32px]">
            {item.name}
          </h1>
          <p className="mt-1 text-[15px] text-body">
            {item.category.name} · {item.storage_location || 'No storage location set'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isStaff && (
            <>
              <Button
                variant="outline"
                icon={<Pencil className="size-4" />}
                onClick={() => setEditOpen(true)}
              >
                Edit
              </Button>
              {item.is_active ? (
                <>
                  <Button
                    variant="outline"
                    icon={<Wrench className="size-4" />}
                    onClick={() => setMaintenanceOpen(true)}
                  >
                    Mark maintenance
                  </Button>
                  <Button
                    variant="outline"
                    icon={<Trash2 className="size-4" />}
                    onClick={() => setRemoveOpen(true)}
                  >
                    Archive / Delete
                  </Button>
                </>
              ) : (
                <Button
                  icon={<RotateCcw className="size-4" />}
                  onClick={() =>
                    restoreEquipment.mutate(undefined, {
                      onSuccess: () => toast(`${item.name} restored to the active inventory.`),
                      onError: () => toast('Unable to restore this equipment.', 'error'),
                    })
                  }
                >
                  Restore to inventory
                </Button>
              )}
            </>
          )}
          <Button icon={<TriangleAlert className="size-4" />} onClick={() => setIssueOpen(true)}>
            Report an issue
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatBox label={`Total quantity (${item.unit})`} value={item.total_quantity} />
        <StatBox label="Available" value={availability.available} tone="text-status-available" />
        <StatBox label="Reserved" value={availability.reserved} tone="text-status-approved" />
        <StatBox
          label="Under maintenance"
          value={availability.under_maintenance}
          tone="text-status-maintenance"
        />
      </div>

      {/* Maintenance warning */}
      {item.status === 'MAINTENANCE' && (
        <div className="mt-6 flex items-start gap-2.5 rounded-xl border border-status-maintenance/25 bg-status-maintenance-bg px-4 py-3 text-sm text-status-maintenance">
          <Wrench className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <span className="font-semibold">Under maintenance.</span> This equipment cannot be
            reserved until the maintenance records are resolved.
          </p>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* Inspection guidance */}
          <Card>
            <CardHeader
              title="Inspection"
              description="SAS staff record the state of this equipment before and after every use."
            />
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-line p-4">
                <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                  <ShieldCheck className="size-4 text-status-available" aria-hidden />
                  Before-use inspection
                </p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-body">
                  Verify the item is present, functional, and in the recorded condition before
                  handing it to the requester.
                </p>
              </div>
              <div className="rounded-xl border border-line p-4">
                <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                  <ShieldCheck className="size-4 text-status-approved" aria-hidden />
                  After-use inspection
                </p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-body">
                  Inspect on return, confirm quantity, and report damage, missing items, or
                  malfunctions through the check-out flow.
                </p>
              </div>
            </div>
          </Card>

          {/* Usage history */}
          <Card>
            <CardHeader
              title="Reservation usage"
              description="Every reservation that has included this equipment"
            />
            {!history || history.length === 0 ? (
              <EmptyState
                icon={<History className="size-5" />}
                title="No usage yet"
                description="Reservations that include this equipment will appear here."
              />
            ) : (
              <div className="mt-4">
                <table className="hidden w-full sm:table">
                  <thead>
                    <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
                      <th className="py-2.5 pr-4">Reservation</th>
                      <th className="px-4 py-2.5">Event</th>
                      <th className="px-4 py-2.5">Date</th>
                      <th className="px-4 py-2.5">Quantity</th>
                      <th className="px-4 py-2.5">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {history.map((row) => (
                      <tr key={`${row.reservation}-${row.quantity}`} className="text-sm">
                        <td className="py-3 pr-4">
                          <Link
                            to={`/reservations/${row.reservation}`}
                            className="font-medium text-ink hover:text-brand"
                          >
                            {row.reservation_id}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-body">{row.event_name}</td>
                        <td className="px-4 py-3 tabular-nums text-body">
                          {format(new Date(`${row.date}T00:00:00`), 'MMM d, yyyy')}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-body">
                          {row.quantity} {row.quantity > 1 ? 'units' : 'unit'}
                        </td>
                        <td className="px-4 py-3">
                          <Badge
                            tone={
                              row.status === 'COMPLETED'
                                ? 'teal'
                                : row.status === 'APPROVED'
                                  ? 'sky'
                                  : row.status === 'ACTIVE'
                                    ? 'sky'
                                    : row.status === 'PENDING'
                                      ? 'amber'
                                      : row.status === 'REJECTED'
                                        ? 'rose'
                                        : 'gray'
                            }
                          >
                            {row.status_label}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ul className="divide-y divide-line sm:hidden">
                  {history.map((row) => (
                    <li key={`${row.reservation}-${row.quantity}`} className="py-3">
                      <Link
                        to={`/reservations/${row.reservation}`}
                        className="text-sm font-medium text-ink hover:text-brand"
                      >
                        {row.event_name}
                      </Link>
                      <p className="mt-0.5 text-xs text-muted">
                        {row.reservation_id} · {format(new Date(`${row.date}T00:00:00`), 'MMM d, yyyy')} ·{' '}
                        {row.quantity} {row.quantity > 1 ? 'units' : 'unit'}
                      </p>
                      <div className="mt-1.5">
                        <Badge tone={row.status === 'COMPLETED' ? 'teal' : row.status === 'APPROVED' || row.status === 'ACTIVE' ? 'sky' : row.status === 'PENDING' ? 'amber' : row.status === 'REJECTED' ? 'rose' : 'gray'}>
                          {row.status_label}
                        </Badge>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {/* Maintenance history */}
          <Card>
            <CardHeader
              title="Maintenance history"
              description="Open maintenance can be resolved by SAS staff once the work is done."
            />
            {!maintenance || maintenance.length === 0 ? (
              <EmptyState
                icon={<Wrench className="size-5" />}
                title="No maintenance records"
                description="Issues reported for this equipment will appear here."
              />
            ) : (
              <ul className="mt-4 divide-y divide-line">
                {maintenance.map((record) => (
                  <li key={record.id} className="flex items-start gap-4 py-3.5">
                    <span
                      className={cn(
                        'mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg',
                        record.status === 'OPEN'
                          ? 'bg-status-maintenance-bg text-status-maintenance'
                          : 'bg-status-available-bg text-status-available',
                      )}
                    >
                      <Wrench className="size-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium text-ink">
                          {record.issue_type_label}
                          <span className="ml-1.5 text-xs font-normal text-muted">
                            · {record.quantity} {record.quantity > 1 ? 'units' : 'unit'}
                          </span>
                        </p>
                        <Badge tone={record.status === 'OPEN' ? 'orange' : 'emerald'}>
                          {record.status_label}
                        </Badge>
                      </div>
                      {record.description && (
                        <p className="mt-1 text-[13px] text-body">{record.description}</p>
                      )}
                      <p className="mt-1 text-xs text-muted">
                        {record.reported_by_name || 'SAS Staff'} · {formatDateTime(record.created_at)}
                        {record.resolved_at && ` · Resolved ${formatDateTime(record.resolved_at)}`}
                      </p>
                    </div>
                    {isStaff && record.status === 'OPEN' && (
                      <ResolveMaintenanceButton equipmentId={equipmentId} recordId={record.id} />
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Details" />
            <div className="mt-4">
              <EquipmentImage src={item.image} size="lg" className="mx-auto" />
            </div>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Category</dt>
                <dd className="font-medium text-ink">{item.category.name}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Status</dt>
                <dd className="font-medium text-ink">{item.status_label}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Condition</dt>
                <dd className="font-medium text-ink">{item.condition_label}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Unit</dt>
                <dd className="font-medium text-ink">{item.unit}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Asset code</dt>
                <dd className="font-medium text-ink">{item.asset_code || '—'}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Storage</dt>
                <dd className="text-right font-medium text-ink">{item.storage_location || '—'}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Open issues</dt>
                <dd className="font-medium text-ink">{item.open_maintenance ?? 0}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Updated</dt>
                <dd className="font-medium text-ink">{formatDateTime(item.updated_at)}</dd>
              </div>
            </dl>
            {item.description && (
              <div className="mt-4 border-t border-line pt-4">
                <p className="text-[13px] font-semibold uppercase tracking-[0.1em] text-muted">
                  Description
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-body">{item.description}</p>
              </div>
            )}
            {item.notes && (
              <div className="mt-4 border-t border-line pt-4">
                <p className="text-[13px] font-semibold uppercase tracking-[0.1em] text-muted">Notes</p>
                <p className="mt-1.5 text-sm leading-relaxed text-body">{item.notes}</p>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Report issue modal */}
      <Modal
        open={issueOpen}
        onClose={() => setIssueOpen(false)}
        title="Report equipment issue"
        description={`Report damage, missing items, or malfunctions for ${item.name}.`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setIssueOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submitIssue} loading={reportIssue.isPending}>
              Submit report
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Issue type" htmlFor="equipment-issue-type">
            <Select
              id="equipment-issue-type"
              value={issueType}
              onChange={(event) => setIssueType(event.target.value)}
            >
              {ISSUE_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Description" htmlFor="equipment-issue-description">
            <Textarea
              id="equipment-issue-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe the issue and when it was noticed…"
            />
          </Field>
          <Field label="Photo (optional)" htmlFor="equipment-issue-photo">
            <input
              id="equipment-issue-photo"
              type="file"
              accept="image/*"
              onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
              className="block w-full text-sm text-body file:mr-3 file:rounded-lg file:border-0 file:bg-brand-soft file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand hover:file:bg-brand-faint"
            />
          </Field>
        </div>
      </Modal>

      {/* Edit modal */}
      <EquipmentFormModal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        equipment={item}
        categories={categories ?? []}
        onSubmit={(payload) =>
          updateEquipment.mutateAsync(payload).then(() => {
            toast(`${item.name} updated.`)
          })
        }
      />

      {/* Maintenance modal */}
      {maintenanceOpen && (
        <MaintenanceModal
          equipment={item}
          onClose={() => setMaintenanceOpen(false)}
          onSubmit={(payload) =>
            setMaintenance.mutateAsync(payload).then(() => {
              toast(`${payload.quantity} unit${payload.quantity > 1 ? 's' : ''} marked under maintenance.`)
            })
          }
        />
      )}

      {/* Remove modal */}
      {removeOpen && <RemoveEquipmentModal equipment={item} onClose={() => setRemoveOpen(false)} />}
    </div>
  )
}

function ResolveMaintenanceButton({ equipmentId, recordId }: { equipmentId: number; recordId: number }) {
  const { toast } = useToast()
  const resolve = useResolveMaintenance(equipmentId)
  return (
    <Button
      variant="outline"
      size="sm"
      loading={resolve.isPending}
      onClick={() =>
        resolve.mutate(recordId, {
          onSuccess: () => toast('Maintenance resolved — units are reservable again.'),
          onError: () => toast('Unable to resolve this record.', 'error'),
        })
      }
    >
      Resolve
    </Button>
  )
}

function StatBox({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="card p-4">
      <p className={cn('text-2xl font-semibold leading-none tabular-nums', tone ?? 'text-ink')}>{value}</p>
      <p className="mt-1.5 text-[13px] text-muted">{label}</p>
    </div>
  )
}