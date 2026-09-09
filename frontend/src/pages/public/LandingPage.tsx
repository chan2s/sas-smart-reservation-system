import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  Menu,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react'
import { useEquipment, useEquipmentStats, useFacilities } from '@/hooks/queries'
import { getEquipmentImageUrl, cn } from '@/lib/utils'
import { BrandMark } from '@/components/auth/AuthPanel'
import heroVideo from '@/assets/0625.mp4'

gsap.registerPlugin(ScrollTrigger)

/* ---------------------------------------------------------------------------
   Motion helpers
   --------------------------------------------------------------------------- */

/** True when the user prefers reduced motion. */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/** True on small viewports where heavy scroll effects should stay off. */
function prefersLightMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
}

/**
 * Lightweight one-shot scroll reveal for small content blocks. GSAP handles
 * the big cinematic moments; this keeps simple reveals cheap and scoped.
 */
function Reveal({
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
    if (prefersReducedMotion()) return // content simply shows

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

/** Staggered line reveal for editorial headings. Lines rise sequentially. */
function StaggeredHeading({
  lines,
  className,
  onDark = false,
}: {
  lines: string[]
  className?: string
  onDark?: boolean
}) {
  const ref = useRef<HTMLHeadingElement | null>(null)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    if (prefersReducedMotion()) return

    const context = gsap.context(() => {
      gsap.fromTo(
        element.querySelectorAll('[data-line-inner]'),
        { opacity: 0, y: 44 },
        {
          opacity: 1,
          y: 0,
          duration: 0.9,
          stagger: 0.1,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: element,
            start: 'top 82%',
            once: true,
          },
        },
      )
    }, element)
    return () => context.revert()
  }, [])

  return (
    <h2
      ref={ref}
      className={cn('font-bold tracking-tight', onDark ? 'text-white' : 'text-ink', className)}
    >
      {lines.map((line) => (
        <span key={line} className="block overflow-hidden">
          <span data-line-inner className="block">
            {line}
          </span>
        </span>
      ))}
    </h2>
  )
}

/* ---------------------------------------------------------------------------
   Small editorial primitives
   --------------------------------------------------------------------------- */

function Eyebrow({
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

/* ---------------------------------------------------------------------------
   Navigation
   --------------------------------------------------------------------------- */

const NAV_LINKS = [
  { label: 'Overview', id: 'overview' },
  { label: 'Facilities', id: 'facilities' },
  { label: 'Equipment', id: 'equipment' },
  { label: 'About', id: 'about' },
]

function LandingNav({
  activeSection,
  scrolled,
  onOpenMenu,
}: {
  activeSection: string
  scrolled: boolean
  onOpenMenu: () => void
}) {
  return (
    /* Fixed so it stays above every section, video, and GSAP layer.
       The hero already pads its content, so nothing shifts when scrolling. */
    <header className="fixed inset-x-0 top-0 z-40">
      <div
        className={cn(
          'mx-auto max-w-[1400px] px-4 transition-all duration-300 ease-out sm:px-6',
          scrolled ? 'pt-2' : 'pt-4',
        )}
      >
        <nav
          aria-label="Primary"
          className={cn(
            'flex items-center justify-between gap-3 rounded-2xl border px-4 backdrop-blur-md transition-all duration-300 ease-out sm:px-6',
            scrolled
              ? 'h-16 border-[var(--nav-scrolled-border)] bg-[var(--nav-scrolled-background)] shadow-float backdrop-blur-lg'
              : 'h-[72px] bg-[var(--nav-background-applied)]',
          )}
        >
          <Link
            to="/"
            className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-faint"
            aria-label="SAS Reserve — back to top"
          >
            <BrandMark onDark />
          </Link>

          <div className="hidden items-center gap-8 lg:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.id}
                href={`#${link.id}`}
                aria-current={activeSection === link.id ? 'true' : undefined}
                className={cn(
                  'relative flex flex-col items-center gap-1 text-sm font-medium transition-colors',
                  activeSection === link.id ? 'text-[var(--nav-foreground)]' : 'text-[var(--nav-foreground-muted)] hover:text-[var(--nav-foreground)]',
                )}
              >
                {link.label}
                <span
                  aria-hidden
                  className={cn(
                    'h-0.5 rounded-full bg-[var(--nav-accent)] transition-all duration-300',
                    activeSection === link.id ? 'w-5 opacity-100' : 'w-0 opacity-0',
                  )}
                />
              </a>
            ))}
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2">
            <Link
              to="/login"
              className="hidden rounded-xl px-3.5 py-2 text-sm font-medium text-[var(--nav-foreground-muted)] transition-colors hover:bg-white/10 hover:text-[var(--nav-foreground)] sm:inline-flex"
            >
              Log In
            </Link>
            <Link
              to="/register"
              className="inline-flex h-10 items-center gap-1.5 rounded-full bg-[var(--nav-button-background)] px-4 text-sm font-semibold text-[var(--nav-button-foreground)] shadow-sm transition-colors hover:bg-brand-dark"
            >
              Create Account
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
            <button
              type="button"
              onClick={onOpenMenu}
              aria-label="Open menu"
              aria-expanded="false"
              className="ml-1 inline-flex size-9 items-center justify-center rounded-xl text-[var(--nav-foreground)] transition-colors hover:bg-white/10 lg:hidden"
            >
              <Menu className="size-5" aria-hidden />
            </button>
          </div>
        </nav>
      </div>
    </header>
  )
}

