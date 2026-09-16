import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/Misc'

/**
 * Reusable responsive table.
 *
 * ONE implementation of the app-wide table pattern:
 *   - Desktop/tablet: a real semantic `<table>` (unchanged from the original
 *     hand-rolled markup — same header styling, same row renderers).
 *   - Mobile: the same data rendered as stacked cards with semantic labels,
 *     so nothing important is lost and no horizontal scrolling is needed.
 *
 * The component owns the shared states (loading skeleton, error, empty) so
 * every table presents them consistently. Pages keep full control of their
 * desktop `<tr>` markup and their mobile card content.
 */

export interface ResponsiveTableColumn {
  /** Stable key for the column. */
  key: string
  /** Header label shown on desktop only. */
  label: string
  align?: 'left' | 'right'
  /** Extra classes for the `<th>` (e.g. max-widths). */
  className?: string
}

interface ResponsiveTableProps<T> {
  columns: ResponsiveTableColumn[]
  data: T[]
  rowKey: (item: T, index: number) => string | number
  /** Desktop `<tr>` content — rendered inside `<tbody>` for each item. */
  renderDesktopRow: (item: T, index: number) => ReactNode
  /** Mobile card content — rendered inside a `<li>` for each item. */
  renderMobileCard: (item: T, index: number) => ReactNode
  isLoading?: boolean
  isEmpty?: boolean
  /** Rendered instead of the table when set (API failure states). */
  errorState?: ReactNode
  /** Rendered when `isEmpty` (filters give pages full control of the copy). */
  emptyState?: ReactNode
  /** Number of loading skeleton rows. */
  skeletonRows?: number
  /** Breakpoint at/above which the table layout is used. Defaults to `md`. */
  breakpoint?: 'sm' | 'md'
  /** Accessible caption for the desktop table. */
  caption?: string
  /** Optional content under the table/card list (e.g. background refresh). */
  footer?: ReactNode
}

export function ResponsiveTable<T>({
  columns,
  data,
  rowKey,
  renderDesktopRow,
  renderMobileCard,
  isLoading = false,
  isEmpty = false,
  errorState,
  emptyState,
  skeletonRows = 6,
  breakpoint = 'md',
  caption,
  footer,
}: ResponsiveTableProps<T>) {
  const tableVisibility = breakpoint === 'sm' ? 'hidden sm:table' : 'hidden md:table'
  const cardVisibility = breakpoint === 'sm' ? 'sm:hidden' : 'md:hidden'

  return (
    <div>
      {errorState}
      {!errorState && isLoading && (
        <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading">
          {Array.from({ length: skeletonRows }).map((_, index) => (
            <Skeleton key={index} className="h-12" />
          ))}
        </div>
      )}
      {!errorState && !isLoading && isEmpty && emptyState}
      {!errorState && !isLoading && !isEmpty && (
        <>
          {/* Desktop / tablet — semantic table preserved from the original UI */}
          <table className={cn('w-full text-left', tableVisibility)}>
            {caption && <caption className="sr-only">{caption}</caption>}
            <thead>
              <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
                {columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className={cn(
                      'py-3.5 first:pl-5 last:pr-5 px-4',
                      column.align === 'right' && 'text-right',
                      column.className,
                    )}
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((item, index) => renderDesktopRow(item, index))}
            </tbody>
          </table>

          {/* Mobile — stacked cards with semantic labels */}
          <ul className={cn('divide-y divide-line', cardVisibility)}>
            {data.map((item, index) => (
              <li key={rowKey(item, index)}>{renderMobileCard(item, index)}</li>
            ))}
          </ul>
        </>
      )}
      {footer}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mobile card building blocks (shared by every table's mobile presentation)
// ---------------------------------------------------------------------------

/** A labeled field inside a mobile card: tiny uppercase label + value. */
export function CardField({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</p>
      <div className="mt-0.5 text-sm text-ink">{children}</div>
    </div>
  )
}

/**
 * A wrapped action group for mobile cards. Buttons never overflow or overlap:
 * the group wraps to the next line, and every child keeps a comfortable
 * touch target (sm buttons are h-8/32px + py padding of the row ≥ 44px).
 */
export function CardActions({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-wrap items-center gap-2 border-t border-line pt-3', className)}>
      {children}
    </div>
  )
}
