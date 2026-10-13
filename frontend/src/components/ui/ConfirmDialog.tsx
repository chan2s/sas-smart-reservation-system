import { useEffect, useState, type ReactNode } from 'react'
import { ShieldAlert, TriangleAlert } from 'lucide-react'
import { apiErrorMessage } from '@/lib/api'
import { Button } from './Button'
import { Modal } from './Modal'

/**
 * Shared confirmation dialog for destructive or consequential actions.
 *
 * Wraps the standard Modal with the pieces every confirmation needs: a
 * severity-tinted warning icon, the affected record's name, an explicit
 * Cancel that never triggers the action, and a confirmation button that
 * shows a loading state while the (asynchronous) handler runs. An error
 * keeps the dialog open and shows the message inline, so the user's context
 * survives a failed request; success closes the dialog (the caller toasts).
 *
 * The dialog is a UX gate only — authorization and business rules stay on
 * the backend.
 */
export function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  recordName,
  tone = 'danger',
  confirmLabel,
  cancelLabel = 'Cancel',
  onConfirm,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  description: string
  /** Name/identifier of the affected record, highlighted above the details. */
  recordName?: string
  /** danger = irreversible/serious (red); warning = consequential but reversible (amber). */
  tone?: 'danger' | 'warning'
  confirmLabel: string
  cancelLabel?: string
  /** The existing API call. Rejecting keeps the dialog open with the error. */
  onConfirm: () => Promise<void>
  children?: ReactNode
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  // Reopening after a failure or a dismissed attempt must not resurrect the
  // previous error text or a stuck pending state.
  useEffect(() => {
    if (!open) {
      setPending(false)
      setError('')
    }
  }, [open])

  async function handleConfirm() {
    if (pending) return
    setPending(true)
    setError('')
    try {
      await onConfirm()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, `${confirmLabel} failed. Please try again.`))
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => (pending ? undefined : onClose())}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            onClick={handleConfirm}
            loading={pending}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3.5">
        <span
          className={cnIcon(tone)}
          aria-hidden
        >
          {tone === 'danger' ? (
            <TriangleAlert className="size-5" />
          ) : (
            <ShieldAlert className="size-5" />
          )}
        </span>
        <div className="min-w-0 space-y-2.5 text-sm leading-relaxed text-body">
          <p>{description}</p>
          {recordName && (
            <p className="break-words font-semibold text-ink">{recordName}</p>
          )}
          {children}
        </div>
      </div>
      {error && (
        <p
          role="alert"
          className="mt-4 rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected"
        >
          {error}
        </p>
      )}
    </Modal>
  )
}

function cnIcon(tone: 'danger' | 'warning'): string {
  return [
    'flex size-10 shrink-0 items-center justify-center rounded-full',
    tone === 'danger'
      ? 'bg-status-rejected-bg text-status-rejected'
      : 'bg-status-pending-bg text-status-pending',
  ].join(' ')
}
