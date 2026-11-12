import { Info, Receipt } from 'lucide-react'
import type { PricingFeeLine, PricingQuote } from '@/lib/types'
import { cn, formatCurrency, pluralizeUnit } from '@/lib/utils'

/** Displays the server's official quote. Internal reference charges are shown
 * alongside their waiver while the payable total remains zero. */
export function PricingBreakdown({
  pricing,
  loading,
  className,
  title,
}: {
  pricing: PricingQuote | null | undefined
  loading?: boolean
  className?: string
  title?: string
}) {
  if (!pricing) {
    if (!loading) return null
    return <div className={cn('rounded-xl border border-line bg-surface p-5', className)} aria-busy="true">
      <div className="h-4 w-1/3 animate-pulse rounded bg-soft" />
      <div className="mt-4 space-y-2">{[1, 2, 3].map((n) => <div key={n} className="h-3 animate-pulse rounded bg-soft" />)}</div>
    </div>
  }

  const external = pricing.external
  const heading = title ?? (external ? 'Estimated rental charges' : 'Internal Reservation — No Payment Required')
  return (
    <section className={cn('overflow-hidden rounded-xl border', external ? 'border-brand/20 bg-brand-soft/40' : 'border-line bg-surface', className)} aria-label={heading}>
      <div className="flex items-start gap-2.5 px-5 pt-5">
        <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-xl', external ? 'bg-brand text-white' : 'bg-soft text-body')} aria-hidden>
          <Receipt className="size-4.5" />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink">{heading}</h3>
          <p className="text-[13px] text-body">
            {external
              ? 'Official NORSU-BSC Rental Agreement rates apply.'
              : 'The same official rental rates are shown for reference. All charges are waived for internal reservations.'}
          </p>
        </div>
      </div>

      <dl className="mt-4 divide-y divide-line/70 border-t border-line/70">
        {pricing.fees.map((line, index) => <FeeRow key={`${line.fee_type}-${line.description}-${index}`} line={line} />)}
      </dl>

      {!external && (
        <div className="flex justify-between gap-4 border-t border-line/70 px-5 py-3.5 text-sm">
          <span className="font-medium text-body">Official rental value</span>
          <span className="font-semibold tabular-nums text-muted">{formatCurrency(pricing.reference_total)}</span>
        </div>
      )}

      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-line/70 bg-surface/60 px-5 py-4">
        <span className="text-sm font-semibold uppercase tracking-[0.08em] text-muted">{external ? 'Total amount payable' : 'Total payable'}</span>
        <span className="text-xl font-semibold tabular-nums text-ink" aria-live="polite">
          {external ? formatCurrency(pricing.total) : `PHP ${Number(pricing.total).toFixed(2)}`}
        </span>
      </div>

      <p className="flex items-start gap-1.5 border-t border-line/70 px-5 py-3 text-xs leading-relaxed text-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>{pricing.note || (external ? 'The SAS Office confirms the final amount when the reservation is approved.' : 'Internal Reservation — No Payment Required.')}</span>
      </p>
    </section>
  )
}

function FeeRow({ line }: { line: PricingFeeLine }) {
  const detail = line.fee_type === 'FACILITY' && line.rental_period === 'PER_HOUR'
    ? `${line.quantity} hours × ${formatCurrency(line.unit_price)}`
    : line.fee_type === 'EQUIPMENT'
    ? `${line.quantity} ${Number(line.quantity) === 1 ? line.equipment_unit || 'unit' : pluralizeUnit(line.equipment_unit || 'unit')} × ${formatCurrency(line.unit_price)}`
    : line.period_label || (line.fee_type === 'OPERATOR' ? 'Operator service' : line.fee_type === 'ENVIRONMENTAL' ? 'Required fee' : line.unit === 'hour' ? `${line.quantity} hours × ${formatCurrency(line.unit_price)}` : 'Rental charge')
  return (
    <div className="flex items-start justify-between gap-4 px-5 py-3.5">
      <dt className="min-w-0">
        <p className="break-words text-sm font-medium text-ink">{line.description}</p>
        <p className="mt-0.5 break-words text-xs tabular-nums text-muted">{detail}{line.waived ? ' · Waived' : ''}</p>
      </dt>
      <dd className="shrink-0 text-sm font-semibold tabular-nums text-ink">
        {line.waived && <span className="mr-2 text-xs font-normal text-muted">Waived</span>}
        <span className={line.waived ? 'line-through text-muted' : ''}>{formatCurrency(line.subtotal)}</span>
      </dd>
    </div>
  )
}