/* ---------------------------------------------------------------------------
   Mobile menu — centralized nav tokens so it follows the same theming rules.
   --------------------------------------------------------------------------- */


/* ---------------------------------------------------------------------------
   Mobile menu — centralized nav tokens so it follows the same theming rules.
   --------------------------------------------------------------------------- */

function MobileMenu({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 lg:hidden"
      role="dialog"
      aria-modal="true"
      aria-label="Menu"
    >
      <div
        className="absolute inset-0 bg-[var(--nav-background)]/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div className="absolute inset-x-3 top-3 rounded-3xl border border-[var(--nav-border)] bg-[var(--nav-background)] p-6 shadow-float">
        <div className="flex items-center justify-between">
          <BrandMark onDark />
        <button
              type="button"
              onClick={onClose}
              aria-label="Close menu"
              className="inline-flex size-9 items-center justify-center rounded-xl text-[var(--nav-foreground)] transition-colors hover:bg-[var(--nav-background)]/10"
            >
            <X className="size-5" aria-hidden />
          </button>
        </div>

        <nav aria-label="Mobile" className="mt-8">
          <ul>
            {NAV_LINKS.map((link) => (
              <li key={link.id}>
                <a
                  href={`#${link.id}`}
                  onClick={onClose}
                  className="flex items-center justify-between border-t border-[var(--nav-border)] py-4 text-2xl font-semibold tracking-tight text-[var(--nav-foreground)] transition-colors hover:text-[var(--nav-foreground)]"
                >
                  {link.label}
                  <ArrowUpRight className="size-5 text-[var(--nav-foreground)]/40" aria-hidden />
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="mt-8 flex flex-col gap-3">
          <Link
            to="/login"
            onClick={onClose}
            className="inline-flex h-11 items-center justify-center rounded-full border border-[var(--nav-border)] text-sm font-semibold text-[var(--nav-foreground)] transition-colors hover:bg-[var(--nav-background)]/10"
          >
            Log In
          </Link>
          <Link
            to="/register"
            onClick={onClose}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-[var(--nav-accent)] text-sm font-semibold text-[var(--nav-button-foreground)] transition-colors hover:bg-brand-dark"
          >
            Create Account
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
   Content
   --------------------------------------------------------------------------- */

const HERO_BENEFITS = ['Facility reservations', 'Equipment management', 'Real-time availability']

const STEPS = [
  {
    number: '01',
    title: 'Create an account',
    description:
      'Sign up with your institutional details — every reservation starts with a secure SAS RESERVE account.',
  },
  {
    number: '02',
    title: 'Plan your event',
    description:
      'Define the event type, date, time, and expected participants before you choose a space.',
  },
  {
    number: '03',
    title: 'Choose facilities & resources',
    description:
      'Pick the facility and the equipment your event needs, with availability checked in real time.',
  },
  {
    number: '04',
    title: 'Track your reservation',
    description:
      'Follow your request through approval, check-in, and completion — all from one place.',
  },
]
/* ---------------------------------------------------------------------------
   Components
   --------------------------------------------------------------------------- */

interface FeatureCardProps {
  title: string
  description: string
  icon?: ReactNode
  href?: string
  secondary?: boolean
}

function FeatureCard({ title, description, icon, href, secondary }: FeatureCardProps) {
  return (
    <article className={cn('group relative overflow-hidden rounded-2xl border border-line bg-surface p-6 sm:p-7 transition-colors hover:border-line-strong', secondary && 'sm:col-span-2')}>
      {icon && (
        <span className="flex size-11 items-center justify-center rounded-xl bg-brand-soft text-brand">
          {icon}
        </span>
      )}
      <h3 className="mt-5 text-base font-semibold tracking-tight text-ink">{title}</h3>
      <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-body">{description}</p>
      {href && (
        <a
          href={href}
          className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-brand transition-colors hover:text-brand-dark"
        >
          Learn more
          <ArrowRight className="size-4" aria-hidden />
        </a>
      )}
    </article>
  )
}

/* ---------------------------------------------------------------------------
   Landing page
   --------------------------------------------------------------------------- */

export function LandingPage() {
  const { data: facilities, isLoading: facilitiesLoading } = useFacilities()
  const { data: equipment } = useEquipment()
  const { data: stats } = useEquipmentStats()

  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)

  /* Sticky-nav scroll state — boolean flips only at the threshold, so
     React re-renders stay minimal and CSS owns the 300ms transition. */
  const [navScrolled, setNavScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setNavScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const activeFacilities = (facilities ?? []).filter((facility) => facility.is_active)
  const featured = activeFacilities[0]
  const secondary = activeFacilities.slice(1, 3)

  // Real equipment rows only — quantities come straight from the API.
  const equipmentItems = (equipment ?? []).filter((item) => item.is_active).slice(0, 8)

  /* -----------------------------------------------------------------------
     One useLayoutEffect owns every ScrollTrigger so React re-renders never
     create duplicates. The gsap.context revert cleans up everything on unmount.
     ----------------------------------------------------------------------- */
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [activeSection, setActiveSection] = useState('overview')

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return

    // Active-nav highlighting runs in every motion mode.
    const sections = Array.from(root.querySelectorAll<HTMLElement>('section[id]'))
    const navObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActiveSection(entry.target.id)
        }
      },
      { rootMargin: '-40% 0px -50% 0px' },
    )
    sections.forEach((section) => navObserver.observe(section))

    // Reduced motion or small screens: content shows as-is, no scroll effects.
    if (prefersReducedMotion() || prefersLightMotion()) {
      return () => navObserver.disconnect()
    }

    const context = gsap.context(() => {
      /* ---- Post-hero intro: gentle depth on the visual column ---------- */
      const introVisual = root.querySelector<HTMLElement>('[data-intro-visual]')
      if (introVisual) {
        gsap.fromTo(
          introVisual,
          { y: 40 },
          {
            y: -24,
            ease: 'none',
            scrollTrigger: {
              trigger: '[data-intro-section]',
              start: 'top bottom',
              end: 'bottom top',
              scrub: true,
            },
          },
        )
      }

      /* ---- Large parallax visual block: media drifts slower than page -- */
      const visualMedia = root.querySelector<HTMLElement>('[data-visual-media]')
      if (visualMedia) {
        gsap.fromTo(
          visualMedia,
          { yPercent: -10 },
          {
            yPercent: 10,
            ease: 'none',
            scrollTrigger: {
              trigger: '[data-visual-block]',
              start: 'top bottom',
              end: 'bottom top',
              scrub: true,
            },
          },
        )
      }

      /* ---- Facility parallax + clip-path reveal ------------------------ */
      const featuredMedia = root.querySelector<HTMLElement>('[data-facility-featured-media]')
      if (featuredMedia) {
        gsap.fromTo(
          featuredMedia,
          { yPercent: -8 },
          {
            yPercent: 8,
            ease: 'none',
            scrollTrigger: {
              trigger: '[data-facility-featured]',
              start: 'top bottom',
              end: 'bottom top',
              scrub: true,
            },
          },
        )
      }

      root.querySelectorAll<HTMLElement>('[data-facility-side-media]').forEach((media) => {
        gsap.fromTo(
          media,
          { yPercent: 6 },
          {
            yPercent: -6,
            ease: 'none',
            scrollTrigger: {
              trigger: media,
              start: 'top bottom',
              end: 'bottom top',
              scrub: true,
            },
          },
        )
      })

      root.querySelectorAll<HTMLElement>('[data-clip-reveal]').forEach((media) => {
        gsap.fromTo(
          media,
          { clipPath: 'inset(0 100% 0 0)' },
          {
            clipPath: 'inset(0 0% 0 0)',
            duration: 1.1,
            ease: 'power3.inOut',
            scrollTrigger: {
              trigger: media,
              start: 'top 80%',
              once: true,
            },
          },
        )
      })

      /* ---- Equipment: subtle horizontal drift ("moving into place") ---- */
      root.querySelectorAll<HTMLElement>('[data-equipment-card]').forEach((card, index) => {
        const direction = index % 2 === 0 ? 1 : -1
        gsap.fromTo(
          card,
          { x: 48 * direction },
          {
            x: 0,
            ease: 'none',
            scrollTrigger: {
              trigger: card,
              start: 'top 95%',
              end: 'top 55%',
              scrub: true,
            },
          },
        )
      })

      /* ---- How-it-works steps: staggered rise -------------------------- */
      const steps = root.querySelectorAll<HTMLElement>('[data-step]')
      if (steps.length > 0) {
        gsap.fromTo(
          steps,
          { opacity: 0, y: 40 },
          {
            opacity: 1,
            y: 0,
            duration: 0.8,
            stagger: 0.12,
            ease: 'power3.out',
            scrollTrigger: {
              trigger: '[data-steps-list]',
              start: 'top 80%',
              once: true,
            },
          },
        )
      }

      /* ---- Final CTA: background drifts slowly, content stays stable --- */
      const ctaBackground = root.querySelector<HTMLElement>('[data-cta-background]')
      if (ctaBackground) {
        gsap.fromTo(
          ctaBackground,
          { yPercent: -12 },
          {
            yPercent: 12,
            ease: 'none',
            scrollTrigger: {
              trigger: '[data-cta-section]',
              start: 'top bottom',
              end: 'bottom top',
              scrub: true,
            },
          },
        )
      }
    }, root)

    return () => {
      navObserver.disconnect()
      context.revert()
    }
  }, [])

  return (
    <div ref={rootRef} className="bg-white text-ink">
      {/* Sticky premium navigation — fixed above all sections and effects */}
      <LandingNav
        activeSection={activeSection}
        scrolled={navScrolled}            onOpenMenu={() => setMenuOpen(true)}
      />

      {/* ===================================================================
          Hero — cinematic video, controlled editorial typography
          =================================================================== */}
      <section
        className="relative flex min-h-[88vh] flex-col overflow-hidden rounded-b-[2rem] bg-navy sm:rounded-b-[3rem]"
        aria-label="Introduction"
      >
        {/* Cinematic background video */}
        <video
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          className="absolute inset-0 h-full w-full object-cover"
          aria-hidden
        >
          <source src={heroVideo} type="video/mp4" />
        </video>

        {/* Layered overlay — darkest at the text, video stays visible right */}
        <div
          className="absolute inset-0 bg-gradient-to-r from-navy/95 via-navy/55 to-navy/10"
          aria-hidden
        />
        <div
          className="absolute inset-0 bg-gradient-to-b from-navy/55 via-navy/10 to-navy/35"
          aria-hidden
        />

        {/* Hero content — left-weighted, vertically centered-lower */}
        <div className="relative z-10 mx-auto flex w-full max-w-[1400px] flex-1 flex-col justify-center px-10 pb-20 pt-32 sm:px-12 sm:pt-36 lg:px-[max(40px,8vw)] lg:pt-40">
          <div className="max-w-[850px]">
            <p
              className="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.2em] text-brand-faint"
              style={{ animation: 'hero-rise 900ms var(--ease-out-soft) both 120ms' }}
            >
              <span className="h-px w-10 bg-brand" aria-hidden />
              Smart Facility Management
            </p>

            <h1
              className="mt-6 max-w-[850px] text-[clamp(2.75rem,5.5vw,5.125rem)] font-extrabold leading-[0.98] tracking-[-0.035em] text-white"
              style={{ animation: 'hero-rise 900ms var(--ease-out-soft) both 220ms' }}
            >
              Reserve spaces. Manage resources. Simplify events.
            </h1>

            <p
              className="mt-6 max-w-[600px] text-lg leading-relaxed text-white/75 sm:text-xl"
              style={{ animation: 'hero-rise 900ms var(--ease-out-soft) both 340ms' }}
            >
              Plan and manage campus events with a centralized reservation system for facilities,
              equipment, and shared resources.
            </p>

            <div
              className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center"
              style={{ animation: 'hero-rise 900ms var(--ease-out-soft) both 460ms' }}
            >
              <Link
                to="/register"
                className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-brand px-7 text-sm font-semibold text-white shadow-sm transition-colors duration-200 hover:bg-brand-dark"
              >
                Create an Account
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              <a
                href="#facilities"
                className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-white px-7 text-sm font-semibold text-ink transition-colors duration-200 hover:bg-white/90"
              >
                Explore Facilities
                <ArrowRight className="size-4" aria-hidden />
              </a>
            </div>

            <p
              className="mt-9 flex flex-wrap items-center gap-x-7 gap-y-2.5 text-sm text-white/70"
              style={{ animation: 'hero-rise 900ms var(--ease-out-soft) both 580ms' }}
            >
              {HERO_BENEFITS.map((benefit) => (
                <span key={benefit} className="flex items-center gap-2">
                  <span className="flex size-5 items-center justify-center rounded-full bg-white/10">
                    <Check className="size-3 text-brand-faint" aria-hidden />
                  </span>
                  {benefit}
                </span>
              ))}
            </p>
          </div>
        </div>
      </section>

      {/* ===================================================================
          Intro / overview — editorial split with parallax visual
          =================================================================== */}
      <section
        id="overview"
        data-intro-section
        className="scroll-mt-24 bg-soft py-24 sm:py-32 lg:py-40"
      >
        <div className="mx-auto max-w-[1400px] px-5 sm:px-8">
          <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
            <div className="lg:col-span-4">
              <Reveal>
                <p className="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.2em] text-brand">
                  <span className="h-px w-8 bg-brand" aria-hidden />
                  01 — Overview
                </p>
              </Reveal>
            </div>
            <div className="lg:col-span-8">
              <StaggeredHeading
                lines={['Everything you need', 'to plan your next event.']}
                className="text-[clamp(2.1rem,4vw,3.4rem)] leading-[1.08]"
              />
              <Reveal delay={0.15}>
                <p className="mt-7 max-w-2xl text-lg leading-relaxed text-body">
                  SAS RESERVE brings facility reservations, shared equipment, availability, and
                  event planning together in one centralized platform.
                </p>
              </Reveal>

              {/* Visual column — drifts slightly slower than the page */}
              <div
                data-intro-visual
                className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3"
              >
                {['One booking flow', 'Real-time availability', 'Account-based access'].map(
                  (label, index) => (
                    <div key={label} className="bg-surface p-6 sm:p-7">
                      <p className="text-[15px] font-semibold tracking-tight text-ink">{label}</p>
                      <p className="mt-1.5 text-sm leading-relaxed text-body">
                        {label === 'One booking flow' &&
                          'Facilities, equipment, and approvals in a single request.'}
                      </p>
              <p className="mt-1.5 text-sm leading-relaxed text-body">
                        {label === 'Real-time availability' &&
                          'Live checks against schedules and inventory before you commit.'}
                      </p>
              <p className="mt-1.5 text-sm leading-relaxed text-body">
                        {label === 'Account-based access' &&
                          'Secure sign-in — every reservation is tied to an account.'}
                      </p>
                      <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
                        0{index + 1}
                      </p>
                    </div>
                  ),
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===================================================================
          Large parallax visual block — real facility imagery when available,
          otherwise a clean treatment from the existing design system.
          =================================================================== */}
      <section data-visual-block className="relative overflow-hidden bg-soft pb-24 sm:pb-32 lg:pb-40">
        <div className="mx-auto max-w-[1400px] px-5 sm:px-8">
          <div className="relative h-[46vh] min-h-[340px] overflow-hidden rounded-[2rem] sm:h-[56vh]">
            {featured?.image ? (
              <>
                <div className="absolute inset-0 scale-[1.22]" data-visual-media>
                  <img
                    src={getEquipmentImageUrl(featured.image) ?? undefined}
                    alt=""
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                </div>
                <div className="absolute inset-0 bg-navy/35" aria-hidden />
              </>
            ) : (
              <div className="absolute inset-0 scale-[1.22] bg-navy" data-visual-media>
                <div
                  aria-hidden
                  className="absolute inset-0 opacity-[0.08]"
                  style={{
                    backgroundImage:
                      'linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)',
                    backgroundSize: '72px 72px',
                  }}
                />
                <div className="absolute -right-40 -top-40 size-[480px] rounded-full bg-brand/25 blur-3xl" />
              </div>
            )}
            <div className="absolute inset-x-0 bottom-0 p-8 sm:p-12">
              <p className="max-w-xl text-2xl font-bold leading-snug tracking-tight text-white sm:text-3xl">
                {featured ? featured.name : 'Campus spaces, ready for your next event.'}
              </p>
              {featured?.capacity ? (
                <p className="mt-2 inline-flex items-center gap-2 text-sm text-white/75">
                  <Users className="size-4" aria-hidden />
                  {featured.capacity} capacity
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {/* ===================================================================
          Facilities — asymmetric editorial composition
          =================================================================== */}
      <section id="facilities" className="scroll-mt-24 bg-white py-24 sm:py-32">
        <div className="mx-auto max-w-[1400px] px-5 sm:px-8">
          <Reveal>
            <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <Eyebrow>Facilities</Eyebrow>
                <StaggeredHeading
                  lines={['Spaces made', 'for your events.']}
                  className="mt-4 text-[clamp(2.1rem,4vw,3.4rem)] leading-[1.08]"
                />
              </div>
              <Link
                to="/facilities"
                className="group inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-ink transition-colors hover:text-brand"
              >
                View all facilities
                <ArrowRight
                  className="size-4 transition-transform duration-300 group-hover:translate-x-0.5"
                  aria-hidden
                />
              </Link>
            </div>
          </Reveal>

          {facilitiesLoading ? (
            <div className="mt-12 grid gap-5 lg:grid-cols-12">
              <div className="skeleton aspect-[16/10] rounded-[2rem] lg:col-span-8" aria-hidden />
              <div className="grid content-start gap-5 lg:col-span-4">
                <div className="skeleton aspect-[16/9] rounded-2xl" aria-hidden />
                <div className="skeleton aspect-[16/9] rounded-2xl" aria-hidden />
              </div>
            </div>
          ) : activeFacilities.length === 0 ? (
            <p className="mt-12 text-sm text-muted">No facilities are published yet.</p>
          ) : (
            <div className="mt-12 grid gap-5 lg:grid-cols-12">
              {/* Large featured visual — parallax + clip reveal */}
              {featured && (
                <div data-facility-featured className="lg:col-span-8">
                  <Link to={`/facilities/${featured.id}`} className="group block">
                    <article className="relative aspect-[16/10] overflow-hidden rounded-[2rem] sm:aspect-[16/9]">
                      <div
                        data-facility-featured-media
                        data-clip-reveal
                        className="absolute inset-0 scale-[1.18]"
                      >
                        {featured.image ? (
                          <img
                            src={getEquipmentImageUrl(featured.image) ?? undefined}
                            alt=""
                            className="h-full w-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center bg-navy-2 text-white/40">
                            <Building2 className="size-14" aria-hidden />
                          </div>
                        )}
                      </div>
                      <div
                        className="absolute inset-0 bg-gradient-to-t from-navy/55 via-transparent to-transparent"
                        aria-hidden
                      />
                      <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-end justify-between gap-3 p-6 sm:p-8">
                        <div>
                          <h3 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
                            {featured.name}
                          </h3>
                          <p className="mt-1.5 line-clamp-2 max-w-lg text-sm leading-relaxed text-white/75">
                            {featured.description}
                          </p>
                        </div>
                        <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-white/90">
                          View facility
                          <ArrowRight
                            className="size-4 transition-transform duration-300 group-hover:translate-x-0.5"
                            aria-hidden
                          />
                        </span>
                      </div>
                    </article>
                  </Link>
                </div>
              )}

              {/* Secondary cards — opposite parallax direction */}
              <div className="grid content-start gap-5 lg:col-span-4">
                {secondary.map((facility) => {
                  const operational = facility.status === 'OPERATIONAL'
                  return (
                    <Link
                      key={facility.id}
                      to={`/facilities/${facility.id}`}
                      className="group block"
                    >
                      <article className="relative aspect-[16/9] overflow-hidden rounded-2xl border border-line bg-soft transition-colors duration-300 hover:border-line-strong">
                        <div
                          data-facility-side-media
                          data-clip-reveal
                          className="absolute inset-0 scale-[1.12]"
                        >
                          {facility.image ? (
                            <img
                              src={getEquipmentImageUrl(facility.image) ?? undefined}
                              alt=""
                              className="h-full w-full object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <div className="flex h-full items-center justify-center bg-navy-2 text-white/40">
                              <Building2 className="size-10" aria-hidden />
                            </div>
                          )}
                        </div>
                        <div
                          className="absolute inset-0 bg-gradient-to-t from-navy/55 via-transparent to-transparent"
                          aria-hidden
                        />
                        <span
                          className={cn(                              'absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold backdrop-blur-md',
                            operational
                              ? 'bg-white/90 text-status-available'
                              : 'bg-white/90 text-status-maintenance',
                          )}
                        >
                          <span
                            className={cn(
                              'size-1.5 rounded-full',
                              operational ? 'bg-status-available' : 'bg-status-maintenance',
                            )}
                            aria-hidden
                          />
                          {operational ? 'Available' : 'Under maintenance'}
                        </span>
                        <div className="absolute inset-x-0 bottom-0 p-5 sm:p-6">
                          <h3 className="text-xl font-bold tracking-tight text-white">
                            {facility.name}
                          </h3>
                          <p className="mt-1 flex items-center gap-1.5 text-sm text-white/70">
                            <Users className="size-4" aria-hidden />
                            {facility.capacity} capacity
                          </p>
                        </div>
                      </article>
                    </Link>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ===================================================================
          Equipment — real API inventory, subtle horizontal drift on scroll
          =================================================================== */}
      <section id="equipment" className="scroll-mt-24 bg-soft py-24 sm:py-32">
        <div className="mx-auto max-w-[1400px] px-5 sm:px-8">
          <Reveal>
            <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <Eyebrow>Equipment</Eyebrow>
                <StaggeredHeading
                  lines={['Everything your', 'event needs.']}
                  className="mt-4 text-[clamp(2.1rem,4vw,3.4rem)] leading-[1.08]"
                />
              </div>
              <Link
                to="/equipment"
                className="group inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-ink transition-colors hover:text-brand"
              >
                Browse equipment
                <ArrowRight
                  className="size-4 transition-transform duration-300 group-hover:translate-x-0.5"
                  aria-hidden
                />
              </Link>
            </div>
          </Reveal>

          {stats && (
            <Reveal delay={0.1}>
              <dl className="mt-12 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4">
                <div className="bg-surface p-6 sm:p-7">
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
                    Equipment types
                  </dt>
                  <dd className="mt-2.5 text-3xl font-bold tabular-nums tracking-tight text-ink sm:text-4xl">
                    {stats.equipment_types}
                  </dd>
                </div>
                <div className="bg-surface p-6 sm:p-7">
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
                    Total units
                  </dt>
                  <dd className="mt-2.5 text-3xl font-bold tabular-nums tracking-tight text-ink sm:text-4xl">
                    {stats.total_units}
                  </dd>
                </div>
                <div className="bg-surface p-6 sm:p-7">
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
                    Available now
                  </dt>
                  <dd className="mt-2.5 text-3xl font-bold tabular-nums tracking-tight text-status-available sm:text-4xl">
                    {stats.available_units}
                  </dd>
                  <dd className="mt-1 text-xs text-muted">units ready to reserve</dd>
                </div>
                <div className="bg-surface p-6 sm:p-7">
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
                    Reserved
                  </dt>
                  <dd className="mt-2.5 text-3xl font-bold tabular-nums tracking-tight text-status-approved sm:text-4xl">
                    {stats.reserved_units}
                  </dd>
                  <dd className="mt-1 text-xs text-muted">units in current reservations</dd>
                </div>
              </dl>
            </Reveal>
          )}

          {equipmentItems.length === 0 ? (
            <p className="mt-10 text-sm text-muted">
              Equipment inventory is being prepared — check back soon.
            </p>
          ) : (
            <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {equipmentItems.map((item) => (
                <li key={item.id} data-equipment-card>
                  <Link
                    to={`/equipment/${item.id}`}
                    className="card card-hover group flex h-full flex-col p-6"
                  >
                    <span className="flex size-11 items-center justify-center rounded-xl bg-brand-soft text-brand">
                      <Building2 className="size-5" aria-hidden />
                    </span>
                    <h3 className="mt-5 text-base font-semibold tracking-tight text-ink">
                      {item.name}
                    </h3>
                    <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-body">
                      {item.description || item.category.name}
                    </p>
                    <p className="mt-auto pt-5 text-sm font-semibold text-status-available">
                      {item.availability.available} available
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* ===================================================================
          How it works
          =================================================================== */}
      <section id="process" className="scroll-mt-24 bg-white py-24 sm:py-32">
        <div className="mx-auto max-w-[1400px] px-5 sm:px-8">
          <Reveal>
            <div className="max-w-2xl">
              <Eyebrow>Process</Eyebrow>
              <StaggeredHeading
                lines={['How it works']}
                className="mt-4 text-[clamp(2.1rem,4vw,3.4rem)] leading-[1.08]"
              />
              <p className="mt-4 text-lg leading-relaxed text-body">
                Four steps between your idea and a confirmed event.
              </p>
            </div>
          </Reveal>

          <ol data-steps-list className="mt-14">
            {STEPS.map((step) => (
              <li
                key={step.number}
                data-step
                className="grid gap-3 border-t border-line py-8 sm:grid-cols-12 sm:items-baseline sm:gap-6 sm:py-10"
              >
                <span className="text-[2.75rem] font-bold leading-none tracking-tight text-brand/80 tabular-nums sm:col-span-3">
                  {step.number}
                </span>
                <h3 className="text-xl font-bold tracking-tight text-ink sm:col-span-4 sm:text-2xl">
                  {step.title}
                </h3>
                <p className="text-[15px] leading-relaxed text-body sm:col-span-5">
                  {step.description}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ===================================================================
          About
          =================================================================== */}
      <section id="about" className="scroll-mt-24 bg-soft py-24 sm:py-32">
        <div className="mx-auto grid max-w-[1400px] gap-10 px-5 sm:px-8 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-4">
            <Reveal>
              <Eyebrow>About</Eyebrow>
            </Reveal>
          </div>
          <div className="max-w-3xl lg:col-span-8">
            <StaggeredHeading
              lines={['SAS RESERVE, in brief.']}
              className="text-[clamp(2rem,3.6vw,3rem)] leading-[1.1]"
            />
            <Reveal delay={0.1}>
              <p className="mt-6 text-lg leading-relaxed text-body">
                SAS RESERVE is a Smart Facility &amp; Resource Reservation System designed to
                simplify campus event planning and centralized management of facilities and shared
                resources. Facilities are physical spaces; resources are the equipment your event
                depends on — both managed through one secure account.
              </p>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ===================================================================
          Final CTA — layered parallax depth
          =================================================================== */}
      <section data-cta-section className="relative overflow-hidden bg-navy py-24 sm:py-32">
        <div
          data-cta-background
          aria-hidden
          className="pointer-events-none absolute inset-0 scale-[1.25]"
        >
          <div className="absolute -right-48 top-1/2 size-[520px] -translate-y-1/2 rounded-full bg-brand/20 blur-3xl" />
          <div className="absolute -left-40 -bottom-40 size-[420px] rounded-full bg-brand/10 blur-3xl" />
        </div>

        <div className="relative z-10 mx-auto max-w-3xl px-5 text-center">
          <Reveal>
            <Eyebrow onDark centered>
              Get started
            </Eyebrow>
            <StaggeredHeading
              lines={['Ready to plan your next event?']}
              onDark
              className="mt-5 text-[clamp(2.2rem,5vw,3.6rem)] leading-[1.06]"
            />
            <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-white/70">
              Create an account and start managing your campus reservations in one place.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                to="/register"
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-brand px-8 text-[15px] font-semibold text-white shadow-sm transition-colors duration-200 hover:bg-brand-dark sm:w-auto"
              >
                Create an Account
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              <Link
                to="/login"
                className="inline-flex h-12 w-full items-center justify-center rounded-full border border-white/25 px-8 text-[15px] font-semibold text-white transition-colors duration-200 hover:bg-white/10 sm:w-auto"
              >
                Log In
              </Link>
            </div>
            <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-white/50">
              <ShieldCheck className="size-3.5 text-brand-faint" aria-hidden />
              Reservations require an account — there is no guest option.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ===================================================================
          Footer
          =================================================================== */}
      <footer className="border-t border-line bg-white" aria-label="Site footer">
        <div className="mx-auto max-w-[1400px] px-5 py-14 sm:px-8">
          <div className="grid gap-10 md:grid-cols-12">
            <div className="md:col-span-5">
              <BrandMark />
              <p className="mt-5 max-w-sm text-sm leading-relaxed text-body">
                Smart Facility &amp; Resource Reservation System — centralized reservations for
                campus facilities, equipment, and shared resources.
              </p>
            </div>

            <div className="md:col-span-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
                Explore
              </p>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li>
                  <a href="#overview" className="text-body transition-colors hover:text-ink">
                    Overview
                  </a>
                </li>
                <li>
                  <a href="#facilities" className="text-body transition-colors hover:text-ink">
                    Facilities
                  </a>
                </li>
                <li>
                  <a href="#equipment" className="text-body transition-colors hover:text-ink">
                    Equipment
                  </a>
                </li>
                <li>
                  <a href="#about" className="text-body transition-colors hover:text-ink">
                    About
                  </a>
                </li>
              </ul>
            </div>

            <div className="md:col-span-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
                Account
              </p>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li>
                  <Link to="/login" className="text-body transition-colors hover:text-ink">
                    Log In
                  </Link>
                </li>
                <li>
                  <Link to="/register" className="text-body transition-colors hover:text-ink">
                    Create Account
                  </Link>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-6 text-xs text-muted">
            <p>© {new Date().getFullYear()} SAS RESERVE. Managed by the SAS Office.</p>
            <p className="flex items-center gap-1.5">
              <ShieldCheck className="size-3.5 text-status-available" aria-hidden />
              Account required for reservations
            </p>
          </div>
        </div>
      </footer>

      <MobileMenu open={menuOpen} onClose={closeMenu} />
    </div>
  )
}
