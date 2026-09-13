import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Package, X } from 'lucide-react'
import { EquipmentImage } from '@/components/equipment/EquipmentImage'
import type { Equipment } from '@/lib/types'
import { cn } from '@/lib/utils'

/**
 * Polished image viewer for a single equipment item. Shows the authoritative
 * backend image (same source as the admin preview) without cropping, plus
 * just enough context to help a requester identify the physical item.
 * No internal IDs, no admin notes, no maintenance data.
 */
export function EquipmentImageViewer({
  equipment,
  onClose,
}: {
  equipment: Equipment | null
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  const open = equipment != null

  useEffect(() => {
    if (!open) return
    const panel = panelRef.current
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
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
  }, [open, onClose])

  if (!open || !equipment) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={`${equipment.name} image`}
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
          <h2 className="text-base font-semibold text-ink">{equipment.name}</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-soft hover:text-ink"
            aria-label="Close image viewer"
          >
            <X className="size-5" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 items-center justify-center bg-soft/60 p-4">
          {equipment.image ? (
            <EquipmentImage
              src={equipment.image}
              size="lg"
              fit="contain"
              alt={equipment.name}
              className="max-h-[60vh] w-auto max-w-full"
            />
          ) : (
            <div className="flex flex-col items-center gap-2 py-12 text-muted" role="img" aria-label="No image available">
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
