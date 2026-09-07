import { useEffect, useState } from 'react'
import { Wrench } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Field, Input, Textarea } from '@/components/ui/Form'
import type { Equipment } from '@/lib/types'

export function MaintenanceModal({
  equipment,
  onClose,
  onSubmit,
}: {
  equipment: Equipment
  onClose: () => void
  /** Resolves on success; rejects with the server error on failure. */
  onSubmit: (payload: { quantity: number; reason?: string }) => Promise<unknown>
}) {
  const [quantity, setQuantity] = useState('1')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setQuantity('1')
    setReason('')
    setError(null)
  }, [equipment.id])

  const available = equipment.availability.available

  async function handleSubmit() {
    setError(null)
    const value = Number(quantity)
    if (!Number.isInteger(value) || value < 1) {
      setError('Quantity must be a whole number of at least 1.')
      return
    }
    if (value > available) {
      setError(
        `Only ${available} ${available === 1 ? 'unit is' : 'units are'} currently available to take out of service.`,
      )
      return
    }
    setSubmitting(true)
    try {
      await onSubmit({ quantity: value, reason: reason.trim() || undefined })
      onClose()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to update maintenance status.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Mark under maintenance"
      description={`Take units of ${equipment.name} out of service. ${available} ${available === 1 ? 'unit is' : 'units are'} currently available.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={submitting} icon={<Wrench className="size-4" />}>
            Mark under maintenance
          </Button>
        </>
      }
    >
      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-status-rejected/25 bg-status-rejected-bg px-3.5 py-2.5 text-sm text-status-rejected"
        >
          {error}
        </p>
      )}
      <div className="space-y-4">
        <Field
          label={`Quantity to take out of service (max ${available})`}
          htmlFor="maintenance-quantity"
        >
          <Input
            id="maintenance-quantity"
            type="number"
            min={1}
            max={available}
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </Field>
        <Field label="Reason (optional)" htmlFor="maintenance-reason">
          <Textarea
            id="maintenance-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. Two units have faulty cables and need servicing."
          />
        </Field>
        <p className="text-xs leading-relaxed text-muted">
          These units stop being reservable immediately. If every unit is taken out of service, the
          item's status becomes <span className="font-medium text-ink">Under Maintenance</span>.
        </p>
      </div>
    </Modal>
  )
}