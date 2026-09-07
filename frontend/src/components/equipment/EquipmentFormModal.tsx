import { useEffect, useState } from 'react'
import { ImagePlus, Image, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select, Textarea } from '@/components/ui/Form'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { Modal } from '@/components/ui/Modal'
import type { Equipment, EquipmentCategory, EquipmentCondition, EquipmentStatus } from '@/lib/types'

export interface EquipmentFormValues {
  name: string
  category_id: number | ''
  description: string
  total_quantity: string
  unit: string
  condition: EquipmentCondition
  status: EquipmentStatus
  storage_location: string
  asset_code: string
  notes: string
}

const CONDITIONS: { value: EquipmentCondition; label: string }[] = [
  { value: 'EXCELLENT', label: 'Excellent' },
  { value: 'GOOD', label: 'Good' },
  { value: 'FAIR', label: 'Fair' },
  { value: 'POOR', label: 'Poor' },
  { value: 'DAMAGED', label: 'Damaged' },
]

const STATUSES: { value: EquipmentStatus; label: string }[] = [
  { value: 'AVAILABLE', label: 'Available' },
  { value: 'MAINTENANCE', label: 'Under Maintenance' },
  { value: 'UNAVAILABLE', label: 'Unavailable' },
  { value: 'RETIRED', label: 'Retired' },
]

function initialValues(equipment: Equipment | null): EquipmentFormValues {
  return {
    name: equipment?.name ?? '',
    category_id: equipment?.category.id ?? '',
    description: equipment?.description ?? '',
    total_quantity: String(equipment?.total_quantity ?? 1),
    unit: equipment?.unit ?? 'unit',
    condition: equipment?.condition ?? 'GOOD',
    status: equipment?.status ?? 'AVAILABLE',
    storage_location: equipment?.storage_location ?? '',
    asset_code: equipment?.asset_code ?? '',
    notes: equipment?.notes ?? '',
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const data = error.data as Record<string, unknown> | null
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      if (data.detail) return String(data.detail)
      // Field errors: pick the first one, e.g. total_quantity.
      const field = Object.values(data)[0]
      if (Array.isArray(field)) return String(field[0])
      if (typeof field === 'string') return field
    }
    return error.message
  }
  return 'Unable to save equipment. Please try again.'
}

