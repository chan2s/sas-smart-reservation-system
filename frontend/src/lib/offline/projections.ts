/**
 * Minimal projections for the offline backup.
 *
 * These functions are the ONLY place that decides what leaves the API response
 * and enters IndexedDB. They deliberately strip everything that is sensitive or
 * that could be misrepresented offline:
 *
 *  - facility/equipment `availability` and maintenance counts are omitted:
 *    availability is computed live from reservations and must never be
 *    presented from a stale cache;
 *  - equipment `price` / facility fees are financial and are not stored;
 *  - reservation contact details, fees, totals, approval-email diagnostics and
 *    timeline are not stored — only a compact status summary.
 */

import type { Equipment, Facility, ReservationSummary } from '@/lib/types'
import type { OfflineEquipment, OfflineFacility, OfflineReservation } from './db'

export function projectFacility(facility: Facility): OfflineFacility {
  return {
    id: facility.id,
    name: facility.name,
    facility_type_label: facility.facility_type_label,
    description: facility.description ?? '',
    capacity: facility.capacity,
    location: facility.location,
    image: facility.image ?? null,
    status_label: facility.status_label,
    is_active: facility.is_active,
  }
}

export function projectEquipment(equipment: Equipment): OfflineEquipment {
  return {
    id: equipment.id,
    name: equipment.name,
    category_name: equipment.category?.name ?? '',
    total_quantity: equipment.total_quantity,
    unit: equipment.unit,
    condition_label: equipment.condition_label,
    status_label: equipment.status_label,
    storage_location: equipment.storage_location,
    image: equipment.image ?? null,
    is_active: equipment.is_active,
  }
}

export function projectReservation(reservation: ReservationSummary): OfflineReservation {
  return {
    id: reservation.id,
    reservation_id: reservation.reservation_id,
    event_name: reservation.event_name,
    facility: reservation.facility,
    facility_id: reservation.facility_id,
    date: reservation.date,
    start_time: reservation.start_time,
    end_time: reservation.end_time,
    status_label: reservation.status_label,
  }
}

/** Cap the number of cached rows so a busy staff account cannot bloat storage. */
export const MAX_BACKUP_RESERVATIONS = 50

/**
 * Only the current user's OWN reservations may be cached.
 *
 * Staff/admin list endpoints return every reservation in the system; caching
 * those would leak other people's data onto a shared device. Ownership is taken
 * from the server-computed `requester_id`, never from a name.
 */
export function selectOwnReservations(
  reservations: ReservationSummary[],
  userId: number,
): ReservationSummary[] {
  return reservations
    .filter((reservation) => reservation.requester_id === userId)
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, MAX_BACKUP_RESERVATIONS)
}
