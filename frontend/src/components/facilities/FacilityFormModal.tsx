import { useEffect, useState } from 'react'
import { ApiError, type GalleryChange } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select, Textarea } from '@/components/ui/Form'
import { Modal } from '@/components/ui/Modal'
import {
  EMPTY_GALLERY_STATE,
  ImageGalleryManager,
  type GalleryState,
} from '@/components/ui/ImageGalleryManager'
import type {
  Facility,
  FacilityStatus,
  FacilityType,
  SeatingType,
} from '@/lib/types'

export interface FacilityFormValues {
  name: string
  facility_type: FacilityType
  description: string
  capacity: string
  location: string
  status: FacilityStatus
  is_active: boolean
  /** Multi-line guidelines, one per line. */
  rules: string
  /** Comma-separated built-in amenities (drives the wizard's suggestions). */
  built_ins: string
  seating_type: SeatingType | ''
  built_in_seats: string
}

const FACILITY_TYPES: { value: FacilityType; label: string }[] = [
  { value: 'GYMNASIUM', label: 'Gymnasium' },
  { value: 'CAFETERIA', label: 'Cafeteria' },
  { value: 'AVR', label: 'Audio-Visual Room' },
  { value: 'MULTI_PURPOSE', label: 'Multi-Purpose Hall' },
  { value: 'OUTDOOR', label: 'Outdoor Area' },
  { value: 'OTHER', label: 'Other' },
]

// Available / Unavailable are the enabled flag; Maintenance is the operational
// status. Together they express every state the admin can set.
const STATUSES: { value: FacilityStatus; label: string }[] = [
  { value: 'OPERATIONAL', label: 'Available' },
  { value: 'MAINTENANCE', label: 'Under Maintenance' },
]

const SEATING_TYPES: { value: SeatingType; label: string }[] = [
  { value: 'tables_and_chairs', label: 'Tables and chairs' },
  { value: 'fixed_rows', label: 'Fixed rows' },
  { value: 'open_floor', label: 'Open floor' },
]

function initialValues(facility: Facility | null): FacilityFormValues {
  return {
    name: facility?.name ?? '',
    facility_type: facility?.facility_type ?? 'OTHER',
    description: facility?.description ?? '',
    capacity: String(facility?.capacity ?? 0),
    location: facility?.location ?? '',
    status: facility?.status ?? 'OPERATIONAL',
    is_active: facility?.is_active ?? true,
    rules: (facility?.rules ?? []).join('\n'),
    built_ins: (facility?.built_ins ?? []).join(', '),
    seating_type: facility?.seating_type ?? '',
    built_in_seats:
      facility?.built_in_seats != null ? String(facility.built_in_seats) : '',
  }
}

function splitTokens(value: string): string[] {
  return value
    .split(',')
    .map((token) => token.trim())
    .filter(Boolean)
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const data = error.data as Record<string, unknown> | null
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      if (typeof data.detail === 'string') return data.detail
      // Field errors: pick the first one, e.g. name.
      const field = Object.values(data)[0]
      if (Array.isArray(field)) return String(field[0])
      if (typeof field === 'string') return field
    }
    return error.message
  }
  return 'Unable to save the facility. Please try again.'
}

