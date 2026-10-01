import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ArrowUpDown,
  CircleCheck,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  Pencil,
  RotateCcw,
  Shapes,
  Trash2,
  Wrench,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dropdown, MenuItem } from '@/components/ui/Dropdown'
import { Skeleton } from '@/components/ui/Misc'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { cn, equipmentPrimaryImageUrl } from '@/lib/utils'
import type { Equipment, EquipmentCondition } from '@/lib/types'

/**
 * Equipment inventory table.
 *
 * Modern inventory-management dashboard. Each row is a distinct, spacious card:
 * a clearly visible pastel surface, a 5px coloured rail on the leading edge,
 * a 1px outline, a 12px radius, a soft shadow and 10px of breathing room
 * against the row below. A single deep-navy header separates itself cleanly
 * from the body.
 *
 * Colors are set once per row and carried by CSS custom properties
 * (`--row-bg`, `--row-accent`, `--row-border`), so every cell and the mobile
 * card stay in sync without duplication.
 */

export interface EquipmentRowPalette {
  /** Pastel surface behind the row. */
  bg: string
  /** 5px rail on the leading edge. */
  accent: string
  /** Row outline. */
  border: string
}

const BLUE: EquipmentRowPalette = { bg: '#E8F4FF', accent: '#2563EB', border: '#BFDBFE' }
const ORANGE: EquipmentRowPalette = { bg: '#FFF4E5', accent: '#EA580C', border: '#FED7AA' }
const PURPLE: EquipmentRowPalette = { bg: '#F3E8FF', accent: '#9333EA', border: '#DDD6FE' }
const GREEN: EquipmentRowPalette = { bg: '#E6FAF0', accent: '#059669', border: '#A7F3D0' }

/** A fixed palette for the four core pieces of equipment — named or cycled. */
const NAMED_PALETTES: Record<string, EquipmentRowPalette> = {
  'Event Signage Stand': BLUE,
  'Extension Cord (50 ft)': ORANGE,
  'Folding Chair': PURPLE,
  'Folding Table (6 ft)': GREEN,
}

const PALETTE_CYCLE = [BLUE, ORANGE, PURPLE, GREEN]

export function equipmentRowPalette(
  item: Pick<Equipment, 'name'>,
  index: number,
): EquipmentRowPalette {
  return NAMED_PALETTES[item.name] ?? PALETTE_CYCLE[index % PALETTE_CYCLE.length]
}

/** Publishes the palette as custom properties on a row/card element. */
function paletteVars(palette: EquipmentRowPalette): CSSProperties {
  return {
    '--row-bg': palette.bg,
    '--row-accent': palette.accent,
    '--row-border': palette.border,
  } as CSSProperties
}

type CellPosition = 'first' | 'middle' | 'last'

/**
 * Chrome shared by every cell of a coloured row. Borders are declared per
 * side (never a shorthand) so the 5px accent rail can never be overridden by
 * the 1px outline, whatever order the utilities land in. No conflicting
 * background or border utilities are mixed in: the custom properties win.
 */
function rowCellClass(position: CellPosition, extra?: string) {
  return cn(
    'border-y-[color:var(--row-border)] border-r border-r-[color:var(--row-border)]',
    'bg-[var(--row-bg)] align-middle px-5 py-3',
    'rounded-xl',
    position === 'first' &&
      'w-[32%] border-l-[5px] border-l-[color:var(--row-accent)] rounded-l-xl pl-6',
    position === 'last' && 'rounded-r-xl',
    extra,
  )
}

// ---------------------------------------------------------------------------
// Condition pill — green check-circle badge
// ---------------------------------------------------------------------------

const CONDITION_PILL: Record<
  EquipmentCondition,
  { label: string; className: string; Icon: typeof CircleCheck }
> = {
  EXCELLENT: { label: 'Excellent', className: 'bg-[#ECFDF5] text-[#047857] ring-[#A7F3D0]', Icon: CircleCheck },
  GOOD: { label: 'Good', className: 'bg-[#ECFDF5] text-[#047857] ring-[#A7F3D0]', Icon: CircleCheck },
  FAIR: { label: 'Fair', className: 'bg-[#FFFBEB] text-[#B45309] ring-[#FDE68A]', Icon: CircleCheck },
  POOR: { label: 'Poor', className: 'bg-[#FFF1F2] text-[#BE123C] ring-[#FECDD3]', Icon: CircleCheck },
  DAMAGED: { label: 'Damaged', className: 'bg-[#FFF1F2] text-[#BE123C] ring-[#FECDD3]', Icon: CircleCheck },
}

