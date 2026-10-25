import { cn } from '@/lib/utils'

export interface TabItem {
  key: string
  label: string
  count?: number
}

export function Tabs({
  items,
  active,
  onChange,
  className,
  stretch = false,
}: {
  items: TabItem[]
  active: string
  onChange: (key: string) => void
  className?: string
  /** Share the available width between tabs on narrow screens. */
  stretch?: boolean
}) {
  return (
    <div
      role="tablist"
      className={cn(
        'flex items-center gap-1 overflow-x-auto border-b border-line',
        className,
      )}
    >
      {items.map((item) => {
        const selected = item.key === active
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(item.key)}
            className={cn(
              'relative -mb-px flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors duration-150',
              'focus-visible:rounded-t-md focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand',
              stretch && 'flex-1 justify-center sm:flex-none sm:justify-start',
              selected
                ? 'border-brand text-brand'
                : 'border-transparent text-body hover:text-ink',
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums',
                  selected ? 'bg-brand-soft text-brand' : 'bg-soft text-muted',
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