export function FacilityFormModal({
  open,
  onClose,
  facility,
  onSubmit,
  onSaveGallery,
}: {
  open: boolean
  onClose: () => void
  /** Existing facility for edit mode, null to create. */
  facility: Facility | null
  /** Saves the facility fields and resolves with the saved record. */
  onSubmit: (payload: FormData) => Promise<Facility>
  /** Applies image gallery edits once the facility has an id. */
  onSaveGallery: (facilityId: number, change: GalleryChange) => Promise<void>
}) {
  const [values, setValues] = useState<FacilityFormValues>(() => initialValues(facility))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [gallery, setGallery] = useState<GalleryState>(EMPTY_GALLERY_STATE)

  // Remounting the manager per edit session drops stale selections and revokes
  // its preview blob URLs (its unmount cleanup).
  const galleryKey = `${open ? 'open' : 'closed'}-${facility?.id ?? 'new'}`

  useEffect(() => {
    setValues(initialValues(facility))
    setError(null)
    setGallery(EMPTY_GALLERY_STATE)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, facility?.id])

  const set = <K extends keyof FacilityFormValues>(key: K, value: FacilityFormValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }))

  async function handleSubmit() {
    setError(null)
    const name = values.name.trim()
    const capacity = Number(values.capacity)

    if (!name) {
      setError('Facility name is required.')
      return
    }
    if (!Number.isInteger(capacity) || capacity < 0) {
      setError('Capacity must be a whole number of at least 0.')
      return
    }
    if (values.built_in_seats !== '') {
      const seats = Number(values.built_in_seats)
      if (!Number.isInteger(seats) || seats < 0) {
        setError('Built-in seats must be a whole number of at least 0.')
        return
      }
    }

    const rules = values.rules
      .split('\n')
      .map((rule) => rule.trim())
      .filter(Boolean)

    const form = new FormData()
    form.append('name', name)
    form.append('facility_type', values.facility_type)
    form.append('description', values.description)
    form.append('capacity', String(capacity))
    form.append('location', values.location)
    form.append('status', values.status)
    form.append('is_active', String(values.is_active))
    form.append('rules', JSON.stringify(rules))
    form.append('built_ins', JSON.stringify(splitTokens(values.built_ins)))
    if (values.seating_type) form.append('seating_type', values.seating_type)
    if (values.built_in_seats !== '') {
      form.append('built_in_seats', String(Number(values.built_in_seats)))
    }
    // No image field here: the gallery is saved through its own endpoints, so
    // omitting it preserves stored images on a plain field edit.

    setSubmitting(true)
    try {
      const saved = await onSubmit(form)
      await onSaveGallery(saved.id, gallery.change)
      onClose()
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setSubmitting(false)
    }
  }

  const isEditing = facility != null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEditing ? `Edit ${facility.name}` : 'Add facility'}
      description={
        isEditing
          ? 'Update the facility details. Disabling it hides it from new reservations without deleting history.'
          : 'Add a new space. It becomes available for reservations immediately.'
      }
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={submitting}>
            {isEditing ? 'Save changes' : 'Add Facility'}
          </Button>
        </>
      }
    >
      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-status-rejected/25 bg-status-rejected-bg px-3.5 py-2.5 text-sm text-status-rejected"
        >
          {error}
        </p>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Facility name *" htmlFor="facility-name" className="sm:col-span-2">
          <Input
            id="facility-name"
            value={values.name}
            onChange={(event) => set('name', event.target.value)}
            placeholder="e.g. Gymnasium"
            autoFocus
          />
        </Field>

        <Field label="Facility type" htmlFor="facility-type">
          <Select
            id="facility-type"
            value={values.facility_type}
            onChange={(event) => set('facility_type', event.target.value as FacilityType)}
          >
            {FACILITY_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Capacity" htmlFor="facility-capacity" hint="Maximum number of people.">
          <Input
            id="facility-capacity"
            type="number"
            min={0}
            value={values.capacity}
            onChange={(event) => set('capacity', event.target.value)}
          />
        </Field>

        <Field label="Location / details" htmlFor="facility-location" className="sm:col-span-2">
          <Input
            id="facility-location"
            value={values.location}
            onChange={(event) => set('location', event.target.value)}
            placeholder="e.g. 2nd Floor, Admin Building"
          />
        </Field>

        <Field label="Status" htmlFor="facility-status">
          <Select
            id="facility-status"
            value={values.status}
            onChange={(event) => set('status', event.target.value as FacilityStatus)}
          >
            {STATUSES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Reservations"
          htmlFor="facility-active"
          hint="Disabled facilities cannot be reserved, but keep their records."
        >
          <label className="flex h-10 items-center gap-2 rounded-lg border border-line px-3 text-sm text-ink">
            <input
              id="facility-active"
              type="checkbox"
              className="size-4 accent-[var(--color-brand)]"
              checked={values.is_active}
              onChange={(event) => set('is_active', event.target.checked)}
            />
            {values.is_active ? 'Enabled — open for reservations' : 'Disabled — hidden'}
          </label>
        </Field>

        <Field label="Seating type" htmlFor="facility-seating" hint="Optional. Leave blank when unverified.">
          <Select
            id="facility-seating"
            value={values.seating_type}
            onChange={(event) => set('seating_type', event.target.value as SeatingType | '')}
          >
            <option value="">Not verified</option>
            {SEATING_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Built-in seats"
          htmlFor="facility-built-in-seats"
          hint="Seats the space already provides."
        >
          <Input
            id="facility-built-in-seats"
            type="number"
            min={0}
            value={values.built_in_seats}
            onChange={(event) => set('built_in_seats', event.target.value)}
            placeholder="Optional"
          />
        </Field>

        <Field
          label="Built-in amenities"
          htmlFor="facility-built-ins"
          className="sm:col-span-2"
          hint="Comma-separated, e.g. tables, chairs, projector, sound_system. These are not suggested as extra equipment."
        >
          <Input
            id="facility-built-ins"
            value={values.built_ins}
            onChange={(event) => set('built_ins', event.target.value)}
            placeholder="tables, chairs, sound_system"
          />
        </Field>

        <Field label="Description" htmlFor="facility-description" className="sm:col-span-2">
          <Textarea
            id="facility-description"
            value={values.description}
            onChange={(event) => set('description', event.target.value)}
            placeholder="Describe the space and what it is used for."
          />
        </Field>

        <Field
          label="Rules & guidelines"
          htmlFor="facility-rules"
          className="sm:col-span-2"
          hint="One rule per line."
        >
          <Textarea
            id="facility-rules"
            rows={3}
            value={values.rules}
            onChange={(event) => set('rules', event.target.value)}
            placeholder={'No food or drinks inside.\nClean up after use.'}
          />
        </Field>

        <Field
          label="Facility images"
          htmlFor="facility-images"
          className="sm:col-span-2"
          hint="The first image (or the one marked primary) is used everywhere else in the app."
        >
          <ImageGalleryManager
            key={galleryKey}
            inputId="facility-images"
            existingImages={facility?.images ?? []}
            entityName={values.name || facility?.name || 'Facility'}
            disabled={submitting}
            onChange={setGallery}
          />
        </Field>
      </div>
    </Modal>
  )
}
