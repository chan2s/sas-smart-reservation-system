import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
} from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Check, MailCheck, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { BrandMark } from '@/components/auth/AuthPanel'
import { cn } from '@/lib/utils'

/** Backend error codes → user-friendly states (see accounts/email_otp.py). */
const OTP_ERROR_MESSAGES: Record<string, string> = {
  invalid_token: 'This verification link is invalid or has expired. Please sign in again.',
  invalid_otp: "That code doesn't match. Try again.",
  expired: 'This verification code has expired. Please request a new code.',
  too_many_attempts: 'Too many verification attempts. Please request a new code.',
  resend_cooldown: 'Please wait before requesting another code.',
  resend_exhausted: 'Too many code requests. Please start a new sign-in.',
  already_verified: 'This email address has already been verified. Please sign in.',
  email_failed: "We couldn't send the verification code. Please try again.",
}

const OTP_LENGTH = 6
const RESEND_COOLDOWN_SECONDS = 60
/** How long the success sequence plays before the dashboard takes over. */
const SUCCESS_EXIT_MS = 620
/** How long "Code sent again" holds before the countdown returns. */
const RESEND_CONFIRMATION_MS = 2600

type SubmitStatus = 'idle' | 'submitting' | 'success'
type ResendStatus = 'idle' | 'sending' | 'sent'

/** Tick that draws itself — used for the confirmed submit state. */
function CheckMark() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-4"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M5 12.8l4.2 4.2L19 7.4" className="animate-otp-check" />
    </svg>
  )
}

/** Quiet indeterminate indicator — used instead of a spinning loader. */
function ProgressIndicator({ track, fill }: { track: string; fill: string }) {
  return (
    <span
      aria-hidden
      className={cn('relative block h-1 w-8 overflow-hidden rounded-full', track)}
    >
      <span
        className={cn('absolute inset-y-0 left-0 w-1/3 animate-otp-progress rounded-full', fill)}
      />
    </span>
  )
}

/**
 * First-time Google sign-in email verification. The OAuth callback created
 * the account but deliberately issued NO JWT — the user lands here with a
 * short-lived single-purpose verification token and must prove email
 * ownership before the app authenticates them.
 *
 * The six cells are presentation: one real (visually hidden) input drives
 * them, so the whole control stays a single field for screen readers,
 * keyboard users, autofill, and pasting.
 */
