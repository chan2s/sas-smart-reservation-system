import { Info, Receipt } from 'lucide-react'
import type { PricingFeeLine, PricingQuote } from '@/lib/types'
import { cn, formatCurrency } from '@/lib/utils'

/**
 * Estimated-cost breakdown for a reservation.
 *
 * Every amount is rendered from the backend's quote — the frontend never
 * computes a rate. For internal campus requesters the backend returns an empty
 * quote (`external: false`), which this component shows as "No external
 * organization fees apply" rather than displaying external prices as if
 * charged. The amount is explicitly labelled an estimate until the reservation
 * is approved.
 */
export function PricingBreakdown({
  pricing,
  loading,
  className,
  title,
}: {
  pricing: PricingQuote | null | undefined
  loading?: boolean
  className?: string
  /** Overrides the default heading (default: "Estimated cost"). */
  title?: string
}) {
  if (!pricing) {
    if (!loading) return null
    return (
      <div
        className={cn('rounded-xl border border-line bg-surface p-5', className)}
        aria-busy="true"
      >
        <div className="h-4 w-1/3 animate-pulse rounded bg-soft" />
        <div className="mt-4 space-y-2">
          {[1, 2, 3].map((index) => (
            <div key={index} className="h-3 animate-pulse rounded bg-soft" />
          ))}
        </div>
      </div>
    )
  }

  const external = pricing.external
  const heading = title ?? (external ? 'Estimated external organization fee' : 'Estimated cost')

  return (
    <section
      className={cn(
        'overflow-hidden rounded-xl border',
        external ? 'border-brand/20 bg-brand-soft/40' : 'border-line bg-surface',
        className,
      )}
      aria-label={heading}
    >
      <div className="flex items-start gap-2.5 px-5 pt-5">
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-xl',
            external ? 'bg-brand text-white' : 'bg-soft text-body',
          )}
          aria-hidden
        >
          <Receipt className="size-4.5" />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink">{heading}</h3>
          <p className="text-[13px] text-body">
            {external
              ? 'Rates are configured by the SAS Office and applied to external organizations.'
              : 'Internal campus requesters are not charged external organization fees.'}
          </p>
        </div>
      </div>

      {external && pricing.fees.length > 0 ? (
        <ul className="mt-4 divide-y divide-line/70 border-t border-line/70">
          {pricing.fees.map((line, index) => (
            <FeeRow key={`${line.fee_type}-${line.equipment_category_id ?? index}-${index}`} line={line} />
          ))}
        </ul>
      ) : (
        <p className="mt-4 border-t border-line/70 px-5 py-4 text-sm text-body">
          {external
            ? 'No fees apply to this reservation with the selected facility and resources.'
            : 'No external organization fees apply.'}
        </p>
      )}

      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-line/70 bg-surface/60 px-5 py-4">
        <span className="text-sm font-semibold uppercase tracking-[0.08em] text-muted">
          Estimated total
        </span>
        <span className="text-xl font-semibold tabular-nums text-ink" aria-live="polite">
          {formatCurrency(pricing.total)}
        </span>
      </div>

      <p className="flex items-start gap-1.5 border-t border-line/70 px-5 py-3 text-xs leading-relaxed text-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>
          {pricing.note ||
            'This is an estimate. The SAS Office confirms the final amount when the reservation is approved.'}
        </span>
      </p>
    </section>
  )
}

function FeeRow({ line }: { line: PricingFeeLine }) {
  return (
    <li className="flex items-start justify-between gap-4 px-5 py-3.5">
      <div className="min-w-0">
        <p className="break-words text-sm font-medium text-ink">{line.description}</p>
        <p className="mt-0.5 break-words text-xs tabular-nums text-muted">
          {feeCalculation(line)}
        </p>
      </div>
      <p className="shrink-0 text-sm font-semibold tabular-nums text-ink">
        {formatCurrency(line.subtotal)}
      </p>
    </li>
  )
}

/** Human-readable arithmetic for one fee line, e.g. "100 × ₱5.00 = ₱500.00". */
function feeCalculation(line: PricingFeeLine): string {
  const unitPrice = formatCurrency(line.unit_price)
  const subtotal = formatCurrency(line.subtotal)

  if (line.unit === 'flat') {
    return `Flat fee = ${subtotal}`
  }
  if (line.unit === 'hour') {
    const hours = line.quantity === '1' ? 'hour' : 'hours'
    return `${line.quantity} ${hours} × ${unitPrice} = ${subtotal}`
  }
  return `${line.quantity} × ${unitPrice} = ${subtotal}`
}
