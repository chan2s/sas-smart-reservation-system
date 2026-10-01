import { Minus, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * The small − / value / + control used for every resource quantity in the
 * wizard (suggested rows and the additional-equipment picker alike).
 *
 * `max` follows live availability: the + button disables at the cap instead of
 * silently clamping, and the caller keeps the value within range.
 */
export function QuantityStepper({
  value,
  onChange,
  max,
  disabled,
  label,
  className,
}: {
  value: number
  onChange: (next: number) => void
  /** Largest selectable value (units available). */
  max: number
  disabled?: boolean
  /** Accessible name, e.g. the equipment name. */
  label: string
  className?: string
}) {
  const blocked = disabled || max <= 0
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <button
        type="button"
        onClick={() => onChange(value - 1)}
        disabled={blocked || value <= 0}
        className="flex size-8 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={`Decrease ${label} quantity`}
      >
        <Minus className="size-3.5" aria-hidden />
      </button>
      <span className="w-8 text-center text-sm font-semibold tabular-nums text-ink" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        onClick={() => onChange(value + 1)}
        disabled={blocked || value >= max}
        className="flex size-8 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={`Increase ${label} quantity`}
      >
        <Plus className="size-3.5" aria-hidden />
      </button>
    </div>
  )
}
