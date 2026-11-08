import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CalendarDays,
  ClipboardList,
  GraduationCap,
  Layers,
  Package,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { BrandMark } from '@/components/auth/AuthPanel'
import { ChatWidget } from '@/components/chatbot/ChatWidget'
import { ABOUT_NAV_ITEMS, LandingNav, MobileMenu } from '@/components/landing/LandingNav'
import { Eyebrow, Reveal } from '@/components/landing/LandingMotion'

const CAPABILITIES = [
  {
    icon: <Building2 className="size-5" aria-hidden />,
    title: 'Explore facilities',
    description:
      'Browse the campus spaces available for events, with capacity and operating details in one place.',
  },
  {
    icon: <ClipboardList className="size-5" aria-hidden />,
    title: 'Submit reservation requests',
    description:
      'File a structured request for the facilities and equipment your event needs — no separate forms.',
  },
  {
    icon: <CalendarDays className="size-5" aria-hidden />,
    title: 'Manage requirements',
    description:
      'Track approvals, schedules, and check-in details from a single, organized reservation record.',
  },
]

const PROJECT_FACTS = [
  { label: 'Project', value: 'SAS RESERVE', icon: <Sparkles className="size-4" aria-hidden /> },
  { label: 'Group', value: 'Group 10', icon: <Layers className="size-4" aria-hidden /> },
  {
    label: 'Institution',
    value: 'Negros Oriental State University – Bayawan-Sta. Catalina Campus',
    icon: <GraduationCap className="size-4" aria-hidden />,
  },
  {
    label: 'Project Type',
    value: 'Academic Capstone Project',
    icon: <GraduationCap className="size-4" aria-hidden />,
  },
]

