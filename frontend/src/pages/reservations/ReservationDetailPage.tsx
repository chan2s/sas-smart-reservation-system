import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  MessageSquareWarning,
  QrCode,
  XCircle,
} from 'lucide-react'
import { format } from 'date-fns'
import { useReservation, useReservationAction } from '@/hooks/queries'
import { ApiError } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { StatusBadge, Badge } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import { Field, Input, Textarea } from '@/components/ui/Form'
import { Skeleton } from '@/components/ui/Misc'
import { cn, formatDateTime, formatTime } from '@/lib/utils'
import type { ReservationDetail, ReservationEvent } from '@/lib/types'

export function ReservationDetailPage() {
  const { id } = useParams()
  const reservationId = Number(id)
  const navigate = useNavigate()
  const { user, isStaff } = useAuth()
  const { toast } = useToast()
  const { data: reservation, isLoading } = useReservation(reservationId)
  const action = useReservationAction(reservationId)

  const [modal, setModal] = useState<null | 'reject' | 'changes' | 'cancel' | 'checkin-override'>(null)
  const [reason, setReason] = useState('')

  if (isLoading || !reservation) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-1/3" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-72 lg:col-span-2" />
          <Skeleton className="h-72" />
        </div>
      </div>
    )
  }

  const isOwner = reservation.requester_id === user?.id
  const isAdmin = user?.role === 'ADMIN'
  // The backend is authoritative, but for the UI we compare the server-provided
  // open time against the device clock so the button state stays fresh.
  const checkInOpen = reservation.check_in_open_time
    ? new Date(reservation.check_in_open_time)
    : null
  const checkInWindowOpen = checkInOpen ? Date.now() >= checkInOpen.getTime() : true
  const checkInOpenLabel =
    checkInOpen && !Number.isNaN(checkInOpen.getTime())
      ? `${format(checkInOpen, 'h:mm a')} on ${format(checkInOpen, 'MMMM d, yyyy')}`
      : ''

  async function runAction(
    actionName: 'approve' | 'reject' | 'request_changes' | 'cancel',
    message: string,
  ) {
    try {
      await action.mutateAsync({
        action: actionName,
        body:
          actionName === 'reject'
            ? { reason: message }
            : actionName === 'request_changes'
              ? { message }
              : actionName === 'cancel'
                ? { reason: message }
                : { comment: message },
      })
      toast(
        actionName === 'approve'
          ? 'Reservation approved.'
          : actionName === 'reject'
            ? 'Reservation rejected.'
            : actionName === 'cancel'
              ? 'Reservation cancelled.'
              : 'Changes requested.',
      )
      setModal(null)
      setReason('')
    } catch (error) {
      toast('Action failed — please try again.', 'error')
    }
  }

  const canApprove = isStaff && reservation.status === 'PENDING'
  const canReject = isStaff && reservation.status === 'PENDING'
  const canRequestChanges = isStaff && reservation.status === 'PENDING'
  const canCancel =
    (isOwner || isStaff) &&
    !['COMPLETED', 'CANCELLED', 'REJECTED'].includes(reservation.status)
  const canCheckIn =
    (isOwner || isStaff) && ['APPROVED', 'ACTIVE'].includes(reservation.status)
  const canCheckOut = isStaff && reservation.status === 'ACTIVE'

  function runCheckIn(override: boolean) {
    action.mutate(
      { action: 'check_in', body: override ? { override: true } : {} },
      {
        onError: (error) => {
          toast(
            error instanceof ApiError && error.message
              ? error.message
              : 'Check-in failed — please try again.',
            'error',
          )
        },
      },
    )
  }

  return (
    <div>
      <Link
        to="/reservations"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> All reservations
      </Link>

      {/* Header */}
      <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
              {reservation.reservation_id}
            </p>
            <StatusBadge status={reservation.status} />
            {reservation.requester_type === 'EXTERNAL' ? (
              <Badge tone="orange">External</Badge>
            ) : (
              <Badge tone="brand">Campus User</Badge>
            )}
          </div>
          <h1 className="mt-1.5 text-3xl font-semibold tracking-tight text-ink sm:text-[32px]">
            {reservation.event_name}
          </h1>
          <p className="mt-1 text-[15px] text-body">
            {reservation.facility} ·{' '}
            {format(new Date(reservation.date), 'EEEE, MMMM d, yyyy')} ·{' '}
            {formatTime(reservation.start_time)} – {formatTime(reservation.end_time)}
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2.5">
          {canCheckIn && (
            <Button
              variant="secondary"
              icon={<QrCode className="size-4" />}
              onClick={() => navigate(`/reservations/${reservation.id}/check-in`)}
            >
              View QR check-in
            </Button>
          )}
          {canCheckIn && reservation.status === 'APPROVED' && (
            <Button
              icon={<ClipboardCheck className="size-4" />}
              onClick={() => {
                if (!checkInWindowOpen && isAdmin) setModal('checkin-override')
                else runCheckIn(false)
              }}
              disabled={!checkInWindowOpen && !isAdmin}
              loading={action.isPending}
              title={
                !checkInWindowOpen && !isAdmin
                  ? `Check-in opens at ${checkInOpenLabel}`
                  : undefined
              }
            >
              Check in
            </Button>
          )}
          {canCheckOut && (
            <Button
              icon={<ClipboardCheck className="size-4" />}
              onClick={() => navigate(`/reservations/${reservation.id}/check-out`)}
            >
              Check out & inspect
            </Button>
          )}
          {canApprove && (
            <Button
              icon={<CheckCircle2 className="size-4" />}
              onClick={() => runAction('approve', '')}
              loading={action.isPending}
            >
              Approve
            </Button>
          )}
          {canReject && (
            <Button
              variant="danger"
              icon={<XCircle className="size-4" />}
              onClick={() => setModal('reject')}
            >
              Reject
            </Button>
          )}
          {canRequestChanges && (
            <Button
              variant="outline"
              icon={<MessageSquareWarning className="size-4" />}
              onClick={() => setModal('changes')}
            >
              Request Changes
            </Button>
          )}
          {canCancel && (
            <Button variant="ghost" onClick={() => setModal('cancel')}>
              Cancel reservation
            </Button>
          )}
        </div>
      </div>

      {/* Check-in window notice for non-admin users before the window opens */}
      {canCheckIn && reservation.status === 'APPROVED' && !checkInWindowOpen && !isAdmin && (
        <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-status-pending/25 bg-status-pending-bg px-4 py-3.5 text-sm">
          <Clock3 className="mt-0.5 size-4.5 shrink-0 text-status-pending" aria-hidden />
          <div>
            <p className="font-semibold text-status-pending">Check-in is not available yet.</p>
            <p className="mt-0.5 leading-relaxed text-status-pending">
              Check-in opens 3 hours before your event — at{' '}
              <span className="font-semibold">{checkInOpenLabel}</span>.
            </p>
          </div>
        </div>
      )}

      {reservation.rejection_reason && (
        <div className="mt-5 rounded-xl border border-status-rejected/25 bg-status-rejected-bg p-4 text-sm text-status-rejected">
          <p className="font-semibold">Rejection reason</p>
          <p className="mt-1">{reservation.rejection_reason}</p>
        </div>
      )}

      {/* Body */}
      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* Event details */}
          <Card>
            <CardHeader title="Event details" />
            <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
              <DetailItem label="Organization" value={reservation.organization || '—'} />
              <DetailItem label="Event type" value={reservation.event_type_label} />
              <DetailItem label="Expected participants" value={`${reservation.expected_participants}`} />
              <DetailItem label="Facility" value={reservation.facility} />
              <DetailItem label="Purpose" value={reservation.purpose || '—'} />
              {reservation.early_check_in_override && (
                <DetailItem
                  label="Early check-in"
                  value="Administrator override was used for this check-in."
                />
              )}
              {reservation.description && (
                <DetailItem label="Description" value={reservation.description} wide />
              )}
              {reservation.notes && <DetailItem label="Notes" value={reservation.notes} wide />}
            </dl>
          </Card>

          {/* Requested resources */}
          <Card>
            <CardHeader title="Requested resources" />
            {reservation.items.length === 0 ? (
              <p className="mt-4 text-sm text-muted">No equipment requested.</p>
            ) : (
              <ul className="mt-4 divide-y divide-line">
                {reservation.items.map((item) => (
                  <li key={item.id} className="flex items-center gap-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink">{item.equipment_name}</p>
                      <p className="text-xs text-muted">{item.category}</p>
                    </div>
                    <span className="rounded-md bg-soft px-2.5 py-1 text-sm font-semibold tabular-nums text-ink">
                      {item.quantity}×
                    </span>
                    {item.returned && <Badge tone="emerald">Returned</Badge>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Availability */}
          {reservation.availability && (
            <Card>
              <CardHeader
                title="Availability check"
                description="Current resource availability around this reservation's window"
              />
              <div className="mt-4">
                <AvailabilitySummary availability={reservation.availability} />
              </div>
            </Card>
          )}
        </div>

        {/* Right column */}
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Requester"
              description="Who the reservation is for — separate from who created it"
            />
            <div className="mt-4 flex items-center gap-3">
              <AvatarInitials name={reservation.requester} />
              <div>
                <p className="text-sm font-semibold text-ink">{reservation.requester}</p>
                <p className="text-xs text-muted">
                  {reservation.requester_type === 'EXTERNAL'
                    ? `External Organization${
                        reservation.organization_type_label
                          ? ` · ${reservation.organization_type_label}`
                          : ''
                      }`
                    : 'Campus User'}
                </p>
              </div>
            </div>
            {/* External contact details — shown to staff viewers. */}
            {reservation.requester_type === 'EXTERNAL' &&
              (reservation.contact_person || reservation.contact_email) && (
                <dl className="mt-4 space-y-2.5 text-sm">
                  {reservation.contact_person && (
                    <DetailItem label="Contact person" value={reservation.contact_person} />
                  )}
                  {reservation.contact_email && (
                    <DetailItem label="Email" value={reservation.contact_email} />
                  )}
                </dl>
              )}
            <dl className="mt-4 space-y-2.5 text-sm">
              <DetailItem label="Submitted" value={formatDateTime(reservation.created_at)} />
              {reservation.created_by_name && (
                <DetailItem label="Created by" value={reservation.created_by_name} />
              )}
              {reservation.approved_by_name && reservation.approved_at && (
                <DetailItem
                  label="Approved by"
                  value={`${reservation.approved_by_name} · ${formatDateTime(reservation.approved_at)}`}
                />
              )}
              {reservation.checked_in_at && (
                <DetailItem label="Checked in" value={formatDateTime(reservation.checked_in_at)} />
              )}
              {reservation.checked_out_at && (
                <DetailItem label="Checked out" value={formatDateTime(reservation.checked_out_at)} />
              )}
            </dl>
          </Card>

          <Card>
            <CardHeader title="Activity timeline" />
            <Timeline events={reservation.events} />
          </Card>
        </div>
      </div>

      {/* Action modals */}
      <Modal
        open={modal === 'reject'}
        onClose={() => setModal(null)}
        title="Reject reservation"
        description="The requester will be notified with your reason."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>
              Keep pending
            </Button>
            <Button
              variant="danger"
              disabled={!reason.trim()}
              onClick={() => runAction('reject', reason)}
              loading={action.isPending}
            >
              Reject reservation
            </Button>
          </>
        }
      >
        <Field label="Reason for rejection" htmlFor="reject-reason">
          <Textarea
            id="reject-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Explain why this request cannot be approved…"
            autoFocus
          />
        </Field>
      </Modal>

      <Modal
        open={modal === 'changes'}
        onClose={() => setModal(null)}
        title="Request changes"
        description="Send this reservation back to the requester with instructions."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>
              Cancel
            </Button>
            <Button
              disabled={!reason.trim()}
              onClick={() => runAction('request_changes', reason)}
              loading={action.isPending}
            >
              Send request
            </Button>
          </>
        }
      >
        <Field label="What should change?" htmlFor="changes-message">
          <Textarea
            id="changes-message"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. Please adjust the end time to 5:00 PM — the AV room is reserved after that."
            autoFocus
          />
        </Field>
      </Modal>

      <Modal
        open={modal === 'cancel'}
        onClose={() => setModal(null)}
        title="Cancel reservation"
        description="This frees the facility and resources for others."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>
              Keep reservation
            </Button>
            <Button variant="danger" onClick={() => runAction('cancel', reason)} loading={action.isPending}>
              Cancel reservation
            </Button>
          </>
        }
      >
        <Field label="Reason (optional)" htmlFor="cancel-reason">
          <Input
            id="cancel-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. Event postponed"
          />
        </Field>
      </Modal>

      {/* Admin override: early check-in requires an explicit confirmation */}
      <Modal
        open={modal === 'checkin-override'}
        onClose={() => setModal(null)}
        title="Check-in window has not opened yet"
        description="This reservation is before the standard 3-hour check-in window."
        footer={
          <>
            <Button variant="outline" onClick={() => setModal(null)} disabled={action.isPending}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                setModal(null)
                runCheckIn(true)
              }}
              loading={action.isPending}
            >
              Check In Anyway
            </Button>
          </>
        }
      >
        <div className="rounded-xl border border-status-pending/25 bg-status-pending-bg p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-status-pending">
            <AlertTriangle className="size-4" aria-hidden />
            Standard check-in window
          </p>
          <dl className="mt-3 space-y-2.5 text-sm">
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-body">Scheduled</dt>
              <dd className="text-right font-medium text-ink">
                {format(new Date(reservation.date), 'MMMM d, yyyy')}
                <br />
                {formatTime(reservation.start_time)} – {formatTime(reservation.end_time)}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-body">Regular check-in opens</dt>
              <dd className="text-right font-medium text-ink">{checkInOpenLabel}</dd>
            </div>
          </dl>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-body">
          You are attempting to check in before the standard 3-hour check-in window. As an
          administrator, you may override this restriction and check the reservation in now.
        </p>
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------------------

