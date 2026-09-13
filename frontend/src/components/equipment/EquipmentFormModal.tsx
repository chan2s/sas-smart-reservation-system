import { useEffect, useRef, useState } from 'react'
import { ImagePlus, Image, Package, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select, Textarea } from '@/components/ui/Form'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { Modal } from '@/components/ui/Modal'
import { getEquipmentImageUrl } from '@/lib/utils'
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

const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_IMAGE_SIZE = 5 * 1024 * 1024 // 5 MB

/** Display-only filename derived from a stored image URL (never an <img src>). */
function filenameFromImageUrl(url: string | null): string | null {
  if (!url) return null
  const last = url.split('?')[0].split('/').filter(Boolean).pop()
  if (!last) return null
  try {
    return decodeURIComponent(last)
  } catch {
    return last
  }
}

/** Why a picked file cannot be used as an equipment image, or null if valid. */
function imageFileError(file: File): string | null {
  if (!ALLOWED_IMAGE_TYPES.includes(file.type) || !/\.(jpe?g|png|webp)$/i.test(file.name)) {
    return 'Please upload a JPG, PNG, or WEBP image smaller than 5 MB.'
  }
  if (file.size > MAX_IMAGE_SIZE) {
    return `Please upload a JPG, PNG, or WEBP image smaller than 5 MB. The selected file is ${(file.size / 1024 / 1024).toFixed(1)} MB.`
  }
  return null
}

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
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // --- Equipment image state -----------------------------------------------
  // These values are kept strictly separate, because each one means something
  // different and they must never stand in for one another:
  //   selectedImageFile         the real File the browser handed us
  //   selectedImagePreviewUrl   the temporary blob: URL for that File
  //   imageLoadState            whether that preview has actually rendered
  //   existingImageUrl          the permanent URL Django returned (derived)
  //   existingImageFilename     display-only text (derived)
  // A filename is display text only — it is never used as an <img src>.
  const [selectedImageFile, setSelectedImageFile] = useState<File | null>(null)
  const [selectedImagePreviewUrl, setSelectedImagePreviewUrl] = useState<string | null>(null)
  const [imageLoadState, setImageLoadState] = useState<
    'idle' | 'loading' | 'loaded' | 'failed'
  >('idle')
  const previewUrlRef = useRef<string | null>(null)

  // Derived from the equipment prop (the authoritative "what the server has"),
  // so they can never drift out of sync with the saved record.
  const existingImageUrl = getEquipmentImageUrl(equipment?.image ?? null)
  const existingImageFilename = filenameFromImageUrl(existingImageUrl)

  /**
   * Point the preview at a real File object, or clear it.
   *
   * The object URL is created synchronously here (before the next render) and
   * the *previous* URL is revoked only once it has been replaced — so the URL
   * currently rendered by the <img> is never revoked out from under it.
   * Anything that is not an actual File (a filename string, undefined, a
   * stale value) means "no image selected".
   */
  function selectImageFile(file: File | null) {
    const next = file instanceof File ? file : null

    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = null
    }
    const nextUrl = next ? URL.createObjectURL(next) : null
    previewUrlRef.current = nextUrl

    setSelectedImageFile(next)
    setSelectedImagePreviewUrl(nextUrl)
    setImageLoadState(next ? 'loading' : 'idle')
  }

  // Reset the form whenever the modal opens (create vs edit vs another item)
  // or closes. A blob URL from a previous edit session is never reused: the
  // selection is dropped and its object URL revoked up front.
  useEffect(() => {
    setValues(initialValues(equipment))
    setError(null)
    selectImageFile(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, equipment?.id])

  // Revoke the live preview URL when this modal component goes away.
  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current)
        previewUrlRef.current = null
      }
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
    // Send the actual File object under the serializer's field name. Nothing
    // is appended when no new image was picked, so Django preserves whatever
    // image is already stored.
    if (selectedImageFile) form.append('image', selectedImageFile)

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
    selectImageFile(null)
  }

  /**
   * Client-side mirror of the backend's authoritative image validation.
   *
   * An invalid pick must never look "selected": the File and its preview URL
   * are cleared and only the validation message is shown.
   */
  function handleImageSelection(file: File | null) {
    setError(null)
    if (!file) {
      selectImageFile(null)
      return
    }
    const problem = imageFileError(file)
    if (problem) {
      selectImageFile(null)
      setError(problem)
      return
    }
    selectImageFile(file)
  }

  const isEditing = equipment != null

  const hasSelectedImage = selectedImageFile != null && selectedImagePreviewUrl != null
  const hasExistingImage = existingImageUrl != null
  const canRemoveImage = isEditing && hasExistingImage && !hasSelectedImage

  // The preview only ever uses a blob URL that belongs to the File selected in
  // this session; otherwise it falls back to the permanent Django URL.
  const currentImageSource = hasSelectedImage ? selectedImagePreviewUrl : existingImageUrl
  const hasImage = currentImageSource != null

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
          hint={
            hasSelectedImage
              ? 'JPG, PNG or WEBP, smaller than 5 MB.'
              : existingImageFilename
                ? `Current image: ${existingImageFilename}`
                : 'Optional photo of the equipment.'
          }
        >
          <div className="flex flex-col gap-3">
            <div className="relative rounded-lg border border-line overflow-hidden bg-soft">
              {hasImage && (
                <EquipmentImage
                  src={currentImageSource}
                  size="preview"
                  className="w-full"
                  alt={values.name || equipment?.name || ''}
                  onLoad={() => setImageLoadState('loaded')}
                  onError={() => setImageLoadState('failed')}
                />
              )}
              {!hasImage && (
                <div className="flex flex-col items-center justify-center gap-2 py-6 text-center">
                  <Package className="size-7 text-muted" aria-hidden />
                  <span className="text-sm text-muted">No image selected</span>
                </div>
              )}
              <div className="absolute right-2 top-2 flex gap-2">
                <label
                  htmlFor="equipment-image"
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
            <label
              htmlFor="equipment-image"
              className={cn(
                'flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-line-strong transition-colors',
                hasImage && 'hover:border-brand hover:bg-brand-soft/40',
              )}
            >
              <ImagePlus className="size-4 text-muted" aria-hidden />
              {selectedImageFile
                ? selectedImageFile.name
                : hasImage
                  ? 'Upload a different image…'
                  : 'Choose an image…'}
              <input
                id="equipment-image"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                onChange={(event) => {
                  // Capture the real File before clearing the input value.
                  handleImageSelection(event.target.files?.[0] ?? null)
                  // Allow re-selecting the same file after a validation error.
                  event.target.value = ''
                }}
              />
            </label>
            {hasSelectedImage && imageLoadState === 'failed' && (
              <p role="alert" className="text-xs text-status-rejected">
                That image could not be previewed. Please choose the file again.
              </p>
            )}
          </div>
        </Field>
      </div>
    </Modal>
  )
}