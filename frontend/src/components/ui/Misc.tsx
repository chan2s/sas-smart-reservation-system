import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'
import { cn, initials } from '@/lib/utils'

// Avatar ---------------------------------------------------------------

export function Avatar({
  name,
  size = 'md',
  className,
}: {
  name: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full bg-brand-soft font-semibold text-brand',
        size === 'sm' && 'size-7 text-[11px]',
        size === 'md' && 'size-9 text-xs',
        size === 'lg' && 'size-12 text-sm',
        className,
      )}
    >
      {initials(name || '?')}
    </span>
  )
}

// Skeleton -------------------------------------------------------------

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton', className)} aria-hidden />
}

export function SkeletonCard() {
  return (
    <div className="card space-y-3 p-5" aria-hidden>
      <Skeleton className="h-4 w-2/5" />
      <Skeleton className="h-3 w-4/5" />
      <Skeleton className="h-9 w-full" />
    </div>
  )
}

// Empty state ----------------------------------------------------------

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string
  description?: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-soft text-muted">
        {icon ?? <Inbox className="size-5" />}
      </div>
      <h3 className="mt-4 text-[15px] font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-body">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

// Spinner --------------------------------------------------------------

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-block size-5 animate-spin rounded-full border-2 border-line border-t-brand',
        className,
      )}
      role="status"
      aria-label="Loading"
    />
  )
}

// Page header ----------------------------------------------------------

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && (
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            {eyebrow}
          </p>
        )}
        <h1 className="mt-1.5 text-3xl font-semibold tracking-tight text-ink sm:text-[36px] sm:leading-[1.15]">
          {title}
        </h1>
        {description && <p className="mt-2 max-w-2xl text-[15px] text-body">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2.5">{actions}</div>}
    </div>
  )
}