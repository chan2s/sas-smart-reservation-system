// API types — mirror the Django REST serializers.

export type Role = 'ADMIN' | 'STAFF' | 'REQUESTER'

export interface User {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  role: Role
  organization: string
  display_name: string
}

export type FacilityStatus = 'OPERATIONAL' | 'MAINTENANCE'
export type FacilityType =
  | 'GYMNASIUM'
  | 'CAFETERIA'
  | 'AVR'
  | 'MULTI_PURPOSE'
  | 'OUTDOOR'
  | 'OTHER'

export interface OperatingHour {
  id: number
  day_of_week: number
  day_label: string
  open_time: string | null
  close_time: string | null
  is_closed: boolean
}

export interface FacilityAvailability {
  status: FacilityStatus
  is_operational: boolean
  date?: string
  overlapping_reservations?: number
  available?: boolean
}

export interface Facility {
  id: number
  name: string
  facility_type: FacilityType
  facility_type_label: string
  description: string
  capacity: number
  location: string
  image: string | null
  rules: string[]
  status: FacilityStatus
  status_label: string
  is_active: boolean
  availability: FacilityAvailability
  operating_hours?: OperatingHour[]
}

/** Reservability level computed from the schedule + item status. */
export type AvailabilityLevel = 'AVAILABLE' | 'PARTIAL' | 'UNAVAILABLE'

/** Item-level operational status (set by SAS staff, not schedule-derived). */
export type EquipmentStatus = 'AVAILABLE' | 'MAINTENANCE' | 'UNAVAILABLE' | 'RETIRED'

export type EquipmentCondition = 'EXCELLENT' | 'GOOD' | 'FAIR' | 'POOR' | 'DAMAGED'

export interface EquipmentAvailability {
  total: number
  /** Units free during the selected window (or at-a-glance). */
  available: number
  reserved: number
  under_maintenance: number
  status: AvailabilityLevel
}

export interface EquipmentCategory {
  id: number
  name: string
  icon: string
  description: string
}

export interface Equipment {
  id: number
  name: string
  category: EquipmentCategory
  description: string
  total_quantity: number
  unit: string
  condition: EquipmentCondition
  condition_label: string
  status: EquipmentStatus
  status_label: string
  storage_location: string
  asset_code: string
  image: string | null
  notes: string
  is_active: boolean
  /** True when the item must be archived rather than hard-deleted on removal. */
  has_history: boolean
  availability: EquipmentAvailability
  open_maintenance?: number
  created_at: string
  updated_at: string
}

export interface EquipmentStats {
  equipment_types: number
  total_units: number
  available_units: number
  reserved_units: number
  under_maintenance_units: number
  unavailable_units: number
  damaged_records: number
}

export interface EquipmentHistoryItem {
  reservation: number
  reservation_id: string
  event_name: string
  date: string
  quantity: number
  status: ReservationStatus
  status_label: string
}

export type ReservationStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'ACTIVE'
  | 'COMPLETED'
  | 'REJECTED'
  | 'CANCELLED'

/** Who the reservation is FOR — independent of who created it. */
export type RequesterType = 'CAMPUS' | 'EXTERNAL'

export type OrganizationType =
  | 'SCHOOL'
  | 'GOVERNMENT'
  | 'PRIVATE'
  | 'COMMUNITY'
  | 'SPORTS'
  | 'COMPANY'
  | 'INDIVIDUAL'
  | 'OTHER'

export type EventType =
  | 'SEMINAR'
  | 'MEETING'
  | 'WORKSHOP'
  | 'TRAINING'
  | 'SPORTS'
  | 'CONFERENCE'
  | 'RECOGNITION'
  | 'ORIENTATION'
  | 'CULTURAL'
  | 'ACADEMIC'
  | 'OTHER'

export interface ReservationItem {
  id: number
  equipment: number
  equipment_id: number
  equipment_name: string
  category: string
  condition: string
  quantity: number
  returned: boolean
}

