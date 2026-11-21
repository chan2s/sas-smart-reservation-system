import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Download,
  Eye,
  FileText,
  Mail,
  QrCode,
  RotateCw,
  Upload,
  UserX,
  XCircle,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  useReservation,
  useReservationAction,
  useRetryApprovalEmail,
  useRetryApprovalDocument,
  useResendApprovalEmail,
  useUpdateReservationPayment,
  useUploadApprovalLetterImage,
} from '@/hooks/queries'
import { api, ApiError, endpoints } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { StatusBadge, Badge } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Field, Input, Select, Textarea } from '@/components/ui/Form'
import { draftForReservationEdit, draftFromReservation, saveDraft } from '@/lib/reservationDraft'
import { EmptyState, Skeleton } from '@/components/ui/Misc'
import { cn, formatCurrency, formatDateTime, formatTime } from '@/lib/utils'
import type {
  ReservationDetail,
  ReservationEvent,
  ReservationFee,
  ReservationPaymentInfo,
} from '@/lib/types'

/**
 * A payment needs acknowledgement whenever the server supplies a warning or
 * reports an outstanding balance. Checking both keeps the dialog from being
 * skipped if either derived field is missing from an API response.
 */
function paymentNeedsAcknowledgement(payment: ReservationPaymentInfo | null | undefined) {
  return Boolean(payment?.approval_warning || payment?.is_outstanding)
}

