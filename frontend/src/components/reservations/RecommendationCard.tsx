import { Sparkles, Check, Minus, Plus } from 'lucide-react'
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
              Based on your event details, these resources are recommended:
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
          const partial = recommendation.status === 'PARTIAL' || recommendation.status === 'UNAVAILABLE'
          return (
            <li
              key={recommendation.equipment_id}
              className={cn(
                'flex items-center gap-3 rounded-lg bg-surface/70 px-3.5 py-2.5',
                requested > 0 && 'border border-brand/30',
              )}
            >
              <EquipmentImage src={equipmentItem?.image} size="md" className="shrink-0 rounded-lg" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{recommendation.name}</p>
                <p className={cn('truncate text-xs', partial ? 'text-status-pending' : 'text-muted')}>
                  {partial
                    ? `Only ${available} available during your selected time.`
                    : `${recommendation.reason} ${available} available.`}
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