export interface ReservationEvent {
  id: number
  event_type:
    | 'CREATED'
    | 'SUBMITTED'
    | 'APPROVED'
    | 'REJECTED'
    | 'CHANGES_REQUESTED'
    | 'CANCELLED'
    | 'CHECKED_IN'
    | 'CHECKED_OUT'
    | 'COMMENT'
  event_type_label: string
  actor: number | null
  actor_name: string
  from_status: string
  to_status: string
  message: string
  created_at: string
}

export interface InspectionReport {
  id: number
  facility_condition: 'EXCELLENT' | 'GOOD' | 'FAIR' | 'POOR' | 'DAMAGED'
  facility_condition_label: string
  equipment_returned: boolean
  missing_items: string
  notes: string
  photo: string | null
  reported_by_name: string
  created_at: string
}

export interface ReservationSummary {
  id: number
  reservation_id: string
  event_name: string
  event_type: EventType
  event_type_label: string
  requester_type: RequesterType
  requester_type_label: string
  organization: string
  organization_type: string
  organization_type_label: string
  expected_participants: number
  contact_person: string
  contact_email: string
  created_by_name: string
  special_requirements: string
  facility: string
  facility_id: number
  facility_type: FacilityType
  requester: string
  requester_id: number | null
  date: string
  start_time: string
  end_time: string
  status: ReservationStatus
  status_label: string
  /** ISO datetime when the 3-hour check-in window opens (start − 3h). */
  check_in_open_time: string
  /** Server-computed: has the 3-hour check-in window opened yet? */
  check_in_window_open: boolean
  checked_in_at: string | null
  checked_out_at: string | null
  resources: string[]
  created_at: string
}

export interface AvailabilityItem {
  equipment_id: number
  name: string | null
  category: string | null
  /** Quantity the user asked for. */
  requested: number
  /** Units free during the selected date/time window (total − reserved − maintenance). */
  available: number
  /** Total inventory of the item. */
  total: number
  status: 'AVAILABLE' | 'PARTIAL' | 'UNAVAILABLE'
  message: string
}

export interface FacilityConflict {
  reservation_id: string
  event_name: string
  start_time: string
  end_time: string
  status: ReservationStatus
  requester: string
}

export interface AvailabilityCheck {
  facility: {
    id: number
    name: string
    status: FacilityStatus
    available: boolean
    operating_hours: {
      open: string | null
      close: string | null
      within_hours: boolean
    } | null
    conflicts: FacilityConflict[]
  }
  items: AvailabilityItem[]
  problems: { type: string; message: string }[]
  overall: { ok: boolean; message: string }
  requested: { date: string; start_time: string; end_time: string }
  alternatives?: AlternativeSlot[]
}

export interface AlternativeSlot {
  date: string
  start_time: string
  end_time: string
  duration: string
}

export interface Recommendation {
  equipment_id: number
  name: string
  category: string
  quantity: number // rule-based recommendation
  available: number // units available during the proposed schedule
  recommended: number // min(quantity, available) — safe prefill
  status: 'AVAILABLE' | 'PARTIAL' | 'UNAVAILABLE'
  reason: string
}

export interface ReservationDetail extends ReservationSummary {
  description: string
  purpose: string
  notes: string
  rejection_reason: string
  checkin_code: string
  early_check_in_override: boolean
  approved_by_name: string
  approved_at: string | null
  items: ReservationItem[]
  events: ReservationEvent[]
  inspection: InspectionReport | null
  availability: {
    ok: boolean
    facility: AvailabilityCheck['facility']
    items: AvailabilityItem[]
    problems: { type: string; message: string }[]
  }
}

