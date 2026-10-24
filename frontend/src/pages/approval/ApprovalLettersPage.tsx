import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { format, parseISO } from 'date-fns'
import {
  BadgeCheck,
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
      <div>
        <PageHeader
          eyebrow="Approval Letters"
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
    <div>
      <PageHeader
        eyebrow="Approval Letters"
        title="Approval Letters"
        description="Review approved reservations and sign the formal approval letters. Signing applies the campus test signature, finalizes the documents, and emails the signed PDF to the requester."
      />

      <div className="mt-6">
        <Tabs
          items={[
            { key: 'pending', label: 'Pending Signature', count: pendingCount },
            { key: 'signed', label: 'Signed', count: signedCount },
          ]}
          active={box}
          onChange={(key) => setBox(key as Box)}
        />
      </div>

      <div className="mt-5 grid items-start gap-5 lg:grid-cols-5 [&>*]:min-w-0">
        {/* Letter list */}
        <Card padding="none" className="overflow-hidden lg:col-span-2">
          {activeQuery.isLoading ? (
            <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading letters">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
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
            <ul className="max-h-[36rem] divide-y divide-line overflow-y-auto">
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
        <div className="lg:col-span-3">
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

function ListError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-body">
        The letter list could not be loaded. Nothing is shown until the server responds.
      </p>
      <Button variant="outline" size="sm" onClick={onRetry} icon={<RefreshCw className="size-3.5" />}>
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
        onClick={onSelect}
        aria-current={selected || undefined}
        className={cn(
          'flex w-full flex-col gap-0.5 px-4 py-3 text-left transition-colors',
          selected ? 'bg-brand-soft/40' : 'hover:bg-soft',
        )}
      >
        <span className="flex items-center justify-between gap-3">
          <span className="truncate text-sm font-semibold text-ink">{letter.letter_id}</span>
          <Badge tone={letterStatusTone(letter.status)} className="shrink-0">
            {letter.status_label}
          </Badge>
        </span>
        <span className="truncate text-[13px] text-body">
          {letter.event_name} · {letter.facility_name}
        </span>
        <span className="text-xs tabular-nums text-muted">
          {letter.requester_name} ·{' '}
          {formatTime(letter.start_time)}–{formatTime(letter.end_time)} ·{' '}
          {letter.reservation_reference}
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
      const filename = `Approval-Letter-${letter.reservation_reference}-SIGNED.${kind}`
      await api.downloadFile(path, filename)
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
      {/* Header + actions */}
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
                {letter.letter_id}
              </p>
              <Badge tone={letterStatusTone(letter.status)}>{letter.status_label}</Badge>
            </div>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
              {letter.event_name}
            </h2>
            <p className="mt-0.5 text-sm text-body">
              {letter.facility_name} · {letter.reservation_reference}
            </p>
          </div>
          <div className="flex flex-wrap shrink-0 items-center gap-2">
            {letter.can_sign && (
              <Button
                icon={<FileSignature className="size-4" />}
                onClick={() => setConfirming(true)}
                loading={signMutation.isPending}
              >
                Sign Document
              </Button>
            )}
            {letter.has_signed_pdf && (
              <Button
                variant="outline"
                icon={<Download className="size-4" />}
                onClick={() => void handleDownload('pdf')}
                loading={pdfBusy}
              >
                Download PDF
              </Button>
            )}
            {letter.has_signed_docx && (
              <Button
                variant="outline"
                icon={<Download className="size-4" />}
                onClick={() => void handleDownload('docx')}
                loading={docxBusy}
              >
                Download DOCX
              </Button>
            )}
          </div>
        </div>

        {/* Signature + delivery record */}
        <dl className="mt-5 grid gap-x-8 gap-y-3 border-t border-line pt-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
              Signatory
            </dt>
            <dd className="mt-1 text-ink">{letter.signatory_name}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
              Signature timestamp
            </dt>
            <dd className="mt-1 text-ink">
              {letter.signed_at ? formatDateTime(letter.signed_at) : 'Awaiting signature'}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
              Email delivery
            </dt>
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
                  letter.email_status === 'SENT'
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : letter.email_status === 'FAILED'
                      ? 'border-red-200 bg-red-50 text-red-700'
                      : 'border-stone-200 bg-stone-50 text-stone-500',
                )}
              >
                <span className="size-1.5 rounded-full bg-current" />
                {letter.email_status_label}
              </span>
              {letter.emailed_at && (
                <span className="text-xs text-muted">{formatDateTime(letter.emailed_at)}</span>
              )}
              {letter.can_retry_email && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleRetryEmail()}
                  loading={retryMutation.isPending}
                  icon={<Send className="size-3.5" />}
                >
                  Retry email
                </Button>
              )}
              {letter.email_status === 'FAILED' && letter.email_error && (
                <span className="inline-flex items-center gap-1 text-xs text-status-rejected">
                  <MailWarning className="size-3.5" aria-hidden />
                  {letter.email_error}
                </span>
              )}
            </dd>
          </div>
        </dl>
      </Card>

      {/* Reservation information */}
      <Card>
        <CardHeader
          title="Reservation information"
          description="The approved booking this letter certifies"
        />
        <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
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
                  <span className="block text-xs text-muted">{letter.requester_email}</span>
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
        title="Sign this approval letter?"
        description="Are you sure you want to sign this reservation approval letter?"
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
    <div className={cn(wide && 'sm:col-span-2')}>
      <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 text-sm text-ink">{value}</dd>
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
        <Button variant="outline" size="sm" icon={<Eye className="size-3.5" />} onClick={() => void openPdf()} loading={pdfBusy}>
          Open PDF
        </Button>
      </div>
      <article className="mt-2 rounded-xl border border-line bg-white p-5 shadow-sm sm:p-8">
        <div className="text-center">
          <h3 className="text-lg font-bold tracking-tight text-ink sm:text-xl">
            {preview.institution}
          </h3>
          <p className="mt-1 text-sm text-body">{preview.issuing_office}</p>
          <p className="text-xs text-muted italic">
            {preview.system_name} — Facility &amp; Resource Reservation System
          </p>
        </div>
        <div className="mt-4 border-t-2 border-brand" aria-hidden />
        <div className="mt-5 text-center">
          <p className="text-sm font-bold uppercase tracking-[0.08em] text-brand">
            Reservation Approval Letter
          </p>
          <p className="mt-0.5 text-xs text-muted">Letter No. {preview.letter_id}</p>
        </div>

        <p className="mt-6 text-sm text-ink">Date of issuance: {preview.issued_date}</p>
        <div className="mt-4 text-sm text-ink">
          <p>{preview.requester_name}</p>
          {preview.organization && <p>{preview.organization}</p>}
        </div>
        <p className="mt-4 text-sm text-ink">Dear {preview.requester_name},</p>
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
                  {rule}
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
                className="text-3xl text-ink"
                style={{ fontFamily: "'Dancing Script', 'Segoe Script', cursive" }}
              >
                {preview.signatory_name}
              </p>
            ) : (
              <div className="flex h-14 items-end">
                <span className="w-56 border-b border-dashed border-line" aria-hidden />
              </div>
            )}
          </div>
          <p className="text-sm font-bold text-ink">{preview.signatory_name}</p>
          <p className="text-[13px] text-body">{preview.signatory_position}</p>
          <p className="mt-1 text-xs text-muted italic">
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
        'grid grid-cols-[minmax(7.5rem,10rem)_1fr] gap-3 px-3.5 py-2',
        zebra && 'bg-soft/60',
      )}
    >
      <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
        {label}
      </dt>
      <dd className="break-words text-ink">{value}</dd>
    </div>
  )
}
