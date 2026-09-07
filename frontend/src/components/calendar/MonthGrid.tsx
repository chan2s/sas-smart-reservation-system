import { format, startOfMonth, endOfMonth, startOfWeek, endOfWeek, addDays, isSameMonth, isSameDay, isToday } from 'date-fns'
import { cn } from '@/lib/utils'

const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

interface MonthGridProps {
  month: Date
  selected?: Date | null
  onSelect?: (date: Date) => void
  renderDay?: (date: Date) => React.ReactNode
  className?: string
}

export function MonthGrid({ month, selected, onSelect, renderDay, className }: MonthGridProps) {
  const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 })
  const end = endOfWeek(endOfMonth(month), { weekStartsOn: 1 })

  const days: Date[] = []
  let cursor = start
  while (cursor <= end) {
    days.push(cursor)
    cursor = addDays(cursor, 1)
  }

  return (
    <div className={className}>
      <div className="grid grid-cols-7 gap-1">
        {weekdayLabels.map((label) => (
          <div
            key={label}
            className="pb-2 text-center text-[11px] font-semibold uppercase tracking-wider text-muted"
          >
            {label}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => {
          const outside = !isSameMonth(day, month)
          const daySelected = selected != null && isSameDay(day, selected)
          const today = isToday(day)
          const interactive = !outside && Boolean(onSelect)
          const content = (
            <>
              {format(day, 'd')}
              {renderDay?.(day)}
            </>
          )
          const cellClass = cn(
            'relative flex min-h-10 flex-col items-center rounded-lg pt-1.5 text-sm transition-colors duration-150 sm:min-h-11',
            outside && 'text-faint',
            interactive && !daySelected && 'hover:bg-soft',
            today && !daySelected && 'font-bold text-brand',
            daySelected && 'bg-brand font-semibold text-white shadow-sm',
          )
          return interactive ? (
            <button
              key={day.toISOString()}
              type="button"
              onClick={() => onSelect?.(day)}
              aria-label={format(day, 'MMMM d, yyyy')}
              aria-pressed={daySelected}
              className={cellClass}
            >
              {content}
            </button>
          ) : (
            <div key={day.toISOString()} className={cellClass}>
              {content}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function CalendarHeader({ month, onPrev, onNext }: { month: Date; onPrev: () => void; onNext: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <h3 className="text-[15px] font-semibold text-ink">{format(month, 'MMMM yyyy')}</h3>
      <div className="flex items-center gap-1">
        <HeaderArrow onClick={onPrev} label="Previous month" direction="prev" />
        <HeaderArrow onClick={onNext} label="Next month" direction="next" />
      </div>
    </div>
  )
}

function HeaderArrow({ onClick, label, direction }: { onClick: () => void; label: string; direction: 'prev' | 'next' }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="flex size-8 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-soft hover:text-ink"
    >
      <svg
        className={cn('size-4', direction === 'prev' && 'rotate-180')}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <path d="m9 18 6-6-6-6" />
      </svg>
    </button>
  )
}