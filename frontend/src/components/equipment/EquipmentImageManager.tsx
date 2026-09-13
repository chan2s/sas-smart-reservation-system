import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, ImagePlus, Star, Trash2, Undo2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import { EMPTY_GALLERY_CHANGE, type EquipmentGalleryChange, type EquipmentImageRef } from '@/lib/api'
import type { EquipmentImage as EquipmentImageData } from '@/lib/types'

const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_IMAGE_SIZE = 5 * 1024 * 1024 // 5 MB

/** What the manager reports back to the form on every change. */
export interface EquipmentGalleryState {
  /** The exact change set to apply after the equipment itself is saved. */
  change: EquipmentGalleryChange
  /** Image-level validation message, if the last selection was rejected. */
  error: string | null
  /** How many images the item will have once saved. */
  count: number
}

export const EMPTY_GALLERY_STATE: EquipmentGalleryState = {
  change: EMPTY_GALLERY_CHANGE,
  error: null,
  count: 0,
}

/**
 * An entry in the manager's list.
 *
 * A selected file is always a real `File` plus its own blob URL — a filename
 * string is never used as an image source. Saved images keep their permanent
 * API URL and an id so the gallery endpoints can act on them.
 */
type Entry =
  | {
      key: string
      kind: 'existing'
      id: number
      url: string
      removed: boolean
    }
  | { key: string; kind: 'new'; file: File; previewUrl: string }

