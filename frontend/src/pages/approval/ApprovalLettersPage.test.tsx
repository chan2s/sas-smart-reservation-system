import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApprovalLetter, ApprovalLetterPreview } from '@/lib/types'

/**
 * Black-box-ish tests for the signatory's Approval Letters workspace: the
 * not-authorized state, the pending list + letter preview, the confirmation
 * dialog gating Sign Document, and the signed-letter document/delivery UI.
 * The backend remains authoritative for every rule — these only pin the UI.
 */

const state = vi.hoisted(() => ({
  isApprovalSignatory: true,
  pending: [] as ApprovalLetter[],
  signed: [] as ApprovalLetter[],
  letter: null as ApprovalLetter | null,
  preview: null as ApprovalLetterPreview | null,
  signLetter: vi.fn(),
  retryEmail: vi.fn(),
  downloadFile: vi.fn(),
  fileUrl: vi.fn(),
}))

vi.mock('react-router-dom', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ isApprovalSignatory: state.isApprovalSignatory, isStaff: true }),
}))

vi.mock('@/hooks/queries', () => ({
  useApprovalLetters: (_params: unknown, enabled = true) => ({
    data: enabled
      ? String((_params as { status?: string }).status ?? '').includes('PENDING')
        ? { count: state.pending.length, results: state.pending }
        : { count: state.signed.length, results: state.signed }
      : undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    isFetching: false,
  }),
  useApprovalLetter: () => ({
    data: state.letter,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useApprovalLetterPreview: () => ({
    data: state.preview,
    isLoading: false,
  }),
  useSignApprovalLetter: () => ({
    mutateAsync: state.signLetter,
    isPending: false,
  }),
  useRetryLetterEmail: () => ({
    mutateAsync: state.retryEmail,
    isPending: false,
  }),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      downloadFile: (...args: unknown[]) => state.downloadFile(...args),
      fileUrl: (...args: unknown[]) => state.fileUrl(...args),
    },
  }
})

vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

import { ApprovalLettersPage } from './ApprovalLettersPage'

function letter(overrides: Partial<ApprovalLetter> = {}): ApprovalLetter {
  return {
    id: 5,
    letter_id: 'NORSU-AL-2026-00001',
    status: 'PENDING_SIGNATURE',
    status_label: 'Pending signature',
    reservation_pk: 42,
    reservation_reference: 'SAS-2026-00042',
    event_name: 'Leadership Summit',
    facility_name: 'Gymnasium',
    reservation_date: '2026-11-02',
    start_time: '09:00',
    end_time: '11:00',
    purpose: 'Leadership training',
    requester_name: 'Maria Santos',
    requester_email: 'maria@campus.edu',
    organization: '',
    approved_at: '2026-10-20T09:00:00+08:00',
    signatory_name: 'Francis M. Galon, Ph.D.',
    signatory_position: 'Assistant Campus Director for Administration and Finance',
    signatory: 3,
    signed_at: null,
    has_signed_pdf: false,
    has_signed_docx: false,
    preview_url: '/api/approval-letters/5/preview/',
    pdf_url: '/api/approval-letters/5/download/pdf/',
    docx_url: '/api/approval-letters/5/download/docx/',
    email_status: 'NOT_SENT',
    email_status_label: 'Not sent',
    email_attempted_at: null,
    emailed_at: null,
    email_error: '',
    can_retry_email: false,
    can_sign: true,
    created_at: '2026-10-20T09:00:00+08:00',
    updated_at: '2026-10-20T09:00:00+08:00',
    ...overrides,
  }
}

function preview(overrides: Partial<ApprovalLetterPreview> = {}): ApprovalLetterPreview {
  return {
    letter_id: 'NORSU-AL-2026-00001',
    status: 'PENDING_SIGNATURE',
    issued_date: 'October 20, 2026',
    requester_name: 'Maria Santos',
    organization: '',
    reservation_reference: 'SAS-2026-00042',
    event_name: 'Leadership Summit',
    facility_name: 'Gymnasium',
    reservation_date: 'November 2, 2026',
    reservation_start: '9:00 AM',
    reservation_end: '11:00 AM',
    purpose: 'Leadership training',
    expected_participants: 50,
    resources: [],
    facility_rules: ['No food in the gym'],
    estimated_total: '',
    is_external: false,
    signatory_name: 'Francis M. Galon, Ph.D.',
    signatory_position: 'Assistant Campus Director for Administration and Finance',
    signed_at: null,
    is_signed: false,
    test_signature_disclaimer: 'Test signature — demonstration only.',
    institution: 'Negros Oriental State University – BSC',
    issuing_office: 'Student Affairs and Services Office',
    system_name: 'SAS RESERVE',
    ...overrides,
  }
}

beforeEach(() => {
  state.isApprovalSignatory = true
  state.pending = []
  state.signed = []
  state.letter = null
  state.preview = null
  state.signLetter = vi.fn().mockResolvedValue(letter())
  state.retryEmail = vi.fn().mockResolvedValue(letter())
  state.downloadFile = vi.fn().mockResolvedValue(undefined)
  state.fileUrl = vi.fn().mockResolvedValue('blob:preview')
})

afterEach(cleanup)

describe('ApprovalLettersPage', () => {
  it('shows a not-authorized state for users without the designation', () => {
    state.isApprovalSignatory = false
    render(<ApprovalLettersPage />)
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
  })

  it('lists pending letters with the signatory identity', () => {
    state.pending = [letter()]
    state.letter = letter()
    state.preview = preview()
    render(<ApprovalLettersPage />)
    // The id appears in both the list and the detail header.
    expect(screen.getAllByText('NORSU-AL-2026-00001').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Francis M. Galon, Ph.D.').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Assistant Campus Director for Administration and Finance/).length).toBeGreaterThan(0)
    expect(screen.getByText('Sign Document')).toBeInTheDocument()
    // The unsigned preview notice is visible.
    expect(screen.getAllByText(/PENDING SIGNATURE/).length).toBeGreaterThan(0)
  })

  it('requires the confirmation dialog before signing', async () => {
    state.pending = [letter()]
    state.letter = letter()
    state.preview = preview()
    render(<ApprovalLettersPage />)

    fireEvent.click(screen.getByText('Sign Document'))
    // The dialog opens with the mandated wording; nothing signed yet.
    expect(
      await screen.findByText(
        'Are you sure you want to apply the test signature to this reservation approval letter? Please verify the document before proceeding.',
      ),
    ).toBeInTheDocument()
    expect(state.signLetter).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('Cancel'))
    expect(state.signLetter).not.toHaveBeenCalled()
  })

  it('signs after Confirm Signature', async () => {
    state.pending = [letter()]
    state.letter = letter()
    state.preview = preview()
    render(<ApprovalLettersPage />)

    fireEvent.click(screen.getByText('Sign Document'))
    fireEvent.click(await screen.findByText('Confirm Signature'))
    await waitFor(() => expect(state.signLetter).toHaveBeenCalledTimes(1))
  })

  it('offers PDF/DOCX downloads and shows delivery state for signed letters', async () => {
    const signed = letter({
      status: 'SENT',
      status_label: 'Signed and sent',
      signed_at: '2026-10-24T10:00:00+08:00',
      has_signed_pdf: true,
      has_signed_docx: true,
      email_status: 'SENT',
      email_status_label: 'Accepted by email service',
      email_attempted_at: '2026-10-24T10:00:05+08:00',
      emailed_at: '2026-10-24T10:00:05+08:00',
      can_sign: false,
    })
    state.pending = []
    state.signed = [signed]
    state.letter = signed
    state.preview = preview({ is_signed: true })
    render(<ApprovalLettersPage />)

    fireEvent.click(screen.getByText('Signed'))
    expect(await screen.findByText('Download PDF')).toBeInTheDocument()
    expect(screen.getByText('Download DOCX')).toBeInTheDocument()
    expect(screen.queryByText('Sign Document')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Download PDF'))
    await waitFor(() =>
      expect(state.downloadFile).toHaveBeenCalledWith(
        signed.pdf_url,
        expect.stringContaining('.pdf'),
      ),
    )
  })
})
