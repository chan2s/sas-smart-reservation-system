import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ReservationEventsModal } from './ReservationEventsModal'
import type { BookedDateEvent } from '@/lib/types'

afterEach(cleanup)

const date = new Date('2026-12-07T12:00:00')

const pendingEvent: BookedDateEvent = {
  event_name: 'Culmination Program',
  facility_name: 'Gymnasium',
  date: '2026-12-07',
  start_time: '14:00',
  end_time: '16:00',
  status: 'PENDING',
  status_label: 'Pending',
  resources: ['Sound System'],
}

const approvedEvent: BookedDateEvent = {
  ...pendingEvent,
  event_name: 'Sports Fest',
  start_time: '08:00',
  end_time: '10:00',
  status: 'APPROVED',
  status_label: 'Approved',
  resources: ['LED Wall'],
}

describe('ReservationEventsModal status presentation', () => {
  it('renders pending and approved reservations with distinct status colors', () => {
    render(
      <ReservationEventsModal
        open
        date={date}
        events={[pendingEvent, approvedEvent]}
        onClose={vi.fn()}
      />,
    )

    // The modal portals to document.body, so query the document, not the
    // render container.
    const badges = [...document.querySelectorAll('span.rounded-full')]
    const pendingBadge = badges.find((badge) => badge.textContent === 'Pending')
    const approvedBadge = badges.find((badge) => badge.textContent === 'Approved')
    expect(pendingBadge).toBeDefined()
    expect(approvedBadge).toBeDefined()
    // Amber family for Pending, green family for Approved — never identical.
    expect(pendingBadge!.className).toContain('bg-status-pending-bg')
    expect(pendingBadge!.className).toContain('text-status-pending')
    expect(approvedBadge!.className).toContain('bg-status-approved-bg')
    expect(approvedBadge!.className).toContain('text-status-approved')
    expect(pendingBadge!.className).not.toEqual(approvedBadge!.className)
  })

  it('shows the schedule and requested resources of a pending reservation', () => {
    render(
      <ReservationEventsModal open date={date} events={[pendingEvent]} onClose={vi.fn()} />,
    )

    expect(screen.getByText('Culmination Program')).toBeInTheDocument()
    expect(screen.getByText('Requested resources')).toBeInTheDocument()
    expect(screen.getByText('Sound System')).toBeInTheDocument()
    expect(screen.getAllByText('Pending').length).toBeGreaterThan(0)
  })

  it('exposes no requester identity or contact details', () => {
    const { container } = render(
      <ReservationEventsModal
        open
        date={date}
        events={[pendingEvent, approvedEvent]}
        onClose={vi.fn()}
      />,
    )

    const text = container.textContent ?? ''
    expect(text).not.toContain('@')
    expect(text).not.toContain('Juan')
    expect(text).not.toContain('0917')
    expect(text).not.toContain('notes')
  })
})