const PILL_BASE =
  'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[12px] font-semibold ring-1 ring-inset'

function ConditionPill({ condition }: { condition: EquipmentCondition }) {
  const { label, className } = CONDITION_PILL[condition]
  return (
    <span className={cn(PILL_BASE, className)}>
      <CircleCheck className="size-3.5 shrink-0" aria-hidden />
      {label}
    </span>
  )
}

function StatusPill({ item }: { item: Equipment }) {
  const { label, dot, className } = statusMeta(item)
  return (
    <span className={cn(PILL_BASE, className)}>
      <span className={cn('size-1.5 shrink-0 rounded-full', dot)} aria-hidden />
      {label}
    </span>
  )
}

/** Same wording as the shared EquipmentStatusBadge, rendered as a dot pill. */
function statusMeta(item: Equipment) {
  const archived = {
    label: 'Archived',
    dot: 'bg-[#6B7280]',
    className: 'bg-[#F3F4F6] text-[#4B5563] ring-[#E5E7EB]',
  }
  const unavailable = {
    label: 'Unavailable',
    dot: 'bg-[#E11D48]',
    className: 'bg-[#FFF1F2] text-[#BE123C] ring-[#FECDD3]',
  }
  const available = {
    label: 'Available',
    dot: 'bg-[#059669]',
    className: 'bg-[#ECFDF5] text-[#047857] ring-[#A7F3D0]',
  }
  const inUse = {
    label: 'In use',
    dot: 'bg-[#0284C7]',
    className: 'bg-[#F0F9FF] text-[#0369A1] ring-[#BAE6FD]',
  }
  const maintenance = {
    label: 'Under maintenance',
    dot: 'bg-[#EA580C]',
    className: 'bg-[#FFF7ED] text-[#C2410C] ring-[#FED7AA]',
  }

  if (!item.is_active) return archived
  switch (item.status) {
    case 'AVAILABLE':
      if (item.availability.status === 'PARTIAL') return inUse
      if (item.availability.status === 'UNAVAILABLE') return unavailable
      return available
    case 'MAINTENANCE':
      return maintenance
    case 'UNAVAILABLE':
      return unavailable
    case 'RETIRED':
      return archived
  }
}

// ---------------------------------------------------------------------------
// Columns
// ---------------------------------------------------------------------------