/** Display-only filename for a stored image URL (never used as a src). */
function fileNameFromUrl(url: string): string {
  const last = url.split('?')[0].split('/').filter(Boolean).pop() ?? ''
  try {
    return decodeURIComponent(last)
  } catch {
    return last
  }
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/** Why a picked file cannot be used, or null when it is valid. */
function imageFileError(file: File): string | null {
  if (!ALLOWED_IMAGE_TYPES.includes(file.type) || !/\.(jpe?g|png|webp)$/i.test(file.name)) {
    return 'must be a JPG, PNG, or WEBP image.'
  }
  if (file.size > MAX_IMAGE_SIZE) {
    return `is ${formatFileSize(file.size)} — images must be smaller than 5 MB.`
  }
  return null
}

function initialEntries(images: EquipmentImageData[]): Entry[] {
  return images.map((image, index) => ({
    key: image.id != null ? `existing-${image.id}` : `legacy-${index}`,
    kind: 'existing',
    // A legacy image has no gallery row, so it is display-only here.
    id: image.id ?? -1,
    url: image.url,
    removed: false,
  }))
}

function initialPrimaryKey(images: EquipmentImageData[]): string | null {
  const primary = images.find((image) => image.is_primary)
  if (!primary) return null
  const index = images.indexOf(primary)
  return primary.id != null ? `existing-${primary.id}` : `legacy-${index}`
}

/**
 * Multi-image editor for an equipment item.
 *
 * Shows the saved gallery plus the files the admin just picked (with their
 * filename and size), and lets them remove, reorder, and choose the primary
 * image — all before anything is sent to the server. It reports a single change
 * set upward; the modal applies it after the equipment itself saves.
 */
export function EquipmentImageManager({
  existingImages,
  equipmentName,
  disabled = false,
  onChange,
}: {
  existingImages: EquipmentImageData[]
  equipmentName: string
  disabled?: boolean
  /** Stable callback (pass a setState function) invoked on every change. */
  onChange: (state: EquipmentGalleryState) => void
}) {
  const [entries, setEntries] = useState<Entry[]>(() => initialEntries(existingImages))
  const [primaryKey, setPrimaryKey] = useState<string | null>(() =>
    initialPrimaryKey(existingImages),
  )
  const [error, setError] = useState<string | null>(null)

  // Every blob URL this component created, revoked on removal and unmount.
  const liveUrlsRef = useRef<Set<string>>(new Set())
  const keyCounterRef = useRef(0)

  useEffect(() => {
    const live = liveUrlsRef.current
    return () => {
      for (const url of live) URL.revokeObjectURL(url)
      live.clear()
    }
  }, [])

  const originalPrimaryId = existingImages.find((image) => image.is_primary)?.id ?? null

  const survivors = entries.filter((entry) => entry.kind === 'new' || !entry.removed)

  // New files are uploaded in list order, so their index in `files` is exactly
  // the fileIndex the save hook resolves back to a gallery id.
  const files = survivors
    .filter((entry): entry is Extract<Entry, { kind: 'new' }> => entry.kind === 'new')
    .map((entry) => entry.file)

  // A legacy image (id <= 0) has no gallery row, so it cannot be part of an
  // order or become primary — it is display-only until the gallery takes over.
  let fileCursor = 0
  const resolvedOrder: EquipmentImageRef[] = []
  for (const entry of survivors) {
    if (entry.kind === 'new') resolvedOrder.push({ fileIndex: fileCursor++ })
    else if (entry.id > 0) resolvedOrder.push({ id: entry.id })
  }

  const deleteIds = entries
    .filter((entry): entry is Extract<Entry, { kind: 'existing' }> => entry.kind === 'existing')
    .filter((entry) => entry.removed && entry.id > 0)
    .map((entry) => entry.id)

  let primaryCursor = 0
  let primary: EquipmentImageRef | null = null
  for (const entry of survivors) {
    if (entry.kind === 'new') {
      if (entry.key === primaryKey) primary = { fileIndex: primaryCursor }
      primaryCursor += 1
    } else if (entry.key === primaryKey && entry.id > 0) {
      primary = { id: entry.id }
    }
  }

  // Only send the order when the admin actually moved something: otherwise the
  // backend's natural order (surviving saved images, then the new files) is
  // already correct.
  const naturalOrder: EquipmentImageRef[] = [
    ...survivors
      .filter(
        (entry): entry is Extract<Entry, { kind: 'existing' }> =>
          entry.kind === 'existing' && entry.id > 0,
      )
      .map((entry) => ({ id: entry.id })),
    ...files.map((_, index) => ({ fileIndex: index })),
  ]
  const orderChanged =
    JSON.stringify(resolvedOrder) !== JSON.stringify(naturalOrder)

  const primaryChanged =
    primary == null ? false : 'id' in primary ? primary.id !== originalPrimaryId : true

  const change: EquipmentGalleryChange = {
    files,
    deleteIds,
    order: orderChanged ? resolvedOrder : [],
    primary: primaryChanged ? primary : null,
  }

  // Publish upward. `onChange` is the parent's setState, so it is stable.
  useEffect(() => {
    onChange({ change, error, count: survivors.length })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries, primaryKey, error])

  function addFiles(selectedFiles: File[]) {
    setError(null)

    const accepted: File[] = []
    const problems: string[] = []
    for (const file of selectedFiles) {
      // A real File is required — anything else (a filename string, a stale
      // value) is ignored rather than treated as an image.
      if (!(file instanceof File)) continue
      const problem = imageFileError(file)
      if (problem) problems.push(`${file.name} ${problem}`)
      else accepted.push(file)
    }

    if (accepted.length > 0) {
      const created: Entry[] = accepted.map((file) => {
        const previewUrl = URL.createObjectURL(file)
        liveUrlsRef.current.add(previewUrl)
        keyCounterRef.current += 1
        return { key: `new-${keyCounterRef.current}`, kind: 'new', file, previewUrl }
      })

      const hasSurvivor = entries.some((entry) => entry.kind === 'new' || !entry.removed)
      if (!hasSurvivor) setPrimaryKey(created[0].key)
      setEntries([...entries, ...created])
    }

    if (problems.length > 0) setError(problems.join(' '))
  }

  function removeEntry(entry: Entry) {
    if (entry.kind === 'new') {
      URL.revokeObjectURL(entry.previewUrl)
      liveUrlsRef.current.delete(entry.previewUrl)
      setEntries((current) => current.filter((item) => item.key !== entry.key))
      if (primaryKey === entry.key) setPrimaryKey(null)
      return
    }
    // Saved images are deleted on save, not now — the admin can undo.
    setEntries((current) =>
      current.map((item) =>
        item.key === entry.key && item.kind === 'existing'
          ? { ...item, removed: !item.removed }
          : item,
      ),
    )
  }

  function moveEntry(key: string, direction: -1 | 1) {
    setEntries((current) => {
      const movable = current.filter((entry) => entry.kind === 'new' || !entry.removed)
      const index = movable.findIndex((entry) => entry.key === key)
      const target = index + direction
      if (index === -1 || target < 0 || target >= movable.length) return current
      const reordered = [...movable]
      ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
      // Removed entries stay at the end until they are undone or saved.
      const removed = current.filter(
        (entry) => entry.kind === 'existing' && entry.removed,
      )
      return [...reordered, ...removed]
    })
  }

  return (
    <div className="space-y-3">
      <label
        htmlFor="equipment-images"
        className={cn(
          'flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-line-strong px-3.5 py-3 transition-colors',
          !disabled && 'hover:border-brand hover:bg-brand-soft/40',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        <ImagePlus className="size-4 shrink-0 text-muted" aria-hidden />
        <span className="min-w-0">
          <span className="block text-sm font-medium text-body">
            {survivors.length > 0 ? 'Add more images…' : 'Choose images…'}
          </span>
          <span className="block text-xs text-muted">
            JPG, PNG or WEBP, up to 5 MB each. Select several at once.
          </span>
        </span>
        <input
          id="equipment-images"
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          className="sr-only"
          disabled={disabled}
          onChange={(event) => {
            addFiles(Array.from(event.target.files ?? []))
            // Allow re-selecting the same files after a validation error.
            event.target.value = ''
          }}
        />
      </label>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-status-rejected/25 bg-status-rejected-bg px-3 py-2 text-xs text-status-rejected"
        >
          {error}
        </p>
      )}

      {entries.length === 0 ? (
        <p className="rounded-lg border border-line bg-soft px-3.5 py-6 text-center text-sm text-muted">
          No images yet. The first image you add becomes the primary image.
        </p>
      ) : (
        <>
          <ul className="grid gap-3 sm:grid-cols-3">
            {entries.map((entry, index) => {
              const isPrimary = primaryKey === entry.key
              const isLegacy = entry.kind === 'existing' && entry.id <= 0
              const isRemoved = entry.kind === 'existing' && entry.removed
              const name =
                entry.kind === 'new'
                  ? entry.file.name
                  : fileNameFromUrl(entry.url) || 'Saved image'
              const meta =
                entry.kind === 'new'
                  ? formatFileSize(entry.file.size)
                  : isLegacy
                    ? 'Legacy image'
                    : 'Saved'

              return (
                <li
                  key={entry.key}
                  className={cn(
                    'overflow-hidden rounded-lg border border-line bg-surface transition-opacity',
                    isRemoved && 'opacity-45',
                    isPrimary && 'ring-2 ring-brand',
                  )}
                >
                  <div className="relative">
                    <EquipmentImage
                      src={entry.kind === 'new' ? entry.previewUrl : entry.url}
                      size="gallery"
                      fit="contain"
                      alt={
                        entry.kind === 'new'
                          ? entry.file.name
                          : `${equipmentName} image ${index + 1}`
                      }
                    />
                    {isPrimary && (
                      <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-brand px-2 py-0.5 text-[11px] font-semibold text-white">
                        <Star className="size-3" aria-hidden /> Primary
                      </span>
                    )}
                  </div>

                  <div className="space-y-2 px-2.5 py-2">
                    <p className="truncate text-xs font-medium text-body" title={name}>
                      {name}
                    </p>
                    <p className="text-[11px] text-muted">
                      {meta}
                      {isRemoved && ' · will be deleted'}
                      {isLegacy && ' · displayed until the gallery is used'}
                    </p>

                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setPrimaryKey(entry.key)}
                        disabled={isPrimary || isRemoved || isLegacy || disabled}
                        aria-label={`Set ${name} as the primary image`}
                        title={
                          isLegacy
                            ? 'This image predates the gallery and cannot be made primary here.'
                            : 'Set as primary'
                        }
                        className="flex size-7 items-center justify-center rounded-md border border-line text-body transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Star className="size-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveEntry(entry.key, -1)}
                        disabled={isRemoved || isLegacy || disabled || index === 0}
                        aria-label={`Move ${name} earlier`}
                        title="Move earlier"
                        className="flex size-7 items-center justify-center rounded-md border border-line text-body transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <ArrowLeft className="size-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveEntry(entry.key, 1)}
                        disabled={isRemoved || isLegacy || disabled || index === entries.length - 1}
                        aria-label={`Move ${name} later`}
                        title="Move later"
                        className="flex size-7 items-center justify-center rounded-md border border-line text-body transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <ArrowRight className="size-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeEntry(entry)}
                        disabled={disabled || isLegacy}
                        aria-label={
                          isRemoved ? `Keep ${name}` : `Remove ${name}`
                        }
                        title={
                          isLegacy
                            ? 'This image predates the gallery and cannot be removed here.'
                            : isRemoved
                              ? 'Keep this image'
                              : 'Remove image'
                        }
                        className={cn(
                          'ml-auto flex size-7 items-center justify-center rounded-md border border-line transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40',
                          isRemoved ? 'text-body' : 'text-body hover:text-status-rejected',
                        )}
                      >
                        {isRemoved ? (
                          <Undo2 className="size-3.5" />
                        ) : (
                          <Trash2 className="size-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
          <p className="text-xs text-muted">
            {survivors.length} image{survivors.length === 1 ? '' : 's'} after saving · the primary
            image is always shown first.
          </p>
        </>
      )}
    </div>
  )
}
