import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { format } from 'date-fns'
import { StepSchedule } from './wizard-steps'
import type { BookedDateEvent, Facility } from '@/lib/types'

// Tomorrow (Asia/Manila, the backend's "today" notion) — always inside the
// rendered month and never in the past, so the day markers are deterministic.
const { TOMORROW_KEY, TOMORROW_WEEKDAY } = vi.hoisted(() => {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Manila',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const [year, month, day] = parts.filter((part) => part.type !== 'literal').map((part) => part.value)
  const tomorrow = new Date(Number(year), Number(month) - 1, Number(day) + 1)
  const key = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`
  return { TOMORROW_KEY: key, TOMORROW_WEEKDAY: (tomorrow.getDay() === 0 ? 6 : tomorrow.getDay() - 1) }
})

// One approved booking (morning) and one pending request (afternoon) on the
// same day: partially booked AND carrying the pending marker.
const BOOKED_EVENTS: BookedDateEvent[] = [
  {
    event_name: 'Sports Fest',
    facility_name: 'Gymnasium',
    date: TOMORROW_KEY,
    start_time: '08:00',
    end_time: '09:30',
    status: 'APPROVED',
    status_label: 'Approved',
    resources: ['LED Wall'],
  },
  {
    event_name: 'Culmination Program',
    facility_name: 'Gymnasium',
    date: TOMORROW_KEY,
    start_time: '14:00',
    end_time: '15:30',
    status: 'PENDING',
    status_label: 'Pending',
    resources: ['Sound System'],
  },
]

// The booked-dates hook is the single data source of both calendar views;
// stubbing it keeps the test focused on presentation, not the network.
vi.mock('@/hooks/queries', () => ({
  useBookedDates: () => ({
    data: BOOKED_EVENTS,
    isPending: false,
    isSuccess: true,
    isError: false,
  }),
}))

const facility = {
  id: 1,
  name: 'Gymnasium',
  is_active: true,
  status: 'OPERATIONAL',
  operating_hours: [
    { day_of_week: TOMORROW_WEEKDAY, open_time: '08:00', close_time: '17:00', is_closed: false },
  ],
} as unknown as Facility

function renderSchedule() {
  return render(
    <StepSchedule
      facility={facility}
      date={new Date(`${TOMORROW_KEY}T12:00:00`)}
      onDateChange={vi.fn()}
      startTime=""
      endTime=""
      onStartTime={vi.fn()}
      onEndTime={vi.fn()}
      report={null}
      checking={false}
      onUseAlternative={vi.fn()}
    />,
  )
}

afterEach(cleanup)

describe('ScheduleStep pending reservation visibility', () => {
  it('marks the pending request in the Calendar View without changing occupancy', () => {
    renderSchedule()

    // The day cell reports its occupancy AND the pending request, and the
    // pending request never turns the day into "Fully booked".
    const dayCell = screen.getByRole('button', {
      name: `${format(new Date(`${TOMORROW_KEY}T12:00:00`), 'MMMM d, yyyy')}, Partially booked, Pending request`,
    })
    expect(dayCell).toBeInTheDocument()
    expect(dayCell.getAttribute('aria-label')).not.toContain('Fully booked')

    // The legend explains the pending marker; it renders under both view panes.
    expect(screen.getAllByText('Pending request').length).toBeGreaterThan(0)
  })

  it('shows pending and approved reservations in the Booked Dates view and its modal', () => {
    renderSchedule()

    fireEvent.click(screen.getByRole('button', { name: 'View Booked Dates' }))
    expect(screen.getByText('Reservations this month')).toBeInTheDocument()
    expect(screen.getByText(/1 pending request/)).toBeInTheDocument()

    // Selecting the date opens the modal with both statuses distinguished.
    fireEvent.click(screen.getByRole('button', { name: /Partially booked, Pending request/ }))
    expect(screen.getByText('Culmination Program')).toBeInTheDocument()
    expect(screen.getByText('Sports Fest')).toBeInTheDocument()
    expect(screen.getAllByText('Requested resources').length).toBe(2)
    expect(screen.getByText('Sound System')).toBeInTheDocument()
    expect(screen.getByText('LED Wall')).toBeInTheDocument()
  }, 15000)
})
