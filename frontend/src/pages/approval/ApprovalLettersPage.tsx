import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { format, parseISO } from 'date-fns'
import {
  BadgeCheck,
  Building2,
  CalendarDays,
  Clock3,
  Download,
  Eye,
  FileSignature,
  FileText,
  MailWarning,
  RefreshCw,
  Send,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import {
  api,
  apiErrorMessage,
} from '@/lib/api'
import {
  useApprovalLetter,
  useApprovalLetters,
  useApprovalLetterPreview,
  useRetryLetterEmail,
  useSignApprovalLetter,
} from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/components/ui/Toast'
import { PageHeader, EmptyState, Skeleton } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Tabs } from '@/components/ui/Tabs'
import { cn, formatDateTime, formatTime } from '@/lib/utils'
import type { ApprovalLetter } from '@/lib/types'

/**
 * The designated signatory's Approval Letters dashboard.
 *
 * Pending letters await the test signature; signed letters expose their
 * finalized documents and email delivery state. The Sign Document button is
 * a UX gate only — the backend re-verifies the signatory designation and the
 * letter's pending state on every request.
 *
 * Layout: the whole workspace lives inside one centered, max-width container
 * so the heading, tabs, list and details share a single alignment axis. The
 * list and the selected letter sit side by side from `lg` (a fixed-feeling
 * list rail plus a fluid detail column) and stack vertically below it.
 */

type Box = 'pending' | 'signed'

const SIGNED_STATUSES = 'SIGNED,SENT,EMAIL_FAILED'

