import { Sparkles, Check, Minus, Plus, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import type { Equipment, Recommendation } from '@/lib/types'
import { cn } from '@/lib/utils'

interface EventContext {
  eventName: string
  participants: string
  facilityName: string
  schedule: string
}

export function RecommendationCard({
  recommendations,
  equipment,
  items,
  onQuantity,
  eventContext,
  loading,
  applied,
  onAccept,
  onDismiss,
}: {
  recommendations: Recommendation[]
  equipment: Equipment[]
  items: Record<number, number>
  onQuantity: (equipmentId: number, quantity: number, available: number) => void
  eventContext?: EventContext
  loading?: boolean
  applied?: boolean
  onAccept?: () => void
  onDismiss?: () => void
}) {
  if (loading) {
    return (
      <div className="rounded-xl border border-brand/20 bg-brand-soft/60 p-5">
        <div className="h-4 w-1/3 animate-pulse rounded bg-brand/10" />
        <div className="mt-4 space-y-2">
          {[1, 2, 3].map((index) => (
            <div key={index} className="h-3 animate-pulse rounded bg-brand/10" />
          ))}
        </div>
      </div>
    )
  }

  if (recommendations.length === 0) return null

  return (
    <div
      className={cn(
        'rounded-xl border p-5 transition-colors duration-200',
        applied ? 'border-status-available/30 bg-status-available-bg' : 'border-brand/20 bg-brand-soft/60',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand text-white shadow-sm">
            <Sparkles className="size-4.5" aria-hidden />
          </span>
          <div>
            <p className="text-sm font-semibold text-ink">Recommended for your event</p>
            <p className="text-[13px] text-body">
              Quantities are calculated from your event details — adjust them as needed.
            </p>
          </div>
        </div>
        {applied && (
          <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-status-available">
            <Check className="size-3.5" /> Applied
          </span>
        )}
      </div>

      {eventContext && (
        <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 rounded-lg bg-surface/70 px-3.5 py-2.5 text-[13px]">
          <div className="flex gap-1.5">
            <dt className="text-muted">Event</dt>
            <dd className="font-medium text-ink">{eventContext.eventName}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-muted">Participants</dt>
            <dd className="font-medium text-ink">{eventContext.participants}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-muted">Facility</dt>
            <dd className="font-medium text-ink">{eventContext.facilityName}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-muted">Schedule</dt>
            <dd className="font-medium text-ink">{eventContext.schedule}</dd>
          </div>
        </dl>
      )}

      <ul className="mt-4 space-y-2">
        {recommendations.map((recommendation) => {
          const equipmentItem = equipment.find((item) => item.id === recommendation.equipment_id)
          const available = equipmentItem?.availability.available ?? recommendation.available
          const requested = items[recommendation.equipment_id] ?? 0
          const shortage = !recommendation.can_fulfill
          return (
            <li
              key={recommendation.equipment_id}
              className={cn(
                'rounded-lg bg-surface/70 px-3.5 py-3',
                requested > 0 && 'border border-brand/30',
                shortage && requested === 0 && 'border-status-pending/30',
              )}
            >
              <div className="flex items-center gap-3">
                <EquipmentImage src={equipmentItem?.image} size="md" className="shrink-0 rounded-lg" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <p className="text-sm font-medium text-ink">{recommendation.name}</p>
                    <span
                      className={cn(
                        'rounded-full px-2 py-0.5 text-[11px] font-semibold',
                        shortage ? 'bg-status-pending-bg text-status-pending' : 'bg-status-available-bg text-status-available',
                      )}
                    >
                      Recommended {recommendation.quantity}{' '}
                      {recommendation.quantity === 1 ? 'unit' : 'units'}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    {recommendation.reason}
                    {recommendation.calculation ? ` · ${recommendation.calculation}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onQuantity(recommendation.equipment_id, requested - 1, available)}
                    disabled={requested === 0}
                    className="flex size-8 items-center justify-center rounded-lg border border-line bg-surface text-body transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label={`Decrease ${recommendation.name} quantity`}
                  >
                    <Minus className="size-3.5" />
                  </button>
                  <span className="w-8 text-center text-sm font-semibold tabular-nums text-ink" aria-live="polite">
                    {requested}
                  </span>
                  <button
                    type="button"
                    onClick={() => onQuantity(recommendation.equipment_id, requested + 1, available)}
                    disabled={requested >= available || available === 0}
                    className="flex size-8 items-center justify-center rounded-lg border border-line bg-surface text-body transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label={`Increase ${recommendation.name} quantity`}
                  >
                    <Plus className="size-3.5" />
                  </button>
                </div>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 sm:pl-12">
                <p className="text-xs text-body">
                  <span className="font-medium text-ink">{available}</span> available during your
                  schedule
                </p>
                {recommendation.recommended > 0 && requested !== recommendation.recommended && (
                  <button
                    type="button"
                    onClick={() =>
                      onQuantity(recommendation.equipment_id, recommendation.recommended, available)
                    }
                    className="text-xs font-semibold text-brand underline-offset-2 transition-colors hover:underline"
                  >
                    Use {recommendation.recommended}
                  </button>
                )}
              </div>

              {recommendation.warning && (
                <p className="mt-1.5 flex items-start gap-1.5 text-xs text-status-pending sm:pl-12">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  {recommendation.warning}
                </p>
              )}
            </li>
          )
        })}
      </ul>

      {!applied && onAccept && (
        <div className="mt-4 flex flex-wrap gap-2.5">
          <Button size="sm" onClick={onAccept}>
            <Check className="size-3.5" /> Use recommended quantities
          </Button>
          {onDismiss && (
            <Button size="sm" variant="ghost" onClick={onDismiss}>
              Not now
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
