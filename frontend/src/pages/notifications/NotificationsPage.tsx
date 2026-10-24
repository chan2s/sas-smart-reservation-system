import { Link } from 'react-router-dom'
import { useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Bell,
  CheckCheck,
  CircleAlert,
  Package,
  Ticket,
  Wrench,
} from 'lucide-react'
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadCount,
} from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { PageHeader, Skeleton, EmptyState } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import type { Notification, NotificationType } from '@/lib/types'

const typeMeta: Record<NotificationType, { icon: React.ReactNode; className: string }> = {
  RESERVATION: { icon: <Ticket className="size-4" />, className: 'bg-brand-soft text-brand' },
  EQUIPMENT: { icon: <Package className="size-4" />, className: 'bg-status-active-bg text-status-active' },
  MAINTENANCE: { icon: <Wrench className="size-4" />, className: 'bg-status-maintenance-bg text-status-maintenance' },
  SYSTEM: { icon: <CircleAlert className="size-4" />, className: 'bg-soft text-body' },
}

export function NotificationsPage() {
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, refetch, isFetching } = useNotifications({ page })
  const { isViewOnly } = useAuth()
  const markAll = useMarkAllNotificationsRead()
  const { data: unreadData } = useUnreadCount()
  const unread = unreadData?.count ?? 0

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="SAS Notifications"
        title="Notifications"
        description="Reservation, facility, equipment, and administrator alert updates."
        actions={
          unread > 0 && !isViewOnly ? (
              <Button variant="outline" size="sm" onClick={() => markAll.mutate()} loading={markAll.isPending} icon={<CheckCheck className="size-4" />}>
              Mark all as read
            </Button>
          ) : undefined
        }
      />

      <Card className="mt-8 p-0" padding="none">
        {isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : isError ? (
          <div className="p-6 text-center">
            <p className="text-sm font-semibold text-status-rejected">Couldn't load notifications</p>
            <p className="mt-1 text-[13px] text-body">The notification service did not return data.</p>
            <Button className="mt-3" variant="outline" size="sm" onClick={() => void refetch()} loading={isFetching}>Retry</Button>
          </div>
        ) : (data?.results ?? []).length === 0 ? (
          <EmptyState
            icon={<Bell className="size-5" />}
            title="You're all caught up"
            description="Notifications about reservations and equipment will appear here."
          />
        ) : (
          <ul className="divide-y divide-line">
            {(data?.results ?? []).map((notification) => (
              <NotificationRow key={`${notification.source ?? 'notification'}-${notification.id}`} notification={notification} />
            ))}
          </ul>
        )}
        {!!data?.count && (
          <div className="flex items-center justify-between border-t border-line px-4 py-3">
            <Button
              variant="outline"
              size="sm"
              disabled={!data.previous || isFetching}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              icon={<ArrowLeft className="size-3.5" />}
            >
              Previous
            </Button>
            <span className="text-xs text-muted">Page {page} of {Math.max(1, Math.ceil(data.count / 20))}</span>
            <Button
              variant="outline"
              size="sm"
              disabled={!data.next || isFetching}
              onClick={() => setPage((value) => value + 1)}
            >
              Next <ArrowRight className="size-3.5" aria-hidden />
            </Button>
          </div>
        )}
      </Card>
    </div>
  )
}

function NotificationRow({ notification }: { notification: Notification }) {
  const { isViewOnly } = useAuth()
  const markRead = useMarkNotificationRead()
  const meta = typeMeta[notification.type] ?? typeMeta.SYSTEM
  const body = (
    <div className={cn('flex w-full items-start gap-4 p-4 sm:p-5', !notification.read && 'bg-brand-soft/30')}>
      <span
        className={cn(
          'mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg',
          meta.className,
        )}
      >
        {meta.icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-semibold text-ink">{notification.title}</p>
          {!notification.read && (
            <span className="mt-1 size-2 shrink-0 rounded-full bg-brand" aria-label="Unread" />
          )}
        </div>
        {notification.message && (
          <p className="mt-0.5 text-[13px] leading-relaxed text-body">{notification.message}</p>
        )}
        <p className="mt-1 text-xs text-muted">{notification.time_ago}</p>
      </div>
    </div>
  )

  const content = notification.link ? (
    <Link
      to={notification.link}
      onClick={() => !notification.read && !isViewOnly && markRead.mutate(notification)}
      className="block transition-colors hover:bg-soft/60"
    >
      {body}
    </Link>
  ) : (
    body
  )

  return <li>{content}</li>
}