export function ReservationDetailPage() {
  const { id } = useParams()
  const reservationId = Number(id)
  const navigate = useNavigate()
  const { user, isStaff, isViewOnly } = useAuth()
  const { toast } = useToast()
  const { data: reservation, isLoading, isError, error, refetch } = useReservation(reservationId)
  const action = useReservationAction(reservationId)
  const retryEmail = useRetryApprovalEmail(reservationId)
  const retryDocument = useRetryApprovalDocument(reservationId)
  const resendExternalEmail = useResendApprovalEmail(reservationId)
  const uploadApprovalImage = useUploadApprovalLetterImage(reservationId)
  const updatePayment = useUpdateReservationPayment(reservationId)

  const [modal, setModal] = useState<
    | null
    | 'reject'
    | 'changes'
    | 'cancel'
    | 'checkin-override'
    | 'no-show'
    | 'payment-warning'
    | 'reschedule-approve'
    | 'reschedule-reject'
    | 'reschedule-info'
  >(null)
  const [reason, setReason] = useState('')
  const [paymentEditing, setPaymentEditing] = useState(false)
  const [paymentType, setPaymentType] = useState<'DOWN_PAYMENT' | 'FULL_PAYMENT'>('DOWN_PAYMENT')
  const [amountPaidInput, setAmountPaidInput] = useState('')
  const [paymentError, setPaymentError] = useState('')
  const [warningPayment, setWarningPayment] = useState<ReservationPaymentInfo | null>(null)
  const [checkingPayment, setCheckingPayment] = useState(false)
  const [revisionSubject, setRevisionSubject] = useState('')
  const [revisionMessage, setRevisionMessage] = useState('')
  const [approvalImageFile, setApprovalImageFile] = useState<File | null>(null)
  const [approvalPreviewUrl, setApprovalPreviewUrl] = useState<string | null>(null)

  useEffect(() => () => {
    if (approvalPreviewUrl) URL.revokeObjectURL(approvalPreviewUrl)
  }, [approvalPreviewUrl])

  if (!Number.isInteger(reservationId) || reservationId <= 0) {
    return (
      <EmptyState
        title="Reservation not found"
        description="This reservation link is not valid. It may have been removed or deleted."
        action={<Button onClick={() => navigate('/reservations')}>Back to reservations</Button>}
      />
    )
  }

  if (isError) {
    // A 404 must win over cached data: React Query can still hold the last
    // successful response for this key after the record is deleted.
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          title="Reservation not found"
          description="This reservation no longer exists. It may have been deleted after the page was opened."
          action={<Button onClick={() => navigate('/reservations')}>Back to reservations</Button>}
        />
      )
    }
    return (
      <EmptyState
        title="Unable to load this reservation"
        description={
          error instanceof ApiError && error.message
            ? error.message
            : 'Check your connection and try again.'
        }
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }

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
  // The warning dialog prefers the fresh payment snapshot fetched at approval
  // time (or returned by the backend's 409) over the cached reservation.
  const warningDetails = warningPayment ?? reservation.payment ?? null
  const partiallyPaid = warningDetails?.status === 'PARTIALLY_PAID'
  const warningIsFullPayment = warningDetails?.payment_type === 'FULL_PAYMENT'

  async function runRescheduleAction(
    actionName: 'approve-reschedule' | 'reject-reschedule' | 'request-reschedule-info',
    body: Record<string, unknown>,
  ) {
    const requestId = reservation?.reschedule_request?.id
    if (!requestId) return
    try {
      await action.mutateAsync({
        action: actionName,
        body: { request_id: requestId, ...body },
      })
      toast(
        actionName === 'approve-reschedule'
          ? 'Reservation rescheduled.'
          : actionName === 'reject-reschedule'
            ? 'Reschedule request rejected.'
            : 'More information requested.',
      )
      setModal(null)
      setReason('')
    } catch (error) {
      toast(
        error instanceof ApiError ? error.message : 'The reschedule request could not be updated.',
        'error',
      )
    }
  }

  async function runAction(
    actionName: 'approve' | 'reject' | 'request_changes' | 'cancel',
    message: string,
    extraBody: Record<string, unknown> = {},
  ) {
    try {
      await action.mutateAsync({
        action: actionName,
        body: {
          ...(actionName === 'reject'
            ? { reason: message }
            : actionName === 'request_changes'
              ? { message }
              : actionName === 'cancel'
                ? { reason: message }
                : { comment: message }),
          ...extraBody,
        },
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
      // The backend refuses an unacknowledged outstanding-payment approval.
      // Open the same confirmation dialog so the admin can explicitly proceed.
      if (
        error instanceof ApiError &&
        error.status === 409 &&
        (error.data as { code?: string } | undefined)?.code === 'PAYMENT_WARNING'
      ) {
        // The backend re-checked the payment and refused an unacknowledged
        // approval. Prefer its current payment data over the cached page.
        const payment = (error.data as { payment?: ReservationPaymentInfo } | undefined)
          ?.payment
        if (payment) setWarningPayment(payment)
        setModal('payment-warning')
        toast(error.message, 'error')
        return
      }
      toast(
        error instanceof ApiError && error.message
          ? error.message
          : 'Action failed — please try again.',
        'error',
      )
    }
  }

  function startPaymentEdit() {
    const payment = reservation?.payment
    setPaymentType(payment?.payment_type === 'FULL_PAYMENT' ? 'FULL_PAYMENT' : 'DOWN_PAYMENT')
    setAmountPaidInput(payment?.amount_paid ?? '0.00')
    setPaymentError('')
    setPaymentEditing(true)
  }

  async function savePayment() {
    const current = reservation
    if (!current) return
    const total = Number.parseFloat(current.payment?.total_amount ?? current.estimated_total ?? '0')
    const paid = Number.parseFloat(amountPaidInput || '0')
    if (!Number.isFinite(paid) || paid < 0) {
      setPaymentError('The amount paid cannot be negative.')
      return
    }
    if (Number.isFinite(total) && paid > total) {
      setPaymentError('The amount paid cannot exceed the total reservation price.')
      return
    }
    setPaymentError('')
    try {
      await updatePayment.mutateAsync({
        payment_type: paymentType,
        amount_paid: paid.toFixed(2),
      })
      toast('Payment information saved.')
      setPaymentEditing(false)
    } catch (error) {
      setPaymentError(
        error instanceof ApiError && error.message
          ? error.message
          : 'Could not save the payment information.',
      )
    }
  }

  async function requestApproval() {
    setCheckingPayment(true)
    try {
      // Always decide from the server's latest payment position rather than a
      // cached page. If the refresh fails, the loaded reservation's own
      // payment warning is still enough to stop the approval and ask first.
      const latest = await refetch()
      const payment = latest.data?.payment
      if (
        paymentNeedsAcknowledgement(payment) ||
        (!payment && paymentNeedsAcknowledgement(reservation?.payment))
      ) {
        setWarningPayment(payment ?? reservation?.payment ?? null)
        setModal('payment-warning')
        return
      }
    } catch {
      if (paymentNeedsAcknowledgement(reservation?.payment)) {
        setWarningPayment(reservation?.payment ?? null)
        setModal('payment-warning')
        return
      }
    } finally {
      setCheckingPayment(false)
    }
    void runAction('approve', '')
  }

  function approveAnyway() {
    void runAction('approve', '', { acknowledge_payment_warning: true })
  }

  function defaultRevisionSubject() {
    return `Action Required: Reservation Revision – ${reservation?.reservation_id ?? ''}`
  }

  function openRevisionModal() {
    setRevisionSubject(defaultRevisionSubject())
    setModal('changes')
  }

  /**
   * Send an administrator's revision request by email.
   *
   * The request is recorded by the backend even if delivery fails; in that
   * case the modal stays open (with the message intact) so the administrator
   * can retry or coordinate another way. The button is disabled while the
   * mutation is pending, which prevents duplicate submissions.
   */
  async function sendRevisionRequest() {
    const current = reservation
    if (
      !current ||
      action.isPending ||
      !revisionMessage.trim() ||
      !revisionSubject.trim()
    ) return
    try {
      const result = await action.mutateAsync({
        action: 'request_changes',
        body: { message: revisionMessage.trim(), subject: revisionSubject.trim() },
      })
      if (result.revision_email_sent === false) {
        toast(
          result.revision_email_detail ||
            'Revision request recorded, but the email could not be sent.',
          'error',
        )
        return
      }
      toast(
        result.revision_email_detail ||
          `Revision request email sent to ${current.requester_email}.`,
      )
      setModal(null)
      setRevisionMessage('')
      setRevisionSubject('')
    } catch (error) {
      toast(
        error instanceof ApiError && error.message
          ? error.message
          : 'Could not send the revision request — please try again.',
        'error',
      )
    }
  }

  /**
   * Staff-only retry for a reservation whose approval email was never sent
   * (legacy approvals) or failed. The backend still owns the decision: it
   * refuses unless the reservation is APPROVED and not already SENT, and it
   * records the real delivery result.
   */
  function runRetryApprovalEmail() {
    retryEmail.mutate(undefined, {
      onSuccess: (result) => {
        if (result.approval_email_status === 'SENT') {
          toast(result.detail || 'Approval email sent to the requester.')
        } else {
          toast(result.detail || 'Approval email not sent.', 'error')
        }
      },
      onError: (error) => {
        toast(
          error instanceof ApiError && error.message
            ? error.message
            : 'Could not retry the approval email.',
          'error',
        )
      },
    })
  }

  async function downloadApprovalDocument() {
    const current = reservation
    if (!current) return
    try {
      await api.downloadFile(
        endpoints.approvalDocument(current.id),
        `GSO-RESERVE-APPROVAL-${current.reservation_id}.pdf`,
      )
    } catch (error) {
      toast(error instanceof ApiError ? error.message : 'Could not download the approval letter.', 'error')
    }
  }

  async function toggleApprovalPreview() {
    const current = reservation
    if (!current) return
    if (approvalPreviewUrl) {
      setApprovalPreviewUrl(null)
      return
    }
    try {
      setApprovalPreviewUrl(await api.fileUrl(endpoints.approvalDocument(current.id, true)))
    } catch (error) {
      toast(error instanceof ApiError ? error.message : 'Could not preview the approval letter.', 'error')
    }
  }

  function runRetryApprovalDocument() {
    retryDocument.mutate(undefined, {
      onSuccess: () => toast('Approval document generated.'),
      onError: (error) => toast(error instanceof ApiError ? error.message : 'Could not generate the approval document.', 'error'),
    })
  }

  function runResendExternalApprovalEmail() {
    resendExternalEmail.mutate(undefined, {
      onSuccess: (result) => toast(result.detail, result.approval_email_status === 'SENT' ? 'success' : 'error'),
      onError: (error) => toast(error instanceof ApiError ? error.message : 'Could not resend the approval email.', 'error'),
    })
  }

  // The requester-submitted event approval letter only applies to internal
  // reservations. External generated approval letters use a separate card.
  const showEventApprovalLetter = reservation.requester_type !== 'EXTERNAL'
  const rescheduleRequest = reservation.reschedule_request
  const rescheduleTone =
    rescheduleRequest?.status === 'APPROVED'
      ? 'emerald'
      : rescheduleRequest?.status === 'REJECTED'
        ? 'rose'
        : rescheduleRequest?.status === 'INFO_REQUIRED'
          ? 'orange'
          : 'amber'
  const canApprove =
    !isViewOnly && isStaff && reservation.status === 'PENDING' &&
    (reservation.requester_type === 'EXTERNAL' || reservation.approval_document_status !== 'AWAITING')
  const canReject = !isViewOnly && isStaff && reservation.status === 'PENDING'
  const canRequestChanges =
    !isViewOnly && isStaff && reservation.status === 'PENDING'
  // Cancellation visibility is decided by the BACKEND: can_cancel is evaluated
  // by the existing policy in services.workflow — the same source of truth the
  // cancel endpoint enforces. That policy already hides the button for every
  // finalized reservation (CANCELLED / NO_SHOW / COMPLETED / REJECTED / EXPIRED),
  // for events that have already ended, and for the 2-day requester window, so
  // the button is never recomputed or trusted from the client. View-only
  // accounts may read this page but cannot cancel or check in/out.
  const canCancel = reservation.can_cancel && !isViewOnly
  // When the user manages this reservation but the policy blocks cancellation
  // (e.g. the 2-day cancellation window), show the backend's reason instead of
  // an active button. Terminal statuses just show their status badge.
  const cancellationNotice =
    (isOwner || isStaff) &&
      !canCancel &&
      ['PENDING', 'APPROVED', 'ACTIVE'].includes(reservation.status)
      ? reservation.cancellation_reason ||
      'Cancellation is no longer available for this reservation.'
      : null
  // The backend decides no-show eligibility (approved, never checked in, event
  // date at least one day in the past) and returns can_mark_no_show; the button
  // never recomputes those rules. Once that window opens, check-in is closed —
  // the two actions are mutually exclusive by design (and the backend enforces
  // the same rule, so hiding a button is never the only protection).
  const canMarkNoShow = !isViewOnly && isStaff && reservation.can_mark_no_show
  const canCheckIn =
    !isViewOnly &&
    (isOwner || isStaff) &&
    ['APPROVED', 'ACTIVE'].includes(reservation.status) &&
    !canMarkNoShow
  const canCheckOut = !isViewOnly && isStaff && reservation.status === 'ACTIVE'

  /**
   * Rebook / request a new schedule: seed the reservation wizard from this
   * (expired) reservation — event, facility, resources, contact — and open it.
   * The schedule is deliberately left blank so a NEW, still-available slot is
   * chosen; the original reservation is never modified.
   */
  function startRebook() {
    if (!reservation) return
    saveDraft(draftFromReservation(reservation, { staff: isStaff }))
    navigate(`/reservations/new?rebookFrom=${reservation.id}`)
  }

  function startEdit() {
    if (!reservation || !isStaff || !reservation.can_edit || isViewOnly) return
    saveDraft(draftForReservationEdit(reservation))
    navigate(`/reservations/${reservation.id}/edit`)
  }

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
              <Badge tone="brand">
                {reservation.organization_type === 'INTERNAL' && !reservation.requester_id
                  ? 'Internal Organization'
                  : 'Campus User'}
              </Badge>
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
              onClick={requestApproval}
              loading={action.isPending || checkingPayment}
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
              icon={<Mail className="size-4" />}
              onClick={openRevisionModal}
            >
              Send Revision Request
            </Button>
          )}
          {isStaff && reservation.can_edit && !isViewOnly && (
            <Button variant="outline" onClick={startEdit}>
              Edit reservation
            </Button>
          )}
          {canMarkNoShow && (
            <Button
              variant="danger"
              icon={<UserX className="size-4" />}
              onClick={() => setModal('no-show')}
            >
              Mark as No-Show
            </Button>
          )}
          {canCancel && (
            <Button variant="ghost" onClick={() => setModal('cancel')}>
              Cancel reservation
            </Button>
          )}
        </div>
        {cancellationNotice && (
          <p className="mt-2 flex items-center gap-1.5 text-[13px] text-status-maintenance">
            <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
            {cancellationNotice}
          </p>
        )}
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

      {/* Expired notice — the event start time was reached before anyone
          approved the request. It can no longer be approved; the only way
          forward is a new reservation (a staff "Rebook" or a requester
          "Request New Schedule"). */}
      {reservation.status === 'EXPIRED' && (
        <div className="mt-5 flex flex-col gap-3 rounded-xl border border-status-expired/25 bg-status-expired-bg px-4 py-3.5 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-2.5">
            <Clock3 className="mt-0.5 size-4.5 shrink-0 text-status-expired" aria-hidden />
            <div>
              <p className="font-semibold text-status-expired">Reservation expired</p>
              <p className="mt-0.5 text-sm leading-relaxed text-status-expired/90">
                {reservation.status_reason ||
                  'This reservation was not approved before the scheduled event time.'}
              </p>
            </div>
          </div>
          {(isOwner || isStaff) && !isViewOnly && (
            <Button className="shrink-0" onClick={startRebook}>
              {isStaff ? 'Rebook Reservation' : 'Request New Schedule'}
            </Button>
          )}
        </div>
      )}

      {/* An expired reservation that has already been replaced links forward. */}
      {reservation.rescheduled_to && (
        <p className="mt-3 text-[13px] text-body">
          A new reservation was created from this one:{' '}
          <Link
            to={`/reservations/${reservation.rescheduled_to.id}`}
            className="font-medium text-brand hover:text-brand-dark"
          >
            {reservation.rescheduled_to.reservation_id}
          </Link>{' '}
          ({reservation.rescheduled_to.status_label})
        </p>
      )}

      {reservation.rejection_reason && (
        <div className="mt-5 rounded-xl border border-status-rejected/25 bg-status-rejected-bg p-4 text-sm text-status-rejected">
          <p className="font-semibold">Rejection reason</p>
          <p className="mt-1">{reservation.rejection_reason}</p>
        </div>
      )}

      {/* Outstanding payment stays visible after approval — payment status is
          independent of the reservation status. */}
      {reservation.requester_type === 'EXTERNAL' &&
        reservation.payment?.is_outstanding &&
        ['PENDING', 'APPROVED', 'ACTIVE'].includes(reservation.status) && (
          <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-status-maintenance/25 bg-status-maintenance-bg px-4 py-3.5 text-sm">
            <AlertTriangle
              className="mt-0.5 size-4.5 shrink-0 text-status-maintenance"
              aria-hidden
            />
            <div>
              <p className="font-semibold text-status-maintenance">
                {reservation.payment.status_label} —{' '}
                {formatCurrency(reservation.payment.remaining_balance)} outstanding
              </p>
              <p className="mt-0.5 leading-relaxed text-status-maintenance">
                This reservation is {reservation.status_label.toLowerCase()} while
                the external organization still has an unpaid balance.
              </p>
            </div>
          </div>
        )}

      {/* Body */}
      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* Event details */}
          <Card>
            <CardHeader title="Event details" />
            <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
              {/* Who the reservation is for — affiliation first, so an
                  external-organization booking is obvious at a glance. */}
              <DetailItem label="Affiliation" value={reservation.affiliation_label || '—'} />
              <DetailItem
                label="Organization"
                value={
                  reservation.organization
                    ? `${reservation.organization}${reservation.organization_code
                      ? ` (${reservation.organization_code})`
                      : ''
                    }`
                    : '—'
                }
              />
              <DetailItem
                label="Organization type"
                value={reservation.organization_type_label || '—'}
              />
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

          {/* Reschedule request — staff review and the actual reschedule. */}
          {isStaff && rescheduleRequest && (
            <Card>
              <CardHeader
                title="Reschedule request"
                description="The requester proposed a new schedule. The reservation is unchanged until you approve it."
                action={<Badge tone={rescheduleTone}>{rescheduleRequest.status_label}</Badge>}
              />
              <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
                <DetailItem
                  label="Current date and time"
                  value={`${format(new Date(`${rescheduleRequest.current_date}T12:00:00`), 'MMMM d, yyyy')} · ${formatTime(rescheduleRequest.current_start_time)} – ${formatTime(rescheduleRequest.current_end_time)}`}
                />
                <DetailItem
                  label="Requested date and time"
                  value={`${format(new Date(`${rescheduleRequest.requested_date}T12:00:00`), 'MMMM d, yyyy')} · ${formatTime(rescheduleRequest.requested_start_time)} – ${formatTime(rescheduleRequest.requested_end_time)}`}
                />
                <DetailItem label="Requester's reason" value={rescheduleRequest.reason} wide />
                <DetailItem
                  label="Submitted"
                  value={formatDateTime(rescheduleRequest.submitted_at)}
                />
                {rescheduleRequest.reviewed_by_name && (
                  <DetailItem
                    label="Reviewed by"
                    value={`${rescheduleRequest.reviewed_by_name}${
                      rescheduleRequest.reviewed_at
                        ? ` · ${formatDateTime(rescheduleRequest.reviewed_at)}`
                        : ''
                    }`}
                  />
                )}
                {rescheduleRequest.status === 'REJECTED' && rescheduleRequest.rejection_reason && (
                  <DetailItem label="Rejection reason" value={rescheduleRequest.rejection_reason} wide />
                )}
                {rescheduleRequest.status === 'INFO_REQUIRED' && rescheduleRequest.admin_message && (
                  <DetailItem label="Information requested" value={rescheduleRequest.admin_message} wide />
                )}
              </dl>
              {rescheduleRequest.status === 'PENDING' && !isViewOnly && (
                <div className="mt-5 flex flex-wrap gap-2.5 border-t border-line pt-4">
                  <Button
                    icon={<CalendarDays className="size-4" />}
                    onClick={() => setModal('reschedule-approve')}
                  >
                    Approve and Reschedule
                  </Button>
                  <Button
                    variant="danger"
                    icon={<XCircle className="size-4" />}
                    onClick={() => setModal('reschedule-reject')}
                  >
                    Reject Request
                  </Button>
                  <Button
                    variant="outline"
                    icon={<Mail className="size-4" />}
                    onClick={() => setModal('reschedule-info')}
                  >
                    Request More Information
                  </Button>
                </div>
              )}
              {rescheduleRequest.status === 'APPROVED' && (
                <p className="mt-4 rounded-lg border border-status-available/25 bg-status-available-bg p-3.5 text-sm text-status-available">
                  This request was approved and the reservation was moved to the requested schedule.
                </p>
              )}
            </Card>
          )}

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

          {/* Estimated cost — snapshotted external-organization fees. */}
          {reservation.requester_type === 'EXTERNAL' ? (
            <>
            <Card>
              <CardHeader
                title="Estimated cost"
                description="External organization fees — estimated until the reservation is approved"
              />
              {reservation.fees.length === 0 ? (
                <p className="mt-4 text-sm text-muted">
                  No fees were recorded for this reservation.
                </p>
              ) : (
                <div className="mt-4">
                  <ul className="divide-y divide-line">
                    {reservation.fees.map((fee) => (
                      <li
                        key={fee.id}
                        className="flex items-start justify-between gap-4 py-3"
                      >
                        <div className="min-w-0">
                          <p className="break-words text-sm font-medium text-ink">
                            {fee.description}
                          </p>
                          <p className="mt-0.5 break-words text-xs tabular-nums text-muted">
                            {feeSummary(fee)}
                          </p>
                        </div>
                        <p className="shrink-0 text-sm font-semibold tabular-nums text-ink">
                          {formatCurrency(fee.subtotal)}
                        </p>
                      </li>
                    ))}
                  </ul>
                  <div className="flex items-baseline justify-between gap-4 border-t border-line pt-3">
                    <span className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
                      Total
                    </span>
                    <span className="text-lg font-semibold tabular-nums text-ink">
                      {formatCurrency(reservation.estimated_total)}
                    </span>
                  </div>
                </div>
              )}
            </Card>

            {/* Administrative payment tracking — external reservations only. */}
            {isStaff && (
              <Card>
                <CardHeader
                  title="Payment"
                  description="Total price, required down payment, and amount received from this external organization"
                />
                {reservation.payment ? (
                  <>
                    <div className="mt-4">
                      {reservation.payment.is_configured ? (
                        <Badge tone={paymentStatusTone(reservation.payment.status)}>
                          {reservation.payment.status_label}
                        </Badge>
                      ) : (
                        <Badge tone="neutral">No payment required</Badge>
                      )}
                    </div>
                    <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
                      <DetailItem
                        label="Total reservation price"
                        value={formatCurrency(reservation.payment.total_amount)}
                      />
                      <DetailItem
                        label="Payment type"
                        value={reservation.payment.payment_type_label}
                      />
                      <DetailItem
                        label={
                          reservation.payment.payment_type === 'FULL_PAYMENT'
                            ? 'Required payment (100%)'
                            : 'Required downpayment (50%)'
                        }
                        value={formatCurrency(reservation.payment.required_amount)}
                      />
                      <DetailItem
                        label="Amount paid"
                        value={formatCurrency(reservation.payment.amount_paid)}
                      />
                      <DetailItem
                        label="Remaining balance"
                        value={
                          <span
                            className={cn(
                              'font-semibold tabular-nums',
                              reservation.payment.is_outstanding
                                ? 'text-status-maintenance'
                                : 'text-status-available',
                            )}
                          >
                            {formatCurrency(reservation.payment.remaining_balance)}
                          </span>
                        }
                      />
                    </dl>
                  </>
                ) : (
                  <p className="mt-4 text-sm text-muted">
                    No payment information is available for this reservation.
                  </p>
                )}

                {!isViewOnly && !paymentEditing && reservation.payment?.is_configured && (
                  <Button
                    className="mt-4"
                    variant="ghost"
                    size="sm"
                    onClick={startPaymentEdit}
                  >
                    Update payment information
                  </Button>
                )}

                {!isViewOnly && paymentEditing && reservation.payment && (
                  <div className="mt-4 space-y-4 rounded-xl border border-line bg-soft/60 p-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Payment type" htmlFor="payment-type">
                        <Select
                          id="payment-type"
                          value={paymentType}
                          onChange={(event) =>
                            setPaymentType(event.target.value as 'DOWN_PAYMENT' | 'FULL_PAYMENT')
                          }
                        >
                          <option value="DOWN_PAYMENT">Down Payment (50%)</option>
                          <option value="FULL_PAYMENT">Full Payment (100%)</option>
                        </Select>
                      </Field>
                      <Field label="Amount paid (₱)" htmlFor="payment-paid">
                        <Input
                          id="payment-paid"
                          type="number"
                          min="0"
                          max={reservation.payment.total_amount}
                          step="0.01"
                          inputMode="decimal"
                          value={amountPaidInput}
                          onChange={(event) => setAmountPaidInput(event.target.value)}
                        />
                      </Field>
                      <DetailItem
                        label="Total reservation price"
                        value={formatCurrency(reservation.payment.total_amount)}
                      />
                      <DetailItem
                        label={
                          paymentType === 'FULL_PAYMENT'
                            ? 'Required payment (100%)'
                            : 'Required downpayment (50%)'
                        }
                        value={formatCurrency(
                          previewRequiredAmount(reservation.payment.total_amount, paymentType),
                        )}
                      />
                      <DetailItem
                        label="Remaining balance"
                        value={formatCurrency(
                          previewRemaining(
                            previewRequiredAmount(reservation.payment.total_amount, paymentType),
                            amountPaidInput,
                          ),
                        )}
                      />
                    </div>
                    {paymentError && (
                      <p role="alert" className="text-xs text-status-rejected">
                        {paymentError}
                      </p>
                    )}
                    <p className="text-xs text-muted">
                      The backend calculates the required amount from the total reservation price.
                      A down payment does not waive the remaining balance.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setPaymentEditing(false)}
                        disabled={updatePayment.isPending}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => void savePayment()}
                        loading={updatePayment.isPending}
                      >
                        Save payment
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            )}
            </>
          ) : (
            <Card>
              <CardHeader
                title="Internal Reservation — No Payment Required"
                description="All official rental charges and applicable fees are waived for this internal reservation."
              />
              <p className="mt-4 text-xl font-semibold tabular-nums text-ink">PHP 0.00</p>
              <p className="mt-1 text-sm text-muted">No payment obligation or balance is due.</p>
            </Card>
          )}

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
          {showEventApprovalLetter && (
            <Card>
              <CardHeader
                title="Event Approval Letter"
                description="Requester authorization document required before approval"
              />
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Badge tone={reservation.approval_document_status === 'SUBMITTED' ? 'emerald' : 'amber'}>
                  {reservation.approval_document_status_label}
                </Badge>
              </div>
              {reservation.approval_document_status === 'NOT_REQUIRED' ? (
                <p className="mt-3 text-sm text-body">This existing reservation predates the event approval letter requirement.</p>
              ) : reservation.approval_document_status === 'SUBMITTED' ? (
                <p className="mt-3 text-sm text-body">An image has been uploaded and is available for review.</p>
              ) : (
                <p role="status" className="mt-3 rounded-lg border border-status-pending/25 bg-status-pending-bg p-3 text-sm text-status-pending">
                  Missing document. This reservation cannot be approved until the event approval letter is submitted.
                </p>
              )}
              {isStaff && reservation.approval_document_status === 'SUBMITTED' && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      const preview = window.open('about:blank', '_blank')
                      if (preview) preview.opener = null
                      try {
                        const url = await api.fileUrl(endpoints.reservationApprovalLetterFile(reservation.id))
                        if (preview) preview.location.href = url
                        else {
                          const anchor = document.createElement('a')
                          anchor.href = url
                          anchor.download = `approval-letter-${reservation.reservation_id}`
                          anchor.click()
                        }
                        window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
                      } catch (error) {
                        preview?.close()
                        toast(error instanceof ApiError ? error.message : 'The document could not be opened.', 'error')
                      }
                    }}
                  >
                    View image
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void api.downloadFile(
                      endpoints.reservationApprovalLetterFile(reservation.id),
                      `approval-letter-${reservation.reservation_id}`,
                    )}
                  >
                    Download image
                  </Button>
                </div>
              )}
              {reservation.status === 'PENDING' && reservation.approval_document_status === 'AWAITING' && (isStaff || isOwner) && (
                <div className="mt-4 space-y-3">
                  <Field label="Upload image" htmlFor="admin-approval-letter-upload" hint="JPG, JPEG, PNG, or WEBP; maximum 5 MB.">
                    <Input
                      id="admin-approval-letter-upload"
                      type="file"
                      accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                      onChange={(event) => {
                        const file = event.target.files?.[0] ?? null
                        const extension = file?.name.split('.').pop()?.toLowerCase()
                        if (file && !['jpg', 'jpeg', 'png', 'webp'].includes(extension ?? '')) {
                          setApprovalImageFile(null)
                          toast('Choose a JPG, JPEG, PNG, or WEBP image.', 'error')
                        } else if (file && file.size > 5 * 1024 * 1024) {
                          setApprovalImageFile(null)
                          toast('The image must be 5 MB or smaller.', 'error')
                        } else {
                          setApprovalImageFile(file)
                        }
                      }}
                    />
                  </Field>
                  <Button
                    disabled={!approvalImageFile}
                    loading={uploadApprovalImage.isPending}
                    icon={<Upload className="size-4" aria-hidden />}
                    onClick={() => approvalImageFile && uploadApprovalImage.mutate(approvalImageFile, {
                      onSuccess: () => {
                        setApprovalImageFile(null)
                        toast('Event approval letter uploaded.')
                      },
                      onError: (error) => toast(error instanceof ApiError ? error.message : 'Upload failed.', 'error'),
                    })}
                  >
                    Submit approval letter
                  </Button>
                </div>
              )}
            </Card>
          )}

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
                    ? `External Organization${reservation.organization_type_label
                      ? ` · ${reservation.organization_type_label}`
                      : ''
                    }`
                    : reservation.organization_type === 'INTERNAL' && !reservation.requester_id
                      ? 'Internal Organization'
                      : 'Campus User'}
                </p>
              </div>
            </div>
            {/* External contact details — shown to staff viewers. */}
            {reservation.requester_type === 'EXTERNAL' &&
              (reservation.contact_person ||
                reservation.representative_position ||
                reservation.contact_email ||
                reservation.organization_address) && (
                <dl className="mt-4 space-y-2.5 text-sm">
                  {reservation.organization_address && (
                    <DetailItem label="Organization address" value={reservation.organization_address} />
                  )}
                  {reservation.contact_person && (
                    <DetailItem label="Representative" value={reservation.contact_person} />
                  )}
                  {reservation.representative_position && (
                    <DetailItem label="Representative position" value={reservation.representative_position} />
                  )}
                  {reservation.contact_email && (
                    <DetailItem label="Email" value={reservation.contact_email} />
                  )}
                </dl>
              )}
            {/* Contact number of the person who filed the reservation.
                Reservations created before the field existed have none. */}
            {reservation.contact_phone && (
              <dl className="mt-4 space-y-2.5 text-sm">
                <DetailItem label="Contact phone" value={reservation.contact_phone} />
              </dl>
            )}
            <dl className="mt-4 space-y-2.5 text-sm">
              <DetailItem label="Submitted" value={formatDateTime(reservation.created_at)} />
              {reservation.created_by_name && (
                <DetailItem label="Created by" value={reservation.created_by_name} />
              )}
              {reservation.rebooked_from_reference && (
                <DetailItem
                  label="Rebooked from"
                  value={
                    <Link
                      to={`/reservations/${reservation.rebooked_from}`}
                      className="font-medium text-brand hover:text-brand-dark"
                    >
                      {reservation.rebooked_from_reference}
                    </Link>
                  }
                />
              )}
              {reservation.approved_by_name && reservation.approved_at && (
                <DetailItem
                  label="Approved by"
                  value={`${reservation.approved_by_name} · ${formatDateTime(reservation.approved_at)}`}
                />
              )}
              {reservation.requester_type === 'EXTERNAL' && reservation.status === 'APPROVED' && (
                <DetailItem
                  label="Approval letter"
                  wide
                  value={reservation.approval_pdf_available ? (
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        {isStaff && (
                          <span className={cn(
                            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
                            reservation.generated_approval_status === 'GENERATED'
                              ? 'border-status-approved/20 bg-status-approved-bg text-status-approved'
                              : reservation.generated_approval_status === 'FAILED'
                                ? 'border-status-rejected/20 bg-status-rejected-bg text-status-rejected'
                                : 'border-line bg-soft text-muted',
                          )}>
                            {reservation.generated_approval_status_label || reservation.generated_approval_status}
                          </span>
                        )}
                        {(isOwner || isStaff) && (
                          <Button variant="primary" size="sm" icon={<Download className="size-4" aria-hidden />} onClick={() => void downloadApprovalDocument()}>
                            Download Approval Letter
                          </Button>
                        )}
                        {isStaff && (
                          <>
                            <Button variant="outline" size="sm" icon={<Eye className="size-4" aria-hidden />} onClick={() => void toggleApprovalPreview()}>
                              {approvalPreviewUrl ? 'Hide preview' : 'Preview PDF'}
                            </Button>
                            {reservation.approval_docx_available && (
                              <Button variant="outline" size="sm" icon={<FileText className="size-4" aria-hidden />} onClick={() => void api.downloadFile(
                                endpoints.approvalDocumentDocx(reservation.id),
                                `GSO-RESERVE-APPROVAL-${reservation.reservation_id}.docx`,
                              ).catch(() => toast('Could not download the DOCX file.', 'error'))}>
                                Download DOCX
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                      {approvalPreviewUrl && isStaff && (
                        <iframe
                          title={`Approval letter preview for ${reservation.reservation_id}`}
                          src={approvalPreviewUrl}
                          className="h-[34rem] w-full rounded-lg border border-line bg-white"
                        />
                      )}
                    </div>
                  ) : isStaff ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-muted">{reservation.generated_approval_status_label || 'Not generated'}</span>
                      {reservation.generated_approval_error && <span className="text-status-rejected">{reservation.generated_approval_error}</span>}
                      <Button variant="outline" size="sm" icon={<RotateCw className="size-4" aria-hidden />} loading={retryDocument.isPending} onClick={runRetryApprovalDocument}>
                        Retry generation
                      </Button>
                    </div>
                  ) : 'Your approval letter is being prepared.'}
                />
              )}
              {isStaff && reservation.status === 'APPROVED' && (
                <DetailItem
                  label="Approval email"
                  wide
                  value={
                    <span className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
                          approvalEmailBadgeClass(reservation.approval_email_status),
                        )}
                      >
                        <span className="size-1.5 rounded-full bg-current" />
                        {reservation.approval_email_status_label ||
                          reservation.approval_email_status}
                      </span>
                      {reservation.requester_type === 'EXTERNAL' ? (
                        <>
                          {reservation.approval_email_sent_at && <span className="text-xs text-muted">Sent {formatDateTime(reservation.approval_email_sent_at)}</span>}
                          <span className="text-xs text-muted">Attempts: {reservation.approval_email_attempts}</span>
                          {reservation.approval_email_last_error && <span className="text-xs text-status-rejected">Last error: {reservation.approval_email_last_error}</span>}
                          {reservation.approval_pdf_available && (
                            <Button variant="outline" size="sm" icon={<Mail className="size-4" aria-hidden />} loading={resendExternalEmail.isPending} onClick={runResendExternalApprovalEmail}>
                              Resend Approval Email
                            </Button>
                          )}
                        </>
                      ) : ['NOT_SENT', 'FAILED'].includes(reservation.approval_email_status) && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={runRetryApprovalEmail}
                          loading={retryEmail.isPending}
                        >
                          Resend email
                        </Button>
                      )}
                    </span>
                  }
                />
              )}
              {reservation.checked_in_at && (
                <DetailItem label="Checked in" value={formatDateTime(reservation.checked_in_at)} />
              )}
              {reservation.checked_out_at && (
                <DetailItem label="Checked out" value={formatDateTime(reservation.checked_out_at)} />
              )}
              {reservation.no_show_marked_at && (
                <DetailItem
                  label="Marked no-show"
                  value={`${
                    reservation.no_show_marked_by_name || 'Administrator'
                  } · ${formatDateTime(reservation.no_show_marked_at)}`}
                />
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
        open={modal === 'reschedule-approve'}
        onClose={() => setModal(null)}
        title="Approve and reschedule"
        description="Availability and fees are re-checked before the reservation's date and time are changed."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>
              Cancel
            </Button>
            <Button
              icon={<CalendarDays className="size-4" />}
              onClick={() => void runRescheduleAction('approve-reschedule', {})}
              loading={action.isPending}
            >
              Approve and Reschedule
            </Button>
          </>
        }
      >
        {rescheduleRequest && (
          <div className="rounded-xl border border-line bg-soft/60 p-4 text-sm">
            <p className="text-body">
              Move <span className="font-medium text-ink">{reservation.event_name}</span> to:
            </p>
            <p className="mt-1 font-semibold text-ink">
              {format(new Date(`${rescheduleRequest.requested_date}T12:00:00`), 'MMMM d, yyyy')}{' '}
              · {formatTime(rescheduleRequest.requested_start_time)} –{' '}
              {formatTime(rescheduleRequest.requested_end_time)}
            </p>
            <p className="mt-3 text-xs leading-5 text-body">
              The reservation reference, approval documents, and payment records are preserved.
              Applicable fees are recalculated automatically. If the slot is unavailable, the
              request stays pending so you can reject it or coordinate another schedule.
            </p>
          </div>
        )}
      </Modal>

      <Modal
        open={modal === 'reschedule-reject'}
        onClose={() => setModal(null)}
        title="Reject reschedule request"
        description="The requester is emailed your reason. The original reservation stays unchanged."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={!reason.trim()}
              onClick={() => void runRescheduleAction('reject-reschedule', { reason })}
              loading={action.isPending}
            >
              Reject Request
            </Button>
          </>
        }
      >
        <Field label="Reason for rejection" htmlFor="reschedule-reject-reason">
          <Textarea
            id="reschedule-reject-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. The facility is already reserved for that time…"
            autoFocus
          />
        </Field>
      </Modal>

      <Modal
        open={modal === 'reschedule-info'}
        onClose={() => setModal(null)}
        title="Request more information"
        description="The requester is emailed your message. The request remains open for review."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>
              Cancel
            </Button>
            <Button
              icon={<Mail className="size-4" />}
              disabled={!reason.trim()}
              onClick={() => void runRescheduleAction('request-reschedule-info', { message: reason })}
              loading={action.isPending}
            >
              Send Request
            </Button>
          </>
        }
      >
        <Field label="Message to the requester" htmlFor="reschedule-info-message">
          <Textarea
            id="reschedule-info-message"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Explain what clarification or detail you need…"
            autoFocus
          />
        </Field>
      </Modal>

      <Modal
        open={modal === 'changes'}
        onClose={() => setModal(null)}
        title="Send Revision Request"
        description="Email the requester the modifications needed before this reservation can proceed."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>
              Cancel
            </Button>
            <Button
              icon={<Mail className="size-4" />}
              disabled={!revisionMessage.trim() || !revisionSubject.trim()}
              onClick={sendRevisionRequest}
              loading={action.isPending}
            >
              Send Email
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Requester's email address" htmlFor="revision-email">
            <Input
              id="revision-email"
              value={reservation.requester_email || reservation.contact_email}
              readOnly
              aria-readonly="true"
              className="cursor-default bg-soft text-body focus:border-line focus:ring-0"
            />
          </Field>
          <Field label="Email subject" htmlFor="revision-subject" required>
            <Input
              id="revision-subject"
              value={revisionSubject}
              onChange={(event) => setRevisionSubject(event.target.value)}
              maxLength={200}
              required
            />
          </Field>
          <Field
            label="Message to the requester"
            htmlFor="revision-message"
            hint="Explain the modifications or additional requirements."
            required
          >
            <Textarea
              id="revision-message"
              value={revisionMessage}
              onChange={(event) => setRevisionMessage(event.target.value)}
              placeholder="e.g. Please adjust the end time to 5:00 PM — the AV room is reserved after that."
              maxLength={5000}
              autoFocus
              required
            />
          </Field>
        </div>
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
        <div className="rounded-xl border border-line bg-soft/60 p-4">
          <dl className="space-y-2.5 text-sm">
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-body">Reservation</dt>
              <dd className="text-right font-medium text-ink">{reservation.event_name}</dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-body">Facility</dt>
              <dd className="text-right font-medium text-ink">{reservation.facility}</dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-body">Date</dt>
              <dd className="text-right font-medium text-ink">
                {format(new Date(reservation.date), 'MMMM d, yyyy')}
                <br />
                {formatTime(reservation.start_time)} – {formatTime(reservation.end_time)}
              </dd>
            </div>
          </dl>
        </div>
        {/* <p className="mt-4 text-sm leading-relaxed text-body">
          Are you sure you want to cancel this reservation?
        </p> */}
        {/* <Field label="Reason (optional)" htmlFor="cancel-reason">
          <Input
            id="cancel-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. Event postponed"
          />
        </Field> */}
      </Modal>

      {/* Approval with an outstanding payment requires explicit confirmation.
          Payment never blocks approval — it only has to be acknowledged. */}
      <Modal
        open={modal === 'payment-warning'}
        onClose={() => setModal(null)}
        title="Payment Required Before Approval"
        description={
          partiallyPaid
            ? warningIsFullPayment
              ? 'This external reservation has not completed the required full payment.'
              : 'This external reservation has not completed the required downpayment.'
            : warningIsFullPayment
              ? 'This external reservation has not received any payment yet. The full reservation price is required before approval.'
              : 'This external reservation has not received any payment yet. The required downpayment is 50% of the total reservation price.'
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)} disabled={action.isPending}>
              Wait for Downpayment
            </Button>
            <Button
              onClick={() => {
                setModal(null)
                approveAnyway()
              }}
              loading={action.isPending}
            >
              Approve Anyway
            </Button>
          </>
        }
      >
        <div className="rounded-xl border border-status-maintenance/25 bg-status-maintenance-bg p-4">
          <p className="flex items-start gap-2 text-sm font-semibold text-status-maintenance">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {partiallyPaid
              ? 'This external reservation has only been partially paid.'
              : 'This external reservation has not received any payment yet.'}
          </p>
          {warningDetails && (
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="shrink-0 text-body">Total Reservation Price</dt>
                <dd className="text-right font-medium tabular-nums text-ink">
                  {formatCurrency(warningDetails.total_amount ?? reservation.estimated_total)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="shrink-0 text-body">
                  {warningIsFullPayment ? 'Required Payment (100%)' : 'Required Downpayment (50%)'}
                </dt>
                <dd className="text-right font-medium tabular-nums text-ink">
                  {formatCurrency(
                    warningIsFullPayment
                      ? warningDetails.required_amount
                      : warningDetails.down_payment_amount ?? warningDetails.required_amount,
                  )}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="shrink-0 text-body">Amount Paid</dt>
                <dd className="text-right font-medium tabular-nums text-ink">
                  {formatCurrency(warningDetails.amount_paid)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="shrink-0 text-body">
                  {warningDetails.payment_type === 'FULL_PAYMENT'
                    ? 'Remaining Payment'
                    : 'Remaining Downpayment'}
                </dt>
                <dd className="text-right font-semibold tabular-nums text-status-maintenance">
                  {formatCurrency(warningDetails.remaining_balance)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="shrink-0 text-body">Payment Status</dt>
                <dd className="text-right font-semibold text-status-maintenance">
                  {warningDetails.status_label}
                </dd>
              </div>
            </dl>
          )}
        </div>
        <p className="mt-4 text-sm leading-relaxed text-body">
          The reservation can still be approved. Selecting <strong>Approve Anyway</strong>{' '}
          keeps the actual payment status and amount paid.
        </p>
      </Modal>

      {/* No-show: staff-only, explicit confirmation, backend revalidates. */}
      <ConfirmDialog
        open={modal === 'no-show'}
        onClose={() => setModal(null)}
        title="Mark Reservation as No-Show?"
        description="Are you sure you want to mark this reservation as a no-show? This action should only be performed if the requester did not attend the scheduled event."
        recordName={`${reservation.event_name} · ${reservation.reservation_id}`}
        confirmLabel="Confirm No-Show"
        cancelLabel="Cancel"
        onConfirm={async () => {
          await action.mutateAsync({ action: 'mark-no-show' })
          toast('Reservation marked as no-show.')
        }}
      />

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

function approvalEmailBadgeClass(status: string) {
  switch (status) {
    case 'SENT':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700'
    case 'FAILED':
      return 'border-red-200 bg-red-50 text-red-700'
    case 'NO_EMAIL':
      return 'border-stone-200 bg-stone-50 text-stone-500'
    default:
      return 'border-amber-200 bg-amber-50 text-amber-700'
  }
}

function DetailItem({
  label,
  value,
  wide,
}: {
  label: string
  value: ReactNode
  wide?: boolean
}) {
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

function paymentStatusTone(
  status: 'UNPAID' | 'PARTIALLY_PAID' | 'FULLY_PAID',
): 'rose' | 'orange' | 'emerald' {
  if (status === 'FULLY_PAID') return 'emerald'
  if (status === 'PARTIALLY_PAID') return 'orange'
  return 'rose'
}

/** Display-only preview; the backend remains authoritative for saved amounts. */
function previewRequiredAmount(
  total: string,
  paymentType: 'DOWN_PAYMENT' | 'FULL_PAYMENT',
): string {
  const totalValue = Number.parseFloat(total || '0')
  if (!Number.isFinite(totalValue)) return '0'
  return String(paymentType === 'FULL_PAYMENT' ? totalValue : totalValue * 0.5)
}

function previewRemaining(required: string, paid: string): string {
  const requiredValue = Number.parseFloat(required || '0')
  const paidValue = Number.parseFloat(paid || '0')
  if (!Number.isFinite(requiredValue) || !Number.isFinite(paidValue)) return '0'
  return String(Math.max(requiredValue - paidValue, 0))
}

function feeSummary(fee: ReservationFee): string {
  if (fee.unit === 'flat') return 'Flat fee'
  if (fee.unit === 'hour') {
    const hours = fee.quantity === '1' ? 'hour' : 'hours'
    return `${fee.quantity} ${hours} × ${formatCurrency(fee.unit_price)}`
  }
  return `${fee.quantity} × ${formatCurrency(fee.unit_price)}`
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
              event.event_type === 'NO_SHOW' && 'bg-status-no-show',
              event.event_type === 'REMINDER_SENT' && 'bg-status-approved',
              event.event_type === 'EXPIRED' && 'bg-status-expired',
              ['REBOOKED', 'NEW_SCHEDULE_REQUESTED', 'PAYMENT_RECORDED'].includes(event.event_type) && 'bg-brand',
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
              {event.recipient_email ? ` · To: ${event.recipient_email}` : ''}
            </p>
          </div>
        </li>
      ))}
    </ol>
  )
}
