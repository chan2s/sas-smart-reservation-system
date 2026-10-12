import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, Database, Package, RefreshCw, TriangleAlert, Users } from 'lucide-react'
import { PageHeader, EmptyState, Skeleton } from '@/components/ui/Misc'
import { useOffline } from '@/hooks/useOffline'
import {
  useOfflineEquipment,
  useOfflineFacilities,
  useOfflineReservations,
} from '@/hooks/useOfflineData'
import { getEquipmentImageUrl, formatDate, formatDateTime, formatTime } from '@/lib/utils'
import { cn } from '@/lib/utils'

type Tab = 'facilities' | 'equipment' | 'reservations'

const TABS: { id: Tab; label: string; icon: typeof Package }[] = [
  { id: 'facilities', label: 'Facilities', icon: Users },
  { id: 'equipment', label: 'Equipment', icon: Package },
  { id: 'reservations', label: 'My reservations', icon: CalendarDays },
]

/**
 * Saved-information view backed by the IndexedDB backup.
 *
 * Read-only by design: it never shows availability, conflicts, or reservation
 * actions — those require Django. Everything here is clearly labelled as a
 * local backup captured at the last successful sync.
 */
export function OfflinePage() {
  const { online, lastSyncedAt, hasBackup, backupError, retryConnection, checking, syncNow } =
    useOffline()
  const [tab, setTab] = useState<Tab>('facilities')

  const facilities = useOfflineFacilities()
  const equipment = useOfflineEquipment()
  const reservations = useOfflineReservations()

  const activeQuery = tab === 'facilities' ? facilities : tab === 'equipment' ? equipment : reservations
  const loading = activeQuery.isLoading

  return (
    <div>
      <PageHeader
        eyebrow="Offline"
        title="Saved information"
        description="A read-only local backup from your last connection. It may be outdated — Django remains the source of truth for schedules, availability, and approvals."
      />

      {/* Backup status */}
      <div className="mt-6 flex flex-col gap-3 rounded-xl border border-line bg-soft p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface text-body">
            <Database className="size-[18px]" aria-hidden />
          </span>
          <div>
            <p className="text-sm font-semibold text-ink">
              {hasBackup ? 'Local backup available' : 'No saved information yet'}
            </p>
            <p className="mt-0.5 text-xs text-body">
              {hasBackup && lastSyncedAt
                ? `Last updated ${formatDateTime(lastSyncedAt)}`
                : 'Connect to the internet and open the app once to create a backup.'}
            </p>
            {backupError && (
              <p className="mt-1 text-xs text-status-rejected">Last error: {backupError}</p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => (online ? void syncNow() : void retryConnection())}
          disabled={checking}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 self-start rounded-lg border border-line bg-surface px-3.5 text-[13px] font-medium text-ink transition-colors hover:border-line-strong disabled:opacity-60 sm:self-auto"
        >
          <RefreshCw className={checking ? 'size-3.5 animate-spin' : 'size-3.5'} aria-hidden />
          {online ? 'Refresh backup' : 'Retry connection'}
        </button>
      </div>

      {online && (
        <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-status-available/20 bg-status-available-bg p-3 text-[13px] text-body">
          <Database className="mt-0.5 size-4 shrink-0 text-status-available" aria-hidden />
          You are online. Live data is used everywhere else in the app; this page always shows the
          saved backup.
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 flex flex-wrap gap-2">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            aria-pressed={tab === id}
            className={cn(
              'inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-colors',
              tab === id
                ? 'border-brand bg-brand-soft text-brand'
                : 'border-line bg-surface text-body hover:border-line-strong hover:text-ink',
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="mt-5">
        {loading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="card space-y-3 p-5">
                <Skeleton className="h-5 w-1/2" />
                <Skeleton className="h-3 w-4/5" />
                <Skeleton className="h-3 w-2/5" />
              </div>
            ))}
          </div>
        ) : !hasBackup || (activeQuery.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon={<Database className="size-5" />}
            title="Nothing saved for offline use"
            description="This backup fills automatically after you sign in online. Once created, your facilities, equipment, and own reservations appear here when the connection drops."
            action={
              <Link
                to="/dashboard"
                className="inline-flex h-9 items-center rounded-lg bg-brand px-4 text-sm font-medium text-white transition-opacity hover:opacity-90"
              >
                Go to dashboard
              </Link>
            }
          />
        ) : (
          <>
            <p className="mb-3 flex items-center gap-2 text-xs text-muted">
              <TriangleAlert className="size-3.5" aria-hidden /> Local backup — may be outdated.
            </p>
            {tab === 'facilities' && <FacilitiesList items={facilities.data ?? []} online={online} />}
            {tab === 'equipment' && <EquipmentList items={equipment.data ?? []} online={online} />}
            {tab === 'reservations' && (
              <ReservationsList items={reservations.data ?? []} online={online} />
            )}
          </>
        )}
      </div>
    </div>
  )
}

function FacilitiesList({
  items,
  online,
}: {
  items: { id: number; name: string; facility_type_label: string; description: string; capacity: number; location: string; image: string | null; status_label: string; is_active: boolean }[]
  online: boolean
}) {
  return (
    <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((facility) => {
        const image = getEquipmentImageUrl(facility.image)
        const body = (
          <article className="card card-hover flex h-full flex-col p-5">
            {image && (
              <img
                src={image}
                alt=""
                loading="lazy"
                className="mb-4 h-32 w-full rounded-lg object-cover"
              />
            )}
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-base font-semibold text-ink">{facility.name}</h3>
              {!facility.is_active && (
                <span className="shrink-0 rounded-full bg-soft px-2 py-0.5 text-[11px] font-medium text-muted">
                  Archived
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-muted">
              {facility.facility_type_label} · {facility.status_label}
            </p>
            <p className="mt-2 line-clamp-2 text-sm text-body">{facility.description}</p>
            <p className="mt-3 text-[13px] text-body">
              {facility.capacity} capacity · {facility.location}
            </p>
          </article>
        )
        return (
          <li key={facility.id}>
            {online ? (
              <Link to={`/facilities/${facility.id}`} className="focus-ring block h-full rounded-card">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        )
      })}
    </ul>
  )
}

function EquipmentList({
  items,
  online,
}: {
  items: { id: number; name: string; category_name: string; total_quantity: number; unit: string; condition_label: string; status_label: string; storage_location: string; image: string | null }[]
  online: boolean
}) {
  return (
    <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => {
        const image = getEquipmentImageUrl(item.image)
        const body = (
          <article className="card card-hover flex h-full items-start gap-4 p-4">
            {image ? (
              <img src={image} alt="" loading="lazy" className="size-14 shrink-0 rounded-full object-cover" />
            ) : (
              <span className="flex size-14 shrink-0 items-center justify-center rounded-full bg-soft text-muted">
                <Package className="size-5" aria-hidden />
              </span>
            )}
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-ink">{item.name}</h3>
              <p className="mt-0.5 text-xs text-muted">{item.category_name}</p>
              <p className="mt-2 text-[13px] text-body">
                {item.total_quantity} {item.unit} · {item.condition_label}
              </p>
              <p className="text-[13px] text-body">{item.status_label}</p>
              {item.storage_location && (
                <p className="mt-0.5 truncate text-xs text-muted">{item.storage_location}</p>
              )}
            </div>
          </article>
        )
        return (
          <li key={item.id}>
            {online ? (
              <Link to={`/equipment/${item.id}`} className="focus-ring block h-full rounded-card">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        )
      })}
    </ul>
  )
}

function ReservationsList({
  items,
  online,
}: {
  items: { id: number; reservation_id: string; event_name: string; facility: string; date: string; start_time: string; end_time: string; status_label: string }[]
  online: boolean
}) {
  return (
    <ul className="space-y-3">
      {items.map((reservation) => {
        const body = (
          <article className="card flex flex-col gap-1 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{reservation.event_name}</p>
              <p className="mt-0.5 text-xs text-muted">
                {reservation.reservation_id} · {reservation.facility}
              </p>
            </div>
            <div className="text-[13px] text-body sm:text-right">
              <p>
                {formatDate(reservation.date)} · {formatTime(reservation.start_time)}–
                {formatTime(reservation.end_time)}
              </p>
              <p className="text-xs text-muted">{reservation.status_label}</p>
            </div>
          </article>
        )
        return (
          <li key={reservation.id}>
            {online ? (
              <Link to={`/reservations/${reservation.id}`} className="focus-ring block rounded-card">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        )
      })}
    </ul>
  )
}
