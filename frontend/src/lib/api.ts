import type {
  AvailabilityCheck,
  CalendarEvent,
  CampusUserOption,
  DashboardSummary,
  Equipment,
  EquipmentCategory,
  EquipmentCondition,
  EquipmentHistoryItem,
  EquipmentStats,
  EquipmentStatus,
  EventType,
  Facility,
  Insights,
  MaintenanceRecord,
  Notification,
  OrganizationType,
  Paginated,
  Recommendation,
  ReportDefinition,
  ReportDetail,
  RequesterType,
  RequesterBreakdown,
  ReservationDetail,
  ReservationStatus,
  ReservationSummary,
  TrendPoint,
  User,
  Utilization,
} from './types'

const ACCESS_KEY = 'sas_access'
const REFRESH_KEY = 'sas_refresh'

export class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, message: string, data?: unknown) {
    super(message)
    this.status = status
    this.data = data
  }
}

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/**
 * Store tokens coming from the Google OAuth callback. The backend hands the
 * JWT pair back via a URL fragment (#access=…&refresh=…) on /auth/callback —
 * fragments are never sent to a server, so tokens stay out of logs/history.
 * This function consumes and clears the fragment immediately.
 */
export function consumeOAuthFragment(): { access: string; refresh: string } | null {
  const hash = window.location.hash.replace(/^#/, '')
  if (!hash.includes('access=')) return null
  const params = new URLSearchParams(hash)
  const access = params.get('access')
  const refresh = params.get('refresh')
  // Scrub the fragment from the address bar regardless of validity.
  history.replaceState(null, '', window.location.pathname + window.location.search)
  if (!access || !refresh) return null
  tokenStore.set(access, refresh)
  return { access, refresh }
}

let refreshPromise: Promise<boolean> | null = null

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const access = tokenStore.access
  if (access) headers.set('Authorization', `Bearer ${access}`)

  const response = await fetch(path, { ...options, headers })

  if (response.status === 401 && tokenStore.refresh && retry) {
    const refreshed = await refreshAccessToken()
    if (refreshed) return request<T>(path, options, false)
  }

  if (!response.ok) {
    let data: unknown = null
    let message = `Request failed (${response.status})`
    try {
      data = await response.json()
      const detail = (data as { detail?: string }).detail
      if (detail) message = detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message, data)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refresh = tokenStore.refresh
      if (!refresh) return false
      try {
        const response = await fetch('/api/auth/refresh/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh }),
        })
        if (!response.ok) {
          tokenStore.clear()
          return false
        }
        const data = (await response.json()) as { access: string }
        localStorage.setItem(ACCESS_KEY, data.access)
        return true
      } catch {
        tokenStore.clear()
        return false
      } finally {
        refreshPromise = null
      }
    })()
  }
  return refreshPromise
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  patchForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'PATCH', body: form }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  // Auth ---------------------------------------------------------------
  login: async (username: string, password: string) => {
    const data = await request<
      | { access: string; refresh: string; user: User }
      | { mfa_required: true; mfa_token: string }
    >('/api/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }, false)
    if ('mfa_required' in data && data.mfa_required) {
      const error = new ApiError(401, 'Two-factor authentication required.', data)
      // Attach the challenge so callers can continue the login.
      ;(error as ApiError & { mfaToken?: string }).mfaToken = data.mfa_token
      throw error
    }
    const tokens = data as { access: string; refresh: string; user: User }
    tokenStore.set(tokens.access, tokens.refresh)
    return tokens.user
  },
  verifyTwoFactorLogin: async (mfaToken: string, code: string) => {
    const data = await request<{ access: string; refresh: string; user: User }>(
      '/api/auth/2fa/verify-login/',
      { method: 'POST', body: JSON.stringify({ mfa_token: mfaToken, code }) },
      false,
    )
    tokenStore.set(data.access, data.refresh)
    return data.user
  },
  googleConfig: () =>
    api.get<{
      configured: boolean
      client_id?: string
      authorize_url?: string
      redirect_uri?: string
      scope?: string[]
    }>('/api/auth/google/'),
  googleStart: () =>
    api.get<{ authorize_url: string }>('/api/auth/google/start/'),
  verifyGoogleOtp: async (verificationToken: string, otp: string) => {
    const data = await request<{ access: string; refresh: string; user: User }>(
      '/api/auth/google/verify-otp/',
      {
        method: 'POST',
        body: JSON.stringify({ verification_token: verificationToken, otp }),
      },
      false,
    )
    tokenStore.set(data.access, data.refresh)
    return data.user
  },
  resendGoogleOtp: (verificationToken: string) =>
    api.post<{ detail: string }>('/api/auth/google/resend-otp/', {
      verification_token: verificationToken,
    }),
  twoFactorStatus: () =>
    api.get<{ enabled: boolean; backup_codes_remaining: number }>(
      '/api/auth/2fa/status/',
    ),
  twoFactorSetup: () =>
    api.post<{
      secret: string
      otpauth_url: string
      qr_png_data_url: string
    }>('/api/auth/2fa/setup/'),
  twoFactorVerify: (code: string) =>
    api.post<{ enabled: boolean; backup_codes: string[] }>('/api/auth/2fa/verify/', {
      code,
    }),
  twoFactorDisable: (password: string, code?: string) =>
    api.post<{ enabled: boolean }>('/api/auth/2fa/disable/', {
      password,
      code: code ?? '',
    }),
  twoFactorBackupCodes: (code: string) =>
    api.post<{ backup_codes: string[] }>('/api/auth/2fa/backup-codes/', { code }),
  auditLog: (params: { action?: string; search?: string; page?: number } = {}) => {
    const qs = new URLSearchParams()
    if (params.action) qs.set('action', params.action)
    if (params.search) qs.set('search', params.search)
    if (params.page) qs.set('page', String(params.page))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return api.get<{
      count: number
      num_pages: number
      results: AuditLogEntry[]
    }>(`/api/auth/audit-log/${suffix}`)
  },
  register: (payload: Record<string, unknown>) =>
    api.post<User>('/api/auth/register/', payload),
  me: () => api.get<User>('/api/auth/me/'),
}

