import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  CircleCheck,
  MoreHorizontal,
  Package,
  PackageX,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  TriangleAlert,
  Wrench,
} from 'lucide-react'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import {
  useCreateEquipment,
  useEquipment,
  useEquipmentCategories,
  useEquipmentStats,
  useRestoreEquipment,
  useSetEquipmentMaintenance,
  useUpdateEquipment,
} from '@/hooks/queries'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import { PageHeader, Skeleton, EmptyState } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Dropdown, MenuItem } from '@/components/ui/Dropdown'
import { Select, Input } from '@/components/ui/Form'
import { EquipmentFormModal } from '@/components/equipment/EquipmentFormModal'
import { MaintenanceModal } from '@/components/equipment/MaintenanceModal'
import { RemoveEquipmentModal } from '@/components/equipment/RemoveEquipmentModal'
import { ConditionBadge, EquipmentStatusBadge } from '@/components/equipment/EquipmentBadges'
import { cn } from '@/lib/utils'
import type { Equipment } from '@/lib/types'

type StatusFilter = 'ALL' | 'AVAILABLE' | 'IN_USE' | 'MAINTENANCE' | 'UNAVAILABLE' | 'ARCHIVED'

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'AVAILABLE', label: 'Available' },
  { value: 'IN_USE', label: 'In Use' },
  { value: 'MAINTENANCE', label: 'Maintenance' },
  { value: 'UNAVAILABLE', label: 'Unavailable' },
]

