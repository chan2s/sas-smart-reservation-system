import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApprovalLetterDocument, ApprovalLetterSettings, User } from '@/lib/types'
import { api } from '@/lib/api'

const state = vi.hoisted(() => ({ toast: vi.fn() }))
const BODY: ApprovalLetterDocument = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 1, textAlign: 'center', spaceAfter: 4 }, content: [{ type: 'text', text: 'RESERVATION APPROVAL LETTER' }] },
    { type: 'documentMetadata' },
    { type: 'paragraph', attrs: { spaceAfter: 4 }, content: [{ type: 'text', text: 'Dear {{requester_name}},' }] },
    { type: 'reservationDetails' },
    { type: 'reservationConditions' },
  ],
}
const VERSION_PAGE = { results: [], count: 0, page: 1, page_size: 3, pages: 0 }

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, role: 'ADMIN' } as User,
    isViewOnly: false,
  }),
}))

vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ toast: state.toast }) }))

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn((path: string) => Promise.resolve(path.includes('/versions/') ? VERSION_PAGE : ({
      authorized_signatory_name: 'Configured Signatory',
      credentials: 'Ph.D.',
      designation: 'Campus Director',
      approval_label: 'Approved by:',
      sas_staff_display_name: 'SAS Administrator',
      sas_staff_designation: 'UED Staff / SAS Staff',
      letter_title: 'RESERVATION APPROVAL LETTER',
      approval_message: 'Approved for {{event_name}} at {{facility_name}}.',
      introductory_paragraphs: '',
      instructions_template: '',
      additional_content: '',
      footer_disclaimer: '',
      body_content: BODY,
      version: 1,
    } satisfies ApprovalLetterSettings))),
    patch: vi.fn(),
    post: vi.fn(),
    postFileUrl: vi.fn().mockResolvedValue('blob:approval-preview'),
  },
}))

import { ApprovalLetterManagementPage } from './ApprovalLetterManagementPage'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ApprovalLetterManagementPage', () => {
  it('loads existing settings, edits the signatory, and previews a draft', async () => {
    const saved = {
      authorized_signatory_name: 'New Signatory',
      credentials: 'Ph.D.',
      designation: 'New Position',
      approval_label: 'Approved by:',
      sas_staff_display_name: 'New SAS Staff Name',
      sas_staff_designation: 'New SAS Staff Role',
      letter_title: 'RESERVATION APPROVAL LETTER',
      approval_message: 'Approved for {{event_name}}.',
      introductory_paragraphs: '',
      instructions_template: '',
      additional_content: '',
      footer_disclaimer: '',
      body_content: BODY,
      version: 2,
    }
    vi.mocked(api.patch).mockResolvedValue(saved as never)
    render(<ApprovalLetterManagementPage />)

    expect(await screen.findByRole('heading', { name: 'Approval Letter Management' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Signatory name')).toHaveValue('Configured Signatory')
    fireEvent.change(screen.getByLabelText('Signatory name'), { target: { value: 'New Signatory' } })
    fireEvent.change(screen.getByLabelText('SAS/UED Staff Display Name'), { target: { value: 'New SAS Staff Name' } })
    fireEvent.change(screen.getByLabelText('SAS/UED Staff Designation'), { target: { value: 'New SAS Staff Role' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add paragraph' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save new version' }))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/admin/settings/approval-letter/',
      expect.objectContaining({
        authorized_signatory_name: 'New Signatory',
        body_content: expect.objectContaining({ type: 'doc' }),
        sas_staff_display_name: 'New SAS Staff Name',
        sas_staff_designation: 'New SAS Staff Role',
      }),
    ))

    fireEvent.change(screen.getByLabelText('Reservation reference'), { target: { value: 'SAS-2026-00032' } })
    fireEvent.click(screen.getByRole('button', { name: 'Preview current draft' }))
    await waitFor(() => {
      expect(api.postFileUrl).toHaveBeenCalledWith(
        '/api/admin/settings/approval-letter/preview/',
        expect.objectContaining({ authorized_signatory_name: 'New Signatory', reservation_reference: 'SAS-2026-00032' }),
      )
      expect(screen.getByTitle('Approval letter PDF preview')).toHaveAttribute('src', 'blob:approval-preview')
    })
  })

  it('shows the supported dynamic placeholder reference', async () => {
    render(<ApprovalLetterManagementPage />)
    await screen.findByRole('button', { name: 'Add paragraph' })
    fireEvent.click(screen.getByText('Insert a supported placeholder'))
    expect(screen.getByText('{{reservation_reference}}')).toBeInTheDocument()
    expect(screen.getByText('{{signatory_designation}}')).toBeInTheDocument()
  })
})
