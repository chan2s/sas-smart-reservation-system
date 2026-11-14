import { useEffect, useState } from 'react'
import { ApprovalLetterManagementSection } from '@/pages/settings/ApprovalLetterManagementSection'
import { PageHeader } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import { api, apiErrorMessage } from '@/lib/api'
import type { ApprovalLetterSettings } from '@/lib/types'

const EMPTY_SETTINGS: ApprovalLetterSettings = {
  authorized_signatory_name: '',
  credentials: '',
  designation: '',
  approval_label: 'Approved by:',
  sas_staff_display_name: '',
  sas_staff_designation: '',
  letter_title: 'RESERVATION APPROVAL LETTER',
  approval_message: 'This is to inform you that your request to use the {{facility_name}} for {{event_name}} has been approved, subject to the reservation details and conditions stated below.',
  introductory_paragraphs: '',
  instructions_template: '',
  additional_content: '',
  footer_disclaimer: '',
  body_content: {
    type: 'doc',
    content: [
      { type: 'heading', attrs: { level: 1, textAlign: 'center', spaceAfter: 4 }, content: [{ type: 'text', text: 'RESERVATION APPROVAL LETTER' }] },
      { type: 'documentMetadata' },
      { type: 'paragraph', attrs: { spaceAfter: 4 }, content: [{ type: 'text', text: 'Dear {{requester_name}},' }] },
      { type: 'paragraph', attrs: { spaceAfter: 4 }, content: [{ type: 'text', text: 'This is to inform you that your request to use the {{facility_name}} for {{event_name}} has been approved.' }] },
      { type: 'reservationDetails' },
      { type: 'heading', attrs: { level: 2, textAlign: 'left', spaceAfter: 4 }, content: [{ type: 'text', text: 'Important instructions' }] },
      { type: 'reservationConditions' },
    ],
  },
}

export function ApprovalLetterManagementPage() {
  const { user, isViewOnly } = useAuth()
  const { toast } = useToast()
  const [settings, setSettings] = useState<ApprovalLetterSettings>(EMPTY_SETTINGS)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    api.get<ApprovalLetterSettings>('/api/admin/settings/approval-letter/')
      .then((value) => { if (active) setSettings(value) })
      .catch((error) => {
        if (active) toast(apiErrorMessage(error, 'Unable to load approval letter settings.'), 'error')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [toast])

  if (!user) return null

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="Administration"
        title="Approval Letter Management"
        description="Manage letter wording, SAS/UED staff details, the authorized approver, previews, and saved versions for future external reservation approval letters."
      />
      {loading ? (
        <Card className="mt-7">
          <p className="text-sm text-muted" role="status">Loading approval letter configuration…</p>
        </Card>
      ) : (
        <ApprovalLetterManagementSection
          value={settings}
          onChange={setSettings}
          disabled={loading || isViewOnly}
          onSaved={setSettings}
        />
      )}
      <p className="mt-4 text-xs text-muted">
        Changes apply to newly generated letters. Previously generated or signed documents remain unchanged.
      </p>
    </div>
  )
}
