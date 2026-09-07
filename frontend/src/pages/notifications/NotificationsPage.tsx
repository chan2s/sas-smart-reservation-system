import { Link } from 'react-router-dom'
import {
  Bell,
  CheckCheck,
  CircleAlert,
  Package,
  Ticket,
  Wrench,
} from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { endpoints } from '@/lib/api'
import { useNotifications } from '@/hooks/queries'
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
  const { data, isLoading } = useNotifications()
  const queryClient = useQueryClient()

  const markAll = useMutation({
    mutationFn: () => endpoints.markAllNotificationsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] })
      void queryClient.invalidateQueries({ queryKey: ['unread-count'] })
    },
  })

  const unread = (data?.results ?? []).filter((notification) => !notification.read).length

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="SAS Notifications"
        title="Notifications"
        description="Updates on your reservations and equipment status."
        actions={
          unread > 0 ? (
            <Button variant="outline" size="sm" onClick={() => markAll.mutate()} icon={<CheckCheck className="size-4" />}>
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
        ) : (data?.results ?? []).length === 0 ? (
          <EmptyState
            icon={<Bell className="size-5" />}
            title="You're all caught up"
            description="Notifications about reservations and equipment will appear here."
          />
        ) : (
          <ul className="divide-y divide-line">
            {(data?.results ?? []).map((notification) => (
              <NotificationRow key={notification.id} notification={notification} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function NotificationRow({ notification }: { notification: Notification }) {
  const queryClient = useQueryClient()
  const markRead = useMutation({
    mutationFn: () => endpoints.markNotificationRead(notification.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] })
      void queryClient.invalidateQueries({ queryKey: ['unread-count'] })
    },
  })
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
      onClick={() => !notification.read && markRead.mutate()}
      className="block transition-colors hover:bg-soft/60"
    >
      {body}
    </Link>
  ) : (
    body
  )

  return <li>{content}</li>
}