export function AboutPage() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [navScrolled, setNavScrolled] = useState(false)

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  useEffect(() => {
    const onScroll = () => setNavScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="bg-white text-ink">
      <LandingNav
        items={ABOUT_NAV_ITEMS}
        activeTo="/about"
        scrolled={navScrolled}
        onOpenMenu={() => setMenuOpen(true)}
      />

      {/* ===================================================================
          Hero — the identity statement of SAS RESERVE
          =================================================================== */}
      <section
        className="relative overflow-hidden rounded-b-[2rem] bg-navy pb-24 pt-36 sm:rounded-b-[3rem] sm:pb-32 sm:pt-44"
        aria-labelledby="about-title"
      >
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
          <div
            className="absolute inset-0 opacity-[0.07]"
            style={{
              backgroundImage:
                'linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)',
              backgroundSize: '72px 72px',
            }}
          />
          <div className="absolute -right-40 -top-40 size-[520px] rounded-full bg-brand/25 blur-3xl" />
          <div className="absolute -bottom-56 -left-32 size-[420px] rounded-full bg-brand/10 blur-3xl" />
        </div>

        <div className="relative z-10 mx-auto max-w-[var(--container-max)] px-5 sm:px-8">
          <Link
            to="/"
            className="inline-flex items-center gap-2 rounded-lg text-sm font-medium text-white/60 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-faint"
          >
            <ArrowLeft className="size-4" aria-hidden />
            Back to home
          </Link>

          <div className="mt-10 max-w-3xl">
            <Reveal>
              <Eyebrow onDark>About Us</Eyebrow>
            </Reveal>
            <Reveal delay={0.08}>
              <h1
                id="about-title"
                className="mt-6 text-[clamp(2.75rem,6vw,4.75rem)] font-extrabold leading-[0.98] tracking-[-0.035em] text-white"
              >
                SAS RESERVE
              </h1>
            </Reveal>
            <Reveal delay={0.16}>
              <p className="mt-6 max-w-2xl text-xl font-medium leading-snug text-white/85 sm:text-2xl">
                A Smart Web-Based Facility and Resource Reservation System for NORSU-BSC
              </p>
            </Reveal>
            <Reveal delay={0.24}>
              <p className="mt-6 max-w-2xl text-base leading-relaxed text-white/65">
                SAS Reserve is a web-based platform developed to streamline and modernize the
                facility and resource reservation process at Negros Oriental State University –
                Bayawan-Sta. Catalina Campus (NORSU-BSC).
              </p>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ===================================================================
          What the platform does — editorial split
          =================================================================== */}
      <section className="bg-white py-24 sm:py-32 lg:py-40" aria-labelledby="about-platform">
        <div className="mx-auto grid max-w-[var(--container-max)] gap-12 px-5 sm:px-8 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-4">
            <Reveal>
              <Eyebrow>The platform</Eyebrow>
            </Reveal>
          </div>
          <div className="max-w-3xl lg:col-span-8">
            <Reveal delay={0.06}>
              <h2
                id="about-platform"
                className="text-[clamp(2rem,3.6vw,3rem)] font-bold leading-[1.08] tracking-tight text-ink"
              >
                One centralized place for campus reservations.
              </h2>
            </Reveal>
            <Reveal delay={0.14}>
              <p className="mt-7 text-lg leading-relaxed text-body">
                It provides a centralized platform where internal and external organizations can
                explore available facilities, submit reservation requests, and manage their
                facility requirements through a more convenient and organized process.
              </p>
            </Reveal>
            <Reveal delay={0.2}>
              <div className="mt-10 grid gap-4 sm:grid-cols-3">
                {CAPABILITIES.map((item) => (
                  <div key={item.title} className="landing-card group p-6">
                    <span className="flex size-11 items-center justify-center rounded-2xl bg-brand-soft text-brand transition-colors duration-200 group-hover:bg-brand group-hover:text-white">
                      {item.icon}
                    </span>
                    <h3 className="mt-5 text-[15px] font-semibold tracking-tight text-ink">
                      {item.title}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-body">{item.description}</p>
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ===================================================================
          Capstone project — facts
          =================================================================== */}
      <section className="bg-soft py-24 sm:py-32 lg:py-40" aria-labelledby="about-capstone">
        <div className="mx-auto max-w-[var(--container-max)] px-5 sm:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <Reveal>
              <Eyebrow centered>Academic project</Eyebrow>
            </Reveal>
            <Reveal delay={0.08}>
              <h2
                id="about-capstone"
                className="mt-6 text-[clamp(2.2rem,4.5vw,3.4rem)] font-bold leading-[1.06] tracking-tight text-ink"
              >
                Our Capstone Project
              </h2>
            </Reveal>
            <Reveal delay={0.14}>
              <p className="mx-auto mt-5 max-w-2xl text-lg leading-relaxed text-body">
                SAS Reserve is developed as an academic capstone project by Group 10. The project
                aims to improve reservation accessibility, operational efficiency, and resource
                management at NORSU-BSC through a centralized web-based reservation platform.
              </p>
            </Reveal>
          </div>

          <Reveal delay={0.18}>
            <dl className="mx-auto mt-14 grid max-w-5xl gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2">
              {PROJECT_FACTS.map((fact) => (
                <div key={fact.label} className="bg-surface p-6 sm:p-8">
                  <dt className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
                    <span className="text-brand">{fact.icon}</span>
                    {fact.label}
                  </dt>
                  <dd className="mt-3 text-[15px] font-semibold leading-snug tracking-tight text-ink sm:text-base">
                    {fact.value}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>
      </section>

      {/* ===================================================================
          Developer credit — a single, explicit attribution
          =================================================================== */}
      <section className="bg-white py-24 sm:py-32 lg:py-40" aria-labelledby="about-developer">
        <div className="mx-auto max-w-[var(--container-max)] px-5 sm:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <Reveal>
              <Eyebrow centered>Developer</Eyebrow>
            </Reveal>
            <Reveal delay={0.08}>
              <h2
                id="about-developer"
                className="mt-6 text-[clamp(2.2rem,4.5vw,3.4rem)] font-bold leading-[1.06] tracking-tight text-ink"
              >
                Developed by
              </h2>
            </Reveal>
          </div>

          <Reveal delay={0.16}>
            <div className="mx-auto mt-12 max-w-3xl overflow-hidden rounded-3xl border border-line bg-surface shadow-card">
              <div className="grid gap-8 p-8 sm:grid-cols-[auto_1fr] sm:items-center sm:gap-10 sm:p-10">
                {/* Profile image placeholder — initials stand in for a photo. */}
                <div className="flex size-24 items-center justify-center rounded-2xl bg-navy text-2xl font-bold tracking-wide text-white sm:size-28">
                  CPG
                  <span className="sr-only">Profile image placeholder</span>
                </div>
                <div>
                  <p className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-brand">
                    <ShieldCheck className="size-3.5" aria-hidden />
                    Developer
                  </p>
                  <h3 className="mt-4 text-2xl font-bold tracking-tight text-ink sm:text-[1.75rem]">
                    Cristian Paul Guillen
                  </h3>
                  <p className="mt-1.5 text-sm text-body">
                    Developer · Group 10 Capstone Project
                  </p>
                  <p className="mt-5 max-w-md text-sm leading-relaxed text-body">
                    Designed and built SAS Reserve as the Group 10 capstone project for
                    NORSU-BSC.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 border-t border-line bg-soft px-8 py-4 text-xs text-muted sm:px-10">
                <Package className="size-3.5" aria-hidden />
                Project: SAS RESERVE
                <span className="text-faint" aria-hidden>
                  ·
                </span>
                Group 10
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ===================================================================
          Return to the landing page / start using SAS RESERVE
          =================================================================== */}
      <section className="relative overflow-hidden bg-navy py-24 sm:py-28">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 overflow-hidden"
        >
          <div className="absolute -right-40 top-1/2 size-[420px] -translate-y-1/2 rounded-full bg-brand/20 blur-3xl" />
          <div className="absolute -bottom-40 -left-32 size-[360px] rounded-full bg-brand/10 blur-3xl" />
        </div>

        <div className="relative z-10 mx-auto max-w-3xl px-5 text-center">
          <Reveal>
            <h2 className="text-[clamp(2rem,4.5vw,3rem)] font-bold leading-[1.08] tracking-tight text-white">
              Explore SAS RESERVE
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-white/70">
              Return to the landing page to browse facilities and equipment, or start a
              reservation request without an account.
            </p>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                to="/"
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-brand px-8 text-[15px] font-semibold text-white shadow-sm transition-all duration-200 hover:bg-brand-dark hover:shadow-pop sm:w-auto"
              >
                <ArrowLeft className="size-4" aria-hidden />
                Back to Home
              </Link>
              <Link
                to="/reserve"
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full border border-white/25 px-8 text-[15px] font-semibold text-white transition-all duration-200 hover:bg-white/10 sm:w-auto"
              >
                Create Reservation
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-line bg-white" aria-label="Site footer">
        <div className="mx-auto flex max-w-[var(--container-max-wide)] flex-col gap-4 px-5 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <Link to="/" aria-label="SAS Reserve home">
            <BrandMark />
          </Link>
          <p className="text-xs text-muted">
            &copy; {new Date().getFullYear()} SAS RESERVE · Group 10 Capstone Project ·
            NORSU-BSC
          </p>
        </div>
      </footer>

      <MobileMenu
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        items={ABOUT_NAV_ITEMS}
      />

      <ChatWidget />
    </div>
  )
}
