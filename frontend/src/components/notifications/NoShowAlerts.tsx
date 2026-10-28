import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import { Bell, BellOff, CheckCheck, CircleAlert, Package, Ticket, Wrench } from 'lucide-react'
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadCount,
} from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { cn, formatTime } from '@/lib/utils'
import type { NoShowAlert, NoShowAlertStage, Notification, NotificationType } from '@/lib/types'

/**
 * Badge colours per stage. The stage itself is decided by the backend, so these
 * classes only style it — the UI never decides whether a reservation is late.
 */
export function stageBadgeClass(stage: NoShowAlertStage): string {
  switch (stage) {
    case 'NO_SHOW_RISK':
      return 'bg-status-rejected-bg text-status-rejected'
    case 'START_REACHED':
      return 'bg-status-maintenance-bg text-status-maintenance'
    default:
      return 'bg-status-pending-bg text-status-pending'
  }
}

export function StageBadge({
  stage,
  label,
  className,
}: {
  stage: NoShowAlertStage
  label: string
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold',
        stageBadgeClass(stage),
        className,
      )}
    >
      {label}
    </span>
  )
}

/** "Oct 23, 2026 · 9:00 AM" for an alert's reservation slot. */
export function alertDateTime(alert: NoShowAlert): string {
  const day = format(new Date(`${alert.date}T00:00:00`), 'MMM d, yyyy')
  return `${day} · ${formatTime(alert.start_time)}`
}

/**
 * Administrator notification center. Its API feed combines persisted workflow
 * notifications and active possible-no-show alerts; the dashboard continues to
 * render the same active alert records directly.
 */
const notificationIcon: Record<NotificationType, React.ReactNode> = {
  RESERVATION: <Ticket className="size-4" aria-hidden />,
  EQUIPMENT: <Package className="size-4" aria-hidden />,
  MAINTENANCE: <Wrench className="size-4" aria-hidden />,
  SYSTEM: <CircleAlert className="size-4" aria-hidden />,
}

export function NotificationCenter({ onNavigate }: { onNavigate?: () => void }) {
  const { isViewOnly } = useAuth()
  const { data, isLoading, isError, refetch, isFetching } = useNotifications({ page: 1 })
  const { data: unreadData } = useUnreadCount()
  const markRead = useMarkNotificationRead()
  const markAll = useMarkAllNotificationsRead()
  const notifications = data?.results ?? []
  const unread = unreadData?.count ?? notifications.filter((notification) => !notification.read).length

  return (
    /*
     * The panel owns the width (full-bleed sheet on mobile, 27rem from `sm`
     * up); this column fills it and only the notification list scrolls, so the
     * header and the "All notifications" footer stay reachable.
     */
    <div className="flex min-h-0 w-full min-w-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-2.5 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Bell className="size-4 shrink-0 text-brand" aria-hidden />
          <p className="text-[13px] font-semibold text-ink">Notifications</p>
          {unread > 0 && <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand">{unread} unread</span>}
        </div>
        {unread > 0 && !isViewOnly && (
          <button
            type="button"
            onClick={() => markAll.mutate()}
            disabled={markAll.isPending}
            className="ml-auto inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-[11px] font-semibold text-brand hover:text-brand-dark disabled:opacity-60"
          >
            <CheckCheck className="size-3.5" aria-hidden />
            Mark all as read
          </button>
        )}
      </div>

      {isError ? (
        <div className="rounded-lg border border-status-rejected/30 bg-status-rejected-bg/40 px-3 py-3">
          <p className="flex items-center gap-1.5 text-[12.5px] font-semibold text-status-rejected">
            <CircleAlert className="size-4" aria-hidden />
            Couldn't load notifications
          </p>
          <p className="mt-1 text-[12px] text-body">
            The notification request failed. Please retry in a moment.
          </p>
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="mt-2 text-[12px] font-semibold text-brand hover:text-brand-dark disabled:opacity-60"
          >
            {isFetching ? 'Retrying…' : 'Retry'}
          </button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2 px-1" aria-busy="true" aria-label="Loading alerts">
          <div className="h-16 rounded-lg bg-soft" />
          <div className="h-16 rounded-lg bg-soft" />
          <div className="h-16 rounded-lg bg-soft" />
        </div>
      ) : notifications.length === 0 ? (
        <div className="flex flex-col items-center px-4 py-6 text-center">
          <span className="flex size-9 items-center justify-center rounded-full bg-soft text-muted">
            <BellOff className="size-4" aria-hidden />
          </span>
          <p className="mt-2 text-[12.5px] font-medium text-ink">You're all caught up</p>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-body">
            Reservation, facility, and system updates will appear here.
          </p>
        </div>
      ) : (
        <ul className="max-h-[min(65vh,560px)] min-h-0 flex-1 divide-y divide-line overflow-y-auto overscroll-contain">
          {notifications.map((notification) => (
            <NotificationCenterRow
              key={`${notification.source ?? 'notification'}-${notification.id}`}
              notification={notification}
              pending={markRead.isPending}
              canMarkRead={!isViewOnly}
              onOpen={() => {
                if (!notification.read && !isViewOnly) markRead.mutate(notification)
                onNavigate?.()
              }}
            />
          ))}
        </ul>
      )}
      <div className="shrink-0 border-t border-line px-2.5 py-2">
        <Link
          to="/notifications"
          onClick={onNavigate}
          className="block rounded-lg px-2 py-1.5 text-center text-[12px] font-semibold text-brand transition-colors hover:bg-brand-soft"
        >
          All notifications{data?.count ? ` (${data.count})` : ''}
        </Link>
      </div>
    </div>
  )
}

function NotificationCenterRow({
  notification,
  pending,
  canMarkRead,
  onOpen,
}: {
  notification: Notification
  pending: boolean
  canMarkRead: boolean
  onOpen: () => void
}) {
  const content = (
    <div className={cn('flex items-start gap-2 rounded-lg px-2 py-2.5 transition-colors hover:bg-soft/70 sm:gap-2.5 sm:px-2.5', !notification.read && 'bg-brand-soft/20')}>
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
        {notificationIcon[notification.type]}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-start justify-between gap-2">
          <span className="min-w-0 flex-1 break-words text-[12.5px] font-semibold leading-snug text-ink">{notification.title}</span>
          <span className={cn('shrink-0 text-[10px] font-medium', notification.read ? 'text-muted' : 'text-brand')}>
            {notification.read ? 'Read' : 'Unread'}
          </span>
        </span>
        {notification.message && <span className="mt-0.5 block break-words text-[11.5px] leading-snug text-body">{notification.message}</span>}
        <span className="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 text-[10.5px] text-muted">
          <span className="break-words">{notification.type_label}</span>
          <span aria-hidden>·</span>
          <time dateTime={notification.created_at} className="break-words">
            {format(new Date(notification.created_at), 'MMM d, yyyy h:mm a')}
          </time>
        </span>
        {notification.stage && notification.stage_label && (
          <StageBadge stage={notification.stage} label={notification.stage_label} className="mt-1" />
        )}
      </span>
    </div>
  )

  return (
    <li>
      {notification.link ? (
        <Link to={notification.link} onClick={onOpen} aria-disabled={pending} className="block">
          {content}
        </Link>
      ) : (
        <button type="button" onClick={onOpen} disabled={pending || !canMarkRead} className="w-full text-left">
          {content}
        </button>
      )}
    </li>
  )
}
