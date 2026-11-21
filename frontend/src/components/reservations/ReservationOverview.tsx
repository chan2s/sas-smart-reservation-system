import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { cn, formatDateTime } from '@/lib/utils'
import type { BookerLookupDetails, ReservationStatus } from '@/lib/types'

/**
 * Organization Reservation Overview — displayed after successful returning-booker OTP verification.
 * Shows summary statistics, recent reservation history, and pending reservations.
 */
export function ReservationOverview({ details }: { details: BookerLookupDetails }) {
  const [showAllRecent, setShowAllRecent] = useState(false)
  const [expandedRecentId, setExpandedRecentId] = useState<number | null>(null)

  if (!details.reservation_summary) {
    return null
  }

  const summary = details.reservation_summary
  const recentReservations = details.recent_reservations ?? []
  const pendingReservations = details.pending_reservations ?? []
  const showMoreRecentButton = (details.recent_reservations?.length ?? 0) > 5

  return (
    <section aria-label="Organization Reservation Overview" className="mt-6 space-y-6">
      <div className="mx-auto w-full max-w-5xl">
        <h2 className="text-lg font-semibold text-ink">Organization Reservation Overview</h2>
        <p className="mt-1 text-sm text-body">
          Here's a summary of your organization's reservation activity with GSO RESERVE.
        </p>

        {/* Summary Cards */}
        <div className="mt-4 grid gap-3 sm:grid-cols-2 md:grid-cols-5">
          <SummaryCard label="Total Reservations" value={summary.total} />
          <SummaryCard label="Pending" value={summary.pending} highlight="pending" />
          <SummaryCard label="Approved" value={summary.approved} highlight="approved" />
          <SummaryCard label="Completed" value={summary.completed} highlight="completed" />
          <SummaryCard label="Rejected/Cancelled" value={summary.rejected} highlight="rejected" />
        </div>
      </div>

      {/* Recent Reservation History */}
      <div className="mx-auto w-full max-w-5xl">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-ink">Recent Reservation History</h3>
          {recentReservations.length === 0 && (
            <span className="text-sm text-muted">No reservations yet</span>
          )}
        </div>

        {recentReservations.length > 0 ? (
          <div className="mt-3 space-y-2">
            {recentReservations
              .slice(0, showAllRecent ? undefined : 5)
              .map((reservation) => (
                <ReservationHistoryRow
                  key={reservation.id}
                  reservation={reservation}
                  isExpanded={expandedRecentId === reservation.id}
                  onToggleExpand={() =>
                    setExpandedRecentId(
                      expandedRecentId === reservation.id ? null : reservation.id,
                    )
                  }
                />
              ))}

            {showMoreRecentButton && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2 w-full"
                onClick={() => setShowAllRecent(!showAllRecent)}
              >
                {showAllRecent ? (
                  <>
                    <ChevronUp className="mr-1 h-4 w-4" /> Show Less
                  </>
                ) : (
                  <>
                    <ChevronDown className="mr-1 h-4 w-4" /> View All
                  </>
                )}
              </Button>
            )}
          </div>
        ) : (
          <Card className="mt-3 !rounded-xl !border-slate-200 !shadow-none p-4 text-center text-sm text-muted">
            No reservation history found for this organization.
          </Card>
        )}
      </div>

      {/* Pending Reservations */}
      <div className="mx-auto w-full max-w-5xl">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-ink">Pending Reservations</h3>
          {pendingReservations.length === 0 && (
            <span className="text-sm text-muted">None</span>
          )}
        </div>

        {pendingReservations.length > 0 ? (
          <div className="mt-3 space-y-2">
            {pendingReservations.map((reservation) => (
              <PendingReservationRow key={reservation.id} reservation={reservation} />
            ))}
          </div>
        ) : (
          <Card className="mt-3 !rounded-xl !border-slate-200 !shadow-none p-4 text-center text-sm text-muted">
            No pending reservations for this organization.
          </Card>
        )}
      </div>
    </section>
  )
}

/**
 * Summary statistic card — shows count and color-coded highlight.
 */
