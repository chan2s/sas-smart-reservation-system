import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  Package,
  Pencil,
  Plus,
  Trash2,
  Wrench,
} from 'lucide-react'
import {
  useCreateFacilityResource,
  useDeleteFacilityResource,
  useEquipment,
  useFacility,
  useFacilityResourceAssignments,
  useUpdateFacilityResource,
} from '@/hooks/queries'
import type { Equipment, FacilityResource, FacilityResourceStatus } from '@/lib/types'
import { PageHeader, EmptyState, Skeleton } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Input, Select } from '@/components/ui/Form'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { useToast } from '@/components/ui/Toast'
import { Backdrop } from '@/components/decor/Backdrop'
import { formatCurrency } from '@/lib/utils'

const STATUS_OPTIONS: { value: FacilityResourceStatus; label: string }[] = [
  { value: 'AVAILABLE', label: 'Available' },
  { value: 'UNAVAILABLE', label: 'Unavailable' },
  { value: 'MAINTENANCE', label: 'Under maintenance' },
  { value: 'DAMAGED', label: 'Damaged' },
]

const STATUS_TONE: Record<FacilityResourceStatus, 'emerald' | 'orange' | 'gray'> = {
  AVAILABLE: 'emerald',
  MAINTENANCE: 'orange',
  UNAVAILABLE: 'gray',
  DAMAGED: 'gray',
}

/**
 * Administrator configuration of which equipment/resources belong to a
 * facility.
 *
 * The database relationship is the single source of truth: anything assigned
 * here is exactly what a requester can pick in the reservation form when they
 * select this facility, and anything removed here disappears from it.
 */
