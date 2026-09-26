import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  endpoints,
  galleryChangeIsEmpty,
  type CreateReservationPayload,
  type EquipmentGalleryChange,
  type EquipmentImageRef,
  type EquipmentPayload,
  type ReservationFilters,
} from '@/lib/api'
import type { RequesterType } from '@/lib/types'
import type {
  AffiliationPayload,
  OrganizationFilters,
  OrganizationVerificationAction,
} from '@/lib/api'

// ---------------------------------------------------------------------------
// Facilities
// ---------------------------------------------------------------------------

export function useFacilities(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['facilities', params],
    queryFn: () => endpoints.facilities(params),
  })
}

export function useFacility(id: number | null) {
  return useQuery({
    queryKey: ['facility', id],
    queryFn: () => endpoints.facility(id as number),
    enabled: id != null,
  })
}

// ---------------------------------------------------------------------------
// Equipment
// ---------------------------------------------------------------------------

export function useEquipment(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['equipment', params],
    queryFn: () => endpoints.equipment(params),
  })
}

export function useEquipmentItem(id: number | null) {
  return useQuery({
    queryKey: ['equipment-item', id],
    queryFn: () => endpoints.equipmentItem(id as number),
    enabled: id != null,
  })
}

export function useEquipmentStats() {
  return useQuery({
    queryKey: ['equipment-stats'],
    queryFn: () => endpoints.equipmentStats(),
  })
}

export function useEquipmentCategories() {
  return useQuery({
    queryKey: ['equipment-categories'],
    queryFn: () => endpoints.equipmentCategories(),
  })
}

export function useEquipmentMaintenance(id: number | null) {
  return useQuery({
    queryKey: ['equipment-maintenance', id],
    queryFn: () => endpoints.equipmentMaintenance(id as number),
    enabled: id != null,
  })
}

