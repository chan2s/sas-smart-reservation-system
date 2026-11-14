import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, apiErrorMessage } from '@/lib/api'
import type {
  ApprovalLetterSettings,
  ApprovalLetterTemplateVersionPage,
} from '@/lib/types'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Input } from '@/components/ui/Form'
import { ApprovalLetterRichTextEditor } from '@/pages/admin/ApprovalLetterRichTextEditor'

const PLACEHOLDERS: Array<[string, string]> = [
  ['{{requester_name}}', "Requester's displayed name or external contact person."],
  ['{{organization_name}}', 'Reservation organization, when provided.'],
  ['{{requester_email}}', 'Reservation contact email or the requester account email.'],
  ['{{contact_phone}}', 'Reservation contact phone number, when provided.'],
  ['{{reservation_reference}}', 'SAS RESERVE reservation ID.'],
  ['{{facility_name}}', 'Reserved facility name.'],
  ['{{event_name}}', 'Reservation event name.'],
  ['{{reservation_date}}', 'Reservation date, formatted for the letter.'],
  ['{{start_time}}', 'Reservation start time.'],
  ['{{end_time}}', 'Reservation end time.'],
  ['{{purpose}}', 'Reservation purpose, when provided.'],
  ['{{attendees}}', 'Expected participant count, when provided.'],
  ['{{equipment_list}}', 'Requested equipment and quantities, when provided.'],
  ['{{total_amount}}', 'Applicable total from stored reservation fees, when available.'],
  ['{{signatory_name}}', 'Configured authorized signatory name.'],
  ['{{signatory_credentials}}', 'Configured signatory credentials, when provided.'],
  ['{{signatory_designation}}', 'Configured official designation.'],
]

type Props = {
  value: ApprovalLetterSettings
  onChange: (value: ApprovalLetterSettings) => void
  disabled: boolean
  onSaved: (value: ApprovalLetterSettings) => void
}

