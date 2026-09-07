import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  endpoints,
  type CreateReservationPayload,
  type EquipmentPayload,
  type GuestReservationPayload,
  type ReservationFilters,
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

export function useCreateGuestReservation() {
  return useMutation({
    mutationFn: (payload: GuestReservationPayload) =>
      endpoints.createGuestReservation(payload),
  })
}

export function useTrackReservation() {
  return useMutation({
    mutationFn: (payload: { reservation_code: string; email: string }) =>
      endpoints.trackReservation(payload),
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