export function useReportEquipmentIssue(equipmentId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: FormData) => endpoints.reportEquipmentIssue(equipmentId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-maintenance'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useCreateEquipment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: EquipmentPayload | FormData) => endpoints.createEquipment(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useUpdateEquipment(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: EquipmentPayload | FormData) => endpoints.updateEquipment(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-item', id] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useDeleteEquipment(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => endpoints.deleteEquipment(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-item', id] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useRestoreEquipment(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => endpoints.restoreEquipment(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-item', id] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

/**
 * Applies an admin's gallery edits to an equipment item.
 *
 * The work is split across the gallery endpoints because a multipart PATCH
 * cannot express "delete this one, reorder the rest, and promote that one":
 *   1. delete the images the admin removed,
 *   2. upload the new Files (the field name is `images`, repeated per File),
 *   3. reorder the surviving images (ids only known after the upload),
 *   4. promote the chosen primary image.
 *
 * Every step is awaited in order and any failure rejects, so the modal can
 * report a real error instead of pretending the images were saved. Caches are
 * invalidated only after the whole change set succeeds.
 */
export function useSaveEquipmentGallery() {
  const queryClient = useQueryClient()

  return async (equipmentId: number, change: EquipmentGalleryChange) => {
    if (galleryChangeIsEmpty(change)) return

    for (const imageId of change.deleteIds) {
      await endpoints.deleteEquipmentImage(equipmentId, imageId)
    }

    // New files are addressed by index until the backend assigns ids; the
    // upload response returns the created images in the order they were sent.
    const uploadedIds: number[] = []
    if (change.files.length > 0) {
      const response = await endpoints.uploadEquipmentImages(equipmentId, change.files)
      for (const image of response.images) {
        if (image.id != null) uploadedIds.push(image.id)
      }
    }

    const resolve = (ref: EquipmentImageRef): number | null =>
      'id' in ref ? ref.id : uploadedIds[ref.fileIndex] ?? null

    const order = change.order
      .map(resolve)
      .filter((id): id is number => id != null)
    // Only reorder when every image resolved — a partial list would be
    // rejected by the backend (it must name every gallery image exactly once).
    if (order.length > 0 && order.length === change.order.length) {
      await endpoints.reorderEquipmentImages(equipmentId, order)
    }

    if (change.primary) {
      const primaryId = resolve(change.primary)
      if (primaryId != null) {
        await endpoints.setPrimaryEquipmentImage(equipmentId, primaryId)
      }
    }

    await queryClient.invalidateQueries({ queryKey: ['equipment'] })
    await queryClient.invalidateQueries({ queryKey: ['equipment-item', equipmentId] })
    await queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
    await queryClient.invalidateQueries({ queryKey: ['summary'] })
  }
}

export function useEquipmentHistory(id: number | null) {
  return useQuery({
    queryKey: ['equipment-history', id],
    queryFn: () => endpoints.equipmentHistory(id as number),
    enabled: id != null,
  })
}

export function useSetEquipmentMaintenance(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { quantity: number; reason?: string }) =>
      endpoints.equipmentSetMaintenance(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-item', id] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-maintenance'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useResolveMaintenance(equipmentId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (recordId: number) => endpoints.resolveMaintenance(recordId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-item', equipmentId] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-maintenance'] })
      void queryClient.invalidateQueries({ queryKey: ['equipment-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Reservations
// ---------------------------------------------------------------------------

export function useReservations(filters: ReservationFilters = {}) {
  return useQuery({
    queryKey: ['reservations', filters],
    queryFn: () => endpoints.reservations(filters),
    placeholderData: keepPreviousData,
  })
}

export function useReservationCounts() {
  return useQuery({
    queryKey: ['reservation-counts'],
    queryFn: () => api.get<Record<string, number>>('/api/reservations/counts/'),
  })
}

export function useReservation(id: number | null) {
  return useQuery({
    queryKey: ['reservation', id],
    queryFn: () => endpoints.reservation(id as number),
    enabled: id != null,
  })
}

/** Staff-only campus-user directory for "reserve on behalf of" search. */
export function useCampusUsers(search: string, enabled = true) {
  return useQuery({
    queryKey: ['campus-users', search],
    queryFn: () => endpoints.campusUsers(search),
    enabled,
  })
}

export function useCreateReservation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateReservationPayload) => endpoints.createReservation(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reservations'] })
      void queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useReservationAction(id: number | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      action,
      body,
    }: {
      action: 'approve' | 'reject' | 'request_changes' | 'cancel' | 'check_in' | 'check_out'
      body?: Record<string, unknown>
    }) => endpoints.reservationAction(id as number, action, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reservation', id] })
      void queryClient.invalidateQueries({ queryKey: ['reservations'] })
      void queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
      void queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Availability & recommendations
// ---------------------------------------------------------------------------

export function useAvailabilityCheck() {
  return useMutation({
    mutationFn: (payload: {
      facility_id: number
      date: string
      start_time: string
      end_time: string
      items: { equipment_id: number; quantity: number }[]
      requester_type?: RequesterType
    }) => endpoints.checkAvailability(payload),
  })
}

export function useRecommendResources() {
  return useMutation({
    mutationFn: (payload: {
      event_type: string
      expected_participants: number
      facility_id?: number
      purpose?: string
      special_requirements?: string
      date?: string
      start_time?: string
      end_time?: string
      requester_type?: RequesterType
    }) => endpoints.recommendResources(payload),
  })
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

export function useCalendarEvents(params: {
  start: string
  end: string
  facility?: string
  status?: string
  equipment?: string
}) {
  return useQuery({
    queryKey: ['calendar-events', params],
    queryFn: () => endpoints.calendarEvents(params),
  })
}

// ---------------------------------------------------------------------------
// Analytics & reports
// ---------------------------------------------------------------------------

export function useDashboardSummary() {
  return useQuery({
    queryKey: ['summary'],
    queryFn: () => endpoints.summary(),
  })
}

export function useTrends(months = 6) {
  return useQuery({
    queryKey: ['trends', months],
    queryFn: () => endpoints.trends(months),
  })
}

export function useUtilization(days = 30) {
  return useQuery({
    queryKey: ['utilization', days],
    queryFn: () => endpoints.utilization(days),
  })
}

export function useInsights() {
  return useQuery({
    queryKey: ['insights'],
    queryFn: () => endpoints.insights(),
  })
}

export function useRequesterBreakdown(days = 365) {
  return useQuery({
    queryKey: ['requester-breakdown', days],
    queryFn: () => endpoints.requesterBreakdown(days),
  })
}

export function useReports() {
  return useQuery({
    queryKey: ['reports'],
    queryFn: () => endpoints.reports(),
  })
}

export function useReport(slug: string | null, range?: { from?: string; to?: string }) {
  return useQuery({
    queryKey: ['report', slug, range],
    queryFn: () => endpoints.report(slug as string, range),
    enabled: slug != null,
  })
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export function useNotifications(params?: { unread?: boolean; page?: number }) {
  return useQuery({
    queryKey: ['notifications', params],
    queryFn: () => endpoints.notifications(params),
  })
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ['unread-count'],
    queryFn: () => endpoints.unreadNotifications(),
    refetchInterval: 60_000,
  })
}
// ---------------------------------------------------------------------------
// Chatbot
// ---------------------------------------------------------------------------

export function useChatbot() {
  return useMutation({
    mutationFn: (message: string) => endpoints.chatbot(message),
  })
}

// ---------------------------------------------------------------------------
// Affiliation + external organizations
// ---------------------------------------------------------------------------

export function useMyAffiliation() {
  return useQuery({
    queryKey: ['affiliation'],
    queryFn: () => api.myAffiliation(),
  })
}

/**
 * Set the caller's affiliation (and register an external organization).
 *
 * The backend derives the organization from the authenticated user, so the
 * cache for the caller's reservation gating is refreshed on success.
 */
export function useSetAffiliation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AffiliationPayload) => api.setAffiliation(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['affiliation'] })
      void queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

/** Staff verification queue. */
export function useOrganizations(params: OrganizationFilters = {}) {
  return useQuery({
    queryKey: ['organizations', params],
    queryFn: () => api.organizations(params),
    placeholderData: keepPreviousData,
  })
}

export function useOrganization(id: number | null) {
  return useQuery({
    queryKey: ['organization', id],
    queryFn: () => api.organization(id as number),
    enabled: id != null,
  })
}

export function useVerifyOrganization() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      action,
      notes,
    }: {
      id: number
      action: OrganizationVerificationAction
      notes?: string
    }) => api.verifyOrganization(id, action, notes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['organizations'] })
      void queryClient.invalidateQueries({ queryKey: ['organization'] })
      void queryClient.invalidateQueries({ queryKey: ['affiliation'] })
    },
  })
}
