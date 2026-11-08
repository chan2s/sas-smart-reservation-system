import { useLayoutEffect, useRef, type ReactNode } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { cn } from '@/lib/utils'

gsap.registerPlugin(ScrollTrigger)

/** Shared by every landing surface so motion can be switched off at the OS level. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/** Fades and lifts a block into place the first time it enters the viewport. */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode
  className?: string
  delay?: number
}) {
  const ref = useRef<HTMLDivElement | null>(null)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    if (prefersReducedMotion()) return

    const context = gsap.context(() => {
      gsap.fromTo(
        element,
        { opacity: 0, y: 32 },
        {
          opacity: 1,
          y: 0,
          duration: 0.8,
          delay,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: element,
            start: 'top 85%',
            once: true,
          },
        },
      )
    }, element)
    return () => context.revert()
  }, [delay])

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  )
}

/** Small uppercase section label with its leading rule. */
export function Eyebrow({
  children,
  onDark = false,
  centered = false,
}: {
  children: ReactNode
  onDark?: boolean
  centered?: boolean
}) {
  return (
    <p
      className={cn(
        'flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.2em]',
        onDark ? 'text-brand-faint' : 'text-brand',
        centered && 'justify-center',
      )}
    >
      <span className="h-px w-8 bg-brand" aria-hidden />
      {children}
    </p>
  )
}
