import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, Expand } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FacilityImage } from '@/components/facilities/FacilityImage'
import type { FacilityType } from '@/lib/types'

const SWIPE_THRESHOLD = 40 // px before a drag counts as a swipe

/**
 * Image carousel for a facility's gallery.
 *
 * The single display component for a facility's pictures, used by the
 * catalogue cards and the facility detail hero. It always starts on the
 * primary image (which the resolver places first) and behaves correctly for
 * every gallery size:
 *
 *   - no images  → the existing pastel facility placeholder (never a blank box),
 *   - one image  → just the picture, with no unnecessary controls,
 *   - many       → previous/next buttons, dot indicators, a counter, keyboard
 *                  arrows and swipe/touch navigation.
 *
 * The images slide horizontally with a smooth transition; the container fills
 * whatever sized wrapper the caller provides (`h-48`, `h-60 sm:h-72`, …), so
 * the same component adapts to cards, heroes and previews without hard-coded
 * dimensions. Images keep their aspect ratio via the shared FacilityImage
 * (object-cover) and degrade to the placeholder if a URL fails to load.
 */
export function FacilityImageCarousel({
  images,
  name,
  facilityType,
  className,
  overlay,
  onOpenImage,
  rounded = 'rounded-xl',
}: {
  /** Resolved image URLs, primary first. */
  images: string[]
  /** Facility name, used in the accessible labels. */
  name: string
  /** Drives the placeholder gradient when there are no images. */
  facilityType: FacilityType
  /** Extra classes for the root (the caller's wrapper supplies the height). */
  className?: string
  /** Rendered above the image and below the controls (e.g. a hero title band). */
  overlay?: ReactNode
  /** When provided, clicking the image opens a larger preview at that index. */
  onOpenImage?: (index: number) => void
  /** Corner rounding of the whole carousel. */
  rounded?: string
}) {
  const [index, setIndex] = useState(0)
  const touchStartX = useRef<number | null>(null)

  const count = images.length
  const galleryKey = images.join('|')

  // A different gallery (or a reload) starts back at the primary image.
  useEffect(() => {
    setIndex(0)
  }, [galleryKey])

  // No images: the shared placeholder, exactly as single-image callers show it.
  if (count === 0) {
    return (
      <FacilityImage
        name={name}
        facilityType={facilityType}
        src={null}
        rounded={rounded}
        className={cn('h-full w-full', className)}
      />
    )
  }

  const safeIndex = index < count ? index : 0
  const go = (delta: number) => setIndex((current) => (current + delta + count) % count)

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
    <div
      className={cn('group relative h-full w-full overflow-hidden bg-soft', rounded, className)}
    >
      <div
        role="group"
        aria-roledescription="carousel"
        aria-label={`${name} images`}
        tabIndex={count > 1 ? 0 : -1}
        onKeyDown={handleKeyDown}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        className="relative h-full w-full touch-pan-y focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        {/* Sliding track: one full-width slide per image. */}
        <div
          className="flex h-full w-full transition-transform duration-300 ease-out motion-reduce:transition-none"
          style={{ transform: `translateX(-${safeIndex * 100}%)` }}
        >
          {images.map((url, i) => (
            <div
              key={`${url}-${i}`}
              className="relative h-full w-full shrink-0"
              aria-hidden={i !== safeIndex}
            >
              {onOpenImage ? (
                <button
                  type="button"
                  onClick={() => onOpenImage(i)}
                  aria-label={`Open image ${i + 1} of ${count} at full size`}
                  className="group/image relative block h-full w-full cursor-pointer"
                >
                  <FacilityImage
                    name={name}
                    facilityType={facilityType}
                    src={url}
                    rounded="rounded-none"
                  />
                  {/* Subtle hover cue so it is obvious the picture opens. */}
                  <span
                    aria-hidden
                    className="pointer-events-none absolute inset-0 bg-ink/0 transition-colors duration-200 group-hover/image:bg-ink/10"
                  />
                </button>
              ) : (
                <FacilityImage
                  name={name}
                  facilityType={facilityType}
                  src={url}
                  rounded="rounded-none"
                />
              )}
            </div>
          ))}
        </div>

        {/* Caller-owned band (hero title/badges). Pointer-transparent so the
            image underneath still opens the full-size preview. */}
        {overlay}

        {onOpenImage && (
          <span
            aria-hidden
            className="pointer-events-none absolute bottom-3 right-2 inline-flex items-center gap-1 rounded-full bg-ink/70 px-2 py-0.5 text-[11px] font-medium text-white"
          >
            <Expand className="size-3" /> View larger
          </span>
        )}

        {/* Only rendered when there is more than one image to navigate. */}
        {count > 1 && (
          <>
            <button
              type="button"
              onClick={() => go(-1)}
              aria-label="Previous image"
              className="absolute left-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-surface/90 text-body shadow-sm transition-colors hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => go(1)}
              aria-label="Next image"
              className="absolute right-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-surface/90 text-body shadow-sm transition-colors hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <ChevronRight className="size-4" />
            </button>

            <span
              aria-live="polite"
              className="absolute right-2 top-2 rounded-full bg-ink/70 px-2 py-0.5 text-[11px] font-medium tabular-nums text-white"
            >
              {safeIndex + 1} / {count}
            </span>

            {/* Indicator dots (● ○ ○ ○). */}
            <div
              role="group"
              aria-label="Select an image"
              className="absolute inset-x-0 bottom-3 flex items-center justify-center gap-1.5"
            >
              {images.map((_, i) => (
                <button
                  key={`dot-${i}`}
                  type="button"
                  onClick={() => setIndex(i)}
                  aria-label={`Go to image ${i + 1} of ${count}`}
                  aria-current={i === safeIndex}
                  className={cn(
                    'h-2 rounded-full bg-white shadow-sm ring-1 ring-ink/15 transition-all duration-200',
                    i === safeIndex ? 'w-5' : 'w-2 hover:bg-white/90',
                    i === safeIndex ? 'opacity-100' : 'opacity-60',
                  )}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
