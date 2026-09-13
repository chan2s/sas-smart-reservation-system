import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Expand, Package } from 'lucide-react'
import { cn } from '@/lib/utils'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'

const SWIPE_THRESHOLD = 40 // px before a drag counts as a swipe

/**
 * Image carousel for an equipment item's gallery.
 *
 * Works with a single image (controls hidden and disabled), several images
 * (arrows, thumbnails, counter, keyboard and swipe), and none at all (a
 * polished empty state — never a blank box). Images keep their aspect ratio and
 * are never stretched; a failed image falls back to "Image unavailable".
 */
export function EquipmentCarousel({
  images,
  alt,
  onOpenImage,
  className,
}: {
  /** Resolved image URLs, primary first. */
  images: string[]
  /** Equipment name, used for the accessible labels. */
  alt: string
  /** When provided, the main image becomes a button that opens a larger view. */
  onOpenImage?: (index: number) => void
  className?: string
}) {
  const [index, setIndex] = useState(0)
  const touchStartX = useRef<number | null>(null)

  const count = images.length
  const galleryKey = images.join('|')

  // A different gallery (or a reload) starts back at the primary image.
  useEffect(() => {
    setIndex(0)
  }, [galleryKey])

  if (count === 0) {
    return (
      <div
        role="img"
        aria-label={`No images available for ${alt}`}
        className={cn(
          'flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 rounded-xl border border-line bg-soft text-muted',
          className,
        )}
      >
        <Package className="size-8" aria-hidden />
        <span className="text-sm">No images available</span>
      </div>
    )
  }

  const safeIndex = index < count ? index : 0
  const go = (delta: number) =>
    setIndex((current) => (current + delta + count) % count)

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (count < 2) return
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      go(-1)
    } else if (event.key === 'ArrowRight') {
      event.preventDefault()
      go(1)
    }
  }

  const handleTouchStart = (event: React.TouchEvent<HTMLDivElement>) => {
    touchStartX.current = event.touches[0]?.clientX ?? null
  }

  const handleTouchEnd = (event: React.TouchEvent<HTMLDivElement>) => {
    const startX = touchStartX.current
    touchStartX.current = null
    const endX = event.changedTouches[0]?.clientX
    if (count < 2 || startX == null || endX == null) return
    const delta = endX - startX
    if (Math.abs(delta) < SWIPE_THRESHOLD) return
    go(delta < 0 ? 1 : -1)
  }

  return (
    <div className={cn('space-y-2', className)}>
      <div
        role="group"
        aria-roledescription="carousel"
        aria-label={`${alt} images`}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        className="relative touch-pan-y overflow-hidden rounded-xl border border-line bg-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        {onOpenImage ? (
          <button
            type="button"
            onClick={() => onOpenImage(safeIndex)}
            aria-label={`Open image ${safeIndex + 1} of ${count} at full size`}
            className="block w-full cursor-zoom-in"
          >
            <EquipmentImage
              src={images[safeIndex]}
              size="gallery"
              fit="contain"
              alt={`${alt} — image ${safeIndex + 1} of ${count}`}
            />
          </button>
        ) : (
          <EquipmentImage
            src={images[safeIndex]}
            size="gallery"
            fit="contain"
            alt={`${alt} — image ${safeIndex + 1} of ${count}`}
          />
        )}

        {/* Always rendered, disabled when there is nothing to navigate. */}
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

        <span
          aria-live="polite"
          className="absolute bottom-2 right-2 rounded-full bg-ink/70 px-2 py-0.5 text-[11px] font-medium tabular-nums text-white"
        >
          {safeIndex + 1} / {count}
        </span>

        {onOpenImage && (
          <span
            aria-hidden
            className="pointer-events-none absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full bg-ink/70 px-2 py-0.5 text-[11px] font-medium text-white"
          >
            <Expand className="size-3" /> View larger
          </span>
        )}
      </div>

      {count > 1 && (
        <div
          role="group"
          aria-label="Select an image"
          className="flex gap-2 overflow-x-auto pb-1"
        >
          {images.map((url, i) => (
            <button
              key={`${url}-${i}`}
              type="button"
              onClick={() => setIndex(i)}
              aria-label={`Select image ${i + 1}`}
              aria-current={i === safeIndex}
              className={cn(
                'shrink-0 rounded-lg p-0.5 transition-colors',
                i === safeIndex ? 'ring-2 ring-brand' : 'hover:bg-soft',
              )}
            >
              <EquipmentImage src={url} size="sm" className="rounded-md" alt="" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
