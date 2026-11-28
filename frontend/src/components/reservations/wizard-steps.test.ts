import { describe, expect, it } from 'vitest'
import {
  dayStatusLabel,
  hasPendingRequest,
  occupancyFromEvents,
} from './wizard-steps'
import type { BookedDateEvent } from '@/lib/types'

function event(
  status: BookedDateEvent['status'],
  start: string,
  end: string,
  name = 'Event',
): BookedDateEvent {
  return {
    event_name: name,
    facility_name: 'Gymnasium',
    date: '2026-12-07',
    start_time: start,
    end_time: end,
    status,
    status_label: status,
  }
}

// Operating hours 08:00–17:00 as the day functions compute them: every
// 30-minute candidate start, the same intervals as the time selectors.
const FULL_DAY_STARTS = Array.from({ length: 18 }, (_, index) => 8 * 60 + index * 30)

describe('day occupancy from booked events', () => {
  it('a day holding only pending requests stays available — pending is not a booking', () => {
    const events = [event('PENDING', '09:00', '17:00')]
    expect(occupancyFromEvents(events, FULL_DAY_STARTS)).toBe('available')
    expect(occupancyFromEvents(events, FULL_DAY_STARTS)).not.toBe('full')
    expect(hasPendingRequest(events)).toBe(true)
  })

  it('approved reservations make a day partially booked when free slots remain', () => {
    const events = [event('APPROVED', '08:00', '09:30')]
    expect(occupancyFromEvents(events, FULL_DAY_STARTS)).toBe('partial')
    expect(hasPendingRequest(events)).toBe(false)
  })

  it('approved reservations covering every slot make a day fully booked', () => {
    const events = [event('APPROVED', '08:00', '17:00')]
    expect(occupancyFromEvents(events, FULL_DAY_STARTS)).toBe('full')
  })

  it('rejected, cancelled, and expired reservations are ignored entirely', () => {
    const events = [
      event('REJECTED', '08:00', '12:00'),
      event('CANCELLED', '12:00', '15:00'),
      event('EXPIRED', '15:00', '17:00'),
    ]
    expect(occupancyFromEvents(events, FULL_DAY_STARTS)).toBe('available')
    expect(hasPendingRequest(events)).toBe(false)
  })

  it('keeps the backend half-open interval rule: end-to-start adjacency is free', () => {
    // An approved event ending exactly when a candidate starts leaves that
    // slot free — never treated as overlapping. With approved events present
    // a free slot means "partial"; no free slot means "full".
    const events = [event('APPROVED', '08:00', '09:00')]
    expect(occupancyFromEvents(events, [9 * 60])).toBe('partial')
    expect(occupancyFromEvents(events, [8 * 60 + 30])).toBe('full')
  })

  it('mixed approved and pending events book partially and flag pending', () => {
    const events = [event('APPROVED', '08:00', '10:00'), event('PENDING', '14:00', '16:00')]
    expect(occupancyFromEvents(events, FULL_DAY_STARTS)).toBe('partial')
    expect(hasPendingRequest(events)).toBe(true)
    expect(dayStatusLabel('partial', true)).toBe('Partially booked, Pending request')
  })

  it('labels a pending-only day as available with the pending marker', () => {
    expect(dayStatusLabel('available', true)).toBe('Available, Pending request')
    expect(dayStatusLabel('available', false)).toBe('Available')
    expect(dayStatusLabel('unavailable', true)).toBe('Unavailable, Pending request')
  })
})
