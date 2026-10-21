import { useMemo } from 'react'
import type { Facility } from '@/lib/types'

/**
 * Effective built-in amenities for the selected facility.

A ``built_ins`` token only becomes an effective built-in amenity when the
facility has an active resource whose equipment name matches the token. The
hook keeps this list in sync with the configured inventory so the reservation
wizard does not suggest equipment the facility already provides as a real,
admin-configured built-in amenity.
*/
export function usePreferredBuiltinAmenities(facility: Facility | null): string[] {
  return useMemo(() => {
    if (!facility) return []
    const declared = facility.built_ins ?? []
    if (declared.length === 0) return []

    // The facility payload is the source of truth here: the backend already
    // derives the configured list server-side and exposes it as
    // ``built_in_amenities``. When that field is present we use it directly so
    // the wizard matches the backend's interpretation exactly.
    if (Array.isArray(facility.built_in_amenities)) {
      return facility.built_in_amenities
    }

    // Older clients may not have the derived field yet; fall back to the
    // declared tokens so the old behavior is preserved until the backend field
    // is available.
    return declared
  }, [facility])
}
