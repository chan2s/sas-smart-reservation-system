import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import {
  ArrowRight,
  Archive,
  CalendarDays,
  MapPin,
  MoreHorizontal,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  TriangleAlert,
  Users,
} from 'lucide-react'
import {
  useCreateFacility,
  useFacilities,
  useSaveFacilityGallery,
  useUpdateFacility,
} from '@/hooks/queries'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/components/ui/Toast'
import { PageHeader, Skeleton, EmptyState } from '@/components/ui/Misc'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Form'
import { Dropdown, MenuItem } from '@/components/ui/Dropdown'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import { FacilityFormModal } from '@/components/facilities/FacilityFormModal'
import { RemoveFacilityModal } from '@/components/facilities/RemoveFacilityModal'
import { Badge } from '@/components/ui/Badge'
import { Backdrop } from '@/components/decor/Backdrop'
import { cn, facilityPrimaryImageUrl, formatTime } from '@/lib/utils'
import type { Facility } from '@/lib/types'

const nextSevenDays = Array.from({ length: 7 }, (_, index) => {
  const date = new Date(Date.now() + index * 86400_000)
  return date.toISOString().slice(0, 10)
})

/**
 * The facility catalogue — and, for SAS staff, the facility management
 * interface (add / edit / enable / disable / archive) wired straight to the
 * Django API. Requesters see the same read-only layout without the controls.
 */
