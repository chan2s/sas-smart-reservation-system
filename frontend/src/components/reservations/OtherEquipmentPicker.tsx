import { useMemo, useState } from 'react'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { EquipmentImageViewer } from '@/components/equipment/EquipmentImageViewer'
import { EmptyState } from '@/components/ui/Misc'
import { QuantityStepper } from '@/components/reservations/QuantityStepper'
import { cn, equipmentImageUrls, equipmentPrimaryImageUrl, formatCurrency } from '@/lib/utils'
import type { ReservableResource } from '@/lib/types'

/** Operator/service configuration per equipment id, as exposed by the facility. */
export interface OperatorConfig {
  available: boolean
  required: boolean
  fee: string
}

/**
 * The full equipment picker, grouped by category — unchanged behaviour from the
 * old standalone Resources step, now revealed inside the merged step by the
 * "+ Add other equipment" control so nothing is lost in the merge.
 *
 * `equipment` should already exclude the items shown as suggestions, so an item
 * never appears twice on the same step.
 */
export function OtherEquipmentPicker({
  equipment,
  items,
  onQuantity,
  operatorConfig,
  operatorSelections,
  onOperatorChange,
  loading,
}: {
  equipment: ReservableResource[]
  items: Record<number, number>
  onQuantity: (equipmentId: number, quantity: number, available: number) => void
  operatorConfig?: Record<number, OperatorConfig>
  operatorSelections?: Record<number, boolean>
  onOperatorChange?: (equipmentId: number, selected: boolean) => void
  loading?: boolean
}) {
  // Clicking an equipment item opens its image so requesters can identify the
  // physical resource before reserving it.
  const [viewingItem, setViewingItem] = useState<ReservableResource | null>(null)

  const byCategory = useMemo(() => {
    const groups = new Map<string, ReservableResource[]>()
    for (const item of equipment) {
      const key = item.category.name
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(item)
    }
    return [...groups.entries()]
  }, [equipment])

  if (loading) {
    return <div className="mt-4 h-32 animate-pulse rounded-xl bg-soft" aria-hidden />
  }

  if (byCategory.length === 0) {
    return (
      <EmptyState
        title="No other resources available"
        description="Everything this facility offers is already listed above. You can continue without additional resources."
      />
    )
  }

  return (
    <div className="mt-4 space-y-6">
      {byCategory.map(([category, itemsInCategory]) => (
        <div key={category}>
          <h4 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-muted">
            {category}
          </h4>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {itemsInCategory.map((item) => {
              const requested = items[item.id] ?? 0
              const available = item.availability.available
              return (
                <div
                  key={item.id}
                  className={cn(
                    'rounded-xl border border-line bg-surface p-4 transition-colors',
                    requested > 0 && 'border-brand/40 bg-brand-soft/40',
                  )}
                >
                  <div className="flex items-center gap-4">
                    <button
                      type="button"
                      onClick={() => setViewingItem(item)}
                      className="group relative shrink-0 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                      aria-label={`View image of ${item.name}`}
                      title="Click to view image"
                    >
                      <EquipmentImage
                        src={equipmentPrimaryImageUrl(item)}
                        size="md"
                        className="rounded-lg"
                        alt={item.name}
                      />
                      <span
                        aria-hidden
                        className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg bg-ink/0 text-[11px] font-medium text-white opacity-0 transition-all group-hover:bg-ink/45 group-hover:opacity-100"
                      >
                        View
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewingItem(item)}
                      className="min-w-0 flex-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
                      aria-label={`View details of ${item.name}`}
                    >
                      <p className="truncate text-sm font-medium text-ink group-hover:text-brand">
                        {item.name}
                      </p>
                      <p className="mt-0.5 text-xs text-body">
                        {available} of {item.total_quantity} units available
                        {item.availability.status !== 'AVAILABLE' &&
                          item.availability.status !== 'PARTIAL' && (
                            <span className="text-status-rejected"> · unavailable now</span>
                          )}
                      </p>
                      <span className="mt-0.5 inline-block text-[11px] font-medium text-brand">
                        View image →
                      </span>
                    </button>
                    <QuantityStepper
                      value={requested}
                      max={available}
                      label={item.name}
                      onChange={(next) => onQuantity(item.id, next, available)}
                    />
                  </div>
                  {operatorConfig?.[item.id]?.available && (
                    <label className="mt-3 flex cursor-pointer items-center gap-2 border-t border-line/70 pt-3 text-xs text-body">
                      <input
                        type="checkbox"
                        className="size-3.5 accent-[var(--color-brand)]"
                        checked={
                          operatorSelections?.[item.id] ?? Boolean(operatorConfig?.[item.id]?.required)
                        }
                        disabled={Boolean(operatorConfig?.[item.id]?.required)}
                        onChange={(event) => onOperatorChange?.(item.id, event.target.checked)}
                      />
                      <span>
                        Operator service
                        {operatorConfig?.[item.id]?.fee && Number(operatorConfig?.[item.id]?.fee) > 0
                          ? ` (+${formatCurrency(operatorConfig[item.id].fee)})`
                          : ''}
                        {operatorConfig?.[item.id]?.required ? ' · required' : ''}
                      </span>
                    </label>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      <EquipmentImageViewer
        equipment={viewingItem}
        images={equipmentImageUrls(viewingItem)}
        onClose={() => setViewingItem(null)}
      />
    </div>
  )
}
