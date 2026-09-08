import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { CalendarDays, Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Field, Input } from '@/components/ui/Form'
import { Backdrop } from '@/components/decor/Backdrop'

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  not_configured:
    'Google sign-in is not available right now. Please use your username and password.',
  invalid_state:
    'The sign-in request expired or was tampered with. Please try again.',
  cancelled: 'Google sign-in was cancelled.',
  missing_code: 'Google did not return an authorization code. Please try again.',
  token_exchange_failed: 'We could not verify your Google sign-in. Please try again.',
  identity_failed: 'We could not read your Google profile. Please try again.',
  email_unverified:
    'Your Google account email is not verified. Use a verified account or sign in with your password.',
  twofa_required:
    'This account uses two-factor authentication. Sign in with your password to complete verification.',
  otp_send_failed:
    "We couldn't send a verification code to your email. Please sign in with Google again to retry.",
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden>
      <path
        fill="#4285F4"
        d="M23.5 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.45a5.52 5.52 0 0 1-2.4 3.62v3h3.87c2.26-2.09 3.58-5.16 3.58-8.81Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.87-3c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.29v3.1A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.28a7.2 7.2 0 0 1 0-4.56v-3.1H1.29a12 12 0 0 0 0 10.76l3.98-3.1Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.76c1.76 0 3.34.6 4.58 1.8l3.44-3.44A11.97 11.97 0 0 0 12 0 12 12 0 0 0 1.29 6.62l3.98 3.1C6.22 6.87 8.87 4.76 12 4.76Z"
      />
    </svg>
  )
}

export function LoginPage() {
  const { user, login, verifyTwoFactorLogin } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [step, setStep] = useState<'credentials' | 'twofa'>('credentials')
  const [mfaToken, setMfaToken] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  // OAuth failures come back as /login?google_error=… (see backend callback).
  useEffect(() => {
    const googleError = searchParams.get('google_error')
    if (googleError) {
      setError(GOOGLE_ERROR_MESSAGES[googleError] ?? 'Google sign-in failed. Please try again.')
    }
    if (searchParams.get('social') === '2fa') {
      setError(
        'This account uses two-factor authentication. Sign in with your password to continue.',
      )
    }
  }, [searchParams])

  if (user) return <Navigate to="/" replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      if (step === 'twofa') {
        await verifyTwoFactorLogin(mfaToken, totpCode.trim())
        navigate('/', { replace: true })
        return
      }
      await login(username.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        const mfaToken = (err as ApiError & { mfaToken?: string }).mfaToken
        if (mfaToken) {
          // Credentials were valid — the account requires a TOTP code.
          setMfaToken(mfaToken)
          setStep('twofa')
          setTotpCode('')
          return
        }
      }
      setError(
        err instanceof ApiError
          ? err.message
          : 'Unable to sign in. Check your credentials and try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function handleGoogle() {
    setError('')
    setGoogleLoading(true)
    try {
      // The backend issues the signed state and returns the consent URL.
      // The secret never touches the frontend.
      const { authorize_url } = await api.googleStart()
      window.location.href = authorize_url
    } catch {
      setError('Google sign-in is unavailable. Please use your username and password.')
      setGoogleLoading(false)
    }
  }

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
          {step === 'credentials' ? (
            <>
              <h2 className="text-xl font-semibold text-ink">Sign in</h2>
              <p className="mt-1 text-sm text-body">
                Access your reservations and institutional resources.
              </p>

              <button
                type="button"
                onClick={handleGoogle}
                disabled={googleLoading}
                className="mt-6 flex w-full items-center justify-center gap-2.5 rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink shadow-sm transition-colors duration-150 hover:bg-soft disabled:opacity-60"
              >
                <GoogleIcon />
                {googleLoading ? 'Redirecting to Google…' : 'Continue with Google'}
              </button>

              <div className="my-5 flex items-center gap-3" aria-hidden>
                <span className="h-px flex-1 bg-line" />
                <span className="text-xs text-muted">or</span>
                <span className="h-px flex-1 bg-line" />
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <Field label="Username" htmlFor="username">
                  <Input
                    id="username"
                    name="username"
                    autoComplete="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    required
                    autoFocus
                  />
                </Field>

                <Field label="Password" htmlFor="password">
                  <div className="relative">
                    <Input
                      id="password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((value) => !value)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted transition-colors hover:text-ink"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </Field>

                {error && (
                  <p role="alert" className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected">
                    {error}
                  </p>
                )}

                <Button type="submit" loading={submitting} className="w-full" size="lg">
                  Sign in
                </Button>
              </form>
            </>
          ) : (
            <>
              <div className="flex size-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
                <KeyRound className="size-5" aria-hidden />
              </div>
              <h2 className="mt-3 text-xl font-semibold text-ink">Two-factor verification</h2>
              <p className="mt-1 text-sm text-body">
                Enter the 6-digit verification code from your authenticator app.
              </p>

              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <Field label="Verification code" htmlFor="totp">
                  <Input
                    id="totp"
                    name="totp"
                    inputMode="text"
                    autoComplete="one-time-code"
                    placeholder="000000"
                    maxLength={11}
                    value={totpCode}
                    onChange={(event) => setTotpCode(event.target.value.toUpperCase())}
                    required
                    autoFocus
                    className="text-center text-lg tracking-[0.4em]"
                  />
                </Field>

                {error && (
                  <p role="alert" className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected">
                    {error}
                  </p>
                )}

                <Button type="submit" loading={submitting} className="w-full" size="lg">
                  Verify
                </Button>

                <button
                  type="button"
                  className="w-full text-center text-xs font-medium text-muted transition-colors hover:text-ink"
                  onClick={() => {
                    // The same field accepts single-use backup codes.
                    setError('')
                    setTotpCode('')
                  }}
                >
                  Tip: you can enter a backup code here
                </button>

                <button
                  type="button"
                  className="w-full text-center text-xs font-medium text-brand transition-colors hover:text-brand-dark"
                  onClick={() => {
                    setStep('credentials')
                    setTotpCode('')
                    setError('')
                  }}
                >
                  Back to sign in
                </button>
              </form>
            </>
          )}
        </div>

        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted">
          <ShieldCheck className="size-3.5" aria-hidden />
          Managed by the SAS Office — contact staff for account access
        </p>
      </div>
    </div>
  )
}
