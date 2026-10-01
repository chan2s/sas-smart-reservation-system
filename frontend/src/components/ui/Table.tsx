import type {
  ElementType,
  HTMLAttributes,
  ReactNode,
  TableHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from 'react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/Misc'

/**
 * SAS RESERVE table design system.
 *
 * ONE implementation of the administrative data-table pattern, reused by every
 * table in the app so headers, rows, zebra striping, hover, badges, actions,
 * empty/loading states and pagination always look the same.
 *
 *   <TableContainer>
 *     <Table>
 *       <TableHeader>
 *         <TableRow header><TableHead>Event</TableHead>…</TableRow>
 *       </TableHeader>
 *       <TableBody>
 *         <TableRow><TableCell>…</TableCell></TableRow>
 *       </TableBody>
 *     </Table>
 *   </TableContainer>
 *
 * `ResponsiveTable` layers the mobile behaviour on top: desktop keeps a real
 * semantic table (horizontally scrollable when needed), while mobile renders
 * the same data as stacked cards so nothing overflows the page.
 */

// ---------------------------------------------------------------------------
// Container
// ---------------------------------------------------------------------------

/** White surface, subtle border, moderate radius; clips the table's corners. */
export function TableContainer({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'overflow-hidden rounded-card border border-line bg-surface shadow-card',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

/** Optional filter/search strip that sits above the table, visually separate. */
export function TableToolbar({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 border-b border-line bg-soft/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Table primitives
// ---------------------------------------------------------------------------

export function Table({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return <table className={cn('w-full border-collapse text-left text-sm', className)} {...props} />
}

export function TableHeader({
  className,
  ...props
}: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn('bg-softer', className)} {...props} />
}

export function TableBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn('divide-y divide-line', className)} {...props} />
}

export function TableRow({
  className,
  header,
  ...props
}: HTMLAttributes<HTMLTableRowElement> & { header?: boolean }) {
  return (
    <tr
      className={cn(
        'transition-colors duration-150',
        header
          ? 'border-b border-line'
          : 'even:bg-soft/60 hover:bg-brand-soft/50',
        className,
      )}
      {...props}
    />
  )
}

type Align = 'left' | 'center' | 'right'

function alignClass(align?: Align) {
  if (align === 'right') return 'text-right'
  if (align === 'center') return 'text-center'
  return 'text-left'
}

export function TableHead({
  className,
  align,
  children,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement> & { align?: Align }) {
  return (
    <th
      scope="col"
      className={cn(
        'whitespace-nowrap border-b border-line px-4 py-3 first:pl-5 last:pr-5',
        'text-[11px] font-semibold uppercase tracking-[0.08em] text-body',
        alignClass(align),
        className,
      )}
      {...props}
    >
      {children}
    </th>
  )
}

export function TableCell({
  className,
  align,
  children,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement> & { align?: Align }) {
  return (
    <td
      className={cn(
        'px-4 py-3.5 align-middle first:pl-5 last:pr-5',
        alignClass(align),
        className,
      )}
      {...props}
    >
      {children}
    </td>
  )
}

/** Primary value in a cell: darker + semibold. */
export function TablePrimary({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('block font-medium text-ink', className)} {...props} />
}

/** Secondary value in a cell: muted + smaller. */
export function TableSecondary({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('block text-xs text-muted', className)} {...props} />
}

/** Right-aligned action group that never overflows its cell. */
export function TableActions({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn('flex flex-wrap items-center justify-end gap-1.5', className)}>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

type BadgeTone = 'neutral' | 'brand' | 'emerald' | 'amber' | 'rose' | 'orange' | 'sky' | 'teal' | 'gray'

/** One canonical tone per status string, shared by every table in the app. */
const STATUS_TONE: Record<string, BadgeTone> = {
  PENDING: 'amber',
  APPROVED: 'emerald',
  ACTIVE: 'sky',
  COMPLETED: 'teal',
  REJECTED: 'rose',
  CANCELLED: 'gray',
  AVAILABLE: 'emerald',
  UNAVAILABLE: 'rose',
  MAINTENANCE: 'orange',
  DAMAGED: 'rose',
  RETIRED: 'gray',
  SUSPENDED: 'gray',
  ARCHIVED: 'gray',
  OPEN: 'amber',
  RESOLVED: 'emerald',
  INSPECTED: 'amber',
  PARTIAL: 'amber',
  IN_USE: 'sky',
  OPERATIONAL: 'emerald',
}

const TONE_CLASSES: Record<BadgeTone, string> = {
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

const TONE_DOT: Record<BadgeTone, string> = {
  neutral: 'bg-muted',
  brand: 'bg-brand',
  emerald: 'bg-status-available',
  amber: 'bg-status-pending',
  rose: 'bg-status-rejected',
  orange: 'bg-status-maintenance',
  sky: 'bg-status-active',
  teal: 'bg-status-completed',
  gray: 'bg-status-cancelled',
}

function humanize(value: string) {
  return value
    .toLowerCase()
    .split(/[_\s]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Standard status pill used in every table. Pass `tone`/`label` only when a
 * status needs wording or a colour the shared map cannot derive.
 */
export function TableStatusBadge({
  status,
  label,
  tone,
  withDot = true,
  className,
}: {
  status: string
  label?: string
  tone?: BadgeTone
  withDot?: boolean
  className?: string
}) {
  const resolvedTone = tone ?? STATUS_TONE[status?.toUpperCase()] ?? 'neutral'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        TONE_CLASSES[resolvedTone],
        className,
      )}
    >
      {withDot && (
        <span className={cn('size-1.5 rounded-full', TONE_DOT[resolvedTone])} aria-hidden />
      )}
      {label ?? humanize(status || 'Unknown')}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Empty / loading
// ---------------------------------------------------------------------------

export function TableLoading({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2.5 p-5" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-11" />
      ))}
    </div>
  )
}

/** Neutral fallback empty state; pages can pass richer copy via `emptyState`. */
export function TableEmpty({
  title,
  description,
}: {
  title: string
  description?: string
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <p className="text-[15px] font-semibold text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-body">{description}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

/**
 * Standard Previous / page numbers / Next control. Wraps on small screens so
 * it never overflows the page.
 */
export function TablePagination({
  page,
  numPages,
  onPage,
  count,
  className,
}: {
  page: number
  numPages: number
  onPage: (page: number) => void
  /** Optional total record count for the "Showing …" summary. */
  count?: number
  className?: string
}) {
  if (numPages <= 1) return null

  // Compact window of page numbers around the current page.
  const pages: number[] = []
  const start = Math.max(1, Math.min(page - 1, numPages - 2))
  const end = Math.min(numPages, start + 2)
  for (let value = Math.max(1, start); value <= end; value += 1) pages.push(value)

  const buttonBase =
    'inline-flex h-8 min-w-8 items-center justify-center rounded-lg border px-2.5 text-[13px] font-medium transition-colors duration-150 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand'

  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-3 border-t border-line bg-soft/50 px-5 py-3.5',
        className,
      )}
    >
      <p className="text-xs text-muted">
        {typeof count === 'number' ? `${count} total · ` : ''}Page {page} of {numPages}
      </p>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => onPage(Math.max(1, page - 1))}
          disabled={page <= 1}
          className={cn(
            buttonBase,
            'border-line bg-surface text-body hover:bg-soft disabled:text-muted disabled:hover:bg-surface',
          )}
        >
          Previous
        </button>
        {pages[0] > 1 && <span className="px-1 text-xs text-muted">…</span>}
        {pages.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => onPage(value)}
            aria-current={value === page ? 'page' : undefined}
            className={cn(
              buttonBase,
              value === page
                ? 'border-brand bg-brand text-white'
                : 'border-line bg-surface text-body hover:bg-soft',
            )}
          >
            {value}
          </button>
        ))}
        {end < numPages && <span className="px-1 text-xs text-muted">…</span>}
        <button
          type="button"
          onClick={() => onPage(Math.min(numPages, page + 1))}
          disabled={page >= numPages}
          className={cn(
            buttonBase,
            'border-line bg-surface text-body hover:bg-soft disabled:text-muted disabled:hover:bg-surface',
          )}
        >
          Next
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Responsive wrapper
// ---------------------------------------------------------------------------

export interface ResponsiveTableColumn {
  /** Stable key for the column. */
  key: string
  /** Header label shown on desktop only. */
  label: string
  align?: Align
  /** Extra classes for the `<th>` (e.g. widths). */
  className?: string
}

export interface ResponsiveTableProps<T> {
  columns: ResponsiveTableColumn[]
  data: T[]
  rowKey: (item: T, index: number) => string | number
  /** Desktop `<TableRow>` for one item (rendered inside `<tbody>`). */
  renderDesktopRow: (item: T, index: number) => ReactNode
  /** Mobile card body for one item (rendered inside an `<li>`). */
  renderMobileCard: (item: T, index: number) => ReactNode
  isLoading?: boolean
  isEmpty?: boolean
  /** Rendered instead of the table when set (API failure states). */
  errorState?: ReactNode
  /** Rendered when `isEmpty`. */
  emptyState?: ReactNode
  skeletonRows?: number
  /** Breakpoint at/above which the table layout is used. Defaults to `md`. */
  breakpoint?: 'sm' | 'md'
  /** Accessible caption for the desktop table. */
  caption?: string
  /** Min width for the table so columns never crush on narrow screens. */
  minWidthClassName?: string
  /** Optional toolbar row rendered above the table (search/filters). */
  toolbar?: ReactNode
  /** Optional content under the table/card list (e.g. pagination). */
  footer?: ReactNode
  containerClassName?: string
  /**
   * `card` (default) wraps the table in its own bordered surface. Use `bare`
   * when the table is embedded inside an existing Card, to avoid nesting two
   * bordered containers.
   */
  variant?: 'card' | 'bare'
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
  minWidthClassName,
  toolbar,
  footer,
  containerClassName,
  variant = 'card',
}: ResponsiveTableProps<T>) {
  const tableVisibility = breakpoint === 'sm' ? 'hidden sm:table' : 'hidden md:table'
  const cardVisibility = breakpoint === 'sm' ? 'sm:hidden' : 'md:hidden'
  const Wrapper: ElementType = variant === 'bare' ? 'div' : TableContainer

  return (
    <Wrapper className={containerClassName}>
      {toolbar}
      {errorState}
      {!errorState && isLoading && <TableLoading rows={skeletonRows} />}
      {!errorState && !isLoading && isEmpty && (emptyState ?? <TableEmpty title="Nothing to show" />)}
      {!errorState && !isLoading && !isEmpty && (
        <>
          <div className="overflow-x-auto">
            <Table className={cn(minWidthClassName, tableVisibility)}>
              {caption && <caption className="sr-only">{caption}</caption>}
              <TableHeader>
                <TableRow header>
                  {columns.map((column) => (
                    <TableHead key={column.key} align={column.align} className={column.className}>
                      {column.label}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>{data.map((item, index) => renderDesktopRow(item, index))}</TableBody>
            </Table>
          </div>

          <ul className={cn('divide-y divide-line', cardVisibility)}>
            {data.map((item, index) => (
              <li key={rowKey(item, index)}>{renderMobileCard(item, index)}</li>
            ))}
          </ul>
        </>
      )}
      {footer}
    </Wrapper>
  )
}

// ---------------------------------------------------------------------------
// Mobile card building blocks
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

/** Wrapped action group for mobile cards so buttons never overflow/overlap. */
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
