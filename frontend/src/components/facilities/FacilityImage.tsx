import { useEffect, useState } from 'react'
import { Building2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { FacilityType } from '@/lib/types'

// Calm pastel gradients keyed by facility type — used until real photos
// are uploaded through the admin/API.
const gradients: Record<FacilityType, string> = {
  GYMNASIUM: 'from-blob-emerald/70 to-blob-blue/60',
  CAFETERIA: 'from-blob-amber/70 to-blob-indigo/50',
  AVR: 'from-blob-indigo/70 to-blob-blue/50',
  MULTI_PURPOSE: 'from-blob-blue/70 to-blob-emerald/40',
  OUTDOOR: 'from-blob-emerald/50 to-blob-amber/40',
  OTHER: 'from-blob-indigo/40 to-blob-blue/40',
}

export function FacilityImage({
  name,
  facilityType,
  src,
  className,
  rounded = 'rounded-xl',
  fit = 'cover',
  alt,
}: {
  name: string
  facilityType: FacilityType
  src?: string | null
  className?: string
  rounded?: string
  /** 'contain' shows the whole picture without cropping (used in the viewer). */
  fit?: 'cover' | 'contain'
  /** Overrides the default `<name> facility` alt text. */
  alt?: string
}) {
  // A URL that fails to load (moved/deleted file, bad media path) must never
  // show the browser's broken-image icon — fall back to the same placeholder
  // used when there is no image at all.
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [src])

  if (src && !failed) {
    return (
      <img
        src={src}
        alt={alt ?? `${name} facility`}
        loading="lazy"
        onError={() => setFailed(true)}
        className={cn(
          fit === 'contain' ? 'object-contain' : 'h-full w-full object-cover',
          rounded,
          className,
        )}
      />
    )
  }
  return (
    <div
      role="img"
      aria-label={alt ?? `${name} facility`}
      className={cn(
        'relative flex h-full w-full items-center justify-center overflow-hidden bg-gradient-to-br',
        gradients[facilityType] ?? gradients.OTHER,
        rounded,
        className,
      )}
    >
      {/* Subtle geometric decoration */}
      <div
        className="absolute -right-8 -top-10 size-36 rounded-full border-[14px] border-white/25"
        aria-hidden
      />
      <div
        className="absolute -bottom-12 -left-6 size-32 rounded-full border-[10px] border-white/20"
        aria-hidden
      />
      <Building2 className="relative size-10 text-ink/30" aria-hidden />
    </div>
  )
}