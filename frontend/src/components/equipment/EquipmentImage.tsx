import { Package } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getEquipmentImageUrl } from '@/lib/utils'

interface EquipmentImageProps {
  src: string | null | undefined
  size?: 'sm' | 'md' | 'lg' | 'preview'
  className?: string
}

const sizes = {
  sm: 'h-16 w-16',
  md: 'h-30 w-30',
  lg: 'max-h-[400px] max-w-[400px]',
  preview: 'aspect-video max-h-[180px] w-full',
} as const

export function EquipmentImage({
  src,
  size = 'sm',
  className,
}: EquipmentImageProps) {
  const imageUrl = getEquipmentImageUrl(src)
  const dims = sizes[size]

  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt=""
        className={cn(
          'rounded-lg object-cover',
          dims,
          size === 'preview' ? 'object-contain' : 'object-cover',
          className,
        )}
        loading="lazy"
      />
    )
  }

  return (
    <div
      className={cn(
        'flex items-center justify-center rounded-lg bg-soft text-body',
        dims,
        className,
      )}
      aria-label="No equipment image"
      role="img"
    >
      <Package className="size-8 text-muted" aria-hidden />
    </div>
  )
}
