import { format, parseISO } from 'date-fns'
import type { ReservationStatus } from './types'

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ')
}

/**
 * Convert a backend equipment image value into a URL the frontend can render.
 *
 * The Django API returns either:
 *   - a relative path like "/media/equipment/sound-system.jpg" or
 *   - an absolute URL in some deployment configurations.
 *
 * During development the Vite dev server proxies "/media" to Django, so a
 * relative "/media/..." path works as-is from the browser. In production the
 * frontend and media may share a host. If the backend returns an absolute URL
 * on a different host, we trust it as-is.
 */
export function getEquipmentImageUrl(image: string | null | undefined): string | null {
  if (!image) return null

  try {
    const url = new URL(image, window.location.origin)

    // If the backend already returned an absolute media URL, use it as-is.
    // This keeps the frontend working when the API/backend and frontend run
    // on different hosts/ports.
    if (url.pathname.startsWith('/media/')) {
      return url.origin + url.pathname
    }

    // Some deployments may already return an absolute asset URL. Trust it.
    if (url.origin !== window.location.origin) {
      return url.toString()
    }

    // Fallback: relative path rendered from the current origin (Vite proxies
    // /media to Django in development).
    return url.origin + url.pathname
  } catch {
    return null
  }
}

export function formatDate(date: string | Date): string {
  const parsed = typeof date === 'string' ? parseISO(date) : date
  return format(parsed, 'MMM d, yyyy')
}

export function formatTime(time: string): string {
  // "09:00" -> "9:00 AM"
  const [hours, minutes] = time.split(':').map(Number)
  const date = new Date()
  date.setHours(hours, minutes, 0, 0)
  return format(date, 'h:mm a')
}

export function formatDateTime(iso: string): string {
  if (!iso) return '—'
  return format(parseISO(iso), 'MMM d, yyyy · h:mm a')
}

export function weekdayLabel(dayOfWeek: number): string {
  return ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][
    dayOfWeek
  ]
}

export function initials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

export const STATUS_META: Record<
  ReservationStatus,
  { label: string; text: string; bg: string; dot: string }
> = {
  PENDING: {
    label: 'Pending',
    text: 'text-status-pending',
    bg: 'bg-status-pending-bg',
    dot: 'bg-status-pending',
  },
  APPROVED: {
    label: 'Approved',
    text: 'text-status-approved',
    bg: 'bg-status-approved-bg',
    dot: 'bg-status-approved',
  },
  ACTIVE: {
    label: 'Active',
    text: 'text-status-active',
    bg: 'bg-status-active-bg',
    dot: 'bg-status-active',
  },
  COMPLETED: {
    label: 'Completed',
    text: 'text-status-completed',
    bg: 'bg-status-completed-bg',
    dot: 'bg-status-completed',
  },
  REJECTED: {
    label: 'Rejected',
    text: 'text-status-rejected',
    bg: 'bg-status-rejected-bg',
    dot: 'bg-status-rejected',
  },
  CANCELLED: {
    label: 'Cancelled',
    text: 'text-status-cancelled',
    bg: 'bg-status-cancelled-bg',
    dot: 'bg-status-cancelled',
  },
}

export function downloadFile(url: string) {
  // Exports carry Content-Disposition, so a plain anchor works with the
  // Authorization header added by the service layer only if we fetch first.
  fetch(url)
    .then((response) => {
      if (!response.ok) throw new Error('Export failed')
      const disposition = response.headers.get('Content-Disposition') || ''
      const match = disposition.match(/filename="?([^";]+)"?/)
      const filename = match?.[1] ?? 'report'
      return response.blob().then((blob) => ({ blob, filename }))
    })
    .then(({ blob, filename }) => {
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(objectUrl)
    })
    .catch((error) => console.error(error))
}