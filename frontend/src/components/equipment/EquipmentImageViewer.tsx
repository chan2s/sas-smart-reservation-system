import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronLeft, ChevronRight, Package, X } from 'lucide-react'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import type { Equipment } from '@/lib/types'
import { cn } from '@/lib/utils'

/**
 * Lightbox for an equipment item's images.
 *
 * Shows the gallery one image at a time with previous/next controls and a
 * counter. Escape closes it, the arrow keys navigate, the backdrop click
 * closes it (a click on the image itself does not), and background scrolling
 * is locked while it is open. Only public item information is shown — no ids,
 * paths, or admin notes.
 */
export function EquipmentImageViewer({
  equipment,
  images,
  initialIndex = 0,
  onClose,
}: {
  /** The item being viewed; null closes the lightbox. */
  equipment: Equipment | null
  /** Resolved image URLs, primary first. */
  images: string[]
  initialIndex?: number
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [index, setIndex] = useState(initialIndex)

  const open = equipment != null
  const count = images.length

  // Always open on the image the requester clicked.
  useEffect(() => {
    if (!open) return
    const last = Math.max(count - 1, 0)
    setIndex(Math.min(Math.max(initialIndex, 0), last))
  }, [open, initialIndex, count])

  const go = useCallback(
    (delta: number) => {
      if (count < 2) return
      setIndex((current) => (current + delta + count) % count)
    },
    [count],
  )

  useEffect(() => {
    if (!open) return
    const panel = panelRef.current
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault()
        go(-1)
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        go(1)
      }
    }

    panel?.focus()
    document.addEventListener('keydown', onKeyDown, true)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      document.body.style.overflow = ''
      previouslyFocused?.focus()
    }
  }, [open, onClose, go])

  if (!open || !equipment) return null

  const safeIndex = index < count ? index : 0
  const current = images[safeIndex]

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={`${equipment.name} images`}
    >
      {/* Backdrop click closes — consistent with the app's existing Modal. */}
      <div
        className="absolute inset-0 bg-ink/60 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cn(
          'relative flex max-h-[90vh] w-full flex-col overflow-hidden rounded-2xl bg-surface shadow-float outline-none animate-fade-up',
          'sm:max-w-2xl',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-ink">{equipment.name}</h2>
            {count > 0 && (
              <p className="mt-0.5 text-xs text-muted" aria-live="polite">
                Image {safeIndex + 1} of {count}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-soft hover:text-ink"
            aria-label="Close image viewer"
          >
            <X className="size-5" />
          </button>
        </div>

        <div className="relative flex min-h-0 flex-1 items-center justify-center bg-soft/60 p-4">
          {current ? (
            <>
              <EquipmentImage
                src={current}
                size="lg"
                fit="contain"
                alt={`${equipment.name} — image ${safeIndex + 1} of ${count}`}
                className="max-h-[60vh] w-auto max-w-full"
              />
              {/* Always rendered; disabled while the gallery has one image. */}
              <button
                type="button"
                onClick={() => go(-1)}
                disabled={count < 2}
                aria-label="Previous image"
                className="absolute left-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-surface/90 text-body shadow-sm transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => go(1)}
                disabled={count < 2}
                aria-label="Next image"
                className="absolute right-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-surface/90 text-body shadow-sm transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronRight className="size-4" />
              </button>
            </>
          ) : (
            <div
              className="flex flex-col items-center gap-2 py-12 text-muted"
              role="img"
              aria-label="No image available"
            >
              <Package className="size-10" aria-hidden />
              <span className="text-sm">No image available</span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-5 py-3.5 text-[13px]">
          <span className="font-medium text-body">{equipment.category.name}</span>
          {equipment.storage_location && (
            <span className="text-muted">{equipment.storage_location}</span>
          )}
          <span className="text-muted">
            {equipment.availability.available} of {equipment.total_quantity} {equipment.unit}s available
          </span>
        </div>
      </div>
    </div>,
    document.body,
  )
}