export function FacilitiesPage() {
  const { isStaff } = useAuth()
  const { toast } = useToast()

  const [selected, setSelected] = useState<string>('')
  const [search, setSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  // Add / edit form, and remove (archive or delete) confirmation.
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Facility | null>(null)
  const [removing, setRemoving] = useState<Facility | null>(null)

  // Archived facilities are staff-only; opt in to fetch them explicitly.
  const { data, isLoading, isError, refetch } = useFacilities(
    isStaff && showArchived ? { include_inactive: 'true' } : undefined,
  )

  const createFacility = useCreateFacility()
  const updateFacility = useUpdateFacility(editing?.id ?? 0)
  const saveGallery = useSaveFacilityGallery()

  const facilities = data ?? []

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return facilities.filter((facility) => {
      const archived = !facility.is_active
      if (showArchived !== archived) return false
      if (selected && facility.facility_type !== selected) return false
      if (
        query &&
        !(
          facility.name.toLowerCase().includes(query) ||
          facility.location.toLowerCase().includes(query) ||
          facility.description.toLowerCase().includes(query)
        )
      )
        return false
      return true
    })
  }, [facilities, selected, search, showArchived])

  const typeOptions = useMemo(
    () => [...new Set(facilities.map((facility) => facility.facility_type))],
    [facilities],
  )

  function openAdd() {
    setEditing(null)
    setFormOpen(true)
  }

  function openEdit(facility: Facility) {
    setEditing(facility)
    setFormOpen(true)
  }

  return (
    <div className="relative">
      <Backdrop />

      <PageHeader
        eyebrow="SAS Facilities"
        title="Facilities"
        description={
          isStaff
            ? 'Add, edit, and manage the spaces available for reservation.'
            : 'Find and reserve the right space for your next event.'
        }
        actions={
          isStaff ? (
            <Button icon={<Plus className="size-4" />} onClick={openAdd}>
              Add Facility
            </Button>
          ) : undefined
        }
      />

      {/* Search + type filter */}
      <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative lg:max-w-sm lg:flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            type="search"
            placeholder="Search facilities, location…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9"
            aria-label="Search facilities"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip label="All facilities" active={selected === ''} onClick={() => setSelected('')} />
          {typeOptions.map((type) => (
            <FilterChip
              key={type}
              label={facilityTypeLabel(type)}
              active={selected === type}
              onClick={() => setSelected(type)}
            />
          ))}
        </div>
        {isStaff && (
          <button
            type="button"
            onClick={() => setShowArchived((value) => !value)}
            aria-pressed={showArchived}
            className={cn(
              'ml-auto inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-1.5 text-sm font-medium transition-colors lg:shrink-0',
              showArchived
                ? 'border-line-strong bg-soft text-ink'
                : 'border-line bg-surface text-body hover:border-line-strong hover:text-ink',
            )}
          >
            <Archive className="size-3.5" aria-hidden />
            {showArchived ? 'Viewing archived' : 'View archived'}
          </button>
        )}
      </div>

      {/* Cards */}
      <div className="mt-6 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="card overflow-hidden">
              <Skeleton className="h-48 rounded-none" />
              <div className="space-y-3 p-5">
                <Skeleton className="h-5 w-1/2" />
                <Skeleton className="h-3 w-4/5" />
                <Skeleton className="h-10 w-full" />
              </div>
            </div>
          ))}

        {filtered.map((facility) => (
          <FacilityCard
            key={facility.id}
            facility={facility}
            isStaff={isStaff}
            onEdit={() => openEdit(facility)}
            onRemove={() => setRemoving(facility)}
          />
        ))}
      </div>

      {isError && (
        <div className="card mt-6 flex flex-col items-center gap-3 p-10 text-center">
          <p className="text-sm text-status-rejected">
            We could not load the facilities. Please try again.
          </p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <EmptyState
          title={
            showArchived
              ? 'No archived facilities'
              : search || selected
                ? 'No facilities match this filter'
                : 'No facilities yet'
          }
          description={
            isStaff && !showArchived && !search && !selected
              ? 'Add your first facility so requesters can reserve it.'
              : showArchived
                ? 'Facilities you archive will appear here and can be restored.'
                : 'Try adjusting your search or filter.'
          }
          action={
            isStaff && !showArchived && !search && !selected ? (
              <Button size="sm" icon={<Plus className="size-4" />} onClick={openAdd}>
                Add Facility
              </Button>
            ) : undefined
          }
        />
      )}

      {/* Add / edit modal */}
      <FacilityFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        facility={editing}
        onSubmit={(payload) => {
          if (editing) {
            return updateFacility.mutateAsync(payload).then((saved) => {
              toast(`${editing.name} updated.`)
              return saved
            })
          }
          return createFacility.mutateAsync(payload).then((saved) => {
            toast('Facility added and available for reservations.')
            return saved
          })
        }}
        onSaveGallery={(id, change) => saveGallery(id, change)}
      />

      {/* Remove modal */}
      {removing && (
        <RemoveFacilityModal facility={removing} onClose={() => setRemoving(null)} />
      )}
    </div>
  )
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-lg border px-3.5 py-1.5 text-sm font-medium transition-colors duration-150',
        active
          ? 'border-brand bg-brand-soft text-brand'
          : 'border-line bg-surface text-body hover:border-line-strong hover:text-ink',
      )}
    >
      {label}
    </button>
  )
}

function facilityTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    GYMNASIUM: 'Gymnasium',
    CAFETERIA: 'Cafeteria',
    AVR: 'Audio-Visual Room',
    MULTI_PURPOSE: 'Multi-Purpose Hall',
    OUTDOOR: 'Outdoor',
    OTHER: 'Other',
  }
  return labels[type] ?? type
}

