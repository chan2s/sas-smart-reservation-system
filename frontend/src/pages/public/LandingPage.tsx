import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  CalendarCheck,
  CalendarDays,
  Check,
  Clock,
  LayoutDashboard,
  Menu,
  Package,
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

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function prefersLightMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
}

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
   Mobile menu
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
   Landing page
   --------------------------------------------------------------------------- */

export function LandingPage() {
  const { data: facilities, isLoading: facilitiesLoading } = useFacilities()
  const { data: equipment } = useEquipment()
  const { data: stats } = useEquipmentStats()

  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)

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

  const equipmentItems = (equipment ?? []).filter((item) => item.is_active).slice(0, 8)

  const rootRef = useRef<HTMLDivElement | null>(null)
  const [activeSection, setActiveSection] = useState('overview')

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return

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

    if (prefersReducedMotion() || prefersLightMotion()) {
      return () => navObserver.disconnect()
    }

    const context = gsap.context(() => {
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
      {/* Sticky premium navigation */}
      <LandingNav
        activeSection={activeSection}
        scrolled={navScrolled}
        onOpenMenu={() => setMenuOpen(true)}
      />

      {/* ===================================================================
          Hero — cinematic video, controlled editorial typography
          =================================================================== */}
      <section
        className="relative flex min-h-[88vh] flex-col overflow-hidden rounded-b-[2rem] bg-navy sm:rounded-b-[3rem]"
        aria-label="Introduction"
      >
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

        <div
          className="absolute inset-0 bg-gradient-to-r from-navy/95 via-navy/55 to-navy/10"
          aria-hidden
        />
        <div
          className="absolute inset-0 bg-gradient-to-b from-navy/55 via-navy/10 to-navy/35"
          aria-hidden
        />

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
                className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-brand px-8 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:bg-brand-dark hover:shadow-pop"
              >
                Create an Account
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              <a
                href="#facilities"
                className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-white/25 bg-white/10 px-8 text-sm font-semibold text-white backdrop-blur-sm transition-all duration-200 hover:bg-white/20"
              >
                Explore Facilities
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
          Value proposition — centered, spacious, editorial
          =================================================================== */}
      <section
        id="overview"
        data-intro-section
        className="scroll-mt-24 bg-white py-28 sm:py-36 lg:py-44"
      >
        <div className="mx-auto max-w-[var(--container-max)] px-5 sm:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <Reveal>
              <Eyebrow centered>Overview</Eyebrow>
            </Reveal>
            <Reveal delay={0.08}>
              <h2 className="mt-6 text-[clamp(2.2rem,4.5vw,3.8rem)] font-bold leading-[1.06] tracking-tight text-ink">
                Everything you need
                <br />
                to plan your next event.
              </h2>
            </Reveal>
            <Reveal delay={0.16}>
              <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-body">
                SAS RESERVE brings facility reservations, shared equipment, availability, and
                event planning together in one centralized platform.
              </p>
            </Reveal>
          </div>

          {/* Feature highlights — three-column cards */}
          <div
            data-intro-visual
            className="mx-auto mt-16 grid max-w-5xl gap-5 sm:grid-cols-3"
          >
            {[
              {
                icon: <CalendarCheck className="size-5" aria-hidden />,
                title: 'One booking flow',
                description:
                  'Facilities, equipment, and approvals in a single request.',
              },
              {
                icon: <Clock className="size-5" aria-hidden />,
                title: 'Real-time availability',
                description:
                  'Live checks against schedules and inventory before you commit.',
              },
              {
                icon: <ShieldCheck className="size-5" aria-hidden />,
                title: 'Account-based access',
                description:
                  'Secure sign-in — every reservation is tied to an account.',
              },
            ].map((item) => (
              <Reveal key={item.title} delay={0.1}>
                <div className="landing-card group p-7 sm:p-8">
                  <span className="flex size-11 items-center justify-center rounded-2xl bg-brand-soft text-brand transition-colors duration-200 group-hover:bg-brand group-hover:text-white">
                    {item.icon}
                  </span>
                  <h3 className="mt-5 text-[15px] font-semibold tracking-tight text-ink">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-body">
                    {item.description}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ===================================================================
          Large visual block — parallax facility imagery
          =================================================================== */}
      <section data-visual-block className="relative overflow-hidden bg-soft pb-28 sm:pb-36 lg:pb-44">
        <div className="mx-auto max-w-[var(--container-max-wide)] px-5 sm:px-8">
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
          Facilities — asymmetric editorial grid
          =================================================================== */}
      <section id="facilities" className="scroll-mt-24 bg-white py-28 sm:py-36 lg:py-44">
        <div className="mx-auto max-w-[var(--container-max-wide)] px-5 sm:px-8">
          <Reveal>
            <div className="mx-auto max-w-3xl text-center">
              <Eyebrow centered>Facilities</Eyebrow>
              <h2 className="mt-6 text-[clamp(2.2rem,4.5vw,3.8rem)] font-bold leading-[1.06] tracking-tight text-ink">
                Spaces made
                <br />
                for your events.
              </h2>
              <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-body">
                Browse available campus facilities — from auditoriums to meeting rooms —
                each ready for your next event.
              </p>
            </div>
          </Reveal>

          <Reveal delay={0.1}>
            <div className="mt-10 flex justify-center">
              <Link
                to="/facilities"
                className="group inline-flex items-center gap-2 rounded-full border border-line bg-soft px-5 py-2.5 text-sm font-semibold text-ink transition-all duration-200 hover:border-line-strong hover:bg-surface hover:shadow-card"
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
            <div className="mt-14 grid gap-5 lg:grid-cols-12">
              <div className="skeleton aspect-[16/10] rounded-[2rem] lg:col-span-8" aria-hidden />
              <div className="grid content-start gap-5 lg:col-span-4">
                <div className="skeleton aspect-[16/9] rounded-2xl" aria-hidden />
                <div className="skeleton aspect-[16/9] rounded-2xl" aria-hidden />
              </div>
            </div>
          ) : activeFacilities.length === 0 ? (
            <p className="mt-14 text-center text-sm text-muted">No facilities are published yet.</p>
          ) : (
            <div className="mt-14 grid gap-5 lg:grid-cols-12">
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
                        className="absolute inset-0 bg-gradient-to-t from-navy/60 via-navy/10 to-transparent"
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
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white backdrop-blur-sm transition-colors duration-200 group-hover:bg-white/25">
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

              <div className="grid content-start gap-5 lg:col-span-4">
                {secondary.map((facility) => {
                  const operational = facility.status === 'OPERATIONAL'
                  return (
                    <Link
                      key={facility.id}
                      to={`/facilities/${facility.id}`}
                      className="group block"
                    >
                      <article className="relative aspect-[16/9] overflow-hidden rounded-2xl border border-line bg-soft transition-all duration-300 hover:border-line-strong hover:shadow-card">
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
                          className="absolute inset-0 bg-gradient-to-t from-navy/60 via-navy/10 to-transparent"
                          aria-hidden
                        />
                        <span
                          className={cn(
                            'absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold backdrop-blur-md',
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
          Equipment — stats + real inventory
          =================================================================== */}
      <section id="equipment" className="scroll-mt-24 bg-soft py-28 sm:py-36 lg:py-44">
        <div className="mx-auto max-w-[var(--container-max-wide)] px-5 sm:px-8">
          <Reveal>
            <div className="mx-auto max-w-3xl text-center">
              <Eyebrow centered>Equipment</Eyebrow>
              <h2 className="mt-6 text-[clamp(2.2rem,4.5vw,3.8rem)] font-bold leading-[1.06] tracking-tight text-ink">
                Everything your
                <br />
                event needs.
              </h2>
              <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-body">
                From AV systems to furniture — browse available equipment and reserve
                what your event requires.
              </p>
            </div>
          </Reveal>

          <Reveal delay={0.1}>
            <div className="mt-10 flex justify-center">
              <Link
                to="/equipment"
                className="group inline-flex items-center gap-2 rounded-full border border-line bg-surface px-5 py-2.5 text-sm font-semibold text-ink transition-all duration-200 hover:border-line-strong hover:shadow-card"
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
            <Reveal delay={0.12}>
              <dl className="mx-auto mt-14 grid max-w-4xl grid-cols-2 gap-4 lg:grid-cols-4">
                {[
                  {
                    label: 'Equipment types',
                    value: stats.equipment_types,
                    color: 'text-ink',
                  },
                  {
                    label: 'Total units',
                    value: stats.total_units,
                    color: 'text-ink',
                  },
                  {
                    label: 'Available now',
                    value: stats.available_units,
                    color: 'text-status-available',
                    sub: 'units ready to reserve',
                  },
                  {
                    label: 'Reserved',
                    value: stats.reserved_units,
                    color: 'text-status-approved',
                    sub: 'units in current reservations',
                  },
                ].map((stat) => (
                  <div
                    key={stat.label}
                    className="landing-card p-6 text-center sm:p-7"
                  >
                    <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
                      {stat.label}
                    </dt>
                    <dd className={cn('mt-3 text-3xl font-bold tabular-nums tracking-tight sm:text-4xl', stat.color)}>
                      {stat.value}
                    </dd>
                    {stat.sub && (
                      <dd className="mt-1 text-xs text-muted">{stat.sub}</dd>
                    )}
                  </div>
                ))}
              </dl>
            </Reveal>
          )}

          {equipmentItems.length === 0 ? (
            <p className="mt-12 text-center text-sm text-muted">
              Equipment inventory is being prepared — check back soon.
            </p>
          ) : (
            <ul className="mx-auto mt-14 grid max-w-5xl gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {equipmentItems.map((item) => (
                <li key={item.id} data-equipment-card>
                  <Link
                    to={`/equipment/${item.id}`}
                    className="landing-card group flex h-full flex-col p-6"
                  >
                    <span className="flex size-11 items-center justify-center rounded-2xl bg-brand-soft text-brand transition-colors duration-200 group-hover:bg-brand group-hover:text-white">
                      <Package className="size-5" aria-hidden />
                    </span>
                    <h3 className="mt-5 text-[15px] font-semibold tracking-tight text-ink">
                      {item.name}
                    </h3>
                    <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-body">
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
          How it works — clean numbered steps
          =================================================================== */}
      <section id="process" className="scroll-mt-24 bg-white py-28 sm:py-36 lg:py-44">
        <div className="mx-auto max-w-[var(--container-max)] px-5 sm:px-8">
          <Reveal>
            <div className="mx-auto max-w-3xl text-center">
              <Eyebrow centered>Process</Eyebrow>
              <h2 className="mt-6 text-[clamp(2.2rem,4.5vw,3.8rem)] font-bold leading-[1.06] tracking-tight text-ink">
                How it works.
              </h2>
              <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-body">
                Four steps between your idea and a confirmed event.
              </p>
            </div>
          </Reveal>

          <ol data-steps-list className="mx-auto mt-16 max-w-4xl">
            {STEPS.map((step) => (
              <li
                key={step.number}
                data-step
                className="group grid gap-4 border-t border-line py-10 sm:grid-cols-12 sm:items-baseline sm:gap-8 sm:py-12"
              >
                <span className="text-[2.75rem] font-bold leading-none tracking-tight text-brand/70 tabular-nums transition-colors duration-200 group-hover:text-brand sm:col-span-2">
                  {step.number}
                </span>
                <h3 className="text-xl font-bold tracking-tight text-ink sm:col-span-4 sm:text-2xl">
                  {step.title}
                </h3>
                <p className="text-[15px] leading-relaxed text-body sm:col-span-6">
                  {step.description}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ===================================================================
          About — editorial split
          =================================================================== */}
      <section id="about" className="scroll-mt-24 bg-soft py-28 sm:py-36 lg:py-44">
        <div className="mx-auto grid max-w-[var(--container-max)] gap-12 px-5 sm:px-8 lg:grid-cols-12 lg:gap-16">
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
              <p className="mt-7 text-lg leading-relaxed text-body">
                SAS RESERVE is a Smart Facility &amp; Resource Reservation System designed to
                simplify campus event planning and centralized management of facilities and shared
                resources. Facilities are physical spaces; resources are the equipment your event
                depends on — both managed through one secure account.
              </p>
            </Reveal>
            <Reveal delay={0.18}>
              <div className="mt-8 grid gap-4 sm:grid-cols-3">
                {[
                  { icon: <Building2 className="size-5" aria-hidden />, label: 'Facility management' },
                  { icon: <Package className="size-5" aria-hidden />, label: 'Resource tracking' },
                  { icon: <CalendarDays className="size-5" aria-hidden />, label: 'Event scheduling' },
                ].map((item) => (
                  <div key={item.label} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
                      {item.icon}
                    </span>
                    <span className="text-sm font-medium text-ink">{item.label}</span>
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ===================================================================
          Final CTA — dark cinematic
          =================================================================== */}
      <section data-cta-section className="relative overflow-hidden bg-navy py-28 sm:py-36 lg:py-44">
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
            <h2 className="mt-6 text-[clamp(2.2rem,5vw,3.6rem)] font-bold leading-[1.06] tracking-tight text-white">
              Ready to plan your next event?
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-white/70">
              Create an account and start managing your campus reservations in one place.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                to="/register"
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-brand px-8 text-[15px] font-semibold text-white shadow-sm transition-all duration-200 hover:bg-brand-dark hover:shadow-pop sm:w-auto"
              >
                Create an Account
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              <Link
                to="/login"
                className="inline-flex h-12 w-full items-center justify-center rounded-full border border-white/25 px-8 text-[15px] font-semibold text-white transition-all duration-200 hover:bg-white/10 sm:w-auto"
              >
                Log In
              </Link>
            </div>
            <p className="mt-7 flex items-center justify-center gap-1.5 text-xs text-white/50">
              <ShieldCheck className="size-3.5 text-brand-faint" aria-hidden />
              Reservations require an account — there is no guest option.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ===================================================================
          Footer — premium minimal
          =================================================================== */}
      <footer className="border-t border-line bg-white" aria-label="Site footer">
        <div className="mx-auto max-w-[var(--container-max-wide)] px-5 py-16 sm:px-8 sm:py-20">
          <div className="grid gap-12 md:grid-cols-12 md:gap-8">
            <div className="md:col-span-5">
              <BrandMark />
              <p className="mt-5 max-w-sm text-sm leading-relaxed text-body">
                Smart Facility &amp; Resource Reservation System — centralized reservations for
                campus facilities, equipment, and shared resources.
              </p>
              <div className="mt-6 flex items-center gap-1.5 text-xs text-muted">
                <ShieldCheck className="size-3.5 text-status-available" aria-hidden />
                Account required for reservations
              </div>
            </div>

            <div className="md:col-span-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
                Explore
              </p>
              <ul className="mt-5 space-y-3 text-sm">
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
              <ul className="mt-5 space-y-3 text-sm">
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

          <div className="mt-14 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-8 text-xs text-muted">
            <p>&copy; {new Date().getFullYear()} SAS RESERVE. Managed by the SAS Office.</p>
            <p className="flex items-center gap-1.5">
              <LayoutDashboard className="size-3.5" aria-hidden />
              Built for campus event management
            </p>
          </div>
        </div>
      </footer>

      <MobileMenu open={menuOpen} onClose={closeMenu} />
    </div>
  )
}
