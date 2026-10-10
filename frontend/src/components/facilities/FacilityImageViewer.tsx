import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import type { FacilityType } from '@/lib/types'
import { cn } from '@/lib/utils'

/**
 * Full-size lightbox for a facility's gallery.
 *
 * Opened from the facility detail carousel when the requester/admin clicks an
 * image. Shows one picture at a time with previous/next controls and a
 * counter; Escape closes it, the arrow keys navigate, the backdrop closes it
 * (a click on the panel does not), and background scrolling is locked while it
 * is open. The facility placeholder is shown when the gallery is empty, so the
 * viewer is never a blank box.
 */
export function FacilityImageViewer({
  open,
  name,
  facilityType,
  images,
  initialIndex = 0,
  onClose,
}: {
  open: boolean
  name: string
  facilityType: FacilityType
  /** Resolved image URLs, primary first. */
  images: string[]
  initialIndex?: number
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [index, setIndex] = useState(initialIndex)

  const count = images.length

  // Always open on the image that was clicked.
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

  if (!open) return null

  const safeIndex = index < count ? index : 0
  const current = images[safeIndex]

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={`${name} images`}
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
          'sm:max-w-3xl',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-ink">{name}</h2>
            {count > 0 && (
              <p className="mt-0.5 text-xs tabular-nums text-muted" aria-live="polite">
                <span className="sr-only">
                  Image {safeIndex + 1} of {count}
                </span>
                <span aria-hidden>
                  {safeIndex + 1} / {count}
                </span>
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

        <div className="relative flex min-h-0 flex-1 items-center justify-center bg-soft/60 p-3 sm:p-4">
          {/* Viewport-bounded frame: the picture is scaled with object-fit:
              contain, so portrait and landscape photos both stay complete and
              undistorted, and it can never grow past the viewport (no
              horizontal scrolling on small screens). */}
          <div className="aspect-[4/3] max-h-[65vh] w-full max-w-2xl overflow-hidden rounded-xl sm:max-h-[70vh]">
            <FacilityImage
              name={name}
              facilityType={facilityType}
              src={current ?? null}
              fit="contain"
              alt={`${name} facility — image ${safeIndex + 1} of ${count}`}
              rounded="rounded-xl"
              className="h-full w-full"
            />
          </div>

          {count > 1 && (
            <>
              <button
                type="button"
                onClick={() => go(-1)}
                aria-label="Previous image"
                className="absolute left-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-surface/90 text-body shadow-sm transition-colors hover:bg-surface"
              >
                <ChevronLeft className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => go(1)}
                aria-label="Next image"
                className="absolute right-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-surface/90 text-body shadow-sm transition-colors hover:bg-surface"
              >
                <ChevronRight className="size-4" />
              </button>
            </>
          )}
        </div>

        {count > 1 && (
          <div className="flex flex-wrap items-center justify-center gap-2 border-t border-line px-5 py-3.5">
            {images.map((_, i) => (
              <button
                key={`viewer-dot-${i}`}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Go to image ${i + 1} of ${count}`}
                aria-current={i === safeIndex}
                className={cn(
                  'h-2 rounded-full transition-all duration-200',
                  i === safeIndex
                    ? 'w-5 bg-brand'
                    : 'w-2 bg-line-strong hover:bg-muted',
                )}
              />
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