export function FacilityResourcesPage() {
  const { id } = useParams()
  const facilityId = Number(id)
  const { toast } = useToast()

  const facility = useFacility(facilityId)
  const assignments = useFacilityResourceAssignments(facilityId, true)
  const equipment = useEquipment()
  const createAssignment = useCreateFacilityResource()
  const updateAssignment = useUpdateFacilityResource()
  const removeAssignment = useDeleteFacilityResource()

  const [editingId, setEditingId] = useState<number | null>(null)

  const assignedByEquipment = useMemo(() => {
    const map = new Map<number, FacilityResource>()
    for (const resource of assignments.data ?? []) map.set(resource.equipment_id, resource)
    return map
  }, [assignments.data])

  const available = useMemo(
    () =>
      (equipment.data ?? [])
        .filter((item) => !assignedByEquipment.has(item.id))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [equipment.data, assignedByEquipment],
  )

  const assigned = useMemo(
    () =>
      [...(assignments.data ?? [])].sort((a, b) =>
        a.name.localeCompare(b.name),
      ),
    [assignments.data],
  )

  async function add(item: Equipment) {
    try {
      await createAssignment.mutateAsync({ facility: facilityId, equipment: item.id })
      toast(`${item.name} added to this facility.`)
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not assign the resource.', 'error')
    }
  }

  async function remove(resource: FacilityResource) {
    try {
      await removeAssignment.mutateAsync(resource.id)
      if (editingId === resource.id) setEditingId(null)
      toast(`${resource.name} removed from this facility.`)
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not remove the resource.', 'error')
    }
  }

  const loading = facility.isLoading || assignments.isLoading || equipment.isLoading

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-40 w-full rounded-2xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    )
  }

  return (
    <div className="relative">
      <Backdrop />

      <Link
        to={`/facilities/${facilityId}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> {facility.data?.name ?? 'Facility'}
      </Link>

      <div className="mt-4">
        <PageHeader
          eyebrow="Facility configuration"
          title="Manage equipment"
          description={
            facility.data
              ? `Choose which resources are available when reserving the ${facility.data.name}. Requesters only ever see this list.`
              : 'Choose which resources are available for this facility.'
          }
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Currently assigned */}
        <Card>
          <CardHeader
            title={`Currently assigned (${assigned.length})`}
            description="These appear in the reservation form for this facility."
          />
          {assigned.length === 0 ? (
            <EmptyState
              title="No resources assigned"
              description="Add equipment from the list on the right so it can be requested."
            />
          ) : (
            <ul className="mt-4 space-y-3">
              {assigned.map((resource) => (
                <li
                  key={resource.id}
                  className="rounded-xl border border-line p-3.5 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
                      <Package className="size-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-semibold text-ink">
                          {resource.name}
                        </p>
                        <Badge tone={STATUS_TONE[resource.status]}>
                          {resource.status_label}
                        </Badge>
                        {!resource.is_active && <Badge tone="gray">Deactivated</Badge>}
                      </div>
                      <p className="mt-0.5 text-xs text-muted">
                        {resource.category.name} ·{' '}
                        {resource.quantity > 0
                          ? `${resource.quantity} assigned`
                          : `inherits ${resource.total_quantity}`}
                        {resource.operator_available &&
                          Number(resource.operator_fee) > 0 &&
                          ` · operator ${formatCurrency(resource.operator_fee)}`}
                        {resource.operator_required && ' (required)'}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Pencil className="size-3.5" />}
                        onClick={() =>
                          setEditingId(editingId === resource.id ? null : resource.id)
                        }
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Trash2 className="size-3.5" />}
                        onClick={() => remove(resource)}
                      >
                        Remove
                      </Button>
                    </div>
                  </div>

                  {editingId === resource.id && (
                    <ResourceConfigForm
                      resource={resource}
                      onCancel={() => setEditingId(null)}
                      onSave={async (payload) => {
                        try {
                          await updateAssignment.mutateAsync({ id: resource.id, ...payload })
                          setEditingId(null)
                          toast(`${resource.name} configuration saved.`)
                        } catch (err) {
                          toast(
                            err instanceof Error
                              ? err.message
                              : 'Could not save the configuration.',
                            'error',
                          )
                        }
                      }}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Available equipment */}
        <Card>
          <CardHeader
            title={`Available equipment (${available.length})`}
            description="Every equipment record not yet assigned to this facility."
          />
          {available.length === 0 ? (
            <p className="mt-4 text-sm text-muted">
              Every equipment item is already assigned to this facility.
            </p>
          ) : (
            <ul className="mt-4 space-y-2">
              {available.map((item) => (
                <li
                  key={item.id}
                  className="flex items-center gap-3 rounded-xl border border-line p-3"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-soft text-muted">
                    <Package className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{item.name}</p>
                    <p className="text-xs text-muted">
                      {item.category.name} · {item.total_quantity} {item.unit}
                      {item.status !== 'AVAILABLE' && (
                        <span className="text-status-maintenance">
                          {' '}
                          · {item.status_label}
                        </span>
                      )}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    icon={<Plus className="size-3.5" />}
                    onClick={() => add(item)}
                  >
                    Add
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

/** Inline editor for one assignment's facility-specific configuration. */
function ResourceConfigForm({
  resource,
  onSave,
  onCancel,
}: {
  resource: FacilityResource
  onSave: (payload: Partial<FacilityResource>) => void
  onCancel: () => void
}) {
  const [quantity, setQuantity] = useState(String(resource.quantity))
  const [status, setStatus] = useState<FacilityResourceStatus>(resource.status)
  const [additionalFee, setAdditionalFee] = useState(resource.additional_fee)
  const [operatorAvailable, setOperatorAvailable] = useState(resource.operator_available)
  const [operatorRequired, setOperatorRequired] = useState(resource.operator_required)
  const [operatorFee, setOperatorFee] = useState(resource.operator_fee)
  const [isActive, setIsActive] = useState(resource.is_active)

  return (
    <div className="mt-3 grid gap-3 rounded-lg bg-soft p-3 sm:grid-cols-2">
      <Field
        label="Quantity at this facility"
        htmlFor={`quantity-${resource.id}`}
        hint={`0 inherits the inventory (${resource.total_quantity}).`}
      >
        <Input
          id={`quantity-${resource.id}`}
          type="number"
          min={0}
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
        />
      </Field>

      <Field label="Availability" htmlFor={`status-${resource.id}`}>
        <Select
          id={`status-${resource.id}`}
          value={status}
          onChange={(event) => setStatus(event.target.value as FacilityResourceStatus)}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </Field>

      <Field
        label="Additional fee (per unit)"
        htmlFor={`fee-${resource.id}`}
        hint="External organizations only. 0 = no additional fee."
      >
        <Input
          id={`fee-${resource.id}`}
          type="number"
          min={0}
          step="0.01"
          value={additionalFee}
          onChange={(event) => setAdditionalFee(event.target.value)}
        />
      </Field>

      <Field
        label="Operator service fee"
        htmlFor={`operator-fee-${resource.id}`}
        hint="Charged only when requested, or always when required."
      >
        <Input
          id={`operator-fee-${resource.id}`}
          type="number"
          min={0}
          step="0.01"
          value={operatorFee}
          onChange={(event) => setOperatorFee(event.target.value)}
        />
      </Field>

      <label className="flex items-center gap-2 text-[13px] text-ink">
        <input
          type="checkbox"
          className="size-4 accent-[var(--color-brand)]"
          checked={operatorAvailable}
          onChange={(event) => setOperatorAvailable(event.target.checked)}
        />
        Operator service available
      </label>

      <label className="flex items-center gap-2 text-[13px] text-ink">
        <input
          type="checkbox"
          className="size-4 accent-[var(--color-brand)]"
          checked={operatorRequired}
          onChange={(event) => setOperatorRequired(event.target.checked)}
        />
        Operator service required
      </label>

      <label className="flex items-center gap-2 text-[13px] text-ink sm:col-span-2">
        <input
          type="checkbox"
          className="size-4 accent-[var(--color-brand)]"
          checked={isActive}
          onChange={(event) => setIsActive(event.target.checked)}
        />
        Active (uncheck to hide from the reservation form without deleting)
      </label>

      <div className="flex items-center gap-2 sm:col-span-2">
        <Button
          size="sm"
          icon={<Check className="size-3.5" />}
          onClick={() =>
            onSave({
              quantity: Number(quantity) || 0,
              status,
              additional_fee: additionalFee,
              operator_available: operatorAvailable,
              operator_required: operatorRequired,
              operator_fee: operatorFee,
              is_active: isActive,
            })
          }
        >
          Save
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        {status === 'MAINTENANCE' && (
          <span className="flex items-center gap-1 text-xs text-status-maintenance">
            <Wrench className="size-3.5" aria-hidden /> Hidden from new reservations
          </span>
        )}
      </div>
    </div>
  )
}
