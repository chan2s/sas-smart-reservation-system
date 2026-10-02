import { Archive, CalendarX, TriangleAlert } from 'lucide-react'
import { useDeleteFacility } from '@/hooks/queries'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import type { Facility } from '@/lib/types'

/**
 * Confirms removing a facility.
 *
 * The backend is the source of truth: a facility with any reservation history
 * is archived (disabled) instead of hard-deleted, so existing reservations and
 * their foreign keys are never broken. Only a facility that has never been
 * reserved can be permanently deleted.
 */
export function RemoveFacilityModal({
  facility,
  onClose,
}: {
  facility: Facility
  onClose: () => void
}) {
  const { toast } = useToast()
  const remove = useDeleteFacility(facility.id)

  const willArchive = facility.has_history
  const reservationCount = facility.reservation_count ?? 0

  function confirm() {
    remove.mutate(undefined, {
      onSuccess: (result) => {
        toast(
          result.archived
            ? `${facility.name} archived. Existing reservations remain intact.`
            : `${facility.name} deleted.`,
        )
        onClose()
      },
      onError: () =>
        toast('Unable to remove this facility. Please try again.', 'error'),
    })
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={willArchive ? 'Archive facility?' : 'Delete facility?'}
      description={facility.name}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={remove.isPending}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirm} loading={remove.isPending}>
            {willArchive ? 'Archive Facility' : 'Delete Facility'}
          </Button>
        </>
      }
    >
      {willArchive ? (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-body">
            This facility has{' '}
            <span className="font-semibold text-ink">
              {reservationCount} reservation{reservationCount === 1 ? '' : 's'}
            </span>{' '}
            in its history. It will be{' '}
            <span className="font-semibold text-ink">archived</span> instead of
            permanently deleted, which preserves every historical reservation and
            its records.
          </p>
          <p className="flex items-start gap-2 rounded-lg bg-soft px-3.5 py-2.5 text-[13px] text-body">
            <Archive className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
            Archived facilities disappear from new reservations but remain visible to
            administrators and can be re-enabled at any time.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-body">
            This facility has never been reserved, so it can be{' '}
            <span className="font-semibold text-ink">permanently deleted</span>.
          </p>
          <p className="flex items-start gap-2 rounded-lg bg-status-rejected-bg px-3.5 py-2.5 text-[13px] text-status-rejected">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            This action cannot be undone.
          </p>
        </div>
      )}

      <p className="mt-3 flex items-start gap-2 text-[13px] text-muted">
        <CalendarX className="mt-0.5 size-4 shrink-0" aria-hidden />
        {willArchive
          ? 'Historical reservations stay linked to this facility.'
          : 'Any equipment assigned to this facility is unassigned, not deleted.'}
      </p>
    </Modal>
  )
}