export function EquipmentPage() {
  const { isStaff } = useAuth()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')
  const [categoryFilter, setCategoryFilter] = useState('')

  // Add / edit form
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Equipment | null>(null)
  // Maintenance
  const [maintaining, setMaintaining] = useState<Equipment | null>(null)
  // Remove (archive or delete)
  const [removing, setRemoving] = useState<Equipment | null>(null)

  const includeArchived = statusFilter === 'ARCHIVED'
  const { data: equipment, isLoading } = useEquipment(
    includeArchived ? { include_inactive: 'true' } : undefined,
  )
  const { data: stats } = useEquipmentStats()
  const { data: categories } = useEquipmentCategories()

  // Mutations are owned here so the modals stay presentational.
  const createEquipment = useCreateEquipment()
  const updateEquipment = useUpdateEquipment(editing?.id ?? 0)
  const setMaintenance = useSetEquipmentMaintenance(maintaining?.id ?? 0)
  const restoreEquipment = useRestoreEquipment(removing?.id ?? 0)

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return (equipment ?? []).filter((item) => {
      switch (statusFilter) {
        case 'AVAILABLE':
          if (item.status !== 'AVAILABLE' || item.availability.available === 0 || item.availability.reserved > 0)
            return false
          break
        case 'IN_USE':
          if (item.availability.reserved === 0) return false
          break
        case 'MAINTENANCE':
          if (item.status !== 'MAINTENANCE' && item.availability.under_maintenance === 0) return false
          break
        case 'UNAVAILABLE':
          if (item.status === 'AVAILABLE' && item.availability.available > 0) return false
          break
        case 'ARCHIVED':
          if (item.is_active) return false
          break
      }
      if (categoryFilter && item.category.id !== Number(categoryFilter)) return false
      if (
        query &&
        !(
          item.name.toLowerCase().includes(query) ||
          item.category.name.toLowerCase().includes(query) ||
          item.storage_location.toLowerCase().includes(query) ||
          item.asset_code.toLowerCase().includes(query)
        )
      )
        return false
      return true
    })
  }, [equipment, search, statusFilter, categoryFilter])

  function openAdd() {
    setEditing(null)
    setFormOpen(true)
  }

  function openEdit(item: Equipment) {
    setEditing(item)
    setFormOpen(true)
  }

  return (
    <div>
      <PageHeader
        eyebrow="SAS Equipment"
        title="Equipment"
        description="Manage and monitor all equipment and resources available for reservation."
        actions={
          isStaff ? (
            <Button icon={<Plus className="size-4" />} onClick={openAdd}>
              Add Equipment
            </Button>
          ) : undefined
        }
      />

      {/* Stats */}
      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-7">
        <EquipmentStat icon={<Package className="size-[18px]" />} label="Equipment Types" value={stats?.equipment_types} suffix="types" />
        <EquipmentStat icon={<Package className="size-[18px]" />} label="Total Units" value={stats?.total_units} suffix="units" />
        <EquipmentStat icon={<CircleCheck className="size-[18px]" />} label="Available" value={stats?.available_units} suffix="units" accent="text-status-available" />
        <EquipmentStat icon={<ArrowRight className="size-[18px]" />} label="Reserved" value={stats?.reserved_units} suffix="units" accent="text-status-approved" />
        <EquipmentStat icon={<Wrench className="size-[18px]" />} label="Under Maintenance" value={stats?.under_maintenance_units} suffix="units" accent="text-status-maintenance" />
        <EquipmentStat icon={<PackageX className="size-[18px]" />} label="Unavailable" value={stats?.unavailable_units} suffix="units" accent="text-status-rejected" />
        <EquipmentStat icon={<TriangleAlert className="size-[18px]" />} label="Damaged" value={stats?.damaged_records} suffix="records" accent="text-status-rejected" />
      </div>

      {/* Filters */}
      <div className="mt-8 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative flex-1 lg:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            type="search"
            placeholder="Search equipment, category, location, asset code…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9"
            aria-label="Search equipment"
          />
        </div>
        <div className="flex flex-wrap gap-3">
          <Select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
            aria-label="Filter by status"
            className="w-full sm:w-auto"
          >
            {[
              ...STATUS_OPTIONS,
              ...(isStaff ? [{ value: 'ARCHIVED' as const, label: 'Archived' }] : []),
            ].map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Select
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
            aria-label="Filter by category"
            className="w-full sm:w-auto"
          >
            <option value="">All categories</option>
            {(categories ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </Select>
          {(search || categoryFilter || statusFilter !== 'ALL') && (
            <Button
              variant="ghost"
              onClick={() => {
                setSearch('')
                setCategoryFilter('')
                setStatusFilter('ALL')
              }}
            >
              Clear filters
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <Card className="mt-5 overflow-hidden p-0" padding="none">
        {isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No equipment found"
            description={
              search || categoryFilter || statusFilter !== 'ALL'
                ? 'Try adjusting your search or filters.'
                : isStaff
                  ? 'Add your first piece of equipment to build the reservation inventory.'
                  : 'Equipment will appear here once SAS adds it to the inventory.'
            }
            action={
              isStaff && !(search || categoryFilter || statusFilter !== 'ALL') ? (
                <Button size="sm" icon={<Plus className="size-4" />} onClick={openAdd}>
                  Add Equipment
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            {/* Desktop table */}
            <table className="hidden w-full md:table">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
                  <th className="px-5 py-3.5">Equipment</th>
                  <th className="px-4 py-3.5">Category</th>
                  <th className="px-4 py-3.5">Total Quantity</th>
                  <th className="px-4 py-3.5">Available</th>
                  <th className="px-4 py-3.5">Condition</th>
                  <th className="px-4 py-3.5">Status</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filtered.map((item) => (
                  <EquipmentTableRow
                    key={item.id}
                    item={item}
                    isStaff={isStaff}
                    onEdit={() => openEdit(item)}
                    onMaintenance={() => setMaintaining(item)}
                    onRemove={() => setRemoving(item)}
                    onRestore={() =>
                      restoreEquipment.mutate(undefined, {
                        onSuccess: () => toast(`${item.name} restored to the active inventory.`),
                        onError: () => toast('Unable to restore this equipment.', 'error'),
                      })
                    }
                  />
                ))}
              </tbody>
            </table>

            {/* Mobile cards */}
            <ul className="divide-y divide-line md:hidden">
              {filtered.map((item) => (
                <EquipmentMobileRow
                  key={item.id}
                  item={item}
                  isStaff={isStaff}
                  onEdit={() => openEdit(item)}
                  onMaintenance={() => setMaintaining(item)}
                  onRemove={() => setRemoving(item)}
                  onRestore={() =>
                    restoreEquipment.mutate(undefined, {
                      onSuccess: () => toast(`${item.name} restored to the active inventory.`),
                      onError: () => toast('Unable to restore this equipment.', 'error'),
                    })
                  }
                />
              ))}
            </ul>
          </>
        )}
      </Card>

      <p className="mt-4 text-xs text-muted">
        Available quantities are calculated from live reservations and open maintenance — they are
        never manually stored.
      </p>

      {/* Add / edit modal */}
      <EquipmentFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        equipment={editing}
        categories={categories ?? []}
        onSubmit={(payload) => {
          if (editing) {
            return updateEquipment.mutateAsync(payload).then(() => {
              toast(`${editing.name} updated.`)
            })
          }
          return createEquipment.mutateAsync(payload).then(() => {
            toast('Equipment added to the inventory.')
          })
        }}
      />

      {/* Maintenance modal */}
      {maintaining && (
        <MaintenanceModal
          equipment={maintaining}
          onClose={() => setMaintaining(null)}
          onSubmit={(payload) =>
            setMaintenance.mutateAsync(payload).then(() => {
              toast(`${payload.quantity} unit${payload.quantity > 1 ? 's' : ''} marked under maintenance.`)
            })
          }
        />
      )}

      {/* Remove modal */}
      {removing && (
        <RemoveEquipmentModal equipment={removing} onClose={() => setRemoving(null)} />
      )}
    </div>
  )
}

function EquipmentTableRow({
  item,
  isStaff,
  onEdit,
  onMaintenance,
  onRemove,
  onRestore,
}: {
  item: Equipment
  isStaff: boolean
  onEdit: () => void
  onMaintenance: () => void
  onRemove: () => void
  onRestore: () => void
}) {
  return (
    <tr className="transition-colors hover:bg-soft/70">
      <td className="px-5 py-4">
        <div className="flex items-center gap-3">
          <EquipmentImage src={item.image} size="sm" className="shrink-0 rounded-full" />
          <div>
            <Link to={`/equipment/${item.id}`} className="text-sm font-medium text-ink hover:text-brand">
              {item.name}
            </Link>
            <p className="mt-0.5 text-xs text-muted">
              {item.asset_code || item.storage_location || item.category.name}
            </p>
          </div>
        </div>
      </td>
      <td className="px-4 py-4 text-sm text-body">{item.category.name}</td>
      <td className="px-4 py-4 text-sm tabular-nums text-body">
        {item.total_quantity} {item.unit}
      </td>
      <td className="px-4 py-4 text-sm tabular-nums text-body">
        <span
          className={cn(
            'font-medium',
            item.availability.available === 0
              ? 'text-status-rejected'
              : item.availability.available < item.total_quantity
                ? 'text-status-pending'
                : 'text-status-available',
          )}
        >
          {item.availability.available}
        </span>
        {item.availability.reserved > 0 && (
          <span className="ml-1 text-xs text-muted">
            · {Math.min(item.availability.reserved, item.total_quantity)} reserved
          </span>
        )}
      </td>
      <td className="px-4 py-4">
        <ConditionBadge condition={item.condition} />
      </td>
      <td className="px-4 py-4">
        <EquipmentStatusBadge item={item} />
      </td>
      <td className="px-5 py-4 text-right">
        {isStaff ? (
          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onEdit} icon={<Pencil className="size-3.5" />}>
              Edit
            </Button>
            <Dropdown
              trigger={
                <span className="flex size-8 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-soft hover:text-ink">
                  <MoreHorizontal className="size-4" aria-label={`More actions for ${item.name}`} />
                </span>
              }
            >
              {(close) => (
                <>
                  <MenuItem onClick={close}>
                    <Link to={`/equipment/${item.id}`} className="flex w-full items-center gap-2.5">
                      <ArrowRight className="size-4 text-muted" /> View details
                    </Link>
                  </MenuItem>
                  {item.is_active ? (
                    <>
                      <MenuItem onClick={() => { close(); onMaintenance() }}>
                        <Wrench className="size-4 text-muted" /> Under maintenance
                      </MenuItem>
                      <MenuItem danger onClick={() => { close(); onRemove() }}>
                        <Trash2 className="size-4" /> Archive / Delete
                      </MenuItem>
                    </>
                  ) : (
                    <MenuItem onClick={() => { close(); onRestore() }}>
                      <RotateCcw className="size-4 text-muted" /> Restore to inventory
                    </MenuItem>
                  )}
                </>
              )}
            </Dropdown>
          </div>
        ) : (
          <Link
            to={`/equipment/${item.id}`}
            className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:text-brand-dark"
          >
            Details <ArrowRight className="size-3.5" />
          </Link>
        )}
      </td>
    </tr>
  )
}

function EquipmentMobileRow({
  item,
  isStaff,
  onEdit,
  onMaintenance,
  onRemove,
  onRestore,
}: {
  item: Equipment
  isStaff: boolean
  onEdit: () => void
  onMaintenance: () => void
  onRemove: () => void
  onRestore: () => void
}) {
  return (
    <li className="px-5 py-4">        <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <EquipmentImage src={item.image} size="sm" className="shrink-0 rounded-full" />
            <div className="min-w-0">
              <Link to={`/equipment/${item.id}`} className="text-sm font-medium text-ink hover:text-brand">
                {item.name}
              </Link>
              <p className="mt-0.5 text-xs text-muted">
                {item.category.name}
                {item.asset_code ? ` · ${item.asset_code}` : ''}
              </p>
            </div>
          </div>
        </div>
        <EquipmentStatusBadge item={item} />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 rounded-lg bg-soft px-3 py-2.5">
        <p className="text-[13px] text-body">
          <span className="font-semibold text-ink tabular-nums">{item.total_quantity}</span> total
          {' · '}
          <span
            className={cn(
              'font-semibold tabular-nums',
              item.availability.available === 0
                ? 'text-status-rejected'
                : item.availability.available < item.total_quantity
                  ? 'text-status-pending'
                  : 'text-status-available',
            )}
          >
            {item.availability.available}
          </span>{' '}
          available
          {item.availability.reserved > 0 && (
            <>
              {' · '}
              <span className="text-muted">
                {Math.min(item.availability.reserved, item.total_quantity)} reserved
              </span>
            </>
          )}
        </p>
        <ConditionBadge condition={item.condition} />
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        {isStaff ? (
          <>
            <Button variant="outline" size="sm" onClick={onEdit}>
              Edit
            </Button>
            <Dropdown
              trigger={
                <span className="flex size-8 items-center justify-center rounded-lg border border-line text-body">
                  <MoreHorizontal className="size-4" aria-label={`More actions for ${item.name}`} />
                </span>
              }
            >
              {(close) => (
                <>
                  <MenuItem onClick={close}>
                    <Link to={`/equipment/${item.id}`} className="flex w-full items-center gap-2.5">
                      <ArrowRight className="size-4 text-muted" /> View details
                    </Link>
                  </MenuItem>
                  {item.is_active ? (
                    <>
                      <MenuItem onClick={() => { close(); onMaintenance() }}>
                        <Wrench className="size-4 text-muted" /> Under maintenance
                      </MenuItem>
                      <MenuItem danger onClick={() => { close(); onRemove() }}>
                        <Trash2 className="size-4" /> Archive / Delete
                      </MenuItem>
                    </>
                  ) : (
                    <MenuItem onClick={() => { close(); onRestore() }}>
                      <RotateCcw className="size-4 text-muted" /> Restore to inventory
                    </MenuItem>
                  )}
                </>
              )}
            </Dropdown>
          </>
        ) : (
          <Link
            to={`/equipment/${item.id}`}
            className="inline-flex items-center gap-1 text-sm font-medium text-brand"
          >
            Details <ArrowRight className="size-3.5" />
          </Link>
        )}
      </div>
    </li>
  )
}

function EquipmentStat({
  icon,
  label,
  value,
  accent,
  suffix,
}: {
  icon: React.ReactNode
  label: string
  value?: number
  accent?: string
  suffix?: string
}) {
  return (
    <div className="card flex items-center gap-3.5 p-4">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-soft text-body">
        {icon}
      </span>
      <div className="min-w-0">
        <p className={cn('text-xl font-semibold leading-none tabular-nums', accent ?? 'text-ink')}>
          {value ?? 0}
        </p>
        <p className="mt-1 truncate text-xs text-muted">
          {label}
          {suffix ? ` · ${suffix}` : ''}
        </p>
      </div>
    </div>
  )
}