export function EquipmentFormModal({
  open,
  onClose,
  equipment,
  categories,
  onSubmit,
}: {
  open: boolean
  onClose: () => void
  /** Existing equipment for edit mode, null to create. */
  equipment: Equipment | null
  categories: EquipmentCategory[]
  /** Resolves on success; rejects with the server error on failure. */
  onSubmit: (payload: FormData) => Promise<unknown>
}) {
  const [values, setValues] = useState<EquipmentFormValues>(() => initialValues(equipment))
  const [image, setImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset the form every time the modal opens (create vs edit vs another item).
  useEffect(() => {
    if (open) {
      setValues(initialValues(equipment))
      setImage(null)
      setPreviewUrl(null)
      setError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, equipment])

  // Keep the object URL in sync with the selected file, and revoke it when it
  // is no longer needed (new selection, modal close, or component unmount).
  useEffect(() => {
    if (!image) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(image)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [image])

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [])

  const set = <K extends keyof EquipmentFormValues>(key: K, value: EquipmentFormValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }))

  async function handleSubmit() {
    setError(null)
    const name = values.name.trim()
    const quantity = Number(values.total_quantity)

    if (!name) {
      setError('Equipment name is required.')
      return
    }
    if (!values.category_id) {
      setError('Please choose a category.')
      return
    }
    if (!Number.isInteger(quantity) || quantity < 1) {
      setError('Total quantity must be a whole number of at least 1.')
      return
    }

    const form = new FormData()
    form.append('name', name)
    form.append('category_id', String(values.category_id))
    form.append('description', values.description)
    form.append('total_quantity', String(quantity))
    form.append('unit', values.unit.trim() || 'unit')
    form.append('condition', values.condition)
    form.append('status', values.status)
    form.append('storage_location', values.storage_location)
    form.append('asset_code', values.asset_code)
    form.append('notes', values.notes)
    if (image) form.append('image', image)

    setSubmitting(true)
    try {
      await onSubmit(form)
      onClose()
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setSubmitting(false)
    }
  }

  function removeImage() {
    setImage(null)
  }

  const isEditing = equipment != null

  const hasExistingImage = Boolean(equipment?.image)
  const hasSelectedImage = image != null
  const hasImage = hasExistingImage || hasSelectedImage
  const canRemoveImage = isEditing && hasExistingImage && !hasSelectedImage

  const currentImageSource = hasSelectedImage
    ? previewUrl
    : equipment?.image ?? null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEditing ? `Edit ${equipment.name}` : 'Add equipment'}
      description={
        isEditing
          ? 'Update the equipment details. Quantity can never drop below what is already reserved or under maintenance.'
          : 'Add a new resource to the campus inventory. It becomes available in reservation flows immediately.'
      }
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={submitting}>
            {isEditing ? 'Save changes' : 'Add Equipment'}
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
        <Field label="Equipment name *" htmlFor="equipment-name" className="sm:col-span-2">
          <Input
            id="equipment-name"
            value={values.name}
            onChange={(event) => set('name', event.target.value)}
            placeholder="e.g. Portable Sound System"
            autoFocus
          />
        </Field>

        <Field label="Category *" htmlFor="equipment-category">
          <Select
            id="equipment-category"
            value={values.category_id}
            onChange={(event) => set('category_id', Number(event.target.value))}
          >
            <option value="">Select a category…</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Condition" htmlFor="equipment-condition">
          <Select
            id="equipment-condition"
            value={values.condition}
            onChange={(event) => set('condition', event.target.value as EquipmentCondition)}
          >
            {CONDITIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Total quantity *" htmlFor="equipment-quantity">
          <Input
            id="equipment-quantity"
            type="number"
            min={1}
            value={values.total_quantity}
            onChange={(event) => set('total_quantity', event.target.value)}
          />
        </Field>

        <Field label="Unit" htmlFor="equipment-unit" hint="e.g. unit, set, pair">
          <Input
            id="equipment-unit"
            value={values.unit}
            onChange={(event) => set('unit', event.target.value)}
          />
        </Field>

        <Field label="Status" htmlFor="equipment-status">
          <Select
            id="equipment-status"
            value={values.status}
            onChange={(event) => set('status', event.target.value as EquipmentStatus)}
          >
            {STATUSES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Asset code" htmlFor="equipment-asset-code">
          <Input
            id="equipment-asset-code"
            value={values.asset_code}
            onChange={(event) => set('asset_code', event.target.value)}
            placeholder="e.g. SAS-AUD-001"
          />
        </Field>

        <Field label="Storage location" htmlFor="equipment-location" className="sm:col-span-2">
          <Input
            id="equipment-location"
            value={values.storage_location}
            onChange={(event) => set('storage_location', event.target.value)}
            placeholder="e.g. SAS Equipment Room A"
          />
        </Field>

        <Field label="Description" htmlFor="equipment-description" className="sm:col-span-2">
          <Textarea
            id="equipment-description"
            value={values.description}
            onChange={(event) => set('description', event.target.value)}
            placeholder="Briefly describe the equipment and what it is used for."
          />
        </Field>

        <Field label="Notes" htmlFor="equipment-notes" className="sm:col-span-2">
          <Textarea
            id="equipment-notes"
            value={values.notes}
            onChange={(event) => set('notes', event.target.value)}
            placeholder="Included accessories, handling instructions, etc."
          />
        </Field>

        <Field
          label="Equipment image"
          htmlFor="equipment-image"
          className="sm:col-span-2"
          hint={hasImage ? 'JPG, PNG or WEBP, smaller than 5 MB.' : 'Optional photo of the equipment.'}
        >
          <div className="flex flex-col gap-3">
            {hasImage ? (
              <div className="relative rounded-lg border border-line overflow-hidden bg-soft">
                <EquipmentImage src={currentImageSource} size="preview" className="w-full" />
                <div className="absolute right-2 top-2 flex gap-2">
                  <label
                    htmlFor="equipment-image-change"
                    className="cursor-pointer inline-flex items-center gap-1.5 rounded-lg bg-soft/90 px-2.5 py-1.5 text-xs font-medium text-body transition-colors hover:bg-soft"
                  >
                    <Image className="size-3.5" aria-hidden />
                    Change
                  </label>
                  {canRemoveImage && (
                    <button
                      type="button"
                      onClick={removeImage}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-body transition-colors hover:bg-soft hover:text-status-rejected"
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                      Remove
                    </button>
                  )}
                </div>
              </div>
            ) : null}
            <label
              htmlFor="equipment-image"
              className={cn(
                'flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-line-strong transition-colors',
                hasImage && 'hover:border-brand hover:bg-brand-soft/40',
              )}
            >
              <ImagePlus className="size-4 text-muted" aria-hidden />
              {image ? image.name : hasImage ? 'Upload a different image…' : 'Choose an image…'}
              <input
                id="equipment-image"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                onChange={(event) => setImage(event.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        </Field>
      </div>
    </Modal>
  )
}