function FacilityCard({
  facility,
  isStaff,
  onEdit,
  onRemove,
}: {
  facility: Facility
  isStaff: boolean
  onEdit: () => void
  onRemove: () => void
}) {
  const { toast } = useToast()
  const updateFacility = useUpdateFacility(facility.id)

  const archived = !facility.is_active
  const availability = facility.availability
  const maintenance = facility.status === 'MAINTENANCE'

  function toggleActive() {
    const next = !facility.is_active
    updateFacility.mutate(
      { is_active: next },
      {
        onSuccess: () =>
          toast(
            next
              ? `${facility.name} re-enabled for reservations.`
              : `${facility.name} disabled. It is hidden from new reservations.`,
          ),
        onError: () => toast('Unable to update this facility.', 'error'),
      },
    )
  }

  return (
    <article
      className={cn('card card-hover flex flex-col overflow-hidden', archived && 'opacity-70')}
    >
      <div className="relative h-48">
        <FacilityImage
          name={facility.name}
          facilityType={facility.facility_type}
          src={facilityPrimaryImageUrl(facility)}
          rounded="rounded-none"
        />
        <div className="absolute left-4 top-4 flex flex-wrap gap-2">
          {archived ? (
            <Badge tone="gray">Archived</Badge>
          ) : maintenance ? (
            <Badge tone="orange">Under maintenance</Badge>
          ) : (
            <Badge tone="emerald">Available</Badge>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-ink">{facility.name}</h2>
          {isStaff && (
            <Dropdown
              trigger={
                <span className="flex size-8 items-center justify-center rounded-lg border border-line text-body transition-colors hover:bg-soft hover:text-ink">
                  <MoreHorizontal className="size-4" aria-label={`More actions for ${facility.name}`} />
                </span>
              }
            >
              {(close) => (
                <>
                  <MenuItem onClick={() => { close(); onEdit() }}>
                    <Pencil className="size-4 text-muted" /> Edit facility
                  </MenuItem>
                  <MenuItem onClick={() => { close(); toggleActive() }}>
                    {archived ? (
                      <>
                        <RotateCcw className="size-4 text-muted" /> Enable for reservations
                      </>
                    ) : (
                      <>
                        <Archive className="size-4 text-muted" /> Disable
                      </>
                    )}
                  </MenuItem>
                  <MenuItem danger onClick={() => { close(); onRemove() }}>
                    <TriangleAlert className="size-4" /> Archive / Delete
                  </MenuItem>
                </>
              )}
            </Dropdown>
          )}
        </div>
        <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-body">
          {facility.description}
        </p>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
          <div className="flex items-center gap-2 text-body">
            <Users className="size-4 text-muted" aria-hidden />
            <span>
              <span className="font-medium text-ink">{facility.capacity}</span> capacity
            </span>
          </div>
          <div className="flex items-center gap-2 text-body">
            <MapPin className="size-4 text-muted" aria-hidden />
            <span className="truncate">{facility.location}</span>
          </div>
        </dl>

        <div className="mt-4 flex items-center gap-2 rounded-lg bg-soft px-3 py-2.5 text-[13px] text-body">
          <CalendarDays className="size-4 shrink-0 text-muted" aria-hidden />
          {archived ? (
            <span>Archived — not available for reservations</span>
          ) : maintenance ? (
            <span>Reservations paused during maintenance</span>
          ) : (
            <span>
              Next available —{' '}
              <span className="font-medium text-ink">{nextAvailableLabel(facility)}</span>
            </span>
          )}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
          <div className="flex items-center gap-3">
            <Link
              to={`/facilities/${facility.id}`}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-brand transition-colors hover:text-brand-dark"
            >
              View facility <ArrowRight className="size-4" />
            </Link>
            {isStaff && (
              <Link
                to={`/facilities/${facility.id}/resources`}
                title="Manage equipment"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
              >
                <Settings2 className="size-3.5" /> Manage equipment
              </Link>
            )}
          </div>
          {!archived && availability.is_operational && (
            <span className="flex items-center gap-1.5 text-xs text-status-available">
              <span className="size-1.5 rounded-full bg-status-available" aria-hidden />
              Open for reservations
            </span>
          )}
        </div>
      </div>
    </article>
  )
}

function nextAvailableLabel(facility: Facility): string {
  const date = new Date()
  const dayOfWeek = date.getDay() // 0 = Sunday
  const todayIndex = dayOfWeek === 0 ? 6 : dayOfWeek - 1

  // Look for an operating day at or after today; fall back to Monday.
  for (const offset of nextSevenDays) {
    const candidate = new Date(`${offset}T00:00:00`)
    const index = candidate.getDay() === 0 ? 6 : candidate.getDay() - 1
    if (index < todayIndex) continue
    const hours = facility.operating_hours?.find((hour) => hour.day_of_week === index)
    if (hours && !hours.is_closed) {
      const label = format(new Date(`${offset}T00:00:00`), 'EEE, MMM d')
      return hours.open_time ? `${label} · ${formatTime(hours.open_time)}` : label
    }
  }
  return 'Check operating hours'
}