const COLUMNS: { key: string; label: string; align?: 'right' }[] = [
  { key: 'equipment', label: 'Equipment' },
  { key: 'category', label: 'Category' },
  { key: 'total', label: 'Total Quantity', align: 'right' },
  { key: 'available', label: 'Available', align: 'right' },
  { key: 'condition', label: 'Condition' },
  { key: 'status', label: 'Status' },
  { key: 'actions', label: 'Actions', align: 'right' },
]

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function EquipmentTableRow({
  item,
  index,
  isStaff,
  onEdit,
  onMaintenance,
  onRemove,
  onRestore,
}: {
  item: Equipment
  index: number
  isStaff: boolean
  onEdit: () => void
  onMaintenance: () => void
  onRemove: () => void
  onRestore: () => void
}) {
  const palette = equipmentRowPalette(item, index)
  const available = item.availability.available
  const availableClass =
    available === 0
      ? 'text-[#E11D48]'
      : available < item.total_quantity
        ? 'text-[#B45309]'
        : 'text-[#059669]'

  return (
    <tr className="group" style={paletteVars(palette)}>
      {/* Equipment ---------------------------------------------------- */}
      <td className={rowCellClass('first')}>
        <div className="flex items-center gap-4">
          <span className="flex size-[68px] shrink-0 items-center justify-center rounded-[14px] bg-white p-0.5 shadow-sm ring-1 ring-black/5">
            <EquipmentImage src={equipmentPrimaryImageUrl(item)} size="sm" alt={item.name} />
          </span>
          <div className="min-w-0">
            <Link
              to={`/equipment/${item.id}`}
              className="block text-[16px] font-bold leading-tight text-[#172554] transition-colors hover:text-brand"
            >
              {item.name}
            </Link>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <span className="text-[13px] text-body">
                {item.storage_location || item.category.name}
              </span>
              {item.asset_code && (
                <span
                  className="rounded-md px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-white"
                  style={{ backgroundColor: palette.accent }}
                >
                  {item.asset_code}
                </span>
              )}
            </div>
          </div>
        </div>
      </td>

      {/* Category ----------------------------------------------------- */}
      <td className={rowCellClass('middle')}>
        <div className="flex items-center gap-2.5">
          <span
            className="flex size-9 shrink-0 items-center justify-center rounded-md bg-white p-0.5 shadow-sm ring-1 ring-black/5"
            style={{ color: palette.accent }}
          >
            <Shapes className="size-[18px]" aria-hidden />
          </span>
          <span
            className="inline-flex max-w-[140px] items-center rounded-md bg-white/75 px-2 py-1"
            style={{ color: palette.accent, boxShadow: `inset 0 0 0 1px ${palette.border}` }}
          >
            <span className="truncate text-[11px] font-semibold uppercase tracking-[0.06em]">
              {item.category.name}
            </span>
          </span>
        </div>
      </td>

      {/* Total quantity ----------------------------------------------- */}
      <td className={rowCellClass('middle', 'text-right')}>
        <span className="text-[15px] font-bold tabular-nums text-[#172554]">{item.total_quantity}</span>
        <span className="ml-1.5 text-[13px] text-body">{item.unit}</span>
      </td>

      {/* Available ---------------------------------------------------- */}
      <td className={rowCellClass('middle', 'text-right')}>
        <span className={cn('text-[20px] font-extrabold leading-none tabular-nums', availableClass)}>
          {available}
        </span>
        {item.availability.reserved > 0 && (
          <span className="ml-1.5 text-[12px] text-body">
            · {Math.min(item.availability.reserved, item.total_quantity)} reserved
          </span>
        )}
      </td>

      {/* Condition ---------------------------------------------------- */}
      <td className={rowCellClass('middle')}>
        <ConditionPill condition={item.condition} />
      </td>

      {/* Status ------------------------------------------------------- */}
      <td className={rowCellClass('middle')}>
        <StatusPill item={item} />
      </td>

      {/* Actions ------------------------------------------------------ */}
      <td className={rowCellClass('last')}>
        <div className="flex items-center justify-end gap-2">
          <Link
            to={`/equipment/${item.id}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[#4f46e5] px-3 text-[13px] font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-[#4338ca]"
          >
            Details
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
          {isStaff ? (
            <>
              <Button variant="outline" size="sm" onClick={onEdit} icon={<Pencil className="size-3.5" />}>
                Edit
              </Button>
              <Dropdown
                trigger={
                  <span className="flex size-8 items-center justify-center rounded-lg border border-line bg-white text-body transition-colors hover:bg-soft hover:text-ink">
                    <MoreHorizontal className="size-4" aria-label={`More actions for ${item.name}`} />
                  </span>
                }
              >
                {(close) => (
                  <>
                    <MenuItem onClick={close}>
                      <Link to={`/equipment/${item.id}`} className="flex w-full items-center gap-2.5">
                        <ArrowRight className="size-4 text-muted" /> View details
                      </Link>
                    </MenuItem>
                    {item.is_active ? (
                      <>
                        <MenuItem onClick={() => { close(); onMaintenance() }}>
                          <Wrench className="size-4 text-muted" /> Under maintenance
                        </MenuItem>
                        <MenuItem danger onClick={() => { close(); onRemove() }}>
                          <Trash2 className="size-4" /> Archive / Delete
                        </MenuItem>
                      </>
                    ) : (
                      <MenuItem onClick={() => { close(); onRestore() }}>
                        <RotateCcw className="size-4 text-muted" /> Restore to inventory
                      </MenuItem>
                    )}
                  </>
                )}
              </Dropdown>
            </>
          ) : null}
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Mobile card
// ---------------------------------------------------------------------------

function EquipmentMobileRow({
  item,
  index,
  isStaff,
  onEdit,
  onMaintenance,
  onRemove,
  onRestore,
}: {
  item: Equipment
  index: number
  isStaff: boolean
  onEdit: () => void
  onMaintenance: () => void
  onRemove: () => void
  onRestore: () => void
}) {
  const palette = equipmentRowPalette(item, index)
  const available = item.availability.available
  const availableClass =
    available === 0
      ? 'text-[#E11D48]'
      : available < item.total_quantity
        ? 'text-[#B45309]'
        : 'text-[#059669]'

  return (
    <div
      className="overflow-hidden rounded-xl border border-l-[5px] border-l-[color:var(--row-accent)] border-[color:var(--row-border)] bg-[var(--row-bg)] shadow-sm p-4"
      style={paletteVars(palette)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-16 shrink-0 items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
            <EquipmentImage src={equipmentPrimaryImageUrl(item)} size="sm" alt={item.name} />
          </span>
          <div className="min-w-0">
            <Link
              to={`/equipment/${item.id}`}
              className="block truncate text-sm font-bold text-[#172554]"
            >
              {item.name}
            </Link>
            <p className="mt-0.5 truncate text-xs text-body">
              {item.category.name}
              {item.asset_code ? ` · ${item.asset_code}` : ''}
            </p>
          </div>
        </div>
        <StatusPill item={item} />
      </div>

      <div className="mt-3 rounded-lg bg-white/70 px-3 py-2.5">
        <div className="grid grid-cols-2 gap-x-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Total</p>
            <div className="mt-0.5 text-sm text-[#172554]">
              <span className="tabular-nums">
                {item.total_quantity} {item.unit}
              </span>
            </div>
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
              Available
            </p>
            <div className={cn('mt-0.5 font-bold tabular-nums', availableClass)}>{available}</div>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[color:var(--row-border)] pt-3">
        <ConditionPill condition={item.condition} />
        <div className="ml-auto flex items-center gap-2">
          {isStaff ? (
            <>
              <Button variant="outline" size="sm" onClick={onEdit}>
                Edit
              </Button>
              <Dropdown
                trigger={
                  <span className="flex size-8 items-center justify-center rounded-lg border border-line bg-white text-body">
                    <MoreHorizontal className="size-4" aria-label={`More actions for ${item.name}`} />
                  </span>
                }
              >
                {(close) => (
                  <>
                    <MenuItem onClick={close}>
                      <Link to={`/equipment/${item.id}`} className="flex w-full items-center gap-2.5">
                        <ArrowRight className="size-4 text-muted" /> View details
                      </Link>
                    </MenuItem>
                    {item.is_active ? (
                      <>
                        <MenuItem onClick={() => { close(); onMaintenance() }}>
                          <Wrench className="size-4 text-muted" /> Under maintenance
                        </MenuItem>
                        <MenuItem danger onClick={() => { close(); onRemove() }}>
                          <Trash2 className="size-4" /> Archive / Delete
                        </MenuItem>
                      </>
                    ) : (
                      <MenuItem onClick={() => { close(); onRestore() }}>
                        <RotateCcw className="size-4 text-muted" /> Restore to inventory
                      </MenuItem>
                    )}
                  </>
                )}
              </Dropdown>
            </>
          ) : (
            <Link
              to={`/equipment/${item.id}`}
              className="inline-flex items-center gap-1 rounded-lg bg-[#4f46e5] px-2.5 py-1.5 text-[13px] font-semibold text-white"
            >
              Details <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

function EquipmentPagination({
  page,
  numPages,
  pageSize,
  count,
  onPage,
}: {
  page: number
  numPages: number
  pageSize: number
  count: number
  onPage: (page: number) => void
}) {
  // Compact window of page numbers around the current page.
  const pages: number[] = []
  const start = Math.max(1, Math.min(page - 1, numPages - 2))
  const end = Math.min(numPages, start + 2)
  for (let value = Math.max(1, start); value <= end; value += 1) pages.push(value)

  const from = (page - 1) * pageSize + 1
  const to = Math.min(count, page * pageSize)

  const buttonBase =
    'inline-flex h-9 min-w-9 items-center justify-center gap-1 rounded-lg border px-3 text-[13px] font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40'
  const idle =
    'border-line bg-surface text-body hover:bg-soft hover:text-ink'
  const active = 'border-[#4f46e5] bg-[#4f46e5] text-white shadow-sm'

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-4 lg:px-5">
      <p className="text-xs text-muted">
        Showing <span className="font-semibold text-[#1f2937] tabular-nums">{from}</span>–
        <span className="font-semibold text-[#1f2937] tabular-nums">{to}</span> of{' '}
        <span className="font-semibold text-[#1f2937] tabular-nums">{count}</span> items
      </p>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => onPage(Math.max(1, page - 1))}
          disabled={page <= 1}
          aria-label="Previous page"
          className={cn(buttonBase, idle)}
        >
          <ChevronLeft className="size-4" aria-hidden />
          Prev
        </button>
        {pages[0] > 1 && <span className="px-1 text-xs text-muted">…</span>}
        {pages.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => onPage(value)}
            aria-current={value === page ? 'page' : undefined}
            className={cn(buttonBase, value === page ? active : idle)}
          >
            {value}
          </button>
        ))}
        {end < numPages && <span className="px-1 text-xs text-muted">…</span>}
        <button
          type="button"
          onClick={() => onPage(Math.min(numPages, page + 1))}
          disabled={page >= numPages}
          aria-label="Next page"
          className={cn(buttonBase, idle)}
        >
          Next
          <ChevronRight className="size-4" aria-hidden />
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

export function EquipmentTable({
  data,
  isLoading,
  emptyState,
  page,
  numPages,
  pageSize,
  total,
  onPage,
  isStaff,
  onEdit,
  onMaintenance,
  onRemove,
  onRestore,
}: {
  data: Equipment[]
  isLoading: boolean
  emptyState?: ReactNode
  page: number
  numPages: number
  pageSize: number
  /** Items matching the current filters, before slicing for the page. */
  total: number
  onPage: (page: number) => void
  isStaff: boolean
  onEdit: (item: Equipment) => void
  onMaintenance: (item: Equipment) => void
  onRemove: (item: Equipment) => void
  onRestore: (item: Equipment) => void
}) {
  return (
    <div className="mt-5 overflow-hidden rounded-card border border-line bg-surface shadow-card">
      {isLoading ? (
        <div className="space-y-2.5 p-4 lg:p-5" aria-busy="true" aria-label="Loading">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-[115px] rounded-xl" />
          ))}
        </div>
      ) : data.length === 0 ? (
        emptyState
      ) : (
        <>
          <div className="hidden px-4 pb-4 pt-3 md:block lg:px-5 lg:pb-5">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1000px] border-separate border-spacing-x-0 border-spacing-y-2.5 text-left text-sm">
                <caption className="sr-only">Equipment inventory</caption>
                <thead>
                  <tr className="h-[56px] rounded-xl">
                    {COLUMNS.map((column) => (
                      <th
                        key={column.key}
                        scope="col"
                        className="bg-[#172554] px-5 align-middle text-[11px] font-bold uppercase tracking-[0.08em] text-white first:rounded-l-xl last:rounded-r-xl"
                      >
                        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                          {column.label}
                          <ArrowUpDown className="size-3.5 shrink-0 text-white/40" aria-hidden />
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.map((item, index) => (
                    <EquipmentTableRow
                      key={item.id}
                      item={item}
                      index={index}
                      isStaff={isStaff}
                      onEdit={() => onEdit(item)}
                      onMaintenance={() => onMaintenance(item)}
                      onRemove={() => onRemove(item)}
                      onRestore={() => onRestore(item)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="p-4 md:hidden">
            <ul className="space-y-2.5">
              {data.map((item, index) => (
                <li key={item.id}>
                  <EquipmentMobileRow
                    item={item}
                    index={index}
                    isStaff={isStaff}
                    onEdit={() => onEdit(item)}
                    onMaintenance={() => onMaintenance(item)}
                    onRemove={() => onRemove(item)}
                    onRestore={() => onRestore(item)}
                  />
                </li>
              ))}
            </ul>
          </div>

          {numPages > 1 && (
            <EquipmentPagination
              page={page}
              numPages={numPages}
              pageSize={pageSize}
              count={total}
              onPage={onPage}
            />
          )}
        </>
      )}
    </div>
  )
}
