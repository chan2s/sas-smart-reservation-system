import { AlertTriangle, CheckCircle2, Clock3, Sparkles, XCircle } from 'lucide-react'
import { cn, formatDate, formatTime } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import type {
  AlternativeSlot,
  AvailabilityCheck as AvailabilityCheckResult,
  AvailabilityItem,
  FacilityConflict,
} from '@/lib/types'

export function AvailabilityCheck({
  report,
  onUseAlternative,
}: {
  report: AvailabilityCheckResult
  onUseAlternative?: (alternative: AlternativeSlot) => void
}) {
  const { overall, facility, items } = report
  const ok = overall.ok
  const facilityOk = facility.status === 'OPERATIONAL' && facility.conflicts.length === 0

  return (
    <div
      className={cn(
        'overflow-hidden rounded-xl border',
        ok
          ? 'border-status-available/25 bg-status-available-bg'
          : 'border-status-rejected/25 bg-status-rejected-bg',
      )}
      role="status"
      aria-live="polite"
    >
      <div className="px-4 py-3.5">
        <div className="flex items-start gap-2.5">
          {ok ? (
            <CheckCircle2 className="mt-0.5 size-4.5 shrink-0 text-status-available" aria-hidden />
          ) : (
            <AlertTriangle className="mt-0.5 size-4.5 shrink-0 text-status-rejected" aria-hidden />
          )}
          <div>
            <p className={cn('text-sm font-semibold', ok ? 'text-status-available' : 'text-status-rejected')}>
              {ok ? 'Availability confirmed' : 'Resource conflict detected'}
            </p>
            {ok && (
              <p className="mt-0.5 text-[13px] leading-relaxed text-body">
                All requested facilities and resources are available for your selected schedule.
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-1.5 border-t border-black/5 px-4 py-4">
        {/* Facility */}
        <StatusRow
          ok={facilityOk}
          label={`${facility.name} ${facilityOk ? 'available' : 'unavailable'}`}
          detail={
            facility.conflicts.length > 0 ? (
              <ConflictDetail conflicts={facility.conflicts} />
            ) : undefined
          }
        />
        {facility.operating_hours && !facility.operating_hours.within_hours && (
          <StatusRow
            ok={false}
            label={`Within operating hours (${formatTime(facility.operating_hours.open ?? '')}–${formatTime(facility.operating_hours.close ?? '')})`}
          />
        )}

        {/* Equipment — one row per requested resource */}
        {items.map((item) => (
          <ResourceRow key={item.equipment_id} item={item} />
        ))}
      </div>

      {/*
       * Remaining problems. Equipment problems are skipped here because each
       * equipment row already explains its own shortage inline.
       */}
      {!ok &&
        report.problems
          .filter((problem) => problem.type !== 'equipment')
          .map((problem, index) => (
            <p key={index} className="px-4 pb-3 text-[13px] leading-relaxed text-status-rejected">
              {problem.message}
            </p>
          ))}

      {/* Recommended alternative */}
      {!ok && report.alternatives && report.alternatives.length > 0 && (
        <div className="border-t border-black/5 px-4 py-4">
          <p className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
            <Sparkles className="size-3.5 text-brand" aria-hidden />
            Recommended alternative
          </p>
          <div className="mt-2 flex flex-col gap-3 rounded-lg bg-surface p-3.5 shadow-card sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
                <Clock3 className="size-4" aria-hidden />
              </span>
              <div>
                <p className="text-sm font-semibold text-ink">
                  {formatDate(report.alternatives[0].date)}
                </p>
                <p className="text-[13px] tabular-nums text-body">
                  {formatTime(report.alternatives[0].start_time)} –{' '}
                  {formatTime(report.alternatives[0].end_time)}
                </p>
              </div>
            </div>
            <Button
              size="sm"
              onClick={() => onUseAlternative?.(report.alternatives![0])}
            >
              Use recommended schedule
            </Button>
          </div>
          {report.alternatives.length > 1 && (
            <p className="mt-2.5 text-xs text-muted">
              {report.alternatives.length - 1} more alternative schedule
              {report.alternatives.length > 2 ? 's' : ''} available.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Single-line status row for the facility and operating-hours checks.
 */
function StatusRow({
  ok,
  label,
  detail,
}: {
  ok: boolean
  label: string
  detail?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5">
      {ok ? (
        <CheckCircle2 className="size-4 shrink-0 text-status-available" aria-hidden />
      ) : (
        <XCircle className="size-4 shrink-0 text-status-rejected" aria-hidden />
      )}
      <span className={cn('text-[13px] font-medium', ok ? 'text-ink' : 'text-status-rejected')}>
        {label}
      </span>
      {detail && <span className="min-w-0 truncate text-xs text-muted">— {detail}</span>}
    </div>
  )
}

function ConflictDetail({ conflicts }: { conflicts: FacilityConflict[] }) {
  return (
    <>
      {conflicts
        .map(
          (conflict) =>
            `${conflict.event_name} (${formatTime(conflict.start_time)}–${formatTime(conflict.end_time)})`,
        )
        .join(', ')}
    </>
  )
}

/**
 * Equipment availability row.
 *
 * Quantities are always labeled: "N units available" (units free during the
 * selected schedule) and "Requesting M". Never rendered as a bare "N/M".
 * When the request exceeds what is available, the row switches to a
 * warning/error state instead of a green checkmark.
 */
function ResourceRow({ item }: { item: AvailabilityItem }) {
  const name = item.name || `Equipment #${item.equipment_id}`
  const ok = item.status === 'AVAILABLE'
  const partial = item.status === 'PARTIAL'
  const insufficient = item.requested > item.available

  return (
    <div className={cn('rounded-lg px-2.5 py-2', insufficient && 'bg-status-rejected-bg/60')}>
      <div className="flex items-center gap-2.5">
        {ok ? (
          <CheckCircle2 className="size-4 shrink-0 text-status-available" aria-hidden />
        ) : partial ? (
          <AlertTriangle className="size-4 shrink-0 text-status-partial" aria-hidden />
        ) : (
          <XCircle className="size-4 shrink-0 text-status-rejected" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              'text-[13px] font-medium',
              ok ? 'text-ink' : partial ? 'text-status-partial' : 'text-status-rejected',
            )}
          >
            {name}
          </p>
          <div className="mt-0.5 flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <p className="text-xs text-body">
              {item.available} {item.available === 1 ? 'unit' : 'units'} available
            </p>
            <p className="text-xs font-semibold tabular-nums text-ink">
              Requesting {item.requested}
            </p>
          </div>
        </div>
      </div>

      {insufficient && (
        <p
          className={cn(
            'ml-6 mt-1.5 text-[13px] leading-relaxed',
            partial ? 'text-status-partial' : 'text-status-rejected',
          )}
        >
          {item.available === 0
            ? `No units are available during your selected schedule. You need ${item.requested}.`
            : `Only ${item.available} ${
                item.available === 1 ? 'unit is' : 'units are'
              } available during your selected schedule. You need ${item.requested}.`}
        </p>
      )}
    </div>
  )
}