export interface CalendarEvent {
  id: number
  reservation_id: string
  title: string
  start: string // 2026-09-14T09:00
  end: string
  facility_id: number
  facility: string
  status: ReservationStatus
  requester: string
  is_sas_staff: boolean
  requester_type?: string
  organization?: string
  contact_person?: string
  contact_email?: string
  created_by?: string
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type NotificationType = 'RESERVATION' | 'EQUIPMENT' | 'MAINTENANCE' | 'SYSTEM'

export interface Notification {
  id: number
  type: NotificationType
  type_label: string
  title: string
  message: string
  link: string
  read: boolean
  created_at: string
  time_ago: string
}

/** Compact reservation row for server-computed dashboard lists. */
export interface DashboardReservationRow {
  id: number
  reservation_id: string
  event_name: string
  facility: string
  facility_id: number
  requester: string
  date: string
  start_time: string
  end_time: string
  status: ReservationStatus
  status_label: string
}

export interface EquipmentAttentionRow {
  id: number
  name: string
  category: string
  condition: EquipmentCondition
  condition_label: string
  available: number
  total_quantity: number
  availability_status: 'AVAILABLE' | 'UNAVAILABLE'
}

export interface DashboardSummary {
  total_reservations: number
  pending_requests: number
  active_today: number
  facilities: number
  equipment_types: number
  equipment: number
  campus_reservations: number
  external_reservations: number
  facility_utilization: number
  cancellation_rate: number
  no_show_rate: number
  /** The backend's local date (Asia/Manila) that "today" was computed with. */
  today_date: string
  /** Server-computed in Asia/Manila time (not the browser's clock). */
  today: DashboardReservationRow[]
  upcoming: DashboardReservationRow[]
  pending: DashboardReservationRow[]
  recent: DashboardReservationRow[]
  equipment_attention: EquipmentAttentionRow[]
}

export interface RequesterBreakdown {
  days: number
  campus: number
  external: number
  external_facility_usage: { facility: string; count: number }[]
}

/** Compact campus-user profile for the admin "reserve on behalf of" picker. */
export interface CampusUserOption {
  id: number
  display_name: string
  username: string
  email: string
  organization: string
  role: Role
}

// ---------------------------------------------------------------------------
// Public (unauthenticated) API types
// ---------------------------------------------------------------------------

export interface PublicFacility {
  id: number
  name: string
  facility_type: FacilityType
  facility_type_label: string
  description: string
  capacity: number
  location: string
  image: string | null
  status: FacilityStatus
}

export interface GuestReservationResult {
  detail: string
  reservation_id: string
  status: ReservationStatus
  status_label: string
  track: { code: string; email: string }
}

/** Tracking statuses as shown to external requesters. */
export type TrackStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'COMPLETED'
  | 'CHECKED_IN'

export interface TrackResult {
  reservation_id: string
  status: TrackStatus
  status_label: string
  event_name: string
  event_type_label: string
  organization: string
  organization_type_label: string
  contact_person: string
  contact_email: string
  facility: string
  facility_id: number
  date: string
  start_time: string
  end_time: string
  expected_participants: number
  purpose: string
  resources: string[]
  created_at: string
}

export interface TrendPoint {
  month: string
  label: string
  total: number
}

export interface FacilityUtilization {
  overall: number
  days: number
  facilities: {
    facility_id: number
    name: string
    capacity_hours: number
    booked_hours: number
    utilization: number
  }[]
}

export interface EquipmentUtilization {
  overall: number
  items: {
    equipment_id: number
    name: string
    category: string
    total: number
    reserved: number
    utilization: number
  }[]
}

export interface Utilization {
  facility: FacilityUtilization
  equipment: EquipmentUtilization
}

export interface Insights {
  cancellation_rate: number
  no_show_rate: number
  peak_periods: { hour: number; count: number }[]
  most_requested: {
    facilities: { facility__name: string; count: number }[]
    equipment: { equipment__name: string; quantity: number }[]
  }
}

export interface ReportDefinition {
  slug: string
  title: string
  description: string
}

export interface ReportDetail extends ReportDefinition {
  preview: { headers: string[]; rows: (string | number)[][]; count: number }
  range: { from: string | null; to: string | null }
}

export interface MaintenanceRecord {
  id: number
  equipment: number
  equipment_name: string
  quantity: number
  issue_type: 'DAMAGE' | 'MISSING' | 'MALFUNCTION' | 'MAINTENANCE'
  issue_type_label: string
  description: string
  photo: string | null
  reported_by: number
  reported_by_name: string
  status: 'OPEN' | 'RESOLVED'
  status_label: string
  created_at: string
  resolved_at: string | null
}