function SummaryCard({
  label,
  value,
  highlight,
}: {
  label: string
  value: number
  highlight?: 'pending' | 'approved' | 'completed' | 'rejected'
}) {
  const bgClass = {
    pending: 'bg-yellow-50 border-yellow-200',
    approved: 'bg-green-50 border-green-200',
    completed: 'bg-blue-50 border-blue-200',
    rejected: 'bg-red-50 border-red-200',
    undefined: 'bg-slate-50 border-slate-200',
  }[highlight ?? 'undefined']

  const textClass = {
    pending: 'text-yellow-700',
    approved: 'text-green-700',
    completed: 'text-blue-700',
    rejected: 'text-red-700',
    undefined: 'text-slate-700',
  }[highlight ?? 'undefined']

  return (
    <Card className={cn('!rounded-lg !shadow-none border p-4', bgClass)}>
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className={cn('mt-1 text-2xl font-semibold', textClass)}>{value}</p>
    </Card>
  )
}

/**
 * Recent reservation row with optional expansion for full details.
 */
function ReservationHistoryRow({
  reservation,
  isExpanded,
  onToggleExpand,
}: {
  reservation: Extract<BookerLookupDetails['recent_reservations'], Array<any>>[0]
  isExpanded: boolean
  onToggleExpand: () => void
}) {
  return (
    <Card className="!rounded-lg !border-slate-200 !shadow-none overflow-hidden">
      <button
        type="button"
        className="w-full px-4 py-3 text-left hover:bg-slate-50 transition-colors flex items-center justify-between gap-3"
        onClick={onToggleExpand}
        aria-expanded={isExpanded}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink truncate">{reservation.event_name}</span>
            <StatusBadge status={reservation.status} />
          </div>
          <p className="mt-1 text-sm text-muted">{reservation.facility__name}</p>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-5 w-5 text-muted flex-shrink-0" />
        ) : (
          <ChevronDown className="h-5 w-5 text-muted flex-shrink-0" />
        )}
      </button>

      {isExpanded && (
        <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-muted">Reservation Code</p>
              <p className="mt-0.5 font-mono text-ink">{reservation.reservation_id}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-muted">Event Date</p>
              <p className="mt-0.5 text-ink">{reservation.date}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-muted">Submitted</p>
              <p className="mt-0.5 text-ink">{formatDateTime(reservation.created_at)}</p>
            </div>
            {reservation.purpose && (
              <div className="sm:col-span-2">
                <p className="text-xs font-medium text-muted">Purpose</p>
                <p className="mt-0.5 text-ink">{reservation.purpose}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}

/**
 * Pending reservation row — always displays key details.
 */
function PendingReservationRow({
  reservation,
}: {
  reservation: Extract<BookerLookupDetails['pending_reservations'], Array<any>>[0]
}) {
  return (
    <Card className="!rounded-lg !border-slate-200 !shadow-none p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink truncate">{reservation.event_name}</span>
            <StatusBadge status={reservation.status} />
          </div>
          <p className="mt-1 text-sm text-muted">{reservation.facility__name}</p>
          <div className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
            <div>
              <p className="font-medium text-muted">Reservation Code</p>
              <p className="mt-0.5 font-mono text-ink">{reservation.reservation_id}</p>
            </div>
            <div>
              <p className="font-medium text-muted">Requested Date</p>
              <p className="mt-0.5 text-ink">{reservation.date}</p>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}

/**
 * Status badge with color coding.
 */
function StatusBadge({ status }: { status: ReservationStatus }) {
  const colorMap: Record<ReservationStatus, { bg: string; text: string }> = {
    PENDING: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
    APPROVED: { bg: 'bg-green-100', text: 'text-green-800' },
    ACTIVE: { bg: 'bg-blue-100', text: 'text-blue-800' },
    COMPLETED: { bg: 'bg-green-100', text: 'text-green-800' },
    REJECTED: { bg: 'bg-red-100', text: 'text-red-800' },
    CANCELLED: { bg: 'bg-red-100', text: 'text-red-800' },
    NO_SHOW: { bg: 'bg-orange-100', text: 'text-orange-800' },
    EXPIRED: { bg: 'bg-gray-100', text: 'text-gray-800' },
  }

  const colors = colorMap[status] || { bg: 'bg-slate-100', text: 'text-slate-800' }

  const labelMap: Record<ReservationStatus, string> = {
    PENDING: 'Pending',
    APPROVED: 'Approved',
    ACTIVE: 'Active',
    COMPLETED: 'Completed',
    REJECTED: 'Rejected',
    CANCELLED: 'Cancelled',
    NO_SHOW: 'No-show',
    EXPIRED: 'Expired',
  }

  return (
    <Badge className={cn('whitespace-nowrap', colors.bg, colors.text)}>
      {labelMap[status] || status}
    </Badge>
  )
}
