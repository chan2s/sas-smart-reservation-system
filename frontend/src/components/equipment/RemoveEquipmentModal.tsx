import { Archive, TriangleAlert } from 'lucide-react'
import { useDeleteEquipment, useEquipmentHistory } from '@/hooks/queries'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import type { Equipment } from '@/lib/types'

export function RemoveEquipmentModal({
  equipment,
  onClose,
}: {
  equipment: Equipment
  onClose: () => void
}) {
  const { toast } = useToast()
  const { data: history } = useEquipmentHistory(equipment.id)
  const remove = useDeleteEquipment(equipment.id)

  // The backend is the source of truth: equipment with reservation OR
  // maintenance history is archived, everything else can be hard-deleted.
  const willArchive = equipment.has_history
  const reservationCount = history?.length ?? 0

  function confirm() {
    remove.mutate(undefined, {
      onSuccess: (result) => {
        toast(
          result.archived
            ? `${equipment.name} archived. Existing records remain intact.`
            : `${equipment.name} deleted.`,
        )
        onClose()
      },
      onError: () => toast('Unable to remove this equipment.', 'error'),
    })
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={willArchive ? 'Archive equipment?' : 'Delete equipment?'}
      description={equipment.name}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={remove.isPending}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirm} loading={remove.isPending}>
            {willArchive ? 'Archive Equipment' : 'Delete Equipment'}
          </Button>
        </>
      }
    >
      {willArchive ? (
        <div className="space-y-3">
          {reservationCount > 0 ? (
            <p className="text-sm leading-relaxed text-body">
              This equipment has{' '}
              <span className="font-semibold text-ink">
                {reservationCount} reservation{reservationCount > 1 ? 's' : ''}
              </span>{' '}
              in its history. It will be{' '}
              <span className="font-semibold text-ink">archived</span> instead of permanently
              deleted, which preserves all historical reservation records.
            </p>
          ) : (
            <p className="text-sm leading-relaxed text-body">
              This equipment has{' '}
              <span className="font-semibold text-ink">maintenance history</span>. It will be{' '}
              <span className="font-semibold text-ink">archived</span> instead of permanently
              deleted, which preserves those maintenance records.
            </p>
          )}
          <p className="flex items-start gap-2 rounded-lg bg-soft px-3.5 py-2.5 text-[13px] text-body">
            <Archive className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
            Archived equipment disappears from new reservation flows but remains visible to
            administrators and can be restored later.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-body">
            This equipment has never been used in a reservation or maintenance record, so it can be{' '}
            <span className="font-semibold text-ink">permanently deleted</span>.
          </p>
          <p className="flex items-start gap-2 rounded-lg bg-status-rejected-bg px-3.5 py-2.5 text-[13px] text-status-rejected">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            This action cannot be undone.
          </p>
        </div>
      )}
    </Modal>
  )
}