export function VerifyOtpPage() {
  const { user, verifyGoogleOtp } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const verificationToken = searchParams.get('token') ?? ''

  const [code, setCode] = useState('')
  const [status, setStatus] = useState<SubmitStatus>('idle')
  const [resendStatus, setResendStatus] = useState<ResendStatus>('idle')
  const [error, setError] = useState('')
  const [expired, setExpired] = useState(false)
  const [locked, setLocked] = useState(false)
  const [focused, setFocused] = useState(false)
  const [caret, setCaret] = useState(0)
  const [shaking, setShaking] = useState(false)
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS)

  const inputRef = useRef<HTMLInputElement>(null)
  /**
   * Set on the first submit attempt. A successful verify() flips the auth
   * user, which would otherwise redirect instantly and cut the success
   * animation short — this keeps the hand-off on our terms.
   */
  const flowActiveRef = useRef(false)
  /**
   * Where to land once verification succeeds. A brand-new Google account has
   * no affiliation yet, so it completes the affiliation step first; every
   * other account goes straight to the dashboard as before.
   */
  const nextPathRef = useRef('/dashboard')

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

  // The "Code sent again" confirmation steps aside for the countdown.
  useEffect(() => {
    if (resendStatus !== 'sent') return
    const timer = setTimeout(() => setResendStatus('idle'), RESEND_CONFIRMATION_MS)
    return () => clearTimeout(timer)
  }, [resendStatus])

  // Acknowledged: leave only after the cells and the button have said so.
  useEffect(() => {
    if (status !== 'success') return
    const timer = setTimeout(
      () => navigate(nextPathRef.current, { replace: true }),
      SUCCESS_EXIT_MS,
    )
    return () => clearTimeout(timer)
  }, [status, navigate])

  const title = useMemo(() => {
    if (locked) return 'Too many attempts'
    if (expired) return 'Code expired'
    return 'Verify your email'
  }, [locked, expired])

  const isComplete = code.length === OTP_LENGTH
  const isBusy = status !== 'idle'
  /**
   * The cell the next keystroke lands in. Driven by the real caret so arrow
   * keys, clicks and auto-advance all highlight where typing will go.
   */
  const activeIndex =
    focused && status !== 'success' ? Math.min(caret, OTP_LENGTH - 1) : -1

  const syncCaret = useCallback(() => {
    const input = inputRef.current
    if (!input) return
    const position = input.selectionStart ?? input.value.length
    setCaret(Math.min(position, input.value.length, OTP_LENGTH - 1))
  }, [])

  /** Put the caret on a specific cell (and select its digit when retyping). */
  const focusCell = useCallback((index: number) => {
    const input = inputRef.current
    if (!input) return
    input.focus()
    const start = Math.max(0, Math.min(index, OTP_LENGTH - 1, input.value.length))
    // Full code → select the digit so typing replaces instead of overflow.
    const end = input.value.length >= OTP_LENGTH ? start + 1 : start
    requestAnimationFrame(() => {
      input.setSelectionRange(start, end)
      setCaret(start)
    })
  }, [])

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.value.replace(/\D/g, '').slice(0, OTP_LENGTH)
    setCode(next)
    if (error) setError('')
    setCaret(Math.min(event.target.selectionStart ?? next.length, OTP_LENGTH - 1))
  }

  /**
   * With a full code the caret sits between digits, so a keystroke would push
   * the value past `maxLength` and be silently dropped. Selecting the digit
   * under the caret first makes typing replace it — what users expect when
   * they are correcting one digit.
   */
  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (status !== 'idle' || code.length < OTP_LENGTH) return
    if (event.key.length !== 1 || !/\d/.test(event.key)) return
    const position = Math.min(event.currentTarget.selectionStart ?? 0, OTP_LENGTH - 1)
    if (event.currentTarget.selectionStart === event.currentTarget.selectionEnd) {
      event.currentTarget.setSelectionRange(position, position + 1)
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData('text').replace(/\D/g, '')
    if (!pasted) return
    event.preventDefault()
    const input = event.currentTarget
    // A whole code always fills the field from the start; a partial one is
    // inserted at the caret like any other text field.
    let next: string
    if (pasted.length >= OTP_LENGTH) {
      next = pasted.slice(0, OTP_LENGTH)
    } else {
      const start = input.selectionStart ?? code.length
      const end = input.selectionEnd ?? start
      next = (code.slice(0, start) + pasted + code.slice(end)).slice(0, OTP_LENGTH)
    }
    setCode(next)
    if (error) setError('')
    requestAnimationFrame(() => {
      input.setSelectionRange(next.length, next.length)
      setCaret(Math.min(next.length, OTP_LENGTH - 1))
    })
  }

  /** Tapping near a cell puts the caret in it (the input covers the cells). */
  function handleInputClick(event: MouseEvent<HTMLInputElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    if (!rect.width) return
    const ratio = (event.clientX - rect.left) / rect.width
    focusCell(Math.max(0, Math.min(OTP_LENGTH - 1, Math.floor(ratio * OTP_LENGTH))))
  }

  function handleError(err: unknown) {
    if (err instanceof ApiError) {
      const data = err.data as { code?: string } | null
      const errorCode = data?.code ?? ''
      setError(OTP_ERROR_MESSAGES[errorCode] ?? err.message)
      if (errorCode === 'expired' || errorCode === 'invalid_token') setExpired(true)
      if (errorCode === 'too_many_attempts') setLocked(true)
      if (errorCode === 'already_verified') {
        // Fully verified elsewhere — send them to sign in.
        setExpired(true)
      }
    } else {
      setError('Verification failed. Please try again.')
    }

    // Keep the digits, acknowledge with a shake, and hand focus straight back
    // so the next keystroke can replace the code.
    setShaking(true)
    const input = inputRef.current
    if (input) {
      input.focus()
      requestAnimationFrame(() => {
        input.select()
        setCaret(0)
      })
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (status !== 'idle' || !isComplete) return // no duplicate submissions
    flowActiveRef.current = true
    setError('')
    setStatus('submitting')
    try {
      const verified = await verifyGoogleOtp(verificationToken, code)
      // The API is the single source of truth — only a resolved verify()
      // reaches this state, and the exit is handled by the effect above.
      nextPathRef.current = verified.has_affiliation
        ? '/dashboard'
        : '/onboarding/affiliation'
      setStatus('success')
    } catch (err) {
      handleError(err)
      setStatus('idle')
    }
  }

  async function handleResend() {
    if (resendStatus !== 'idle') return // one request at a time
    setError('')
    setExpired(false)
    setResendStatus('sending')
    try {
      await api.resendGoogleOtp(verificationToken)
      setCode('')
      setCooldown(RESEND_COOLDOWN_SECONDS)
      setResendStatus('sent')
      focusCell(0)
    } catch (err) {
      handleError(err)
      setResendStatus('idle')
      // The server holds its own cooldown; start ours so the control can't be
      // hammered while the backend is still refusing sends.
      if (err instanceof ApiError && (err.data as { code?: string } | null)?.code === 'resend_cooldown') {
        setCooldown(RESEND_COOLDOWN_SECONDS)
      }
    }
  }

  if (user && !flowActiveRef.current) {
    return (
      <Navigate
        to={user.has_affiliation ? '/dashboard' : '/onboarding/affiliation'}
        replace
      />
    )
  }
  if (invalidEntry) return null

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-soft px-4 py-10 sm:py-14">
      {/* Background: a single soft brand wash. Deliberately no blurred blobs. */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-[360px] bg-[radial-gradient(58%_100%_at_50%_0%,rgba(79,70,229,0.07),transparent_72%)]" />
      </div>

      <div className="w-full max-w-[400px]">
        {/* Brand — present, but quieter than the task below it. */}
        <div className="mb-7 flex animate-otp-rise flex-col items-center text-center">
          <BrandMark className="justify-center" />
          <p className="mt-2.5 text-[12px] text-muted">
            Smart Facility &amp; Resource Reservation System
          </p>
        </div>

        <div className="card animate-otp-rise p-6 sm:p-7" style={{ animationDelay: '70ms' }}>
          <div
            className="flex size-10 animate-otp-rise items-center justify-center rounded-xl bg-brand-soft text-brand"
            style={{ animationDelay: '130ms' }}
          >
            <MailCheck className="size-5" aria-hidden />
          </div>

          <h2
            className="mt-3.5 animate-otp-rise text-[19px] font-semibold tracking-tight text-ink"
            style={{ animationDelay: '180ms' }}
          >
            {title}
          </h2>
          <p
            id="otp-hint"
            className="mt-1.5 animate-otp-rise text-[13px] leading-relaxed text-body"
            style={{ animationDelay: '230ms' }}
          >
            We&apos;ve sent a 6-digit verification code to your email address.
          </p>

          {!expired && !locked && (
            <form onSubmit={handleSubmit} className="mt-6">
              <div className="relative">
                <label htmlFor="otp" className="sr-only">
                  Verification code
                </label>

                {/* Six cells — aria-hidden: the real field below is the input. */}
                <div
                  data-otp-cells
                  aria-hidden="true"
                  onAnimationEnd={() => setShaking(false)}
                  className={cn(
                    'grid grid-cols-6 gap-1.5 sm:gap-2',
                    shaking && 'animate-otp-shake',
                  )}
                >
                  {Array.from({ length: OTP_LENGTH }, (_, index) => {
                    const digit = code[index] ?? ''
                    const isActive = activeIndex === index
                    const succeeded = status === 'success'
                    const failed = Boolean(error) && !succeeded
                    return (
                      <div
                        key={index}
                        style={succeeded ? { animationDelay: `${index * 45}ms` } : undefined}
                        className={cn(
                          'relative flex h-12 items-center justify-center rounded-xl border bg-surface',
                          'text-[19px] font-semibold tabular-nums text-ink sm:h-14 sm:text-xl',
                          'transition-[border-color,background-color,transform,box-shadow] duration-150 ease-out',
                          succeeded && 'animate-otp-confirm',
                          succeeded
                            ? 'border-status-available/50 bg-status-available-bg text-status-available'
                            : failed
                              ? 'border-status-rejected/55 bg-status-rejected-bg/70 text-status-rejected'
                              : isActive
                                ? '-translate-y-px border-brand bg-brand-soft/45 shadow-[0_0_0_3px_rgba(79,70,229,0.10)]'
                                : digit
                                  ? 'border-line-strong'
                                  : 'border-line',
                        )}
                      >
                        {digit && (
                          <span key={`${index}-${digit}`} className="animate-otp-digit">
                            {digit}
                          </span>
                        )}

                        {isActive && (
                          <span className="absolute inset-x-2 bottom-1 h-0.5 origin-center animate-otp-caret rounded-full bg-brand" />
                        )}
                      </div>
                    )
                  })}
                </div>

                {/* Verified: a quiet line travelling across the cells. */}
                {status === 'success' && (
                  <span
                    aria-hidden
                    className="pointer-events-none absolute inset-0 overflow-hidden rounded-xl"
                  >
                    <span className="absolute inset-y-0 w-1/3 animate-otp-sweep bg-gradient-to-r from-transparent via-status-available/55 to-transparent" />
                  </span>
                )}

                <input
                  ref={inputRef}
                  id="otp"
                  name="otp"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  enterKeyHint="done"
                  maxLength={OTP_LENGTH}
                  value={code}
                  onChange={handleChange}
                  onKeyDown={handleKeyDown}
                  onPaste={handlePaste}
                  onClick={handleInputClick}
                  onSelect={syncCaret}
                  onKeyUp={syncCaret}
                  onFocus={() => {
                    setFocused(true)
                    syncCaret()
                  }}
                  onBlur={() => setFocused(false)}
                  disabled={isBusy}
                  required
                  autoFocus
                  aria-invalid={Boolean(error)}
                  aria-describedby={cn('otp-hint', error && 'otp-error')}
                  className="absolute inset-0 h-full w-full cursor-text rounded-xl border-0 bg-transparent p-0 opacity-0 outline-none"
                />
              </div>

              {error && (
                <p
                  id="otp-error"
                  role="alert"
                  className="mt-3 text-center text-[13px] text-status-rejected"
                >
                  {error}
                </p>
              )}

              <Button
                type="submit"
                size="lg"
                disabled={!isComplete || isBusy}
                style={
                  status === 'success'
                    ? { backgroundColor: 'var(--color-status-available)' }
                    : status === 'submitting'
                      ? { backgroundColor: 'var(--color-brand)' }
                      : undefined
                }
                className={cn(
                  'mt-5 w-full transition-[transform,background-color,color] duration-200 ease-out',
                  status === 'submitting' && 'scale-[0.985]',
                )}
              >
                {status === 'idle' && 'Verify'}

                {status === 'submitting' && (
                  <span className="flex items-center gap-2.5 text-[13px]">
                    <ProgressIndicator track="bg-white/30" fill="bg-white" />
                    Checking…
                  </span>
                )}

                {status === 'success' && (
                  <span className="flex items-center gap-2 text-[13px] font-semibold">
                    <CheckMark />
                    Verified
                  </span>
                )}
              </Button>

              <div className="mt-5 text-center text-[13px]" aria-live="polite">
                {resendStatus === 'sending' ? (
                  <span className="inline-flex items-center gap-2 text-muted">
                    <ProgressIndicator track="bg-brand-faint" fill="bg-brand" />
                    Sending…
                  </span>
                ) : resendStatus === 'sent' ? (
                  <span className="inline-flex items-center gap-1.5 text-status-available">
                    <Check className="size-3.5" aria-hidden />
                    Code sent again
                  </span>
                ) : cooldown > 0 ? (
                  <span className="text-muted">
                    Resend available in <span className="tabular-nums">{cooldown}s</span>
                  </span>
                ) : (
                  <>
                    <span className="text-muted">Didn&apos;t receive the code?</span>{' '}
                    <button
                      type="button"
                      onClick={handleResend}
                      className="rounded font-medium text-brand underline-offset-2 transition-colors hover:text-brand-dark hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                    >
                      Resend code
                    </button>
                  </>
                )}
              </div>
            </form>
          )}

          {(expired || locked) && (
            <div className="mt-6 space-y-4">
              {error && (
                <p
                  role="alert"
                  className="rounded-lg bg-status-rejected-bg px-3 py-2 text-[13px] text-status-rejected"
                >
                  {error}
                </p>
              )}
              <Button
                type="button"
                onClick={handleResend}
                loading={resendStatus === 'sending'}
                disabled={resendStatus !== 'idle'}
                className="w-full"
                size="lg"
              >
                Send a new code
              </Button>
            </div>
          )}
        </div>

        <p
          className="mt-6 flex animate-otp-rise items-center justify-center gap-1.5 text-[12px] text-muted"
          style={{ animationDelay: '330ms' }}
        >
          <ShieldCheck className="size-3.5" aria-hidden />
          Your email is verified once — this won&apos;t be needed on future sign-ins
        </p>

        <p
          className="mt-4 animate-otp-rise text-center text-[13px]"
          style={{ animationDelay: '370ms' }}
        >
          <button
            type="button"
            onClick={() => {
              setSearchParams({}, { replace: true })
              navigate('/login', { replace: true })
            }}
            className="rounded font-medium text-brand transition-colors hover:text-brand-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            Back to sign in
          </button>
        </p>
      </div>
    </div>
  )
}