export interface AuditLogEntry {
  id: number
  actor_name: string
  action: string
  action_label: string
  object_type: string
  object_id: string
  object_repr: string
  detail: string
  ip_address: string | null
  created_at: string
}

export interface ReservationFilters {
  status?: ReservationStatus
  requester_type?: RequesterType
  date?: string
  from?: string
  to?: string
  facility?: number
  requester?: number
  equipment?: number
  search?: string
  page?: number
  ordering?: string
}

export interface EquipmentPayload {
  name: string
  category_id: number
  description: string
  total_quantity: number
  unit: string
  condition: EquipmentCondition
  status: EquipmentStatus
  storage_location: string
  asset_code: string
  notes: string
  image?: File | string | null
}

export interface CreateReservationPayload {
  facility_id: number
  date: string
  start_time: string
  end_time: string
  event_name: string
  event_type: EventType
  organization: string
  organization_type?: string
  purpose: string
  description: string
  expected_participants: number
  contact_person: string
  contact_email?: string
  special_requirements: string
  notes: string
  items: { equipment_id: number; quantity: number }[]
  /** Staff only: create on behalf of another campus user. */
  requester_id?: number
  /** Staff only: CAMPUS (default) or EXTERNAL. */
  requester_type?: RequesterType
}

export interface GuestReservationPayload {
  facility_id: number
  date: string
  start_time: string
  end_time: string
  event_name: string
  event_type: EventType
  organization: string
  organization_type: OrganizationType
  purpose: string
  description: string
  expected_participants: number
  contact_person: string
  contact_email: string
  special_requirements: string
  items: { equipment_id: number; quantity: number }[]
}