export function ApprovalLettersPage() {
  const { isApprovalSignatory } = useAuth()
  const { toast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const [box, setBox] = useState<Box>('pending')
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const pendingQuery = useApprovalLetters({ status: 'PENDING_SIGNATURE' })
  const signedQuery = useApprovalLetters({ status: SIGNED_STATUSES })

  const activeQuery = box === 'pending' ? pendingQuery : signedQuery
  const letters = activeQuery.data?.results ?? []
  const pendingCount = pendingQuery.data?.count ?? 0
  const signedCount = signedQuery.data?.count ?? 0

  // A notification deep-link (?letter=ID) opens that letter directly,
  // whatever box it now lives in.
  useEffect(() => {
    const letterParam = Number(searchParams.get('letter'))
    if (!letterParam) return
    setSelectedId(letterParam)
    setBox((current) => {
      const inSigned = signedQuery.data?.results.some((l) => l.id === letterParam)
      if (inSigned) return 'signed'
      return current
    })
    setSearchParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  // Keep a valid selection: auto-select the first letter of the active box.
  useEffect(() => {
    if (selectedId != null && letters.some((l) => l.id === selectedId)) return
    setSelectedId(letters[0]?.id ?? null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [box, activeQuery.data])

  if (!isApprovalSignatory) {
    return (
      <div className="mx-auto w-full max-w-[1200px]">
        <PageHeader
          eyebrow="Staff workspace"
          title="Approval Letters"
          description="Designated signatory workspace for reservation approval letters."
        />
        <Card className="mt-6">
          <EmptyState
            icon={<ShieldCheck className="size-5" />}
            title="Not authorized"
            description="Only the designated signatory — the Assistant Campus Director for Administration and Finance — can view and sign approval letters. The backend verifies this on every request."
          />
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-[1200px]">
      <PageHeader
        eyebrow="Staff workspace"
        title="Approval Letters"
        description="Review approved reservations and sign the formal approval letters. Signing applies the campus test signature, finalizes the documents, and emails the signed PDF to the requester."
      />

      <Tabs
        className="mt-6"
        stretch
        items={[
          { key: 'pending', label: 'Pending Signature', count: pendingCount },
          { key: 'signed', label: 'Signed', count: signedCount },
        ]}
        active={box}
        onChange={(key) => setBox(key as Box)}
      />

      <div className="mt-5 grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        {/* Letter list */}
        <Card padding="none" className="min-w-0 overflow-hidden">
          {activeQuery.isLoading ? (
            <LetterListSkeleton />
          ) : activeQuery.isError ? (
            <ListError onRetry={() => void activeQuery.refetch()} />
          ) : letters.length === 0 ? (
            <EmptyState
              icon={<FileText className="size-5" />}
              title={box === 'pending' ? 'No letters awaiting signature' : 'No signed letters yet'}
              description={
                box === 'pending'
                  ? 'Approval letters appear here automatically after a reservation is approved.'
                  : 'Letters you sign will be listed here with their documents and delivery status.'
              }
            />
          ) : (
            <ul
              aria-label={box === 'pending' ? 'Letters pending signature' : 'Signed letters'}
              className="max-h-[32rem] divide-y divide-line overflow-y-auto lg:max-h-[calc(100dvh-18rem)]"
            >
              {letters.map((letter) => (
                <LetterListItem
                  key={letter.id}
                  letter={letter}
                  selected={letter.id === selectedId}
                  onSelect={() => setSelectedId(letter.id)}
                />
              ))}
            </ul>
          )}
        </Card>

        {/* Detail + preview */}
        <div className="min-w-0">
          {selectedId == null ? (
            <Card>
              <EmptyState
                icon={<FileSignature className="size-5" />}
                title="Select a letter"
                description="Choose a letter from the list to read the full document."
              />
            </Card>
          ) : (
            <LetterDetail
              key={selectedId}
              letterId={selectedId}
              onSigned={() => {
                toast('Letter signed. The finalized documents were generated and the requester is being emailed.')
              }}
              onEmailRetried={(sent) => {
                if (sent) toast('Approval letter email sent to the requester.')
                else toast('The email could not be delivered yet. You can retry.', 'error')
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function LetterListSkeleton() {
  return (
    <div className="divide-y divide-line" aria-busy="true" aria-label="Loading letters">
      {[0, 1, 2].map((row) => (
        <div key={row} className="space-y-2.5 px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-5 w-20" />
          </div>
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ))}
    </div>
  )
}

function ListError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="text-sm text-body">
        The letter list could not be loaded. Nothing is shown until the server responds.
      </p>
      <Button
        variant="outline"
        size="sm"
        onClick={onRetry}
        icon={<RefreshCw className="size-3.5" aria-hidden />}
        className="shrink-0"
      >
        Retry
      </Button>
    </div>
  )
}

function letterStatusTone(status: string) {
  switch (status) {
    case 'PENDING_SIGNATURE':
      return 'amber' as const
    case 'SENT':
      return 'emerald' as const
    case 'SIGNED':
      return 'sky' as const
    default:
      return 'rose' as const
  }
}

function emailStatusTone(status: string) {
  switch (status) {
    case 'SENT':
      return 'emerald' as const
    case 'FAILED':
      return 'rose' as const
    default:
      return 'neutral' as const
  }
}

function LetterListItem({
  letter,
  selected,
  onSelect,
}: {
  letter: ApprovalLetter
  selected: boolean
  onSelect: () => void
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected || undefined}
        className={cn(
          'flex w-full min-w-0 flex-col gap-1.5 border-l-2 px-4 py-3.5 text-left transition-colors duration-150',
          'focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand',
          selected
            ? 'border-brand bg-brand-soft/50'
            : 'border-transparent hover:bg-soft',
        )}
      >
        <span className="flex min-w-0 items-start justify-between gap-2">
          <span className="min-w-0 text-sm font-semibold break-words text-ink">
            {letter.letter_id}
          </span>
          <Badge tone={letterStatusTone(letter.status)} className="shrink-0">
            {letter.status_label}
          </Badge>
        </span>
        <span className="min-w-0 text-sm break-words text-ink">{letter.event_name}</span>
        <span className="flex min-w-0 items-center gap-1.5 text-xs text-body">
          <Building2 className="size-3.5 shrink-0 text-muted" aria-hidden />
          <span className="min-w-0 break-words">{letter.facility_name}</span>
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted">
          <CalendarDays className="size-3.5 shrink-0" aria-hidden />
          <span className="tabular-nums">
            {format(parseISO(letter.reservation_date), 'MMM d, yyyy')}
          </span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">
            {formatTime(letter.start_time)}–{formatTime(letter.end_time)}
          </span>
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted">
          <UserRound className="size-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">{letter.requester_name}</span>
          <span aria-hidden>·</span>
          <span className="min-w-0 break-words tabular-nums">
            {letter.reservation_reference}
          </span>
        </span>
        <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted">
          <Clock3 className="size-3.5 shrink-0" aria-hidden />
          Issued {format(parseISO(letter.created_at), 'MMM d, yyyy')}
        </span>
      </button>
    </li>
  )
}

// ---------------------------------------------------------------------------

function LetterDetail({
  letterId,
  onSigned,
  onEmailRetried,
}: {
  letterId: number
  onSigned: () => void
  onEmailRetried: (sent: boolean) => void
}) {
  const { toast } = useToast()
  const { data: letter, isLoading, isError, refetch } = useApprovalLetter(letterId)
  const signMutation = useSignApprovalLetter(letterId)
  const retryMutation = useRetryLetterEmail(letterId)
  const [confirming, setConfirming] = useState(false)
  const [pdfBusy, setPdfBusy] = useState(false)
  const [docxBusy, setDocxBusy] = useState(false)

  if (isLoading) {
    return (
      <Card>
        <div className="space-y-3" aria-busy="true" aria-label="Loading letter">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-64" />
        </div>
      </Card>
    )
  }
  if (isError || !letter) {
    return (
      <Card>
        <EmptyState
          title="Letter unavailable"
          description="The letter could not be loaded. It may have been removed or you may not have access."
          action={
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              Retry
            </Button>
          }
        />
      </Card>
    )
  }

  async function handleDownload(kind: 'pdf' | 'docx') {
    if (!letter) return
    const busy = kind === 'pdf' ? setPdfBusy : setDocxBusy
    busy(true)
    try {
      const path = kind === 'pdf' ? letter.pdf_url : letter.docx_url
      const filename = `${letter.letter_id}.${kind}`
      await api.downloadFile(path, filename)
      toast(`${kind === 'pdf' ? 'PDF' : 'DOCX'} downloaded.`)
    } catch (error) {
      toast(apiErrorMessage(error, 'The document could not be downloaded.'), 'error')
    } finally {
      busy(false)
    }
  }

  async function handleSign() {
    await signMutation.mutateAsync()
    onSigned()
  }

  async function handleRetryEmail() {
    try {
      const result = await retryMutation.mutateAsync()
      onEmailRetried(result.email_status === 'SENT')
    } catch (error) {
      toast(apiErrorMessage(error, 'The retry could not be started.'), 'error')
    }
  }

  return (
    <div className="space-y-5">
      {/* Document header + actions */}
      <Card>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
              <p className="text-[11px] font-semibold tracking-[0.14em] break-words text-muted uppercase">
                {letter.letter_id}
              </p>
              <Badge tone={letterStatusTone(letter.status)}>{letter.status_label}</Badge>
            </div>
            <h2 className="mt-1.5 text-xl font-semibold tracking-tight break-words text-ink sm:text-2xl">
              {letter.event_name}
            </h2>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-body">
              <span className="inline-flex min-w-0 items-center gap-1.5">
                <Building2 className="size-3.5 shrink-0 text-muted" aria-hidden />
                <span className="min-w-0 break-words">{letter.facility_name}</span>
              </span>
              <span className="text-faint" aria-hidden>
                ·
              </span>
              <span className="min-w-0 break-words tabular-nums">
                {letter.reservation_reference}
              </span>
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap xl:shrink-0 xl:justify-end">
            {letter.can_sign && (
              <Button
                className="w-full sm:w-auto"
                icon={<FileSignature className="size-4" aria-hidden />}
                onClick={() => setConfirming(true)}
                loading={signMutation.isPending}
              >
                Sign Document
              </Button>
            )}
            {letter.has_signed_pdf && (
              <Button
                variant="outline"
                className="w-full sm:w-auto"
                icon={<Download className="size-4" aria-hidden />}
                onClick={() => void handleDownload('pdf')}
                loading={pdfBusy}
              >
                Download PDF
              </Button>
            )}
            {letter.has_signed_docx && (
              <Button
                variant="outline"
                className="w-full sm:w-auto"
                icon={<Download className="size-4" aria-hidden />}
                onClick={() => void handleDownload('docx')}
                loading={docxBusy}
              >
                Download DOCX
              </Button>
            )}
          </div>
        </div>

        {/* Signature + delivery record */}
        <dl className="mt-5 grid grid-cols-1 gap-x-8 gap-y-4 border-t border-line pt-4 text-sm sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="text-[11px] font-semibold tracking-[0.1em] text-muted uppercase">
              Signatory
            </dt>
            <dd className="mt-1 break-words text-ink">
              {letter.signatory_name}
              <span className="block text-xs text-muted">{letter.signatory_position}</span>
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[11px] font-semibold tracking-[0.1em] text-muted uppercase">
              Signature timestamp
            </dt>
            <dd className="mt-1 break-words text-ink">
              {letter.signed_at ? formatDateTime(letter.signed_at) : 'Awaiting signature'}
            </dd>
          </div>
          <div className="min-w-0 sm:col-span-2">
            <dt className="text-[11px] font-semibold tracking-[0.1em] text-muted uppercase">
              Email delivery
            </dt>
            <dd className="mt-1 flex min-w-0 flex-wrap items-center gap-2">
              <Badge tone={emailStatusTone(letter.email_status)}>
                {letter.email_status_label}
              </Badge>
              {letter.emailed_at && (
                <span className="text-xs break-words text-muted">
                  {formatDateTime(letter.emailed_at)}
                </span>
              )}
              {!letter.emailed_at && letter.email_attempted_at && (
                <span className="text-xs break-words text-muted">
                  Last attempt {formatDateTime(letter.email_attempted_at)}
                </span>
              )}
              {letter.can_retry_email && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleRetryEmail()}
                  loading={retryMutation.isPending}
                  icon={<Send className="size-3.5" aria-hidden />}
                >
                  Retry email
                </Button>
              )}
              {letter.email_status === 'FAILED' && letter.email_error && (
                <span className="flex min-w-0 items-start gap-1 text-xs break-words text-status-rejected">
                  <MailWarning className="mt-px size-3.5 shrink-0" aria-hidden />
                  <span className="min-w-0">{letter.email_error}</span>
                </span>
              )}
            </dd>
            <p className="mt-1 text-xs text-muted">
              This records acceptance by the configured email service; recipient receipt or opening is not tracked.
            </p>
          </div>
        </dl>
      </Card>

      {/* Reservation information */}
      <Card>
        <CardHeader
          title="Reservation information"
          description="The approved booking this letter certifies"
        />
        <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
          <DetailItem
            icon={<FileText className="size-3.5" />}
            label="Reference number"
            value={letter.reservation_reference}
          />
          <DetailItem
            icon={<UserRound className="size-3.5" />}
            label="Requester"
            value={
              <>
                {letter.requester_name}
                {letter.requester_email && (
                  <span className="block text-xs break-words text-muted">
                    {letter.requester_email}
                  </span>
                )}
              </>
            }
          />
          {letter.organization && (
            <DetailItem
              icon={<BadgeCheck className="size-3.5" />}
              label="Organization"
              value={letter.organization}
            />
          )}
          <DetailItem
            icon={<CalendarDays className="size-3.5" />}
            label="Facility"
            value={letter.facility_name}
          />
          <DetailItem
            icon={<Clock3 className="size-3.5" />}
            label="Date & time"
            value={`${format(parseISO(letter.reservation_date), 'EEEE, MMMM d, yyyy')} · ${formatTime(letter.start_time)} – ${formatTime(letter.end_time)}`}
          />
          <DetailItem label="Purpose" value={letter.purpose || '—'} wide />
        </dl>
      </Card>

      {/* Letter preview */}
      <Card>
        <CardHeader
          title="Letter preview"
          description={
            letter.has_signed_pdf
              ? 'The signed document as emailed to the requester'
              : 'The complete letter, exactly as it will be signed'
          }
        />
        <LetterPreview letterId={letter.id} />
      </Card>

      {/* Signing confirmation */}
      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Confirm Digital Signature"
        description="Are you sure you want to apply the test signature to this reservation approval letter? Please verify the document before proceeding."
        recordName={`${letter.letter_id} · ${letter.reservation_reference}`}
        tone="warning"
        confirmLabel="Confirm Signature"
        cancelLabel="Cancel"
        onConfirm={async () => {
          await handleSign()
        }}
      >
        <p className="rounded-lg bg-soft px-3 py-2 text-[13px] text-body">
          Signing applies the campus <strong>test signature</strong>, generates the
          finalized PDF and DOCX, and emails the signed PDF to{' '}
          <strong>{letter.requester_name}</strong>. This cannot be undone.
        </p>
      </ConfirmDialog>
    </div>
  )
}

function DetailItem({
  label,
  value,
  icon,
  wide,
}: {
  label: string
  value: React.ReactNode
  icon?: React.ReactNode
  wide?: boolean
}) {
  return (
    <div className={cn('min-w-0', wide && 'sm:col-span-2')}>
      <dt className="flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.1em] text-muted uppercase">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 text-sm break-words text-ink">{value}</dd>
    </div>
  )
}

// ---------------------------------------------------------------------------

/**
 * Readable rendering of the letter from the backend's structured preview
 * payload — the same content the PDF/DOCX renderers use. "Open PDF" streams
 * the actual document (with the applied signature) in a new tab.
 */
function LetterPreview({ letterId }: { letterId: number }) {
  const { toast } = useToast()
  const { data: preview, isLoading } = useApprovalLetterPreview(letterId)
  const [pdfBusy, setPdfBusy] = useState(false)

  async function openPdf() {
    setPdfBusy(true)
    try {
      const url = await api.fileUrl(`/api/approval-letters/${letterId}/preview/pdf/`)
      window.open(url, '_blank', 'noopener')
      // Give the new tab a moment to load the blob before revoking.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (error) {
      toast(apiErrorMessage(error, 'The PDF preview could not be opened.'), 'error')
    } finally {
      setPdfBusy(false)
    }
  }

  if (isLoading) {
    return (
      <div className="mt-4 space-y-3" aria-busy="true" aria-label="Loading preview">
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-40" />
      </div>
    )
  }
  if (!preview) {
    return <p className="mt-4 text-sm text-muted">The preview is unavailable right now.</p>
  }
  return (
    <>
      <div className="mt-4 flex justify-end">
        <Button
          variant="outline"
          size="sm"
          icon={<Eye className="size-3.5" aria-hidden />}
          onClick={() => void openPdf()}
          loading={pdfBusy}
        >
          Open PDF
        </Button>
      </div>
      <article className="mt-2 w-full min-w-0 rounded-xl border border-line bg-white p-4 shadow-sm sm:p-8">
        <div className="text-center">
          <h3 className="text-lg font-bold tracking-tight break-words text-ink sm:text-xl">
            {preview.institution}
          </h3>
          <p className="mt-1 text-sm break-words text-body">{preview.issuing_office}</p>
          <p className="text-xs break-words text-muted italic">{preview.system_name} — Facility &amp; Resource Reservation System</p>
        </div>
        <div className="mt-4 border-t-2 border-brand" aria-hidden />
        <div className="mt-5 text-center">
          <p className="text-sm font-bold tracking-[0.08em] text-brand uppercase">
            Reservation Approval Letter
          </p>
          <p className="mt-0.5 text-xs break-words text-muted">Correspondence ID {preview.letter_id}</p>
        </div>

        <p className="mt-6 text-sm break-words text-ink">Date of issuance: {preview.issued_date}</p>
        <div className="mt-4 text-sm break-words text-ink">
          <p>{preview.requester_name}</p>
          {preview.organization && <p>{preview.organization}</p>}
        </div>
        <p className="mt-4 text-sm break-words text-ink">Dear {preview.requester_name},</p>
        <p className="mt-3 text-sm leading-relaxed text-body">
          Greetings from the {preview.issuing_office}!
        </p>
        <p className="mt-3 text-sm leading-relaxed text-body">
          This is to formally inform you that your reservation request detailed below has
          been <strong className="text-ink">reviewed and APPROVED</strong> by the{' '}
          {preview.issuing_office}. The approved schedule is as follows:
        </p>

        <dl className="mt-4 overflow-hidden rounded-lg border border-line text-sm">
          <PreviewRow label="Reference number" value={preview.reservation_reference} zebra />
          <PreviewRow label="Event" value={preview.event_name} />
          {preview.organization && <PreviewRow label="Organization" value={preview.organization} zebra />}
          <PreviewRow label="Facility" value={preview.facility_name} />
          <PreviewRow
            label="Date"
            value={preview.reservation_date}
            zebra
          />
          <PreviewRow
            label="Time"
            value={`${preview.reservation_start} – ${preview.reservation_end}`}
          />
          <PreviewRow label="Purpose" value={preview.purpose} zebra />
          {preview.expected_participants > 0 && (
            <PreviewRow
              label="Expected participants"
              value={String(preview.expected_participants)}
            />
          )}
          {preview.resources.length > 0 && (
            <PreviewRow label="Requested resources" value={preview.resources.join('; ')} zebra />
          )}
          {preview.estimated_total && (
            <PreviewRow label="Estimated fees" value={preview.estimated_total} />
          )}
        </dl>

        {!preview.is_signed && (
          <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-[13px] font-semibold text-amber-700">
            PENDING SIGNATURE — this preview is an UNSIGNED copy. It becomes the
            finalized document only after the designated signatory signs it.
          </p>
        )}

        {preview.facility_rules.length > 0 && (
          <>
            <p className="mt-4 text-sm text-body">
              Please be reminded of the following conditions governing the use of the
              facility:
            </p>
            <ul className="mt-2 space-y-1 text-sm text-body">
              {preview.facility_rules.map((rule) => (
                <li key={rule} className="flex gap-2">
                  <span className="text-muted" aria-hidden>
                    •
                  </span>
                  <span className="min-w-0 break-words">{rule}</span>
                </li>
              ))}
            </ul>
          </>
        )}

        <p className="mt-4 text-sm leading-relaxed text-body">
          Kindly present your reservation reference number and a valid ID at the SAS
          Office during check-in, which opens three (3) hours before your event's start
          time. Should you need to make changes, contact the SAS Office as soon as
          possible.
        </p>
        <p className="mt-3 text-sm text-body">We wish you a successful and well-coordinated event.</p>

        <div className="mt-8 border-t border-line pt-5">
          <p className="text-sm text-ink">Very truly yours,</p>
          <div className="mt-5 min-h-[64px]">
            {preview.is_signed ? (
              <p
                className="text-3xl break-words text-ink"
                style={{ fontFamily: "'Dancing Script', 'Segoe Script', cursive" }}
              >
                {preview.signatory_name}
              </p>
            ) : (
              <div className="flex h-14 items-end">
                <span className="w-full max-w-56 border-b border-dashed border-line" aria-hidden />
              </div>
            )}
          </div>
          <p className="text-sm font-bold break-words text-ink">{preview.signatory_name}</p>
          <p className="text-[13px] break-words text-body">{preview.signatory_position}</p>
          <p className="mt-1 text-xs break-words text-muted italic">
            {preview.signed_at
              ? `Signed on ${formatDateTime(preview.signed_at)} (system time)`
              : 'Awaiting signature'}
          </p>
          <p className="mt-2 text-[11px] leading-relaxed text-muted italic">
            {preview.test_signature_disclaimer}
          </p>
        </div>
      </article>
    </>
  )
}

function PreviewRow({
  label,
  value,
  zebra,
}: {
  label: string
  value: string
  zebra?: boolean
}) {
  return (
    <div
      className={cn(
        // Label above value on phones so a long label/value pair can never
        // push the preview wider than the viewport.
        'grid grid-cols-1 gap-0.5 px-3.5 py-2.5 sm:grid-cols-[minmax(7rem,9rem)_minmax(0,1fr)] sm:gap-3 sm:py-2',
        zebra && 'bg-soft/60',
      )}
    >
      <dt className="text-[11px] font-semibold tracking-[0.08em] text-muted uppercase">
        {label}
      </dt>
      <dd className="min-w-0 text-sm break-words text-ink">{value}</dd>
    </div>
  )
}
