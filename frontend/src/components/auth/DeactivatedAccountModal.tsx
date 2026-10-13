import { ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'

/**
 * Exact copy required for the deactivated-account sign-in refusal. It is
 * also the backend's response detail (accounts.serializers.
 * DEACTIVATED_LOGIN_MESSAGE) — the two must stay in sync, but the modal
 * renders this constant rather than trusting an error string.
 */
export const DEACTIVATED_ACCOUNT_MESSAGE =
  'This account has been deactivated. Please contact the SAS Office to restore access.'

/**
 * Modal shown when a sign-in is refused because an administrator deactivated
 * the account — for both authentication methods (the login form's 403 and
 * the OAuth callback's ?google_error=account_deactivated redirect).
 *
 * The backend refuses the sign-in either way; this modal only explains it.
 * It is deliberately a modal, not the inline form error: the account-status
 * condition must stand out from ordinary invalid-credentials failures.
 */
export function DeactivatedAccountModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Account Deactivated"
      size="sm"
      footer={
        <Button onClick={onClose} className="w-full sm:w-auto">
          OK
        </Button>
      }
    >
      <div className="flex flex-col items-center gap-4 py-2 text-center">
        <span
          className="flex size-12 shrink-0 items-center justify-center rounded-full bg-status-pending-bg text-status-pending"
          aria-hidden
        >
          <ShieldAlert className="size-6" />
        </span>
        <p className="text-sm leading-relaxed text-body">
          {DEACTIVATED_ACCOUNT_MESSAGE}
        </p>
      </div>
    </Modal>
  )
}
