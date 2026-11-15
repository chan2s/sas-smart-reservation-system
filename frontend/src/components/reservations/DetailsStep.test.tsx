import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { DetailsStep } from './DetailsStep'
import type { EventDetailsDraft } from '@/lib/reservationDraft'
import type { SuggestedResource } from '@/hooks/useSuggestedResources'

const details: EventDetailsDraft = {
  eventName: '',
  eventType: '',
  expectedParticipants: '',
  purpose: '',
  staffNotes: '',
}

const suggestion: SuggestedResource = {
  equipmentId: 21,
  name: 'Presentation Projector',
  category: 'Projectors',
  unit: 'unit',
  quantity: 1,
  available: 2,
  reason: 'Recommended for a presentation.',
}

function renderDetailsStep(overrides: Partial<React.ComponentProps<typeof DetailsStep>> = {}) {
  const props: React.ComponentProps<typeof DetailsStep> = {
    details,
    onDetailsChange: vi.fn(),
    contact: { name: 'Juan Dela Cruz', phone: '09171234567' },
    onContactChange: vi.fn(),
    reservingAs: 'Student Affairs Office',
    capacity: 100,
    facilityName: 'Audio-Visual Room',
    suggestions: [suggestion],
    suggestionsLoading: false,
    suggestionsError: false,
    items: {},
    onQuantity: vi.fn(),
    onToggleSuggestion: vi.fn(),
    onIgnoreSuggestion: vi.fn(),
    equipment: [],
    resourcesLoading: false,
    focusAttempt: 0,
    showAllErrors: false,
    approvalLetterFile: null,
    onApprovalLetterFile: vi.fn(),
    approvalLetterRequired: true,
    ...overrides,
  }
  return { ...render(<DetailsStep {...props} />), props }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('DetailsStep reservation form presentation', () => {
  it('shows required-field validation and keeps event and contact sections aligned', () => {
    renderDetailsStep({ showAllErrors: true })

    expect(screen.getByRole('heading', { name: 'Event information' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Contact information' })).toBeInTheDocument()
    expect(screen.getByLabelText('Event name')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Event type')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Expected participants')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Purpose')).toHaveAttribute('aria-invalid', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByLabelText('Contact phone')).toHaveAttribute('aria-invalid', 'false')
  })

  it('renders schedule-checked suggestions as optional Add/Ignore actions', () => {
    const { props } = renderDetailsStep()

    expect(screen.getByText('Presentation Projector — 1 × unit')).toBeInTheDocument()
    expect(screen.getByText(/2 available for this schedule/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ignore' }))
    expect(props.onToggleSuggestion).toHaveBeenCalledWith(21, 1, 2)
    expect(props.onIgnoreSuggestion).toHaveBeenCalledWith(21)
  })

  it('shows the event approval letter as a required internal-only field', () => {
    renderDetailsStep({ approvalLetterRequired: true })

    expect(screen.getByLabelText('Upload approval letter image')).toBeInTheDocument()
    expect(screen.getByText(/Required for internal reservations/)).toBeInTheDocument()
  })

  it('shows missing-letter feedback after validation fails', () => {
    renderDetailsStep({ approvalLetterRequired: true, showAllErrors: true })

    expect(screen.getByText('Upload an Event Approval Letter for this internal reservation.')).toBeInTheDocument()
  })

  it('hides the event approval letter for external reservations and shows it again for internal ones', () => {
    const { rerender, props } = renderDetailsStep({ approvalLetterRequired: false })

    expect(screen.queryByLabelText('Upload approval letter image')).not.toBeInTheDocument()
    expect(screen.queryByText(/Required for internal reservations/)).not.toBeInTheDocument()

    rerender(<DetailsStep {...props} approvalLetterRequired />)

    expect(screen.getByLabelText('Upload approval letter image')).toBeInTheDocument()
  })

  it('shows the uploaded-file preview and removes it through the existing callback', () => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:approval-preview'),
      revokeObjectURL: vi.fn(),
    })
    const file = new File(['signed approval'], 'approval-letter.png', { type: 'image/png' })
    const onApprovalLetterFile = vi.fn()
    renderDetailsStep({
      approvalLetterFile: file,
      onApprovalLetterFile,
    })

    expect(screen.getByAltText('Selected event approval letter preview')).toHaveAttribute(
      'src',
      'blob:approval-preview',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Remove file' }))
    expect(onApprovalLetterFile).toHaveBeenCalledWith(null)
  })
})
