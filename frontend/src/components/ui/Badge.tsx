import type { HTMLAttributes } from 'react'
import { cn, STATUS_META } from '@/lib/utils'
import type { ReservationStatus } from '@/lib/types'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: 'neutral' | 'brand' | 'emerald' | 'amber' | 'rose' | 'orange' | 'sky' | 'teal' | 'gray'
}

const tones: Record<NonNullable<BadgeProps['tone']>, string> = {
  neutral: 'bg-soft text-body',
  brand: 'bg-brand-soft text-brand',
  emerald: 'bg-status-available-bg text-status-available',
  amber: 'bg-status-pending-bg text-status-pending',
  rose: 'bg-status-rejected-bg text-status-rejected',
  orange: 'bg-status-maintenance-bg text-status-maintenance',
  sky: 'bg-status-active-bg text-status-active',
  teal: 'bg-status-completed-bg text-status-completed',
  gray: 'bg-status-cancelled-bg text-status-cancelled',
}

export function Badge({ className, tone = 'neutral', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium',
        tones[tone],
        className,
      )}
      {...props}
    />
  )
}

export function StatusBadge({ status, className }: { status: ReservationStatus; className?: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.PENDING
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium',
        meta.bg,
        meta.text,
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', meta.dot)} aria-hidden />
      {meta.label}
    </span>
  )
}