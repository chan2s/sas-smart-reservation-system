import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { format } from 'date-fns'
import { X } from 'lucide-react'
import { cn, formatTime } from '@/lib/utils'
import type { BookedDateEvent } from '@/lib/types'

export function ReservationEventsModal({
  open,
  date,
  events,
  onClose,
}: {
  open: boolean
  date: Date | null
  events: BookedDateEvent[]
  onClose: () => void
}) {
  const [mounted, setMounted] = useState(open)
  const panelRef = useRef<HTMLElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  const openRef = useRef(open)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    openRef.current = open
  }, [open])

  useEffect(() => {
    if (open) {
      setMounted(true)
      return
    }
    if (!mounted) return
    const timeout = window.setTimeout(() => setMounted(false), 220)
    return () => window.clearTimeout(timeout)
  }, [open, mounted])

  useEffect(() => {
    if (!mounted) return
    const previousOverflow = document.body.style.overflow
    const appRoot = document.getElementById('root')
    const previousInert = appRoot?.inert ?? false
    const previousAriaHidden = appRoot?.getAttribute('aria-hidden') ?? null
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && openRef.current) onCloseRef.current()
      if (event.key !== 'Tab') return
      const focusables = panelRef.current
        ? Array.from(panelRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ))
        : []
      if (focusables.length === 0) return
      if (event.shiftKey && document.activeElement === focusables[0]) {
        event.preventDefault()
        focusables[focusables.length - 1].focus()
      } else if (!event.shiftKey && document.activeElement === focusables[focusables.length - 1]) {
        event.preventDefault()
        focusables[0].focus()
      }
    }

    document.body.style.overflow = 'hidden'
    if (appRoot) {
      appRoot.inert = true
      appRoot.setAttribute('aria-hidden', 'true')
    }
    document.addEventListener('keydown', onKeyDown)
    closeButtonRef.current?.focus()

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      if (appRoot) {
        appRoot.inert = previousInert
        if (previousAriaHidden === null) appRoot.removeAttribute('aria-hidden')
        else appRoot.setAttribute('aria-hidden', previousAriaHidden)
      }
      previouslyFocused?.focus()
    }
  }, [mounted])

  if (!mounted || !date) return null

  return createPortal(
    <div
      className={cn(
        'fixed inset-0 z-[100] flex items-center justify-center p-3 transition-opacity duration-200 ease-out motion-reduce:transition-none sm:p-6',
        open ? 'opacity-100' : 'opacity-0',
      )}
      role="presentation"
    >
      <div
        className={cn(
          'absolute inset-0 bg-ink/60 transition-opacity duration-200 ease-out motion-reduce:transition-none',
          open ? 'opacity-100' : 'opacity-0',
        )}
        aria-hidden="true"
        onClick={open ? onClose : undefined}
      />
      <section
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reservation-events-title"
        className={cn(
          'relative flex max-h-[calc(100dvh-1.5rem)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-float transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none sm:max-h-[calc(100dvh-3rem)]',
          open ? 'scale-100 opacity-100' : 'scale-95 opacity-0',
        )}
        tabIndex={-1}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
          <div>
            <h2 id="reservation-events-title" className="text-lg font-semibold text-ink">
              Events on {format(date, 'MMMM d, yyyy')}
            </h2>
            <p className="mt-1 text-sm text-body">
              {events.length} reservation{events.length === 1 ? '' : 's'} at this facility
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl text-body transition-colors hover:bg-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            aria-label="Close event details"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </header>

        <div className="min-h-0 space-y-3 overflow-y-auto p-4 sm:p-6">
          {events.map((event, index) => (
            <article
              key={`${event.date}-${event.start_time}-${event.end_time}-${event.event_name}-${index}`}
              className="rounded-xl border border-line bg-soft p-4 sm:p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-base font-semibold text-ink">{event.event_name}</h3>
                <span className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-semibold text-brand">
                  {event.status_label}
                </span>
              </div>
              <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-medium text-muted">Facility</dt>
                  <dd className="mt-0.5 text-body">{event.facility_name}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-muted">Reservation date</dt>
                  <dd className="mt-0.5 text-body">{format(new Date(`${event.date}T00:00:00`), 'MMMM d, yyyy')}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-muted">Start time</dt>
                  <dd className="mt-0.5 text-body">{formatTime(event.start_time)}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-muted">End time</dt>
                  <dd className="mt-0.5 text-body">{formatTime(event.end_time)}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-muted">Reservation status</dt>
                  <dd className="mt-0.5 text-body">{event.status_label}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </section>
    </div>,
    document.body,
  )
}
