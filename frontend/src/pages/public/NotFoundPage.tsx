import { Link } from 'react-router-dom'
import { ArrowLeft, Building2 } from 'lucide-react'

export function NotFoundPage() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-soft px-6 text-center">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div className="absolute -right-40 -top-40 size-[440px] rounded-full bg-blob-indigo/40 blur-3xl" />
        <div className="absolute -bottom-48 -left-32 size-[400px] rounded-full bg-blob-blue/30 blur-3xl" />
      </div>

      <div className="relative z-10">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-brand text-white shadow-card-hover">
          <Building2 className="size-6" aria-hidden />
        </span>
        <p className="mt-8 text-[11px] font-semibold uppercase tracking-[0.24em] text-brand">
          Error 404
        </p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
          This page doesn&apos;t exist.
        </h1>
        <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-body">
          The page you&apos;re looking for may have moved or never existed. Let&apos;s get you
          back to something useful.
        </p>

        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            to="/"
            className="inline-flex h-12 items-center gap-2 rounded-full bg-brand px-7 text-[15px] font-semibold text-white transition-colors duration-200 hover:bg-brand-dark"
          >
            <ArrowLeft className="size-4" aria-hidden />
            Back to Home
          </Link>
          <Link
            to="/login"
            className="inline-flex h-12 items-center rounded-full border border-line bg-surface px-7 text-[15px] font-semibold text-ink transition-colors duration-200 hover:bg-soft"
          >
            Log In
          </Link>
        </div>
      </div>
    </div>
  )
}