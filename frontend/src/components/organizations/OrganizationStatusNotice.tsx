import { AlertTriangle, CheckCircle2, Clock, ShieldOff } from 'lucide-react'
import type { Organization, VerificationStatus } from '@/lib/types'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'

type Tone = 'brand' | 'emerald' | 'amber' | 'rose' | 'gray'

export const VERIFICATION_TONE: Record<VerificationStatus, Tone> = {
  PENDING: 'amber',
  APPROVED: 'emerald',
  REJECTED: 'rose',
  SUSPENDED: 'gray',
}

export const VERIFICATION_LABEL: Record<VerificationStatus, string> = {
  PENDING: 'Pending verification',
  APPROVED: 'Verified',
  REJECTED: 'Rejected',
  SUSPENDED: 'Suspended',
}

/** Human-friendly status line, e.g. "Status: Pending Administrator Approval". */
export const VERIFICATION_STATUS_LABEL: Record<VerificationStatus, string> = {
  PENDING: 'Pending Administrator Approval',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  SUSPENDED: 'Suspended',
}

export const VERIFICATION_MESSAGE: Record<VerificationStatus, string> = {
  PENDING:
    'Please wait for the administrator to approve your organization before you can reserve a facility.',
  APPROVED:
    'Your organization has been approved. You may now submit facility reservations.',
  REJECTED:
    'Your organization registration was rejected. You cannot reserve a facility. Please contact the SAS Office for assistance.',
  SUSPENDED:
    'Your organization is currently suspended. Reservations are disabled until the SAS Office reactivates it.',
}

const DEFAULT_TITLE: Record<VerificationStatus, string> = {
  PENDING: 'Organization Approval Required',
  APPROVED: 'Organization Verified',
  REJECTED: 'Organization Registration Rejected',
  SUSPENDED: 'Organization Suspended',
}

/** Rendered for an external affiliation when the org is not yet approved. */
const BLOCK_STYLE: Record<VerificationStatus, string> = {
  PENDING: 'border-status-pending/30 bg-status-pending-bg text-status-pending',
  APPROVED: 'border-status-available/30 bg-status-available-bg text-status-available',
  REJECTED: 'border-status-rejected/30 bg-status-rejected-bg text-status-rejected',
  SUSPENDED: 'border-line bg-softer text-body',
}

function Icon({ status }: { status: VerificationStatus }) {
  if (status === 'APPROVED') return <CheckCircle2 className="size-4" aria-hidden />
  if (status === 'PENDING') return <Clock className="size-4" aria-hidden />
  if (status === 'SUSPENDED') return <ShieldOff className="size-4" aria-hidden />
  return <AlertTriangle className="size-4" aria-hidden />
}

/**
 * The single source of truth for organization status messaging.
 *
 * Used on the affiliation page, the profile, and the reservation wizard so a
 * Pending/Rejected/Suspended organization always sees the same explanation
 * (and never a bare "you cannot do this").
 */
export function OrganizationStatusNotice({
  status,
  organization,
  className,
  title,
}: {
  status: VerificationStatus
  organization?: Organization | null
  className?: string
  title?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-wrap items-start gap-2.5 rounded-xl border px-3.5 py-3 text-[13px]',
        BLOCK_STYLE[status],
        className,
      )}
    >
      <span className="mt-0.5 shrink-0">
        <Icon status={status} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{title ?? DEFAULT_TITLE[status]}</p>
        {organization && (
          <p className="mt-0.5 text-xs font-medium opacity-90">
            {organization.organization_name} · {organization.organization_code}
          </p>
        )}
        <p className="mt-1 text-xs opacity-90">
          Status: <span className="font-medium">{VERIFICATION_STATUS_LABEL[status]}</span>
        </p>
        <p className="mt-1 text-xs opacity-90">{VERIFICATION_MESSAGE[status]}</p>
        {status === 'REJECTED' && (
          <p className="mt-1 text-xs opacity-90">
            Update your details and resubmit, or contact the SAS Office for assistance.
          </p>
        )}
      </div>
      <Badge tone={VERIFICATION_TONE[status]}>{VERIFICATION_LABEL[status]}</Badge>
    </div>
  )
}
