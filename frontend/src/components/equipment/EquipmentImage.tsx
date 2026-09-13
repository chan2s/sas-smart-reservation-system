import { useEffect, useState } from 'react'
import { ImageOff, Package } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getEquipmentImageUrl } from '@/lib/utils'

interface EquipmentImageProps {
  src: string | null | undefined
  size?: 'sm' | 'md' | 'lg' | 'preview'
  className?: string
  /**
   * Meaningful alt text (typically the equipment name). Falls back to an
   * empty string when the image is purely decorative.
   */
  alt?: string
  /** 'contain' shows the full image without cropping (used in viewers). */
  fit?: 'cover' | 'contain'
  /** Temporary debug hook for the admin edit modal. */
  onLoad?: () => void
  onError?: () => void
}

const sizes = {
  sm: 'h-16 w-16',
  md: 'h-30 w-30',
  lg: 'max-h-[400px] max-w-[400px]',
  preview: 'aspect-video max-h-[180px] w-full',
} as const

/**
 * Renders an equipment image with graceful degradation:
 * - skeleton box while the image loads (no layout jumping),
 * - polished fallback with an icon when there is no image, the URL is
 *   broken, or the request fails — the browser's broken-image icon must
 *   never be visible.
 */
export function EquipmentImage({
  src,
  size = 'sm',
  className,
  alt = '',
  fit = 'cover',
  onLoad,
  onError,
}: EquipmentImageProps) {
  const imageUrl = getEquipmentImageUrl(src)
  const dims = sizes[size]
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading')

  // Reset when the image source changes (e.g. preview swap after upload).
  useEffect(() => {
    setStatus('loading')
  }, [imageUrl])

  if (imageUrl && status !== 'error') {
    return (
      <span className={cn('relative inline-block', dims, className)}>
        {status === 'loading' && (
          <span
            aria-hidden
            className="absolute inset-0 animate-pulse rounded-lg bg-soft"
          />
        )}
        <img
          src={imageUrl}
          alt={alt}
          className={cn(
            'rounded-lg',
            dims,
            fit === 'contain' || size === 'preview' ? 'object-contain' : 'object-cover',
            status === 'loading' && 'opacity-0',
            className,
          )}
          loading="lazy"
          onLoad={() => {
            setStatus('loaded')
            onLoad?.()
          }}
          onError={() => {
            setStatus('error')
            onError?.()
          }}
        />
      </span>
    )
  }

  // No image (or the URL failed): polished fallback, never a broken icon.
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-1 rounded-lg bg-soft text-body',
        dims,
        className,
      )}
      aria-label={imageUrl ? 'Image unavailable' : 'No equipment image'}
      role="img"
    >
      {imageUrl ? (
        <ImageOff className="size-6 text-muted" aria-hidden />
      ) : (
        <Package className="size-8 text-muted" aria-hidden />
      )}
      {size !== 'sm' && (
        <span className="px-2 text-center text-[11px] leading-tight text-muted">
          {imageUrl ? 'Image unavailable' : 'No image available'}
        </span>
      )}
    </div>
  )
}
