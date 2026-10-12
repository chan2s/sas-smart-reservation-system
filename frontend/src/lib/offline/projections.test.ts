import { describe, expect, it } from 'vitest'
import type { Equipment, Facility, ReservationSummary } from '@/lib/types'
import {
  MAX_BACKUP_RESERVATIONS,
  projectEquipment,
  projectFacility,
  projectReservation,
  selectOwnReservations,
} from './projections'

const facility = {
  id: 3,
  name: 'University Gymnasium',
  facility_type: 'GYMNASIUM',
  facility_type_label: 'Gymnasium',
  description: 'Main indoor court.',
  capacity: 400,
  location: 'Main Campus',
  image: '/media/facilities/gym.png',
  rules: ['No eating inside', 'Shoes required'],
  seating_type: null,
  seating_type_label: '',
  built_in_seats: 120,
  built_ins: ['tables', 'chairs'],
  status: 'AVAILABLE',
  status_label: 'Available',
  is_active: true,
  has_history: true,
  reservation_count: 12,
  availability: { is_available: false, conflicts: ['19:00 reservation'] },
} as unknown as Facility

const equipment = {
  id: 9,
  name: 'Projector',
  category: { id: 1, name: 'Audio-Visual' },
  description: 'Full HD projector.',
  total_quantity: 4,
  unit: 'unit',
  price: '1500.00',
  condition: 'GOOD',
  condition_label: 'Good',
  status: 'AVAILABLE',
  status_label: 'Available',
  storage_location: 'SAS Office',
  asset_code: 'AV-009',
  image: null,
  notes: 'Handle with care',
  is_active: true,
  has_history: false,
  availability: { is_available: true, available_quantity: 2 },
  open_maintenance: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
} as unknown as Equipment

const reservation = {
  id: 41,
  reservation_id: 'RES-2026-0041',
  event_name: 'Org Meeting',
  requester_id: 7,
  requester: 'Jane Cruz',
  requester_type: 'CAMPUS',
  contact_person: 'Jane Cruz',
  contact_email: 'jane@norsu.edu.ph',
  contact_phone: '09171234567',
  facility: 'AVR',
  facility_id: 2,
  date: '2026-11-03',
  start_time: '09:00:00',
  end_time: '11:00:00',
  status: 'PENDING',
  status_label: 'Pending review',
  estimated_total: '1500.00',
  fees: [{ label: 'Projector', amount: '1500.00' }],
  approval_email_status: 'SENT',
  created_at: '2026-10-01T00:00:00Z',
} as unknown as ReservationSummary

describe('projectFacility', () => {
  it('keeps only descriptive, non-sensitive fields', () => {
    const projected = projectFacility(facility)
    expect(Object.keys(projected).sort()).toEqual(
      [
        'capacity',
        'description',
        'facility_type_label',
        'id',
        'image',
        'is_active',
        'location',
        'name',
        'status_label',
      ].sort(),
    )
  })

  it('never carries live availability or facility rules', () => {
    const projected = projectFacility(facility) as unknown as Record<string, unknown>
    expect(projected.availability).toBeUndefined()
    expect(projected.rules).toBeUndefined()
    expect(projected.reservation_count).toBeUndefined()
    expect(projected.has_history).toBeUndefined()
  })

  it('coerces a missing description to an empty string', () => {
    const withoutDescription = { ...facility, description: undefined } as unknown as Facility
    expect(projectFacility(withoutDescription).description).toBe('')
  })
})

describe('projectEquipment', () => {
  it('omits price, availability and maintenance counts', () => {
    const projected = projectEquipment(equipment) as unknown as Record<string, unknown>
    expect(projected.price).toBeUndefined()
    expect(projected.availability).toBeUndefined()
    expect(projected.open_maintenance).toBeUndefined()
    expect(projected.notes).toBeUndefined()
    expect(projected.asset_code).toBeUndefined()
  })

  it('keeps the descriptive catalogue fields', () => {
    const projected = projectEquipment(equipment)
    expect(projected.name).toBe('Projector')
    expect(projected.category_name).toBe('Audio-Visual')
    expect(projected.total_quantity).toBe(4)
    expect(projected.storage_location).toBe('SAS Office')
  })
})

describe('projectReservation', () => {
  it('keeps a compact status summary and drops contact/fee details', () => {
    const projected = projectReservation(reservation) as unknown as Record<string, unknown>
    expect(Object.keys(projected).sort()).toEqual(
      [
        'date',
        'end_time',
        'event_name',
        'facility',
        'facility_id',
        'id',
        'reservation_id',
        'start_time',
        'status_label',
      ].sort(),
    )
    expect(projected.contact_email).toBeUndefined()
    expect(projected.contact_phone).toBeUndefined()
    expect(projected.estimated_total).toBeUndefined()
    expect(projected.fees).toBeUndefined()
    expect(projected.approval_email_status).toBeUndefined()
  })
})

describe('selectOwnReservations', () => {
  const make = (id: number, requesterId: number | null, createdAt: string) =>
    ({ ...reservation, id, requester_id: requesterId, created_at: createdAt }) as ReservationSummary

  it("keeps only the signed-in user's own reservations", () => {
    const rows = [
      make(1, 7, '2026-10-01T00:00:00Z'),
      make(2, 8, '2026-10-02T00:00:00Z'),
      make(3, null, '2026-10-03T00:00:00Z'),
      make(4, 7, '2026-10-04T00:00:00Z'),
    ]
    const selected = selectOwnReservations(rows, 7)
    expect(selected.map((row) => row.id)).toEqual([4, 1])
  })

  it('never exposes another user (staff list endpoint) to the backup', () => {
    const rows = [make(1, 8, '2026-10-01T00:00:00Z'), make(2, 9, '2026-10-02T00:00:00Z')]
    expect(selectOwnReservations(rows, 7)).toEqual([])
  })

  it('caps the cached rows so a busy account cannot bloat storage', () => {
    const rows = Array.from({ length: MAX_BACKUP_RESERVATIONS + 20 }, (_, index) =>
      make(index + 1, 7, `2026-10-${String((index % 28) + 1).padStart(2, '0')}T00:00:00Z`),
    )
    expect(selectOwnReservations(rows, 7)).toHaveLength(MAX_BACKUP_RESERVATIONS)
  })

  it('orders newest first by created_at', () => {
    const rows = [make(1, 7, '2026-09-01T00:00:00Z'), make(2, 7, '2026-10-09T00:00:00Z')]
    expect(selectOwnReservations(rows, 7).map((row) => row.id)).toEqual([2, 1])
  })
})
