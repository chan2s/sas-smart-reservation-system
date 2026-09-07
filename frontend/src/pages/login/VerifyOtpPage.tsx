import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { CalendarDays, MailCheck, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Backdrop } from '@/components/decor/Backdrop'

/** Backend error codes → user-friendly states (see accounts/email_otp.py). */
const OTP_ERROR_MESSAGES: Record<string, string> = {
  invalid_token: 'This verification link is invalid or has expired. Please sign in again.',
  invalid_otp: 'Invalid verification code.',
  expired: 'This verification code has expired. Please request a new code.',
  too_many_attempts: 'Too many verification attempts. Please request a new code.',
  resend_cooldown: 'Please wait before requesting another code.',
  resend_exhausted: 'Too many code requests. Please start a new sign-in.',
  already_verified: 'This email address has already been verified. Please sign in.',
  email_failed: "We couldn't send the verification code. Please try again.",
}

const RESEND_COOLDOWN_SECONDS = 60

/**
 * First-time Google sign-in email verification. The OAuth callback created
 * the account but deliberately issued NO JWT — the user lands here with a
 * short-lived single-purpose verification token and must prove email
 * ownership before the app authenticates them.
 */
export function VerifyOtpPage() {
  const { user, verifyGoogleOtp } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const verificationToken = searchParams.get('token') ?? ''
  const [otp, setOtp] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [expired, setExpired] = useState(false)
  const [locked, setLocked] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS)

  // No valid token (or already signed in) → back to login.
  const invalidEntry = !verificationToken
  useEffect(() => {
    if (invalidEntry) navigate('/login', { replace: true })
  }, [invalidEntry, navigate])

  // Resend countdown.
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setTimeout(() => setCooldown((value) => value - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  const title = useMemo(() => {
    if (locked) return 'Too many attempts'
    if (expired) return 'Code expired'
    return 'Verify your email'
  }, [locked, expired])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await verifyGoogleOtp(verificationToken, otp.replace(/\s/g, ''))
      navigate('/', { replace: true })
    } catch (err) {
      handleError(err)
    } finally {
      setSubmitting(false)
    }
  }

  function handleError(err: unknown) {
    if (err instanceof ApiError) {
      const data = err.data as { code?: string } | null
      const code = data?.code ?? ''
      setError(OTP_ERROR_MESSAGES[code] ?? err.message)
      if (code === 'expired' || code === 'invalid_token') setExpired(true)
      if (code === 'too_many_attempts') setLocked(true)
      if (code === 'already_verified') {
        // Fully verified elsewhere — send them to sign in.
        setExpired(true)
      }
    } else {
      setError('Verification failed. Please try again.')
    }
  }

  async function handleResend() {
    setError('')
    setNotice('')
    setExpired(false)
    setResending(true)
    try {
      await api.resendGoogleOtp(verificationToken)
      setNotice('A new verification code has been sent.')
      setOtp('')
      setCooldown(RESEND_COOLDOWN_SECONDS)
    } catch (err) {
      handleError(err)
      // A successful-ish cooldown error still restarts nothing — keep the
      // existing countdown running so the button stays honest.
    } finally {
      setResending(false)
    }
  }

  if (user) return <Navigate to="/" replace />
  if (invalidEntry) return null

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-soft px-4 py-12">
      <Backdrop />

      <div className="w-full max-w-[400px]">
        {/* Brand */}
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-brand text-white shadow-card-hover">
            <CalendarDays className="size-6" aria-hidden />
          </div>
          <h1 className="mt-4 text-[22px] font-bold tracking-tight text-ink">SAS RESERVE</h1>
          <p className="mt-1 text-sm text-body">
            Smart Facility &amp; Resource Reservation System
          </p>
        </div>

        <div className="card p-7 sm:p-8">
          <div className="flex size-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <MailCheck className="size-5" aria-hidden />
          </div>
          <h2 className="mt-3 text-xl font-semibold text-ink">{title}</h2>
          <p className="mt-1 text-sm text-body">
            We&apos;ve sent a 6-digit verification code to your email address.
          </p>

          {notice && (
            <p
              role="status"
              className="mt-4 rounded-lg bg-brand-soft px-3 py-2 text-sm text-brand-dark"
            >
              {notice}
            </p>
          )}

          {!expired && !locked && (
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <label htmlFor="otp" className="block text-sm font-medium text-ink">
                Verification code
                <input
                  id="otp"
                  name="otp"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  maxLength={6}
                  value={otp}
                  onChange={(event) =>
                    setOtp(event.target.value.replace(/[^\d]/g, '').slice(0, 6))
                  }
                  required
                  autoFocus
                  className="mt-1.5 block w-full rounded-xl border border-line bg-surface px-4 py-2.5 text-center text-lg tracking-[0.5em] text-ink shadow-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
                />
              </label>

              {error && (
                <p
                  role="alert"
                  className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected"
                >
                  {error}
                </p>
              )}

              <Button type="submit" loading={submitting} className="w-full" size="lg">
                Verify
              </Button>
            </form>
          )}

          {(expired || locked) && (
            <div className="mt-6 space-y-4">
              {error && (
                <p
                  role="alert"
                  className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected"
                >
                  {error}
                </p>
              )}
              <Button
                type="button"
                onClick={handleResend}
                loading={resending}
                className="w-full"
                size="lg"
              >
                Send a new code
              </Button>
            </div>
          )}

          {!expired && !locked && (
            <button
              type="button"
              onClick={handleResend}
              disabled={resending || cooldown > 0}
              className="mt-4 w-full text-center text-xs font-medium text-muted transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
            >
              {resending
                ? 'Sending…'
                : cooldown > 0
                  ? `Resend code available in ${cooldown}s`
                  : 'Resend code'}
            </button>
          )}
        </div>

        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted">
          <ShieldCheck className="size-3.5" aria-hidden />
          Your email is verified once — this won&apos;t be needed on future sign-ins
        </p>

        <p className="mt-4 text-center text-sm">
          <button
            type="button"
            onClick={() => {
              setSearchParams({}, { replace: true })
              navigate('/login', { replace: true })
            }}
            className="font-medium text-brand transition-colors hover:text-brand-dark"
          >
            Back to sign in
          </button>
        </p>
      </div>
    </div>
  )
}