function DetailItem({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={cn(wide && 'sm:col-span-2')}>
      <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{value}</dd>
    </div>
  )
}

function AvatarInitials({ name }: { name: string }) {
  return (
    <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-brand-soft text-sm font-semibold text-brand">
      {name
        .split(' ')
        .map((part) => part[0])
        .slice(0, 2)
        .join('')
        .toUpperCase()}
    </span>
  )
}

function AvailabilitySummary({ availability }: { availability: ReservationDetail['availability'] }) {
  const ok = availability.ok
  const conflictItems = availability.items.filter((item) => item.status !== 'AVAILABLE')
  return (
    <div
      className={cn(
        'rounded-xl border p-4',
        ok
          ? 'border-status-available/25 bg-status-available-bg'
          : 'border-status-pending/25 bg-status-pending-bg',
      )}
    >
      <p className={cn('text-sm font-semibold', ok ? 'text-status-available' : 'text-status-pending')}>
        {ok
          ? 'This schedule is currently free'
          : 'Some resources are partially booked right now'}
      </p>
      {conflictItems.length > 0 && (
        <ul className="mt-2 space-y-1 text-[13px]">
          {conflictItems.map((item) => (
            <li key={item.equipment_id} className="flex flex-wrap items-baseline gap-x-1.5">
              <span className="font-medium text-ink">{item.name}</span>
              <span className="text-body">
                — {item.available} {item.available === 1 ? 'unit' : 'units'} available · Requesting {item.requested}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Timeline({ events }: { events: ReservationEvent[] }) {
  return (
    <ol className="mt-4">
      {events.map((event, index) => (
        <li key={event.id} className="relative flex gap-3.5 pb-5 last:pb-0">
          {index < events.length - 1 && (
            <span className="absolute left-[5px] top-4 h-full w-px bg-line" aria-hidden />
          )}
          <span
            className={cn(
              'relative mt-1.5 size-2.5 shrink-0 rounded-full',
              event.event_type === 'APPROVED' && 'bg-status-available',
              event.event_type === 'REJECTED' && 'bg-status-rejected',
              event.event_type === 'CHECKED_IN' && 'bg-status-active',
              event.event_type === 'CHECKED_OUT' && 'bg-status-completed',
              event.event_type === 'CANCELLED' && 'bg-status-cancelled',
              ['CREATED', 'CHANGES_REQUESTED'].includes(event.event_type) && 'bg-status-pending',
              ['COMMENT'].includes(event.event_type) && 'bg-muted',
            )}
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">{event.event_type_label}</p>
            {event.message && <p className="mt-0.5 text-[13px] text-body">{event.message}</p>}
            <p className="mt-1 text-xs text-muted">
              {event.actor_name ? `${event.actor_name} · ` : ''}
              {formatDateTime(event.created_at)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  )
}