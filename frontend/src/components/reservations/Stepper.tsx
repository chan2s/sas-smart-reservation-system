import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface Step {
  key: string
  label: string
}

export function Stepper({ steps, current, onStepClick }: { steps: Step[]; current: number; onStepClick?: (index: number) => void }) {
  return (
    <nav aria-label="Reservation progress">
      {/* Desktop */}
      <ol className="hidden items-center sm:flex">
        {steps.map((step, index) => {
          const done = index < current
          const active = index === current
          return (
            <li key={step.key} className="flex flex-1 items-center last:flex-none">
              <button
                type="button"
                onClick={() => onStepClick?.(index)}
                disabled={!onStepClick}
                className={cn(
                  'group flex items-center gap-2.5',
                  onStepClick && 'cursor-pointer',
                )}
                aria-current={active ? 'step' : undefined}
              >
                <span
                  className={cn(
                    'flex size-8 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold transition-colors duration-150',
                    done && 'bg-brand-soft text-brand',
                    active && 'bg-brand text-white',
                    !done && !active && 'border border-slate-200 bg-white text-muted',
                  )}
                >
                  {done ? <Check className="size-4" aria-hidden /> : String(index + 1).padStart(2, '0')}
                </span>
                <span
                  className={cn(
                    'hidden text-sm font-medium md:block',
                    active ? 'text-ink' : done ? 'text-body' : 'text-muted',
                  )}
                >
                  {step.label}
                </span>
              </button>
              {index < steps.length - 1 && (
                <span
                  className={cn(
                    'mx-3 h-px flex-1 transition-colors duration-300 sm:mx-4',
                    index < current ? 'bg-brand/35' : 'bg-slate-200',
                  )}
                  aria-hidden
                />
              )}
            </li>
          )
        })}
      </ol>

      {/* Mobile */}
      <div className="flex items-center gap-3 sm:hidden">
        <span className="text-sm font-semibold tabular-nums text-brand">
          Step {current + 1} of {steps.length}
        </span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-softer">
          <div
            className="h-full rounded-full bg-brand transition-all duration-300"
            style={{ width: `${((current + 1) / steps.length) * 100}%` }}
          />
        </div>
        <span className="text-sm font-medium text-ink">{steps[current].label}</span>
      </div>
    </nav>
  )
}