export function ApprovalLetterManagementSection({ value, onChange, disabled, onSaved }: Props) {
  const { toast } = useToast()
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewReference, setPreviewReference] = useState('')
  const [changeNote, setChangeNote] = useState('')
  const [history, setHistory] = useState<ApprovalLetterTemplateVersionPage>({
    results: [], count: 0, page: 1, page_size: 3, pages: 0,
  })
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null)

  const loadVersions = useCallback(async (page = 1) => {
    setVersionsLoading(true)
    try {
      const result = await api.get<ApprovalLetterTemplateVersionPage>(
        `/api/admin/settings/approval-letter/versions/?page=${page}`,
      )
      setHistory(result)
    } catch (error) {
      toast(apiErrorMessage(error, 'Unable to load approval letter history.'), 'error')
    } finally {
      setVersionsLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void loadVersions(1)
  }, [loadVersions])

  useEffect(() => () => {
    if (previewUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  function update<K extends keyof ApprovalLetterSettings>(key: K, nextValue: ApprovalLetterSettings[K]) {
    onChange({ ...value, [key]: nextValue })
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const configuration = Object.fromEntries(
        Object.entries(value).filter(([key]) => key !== 'version'),
      )
      const updated = await api.patch<ApprovalLetterSettings>(
        '/api/admin/settings/approval-letter/',
        { ...configuration, change_note: changeNote },
      )
      onSaved(updated)
      setChangeNote('')
      toast('Approval letter template saved as a new version.')
      await loadVersions(1)
    } catch (error) {
      toast(apiErrorMessage(error, 'Unable to save the approval letter template.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  async function preview() {
    setPreviewing(true)
    try {
      const reservationReference = previewReference.trim()
      if (!reservationReference) {
        toast('Enter an approved external reservation reference to preview this letter.', 'error')
        return
      }
      const configuration = Object.fromEntries(
        Object.entries(value).filter(([key]) => key !== 'version'),
      )
      const url = await api.postFileUrl('/api/admin/settings/approval-letter/preview/', {
        ...configuration,
        reservation_reference: reservationReference,
      })
      setPreviewUrl(url)
      toast('Draft preview generated. Reservation status and email delivery were not changed.')
    } catch (error) {
      toast(apiErrorMessage(error, 'Unable to generate the approval letter preview.'), 'error')
    } finally {
      setPreviewing(false)
    }
  }

  async function restore(version: number) {
    setRestoringVersion(version)
    try {
      const restored = await api.post<ApprovalLetterSettings>(
        `/api/admin/settings/approval-letter/versions/${version}/restore/`,
      )
      onSaved(restored)
      toast(`Version ${version} restored as a new active version.`)
      await loadVersions(1)
    } catch (error) {
      toast(apiErrorMessage(error, 'Unable to restore this approval letter version.'), 'error')
    } finally {
      setRestoringVersion(null)
    }
  }

  return (
    <Card className="mt-6">
      <CardHeader
        title="Approval Letter Management"
        description="Edit the letter as a document. The NORSU header, reference block, reservation data table, and signature positions remain protected."
      />
      <form onSubmit={save} className="mt-5 space-y-6">
        <section aria-labelledby="letter-body-heading">
          <div className="mb-3">
            <h3 id="letter-body-heading" className="text-sm font-semibold text-ink">Letter body</h3>
            <p className="mt-1 text-xs text-muted">Type directly into the page. Use Enter for a new paragraph; the toolbar adds formatting, lists, headings, spacing, and reusable placeholders.</p>
          </div>
          <ApprovalLetterRichTextEditor
            value={value.body_content}
            disabled={disabled}
            placeholders={PLACEHOLDERS}
            onChange={(body) => update('body_content', body)}
          />
        </section>

        <div className="grid gap-5 border-t border-line pt-5 sm:grid-cols-2">
          <div className="sm:col-span-2">
          <h4 className="text-sm font-semibold text-ink">Authorized approver</h4>
          <p className="mt-1 text-xs text-muted">These values share the existing Approval Letter Settings and appear in the centered signature block.</p>
          </div>
        <Field label="Signatory name" htmlFor="management-signatory-name" required>
          <Input id="management-signatory-name" required maxLength={160} value={value.authorized_signatory_name} disabled={disabled} onChange={(event) => update('authorized_signatory_name', event.target.value)} />
        </Field>
        <Field label="Professional credentials" htmlFor="management-signatory-credentials" hint="Optional">
          <Input id="management-signatory-credentials" maxLength={80} value={value.credentials} disabled={disabled} onChange={(event) => update('credentials', event.target.value)} />
        </Field>
        <Field label="Signatory position or designation" htmlFor="management-signatory-designation" required className="sm:col-span-2">
          <Input id="management-signatory-designation" required maxLength={180} value={value.designation} disabled={disabled} onChange={(event) => update('designation', event.target.value)} />
        </Field>
        <Field label="Management approval label" htmlFor="management-approval-label" required>
          <Input id="management-approval-label" required maxLength={80} value={value.approval_label} disabled={disabled} onChange={(event) => update('approval_label', event.target.value)} />
        </Field>
        </div>

        <div className="grid gap-5 border-t border-line pt-5 sm:grid-cols-2">
          <div className="sm:col-span-2">
          <h4 className="text-sm font-semibold text-ink">SAS/UED staff signature</h4>
          <p className="mt-1 text-xs text-muted">These values appear on the right side of the renter signature area on future approval letters.</p>
          </div>
        <Field label="SAS/UED Staff Display Name" htmlFor="sas-staff-display-name" required>
          <Input id="sas-staff-display-name" required maxLength={160} value={value.sas_staff_display_name} disabled={disabled} onChange={(event) => update('sas_staff_display_name', event.target.value)} />
        </Field>
        <Field label="SAS/UED Staff Designation" htmlFor="sas-staff-designation" required>
          <Input id="sas-staff-designation" required maxLength={120} value={value.sas_staff_designation} disabled={disabled} onChange={(event) => update('sas_staff_designation', event.target.value)} />
        </Field>
        </div>

        <div className="flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-end sm:justify-between">
          <Field label="Version note" htmlFor="letter-change-note" hint="Optional audit note for this change." className="flex-1">
            <Input id="letter-change-note" maxLength={180} value={changeNote} disabled={disabled} onChange={(event) => setChangeNote(event.target.value)} />
          </Field>
          <Button type="submit" loading={saving} disabled={disabled}>Save new version</Button>
        </div>
      </form>

      <div className="mt-7 border-t border-line pt-5">
        <h4 className="text-sm font-semibold text-ink">PDF preview</h4>
        <p className="mt-1 text-xs text-muted">Choose an approved external reservation. Its personal details appear only in this preview and are never saved to the reusable template.</p>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field label="Reservation reference" htmlFor="preview-reservation" required hint="Preview renders the selected reservation through DOCX and LibreOffice. It does not save the draft, send email, or change status." className="flex-1">
            <Input id="preview-reservation" required value={previewReference} disabled={disabled} onChange={(event) => setPreviewReference(event.target.value)} placeholder="SAS-2026-00032" />
          </Field>
          <Button type="button" variant="outline" loading={previewing} disabled={disabled || !previewReference.trim()} onClick={() => void preview()}>
            Preview current draft
          </Button>
        </div>
        {previewUrl && (
          <iframe title="Approval letter PDF preview" src={previewUrl} className="mt-4 h-[720px] w-full rounded-lg border border-line bg-white" />
        )}
      </div>

      <div className="mt-7 border-t border-line pt-5">
        <h4 className="text-sm font-semibold text-ink">Template history</h4>
        <p className="mt-1 text-xs text-muted">Each saved change is retained. Restoring a version creates a new active version and never changes previously generated documents.</p>
        {versionsLoading ? (
          <p className="mt-3 text-sm text-muted" role="status">Loading template history…</p>
        ) : history.results.length ? (
          <ul className="mt-3 divide-y divide-line rounded-lg border border-line">
            {history.results.map((item) => (
              <li key={item.id} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-ink">Version {item.version}{item.change_note ? ` · ${item.change_note}` : ''}</p>
                  <p className="text-xs text-muted">{item.modified_by_name} · {new Date(item.created_at).toLocaleString()}</p>
                </div>
                <Button type="button" variant="outline" size="sm" disabled={disabled || restoringVersion !== null} loading={restoringVersion === item.version} onClick={() => void restore(item.version)}>
                  Restore version
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-muted">No saved versions yet.</p>
        )}
        <div className="mt-4 flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted" aria-live="polite">
            {history.count === 0 ? 'Showing 0–0 of 0' : `Showing ${(history.page - 1) * history.page_size + 1}–${Math.min(history.page * history.page_size, history.count)} of ${history.count}`}
            {' · '}Page {history.count ? history.page : 0} of {history.pages}
          </p>
          <div className="flex gap-2">
            <Button type="button" size="sm" variant="outline" disabled={versionsLoading || history.page <= 1} onClick={() => void loadVersions(history.page - 1)}>Previous</Button>
            <Button type="button" size="sm" variant="outline" disabled={versionsLoading || history.page >= history.pages} onClick={() => void loadVersions(history.page + 1)}>Next</Button>
          </div>
        </div>
      </div>
    </Card>
  )
}