export const endpoints = {
  facilities: (params?: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString()
    return api.get<Facility[]>(`/api/facilities/${qs ? `?${qs}` : ''}`)
  },
  facility: (id: number) => api.get<Facility>(`/api/facilities/${id}/`),

  equipment: (params?: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString()
    return api.get<Equipment[]>(`/api/equipment/${qs ? `?${qs}` : ''}`)
  },
  equipmentItem: (id: number) => api.get<Equipment>(`/api/equipment/${id}/`),
  equipmentStats: () => api.get<EquipmentStats>('/api/equipment/stats/'),
  equipmentCategories: () => api.get<EquipmentCategory[]>('/api/equipment-categories/'),
  equipmentMaintenance: (id: number) =>
    api.get<MaintenanceRecord[]>(`/api/equipment/${id}/maintenance/`),
  equipmentHistory: (id: number) =>
    api.get<EquipmentHistoryItem[]>(`/api/equipment/${id}/history/`),
  createEquipment: (payload: EquipmentPayload | FormData) =>
    payload instanceof FormData
      ? api.postForm<Equipment>('/api/equipment/', payload)
      : api.post<Equipment>('/api/equipment/', payload),
  updateEquipment: (id: number, payload: EquipmentPayload | FormData) =>
    payload instanceof FormData
      ? api.patchForm<Equipment>(`/api/equipment/${id}/`, payload)
      : api.patch<Equipment>(`/api/equipment/${id}/`, payload),
  deleteEquipment: (id: number) =>
    api.delete<{ archived?: boolean; detail?: string }>(`/api/equipment/${id}/`),
  restoreEquipment: (id: number) =>
    api.patch<Equipment>(`/api/equipment/${id}/`, { is_active: true }),
  equipmentSetMaintenance: (id: number, payload: { quantity: number; reason?: string }) =>
    api.post<MaintenanceRecord>(`/api/equipment/${id}/maintenance/`, payload),
  resolveMaintenance: (id: number) =>
    api.post<MaintenanceRecord>(`/api/maintenance/${id}/resolve/`),
  reportEquipmentIssue: (id: number, payload: FormData) =>
    api.postForm<MaintenanceRecord>(`/api/equipment/${id}/report_issue/`, payload),

  reservations: (filters: ReservationFilters = {}) => {
    const qs = new URLSearchParams()
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') {
        qs.set(key, String(value))
      }
    }
    return api.get<Paginated<ReservationSummary>>(`/api/reservations/?${qs}`)
  },
  campusUsers: (search: string) =>
    api.get<{ results: CampusUserOption[] }>(
      `/api/reservations/users/?search=${encodeURIComponent(search)}`,
    ),
  reservation: (id: number) => api.get<ReservationDetail>(`/api/reservations/${id}/`),
  createReservation: (payload: CreateReservationPayload) =>
    api.post<ReservationDetail>('/api/reservations/', payload),
  reservationAction: (id: number, action: string, body: Record<string, unknown> = {}) =>
    api.post<ReservationDetail>(`/api/reservations/${id}/${action}/`, body),
  reservationActionForm: (id: number, action: string, form: FormData) =>
    api.postForm<ReservationDetail>(`/api/reservations/${id}/${action}/`, form),
  reservationByCheckinCode: (code: string) =>
    api.get<ReservationDetail>(`/api/reservations/checkin/${code}/`),

  checkAvailability: (payload: {
    facility_id: number
    date: string
    start_time: string
    end_time: string
    items: { equipment_id: number; quantity: number }[]
  }) => api.post<AvailabilityCheck>('/api/availability/check/', payload),
  recommendResources: (payload: {
    event_type: string
    expected_participants: number
    facility_id?: number
    purpose?: string
    special_requirements?: string
    date?: string
    start_time?: string
    end_time?: string
  }) => api.post<{ recommendations: Recommendation[] }>('/api/availability/resources/', payload),

  calendarEvents: (params: {
    start: string
    end: string
    facility?: string | number
    status?: string
    equipment?: string | number
  }) => {
    const qs = new URLSearchParams()
    qs.set('start', params.start)
    qs.set('end', params.end)
    if (params.facility) qs.set('facility', String(params.facility))
    if (params.status) qs.set('status', params.status)
    if (params.equipment) qs.set('equipment', String(params.equipment))
    return api.get<CalendarEvent[]>(`/api/calendar/events/?${qs.toString()}`)
  },



  summary: () => api.get<DashboardSummary>('/api/analytics/summary/'),
  trends: (months = 6) => api.get<TrendPoint[]>(`/api/analytics/trends/?months=${months}`),
  utilization: (days = 30) =>
    api.get<Utilization>(`/api/analytics/utilization/?days=${days}`),
  requesterBreakdown: (days = 365) =>
    api.get<RequesterBreakdown>(`/api/analytics/requester-breakdown/?days=${days}`),
  insights: () => api.get<Insights>('/api/analytics/insights/'),

  reports: () => api.get<ReportDefinition[]>('/api/reports/'),
  report: (slug: string, range?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams()
    if (range?.from) qs.set('from', range.from)
    if (range?.to) qs.set('to', range.to)
    const suffix = qs.toString() ? `?${qs}` : ''
    return api.get<ReportDetail>(`/api/reports/${slug}/${suffix}`)
  },
  reportExportUrl: (slug: string, format: 'csv' | 'xlsx', range?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams()
    if (range?.from) qs.set('from', range.from)
    if (range?.to) qs.set('to', range.to)
    const suffix = qs.toString() ? `?${qs}` : ''
    return `/api/reports/${slug}/export/${format}/${suffix}`
  },

  notifications: (params?: { unread?: boolean; page?: number }) => {
    const qs = new URLSearchParams()
    if (params?.unread) qs.set('unread', 'true')
    if (params?.page) qs.set('page', String(params.page))
    return api.get<Paginated<Notification>>(`/api/notifications/?${qs}`)
  },
  unreadNotifications: () => api.get<{ count: number }>('/api/notifications/unread_count/'),
  markNotificationRead: (id: number) =>
    api.post<Notification>(`/api/notifications/${id}/mark_read/`),
  markAllNotificationsRead: () => api.post<{ count: number }>('/api/notifications/mark_all_read/'),
}