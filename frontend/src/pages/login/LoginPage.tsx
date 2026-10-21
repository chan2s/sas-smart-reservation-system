import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { CheckCircle2, Eye, EyeOff, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { api, ApiError, isDeactivatedAccountError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Field, Input } from '@/components/ui/Form'
import { AuthVisualPanel, BackHomeLink, BrandMark } from '@/components/auth/AuthPanel'
import { DeactivatedAccountModal } from '@/components/auth/DeactivatedAccountModal'
import { GoogleAuthButton } from '@/components/auth/GoogleAuthButton'
import { ChatWidget } from '@/components/chatbot/ChatWidget'
import {
  GOOGLE_ERROR_MESSAGES,
  GOOGLE_LOGIN_REDIRECT_CODES,
  GOOGLE_REGISTER_REDIRECT_CODES,
} from '@/lib/googleAuth'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Set after a sign-up redirects here instead of auto-authenticating the
  // new account. 'external' keeps the pending-organization copy; every other
  // registration shows the standard "please log in" success message.
  const registeredParam = searchParams.get('registered')
  const registeredExternal = registeredParam === 'external'
  const registeredSuccess = registeredParam === 'success'
  // A Google sign-up on /register created the account (same approval policy as
  // the form) and returned here; the identity is already linked, so the user
  // signs in with Google.
  const registeredGoogle = registeredParam === 'google'

  // "Continue with Google" that found an existing account redirects here with
  // ?google_error=account_exists (or email_registered). These get a dedicated
  // notice with a direct link to the login form instead of an inline error.
  const googleErrorCode = searchParams.get('google_error') ?? ''
  const accountNoticeCode = GOOGLE_LOGIN_REDIRECT_CODES.has(googleErrorCode)
  // "No account found" gets the same dedicated-notice treatment, but with an
  // easy path to the registration page instead of the login form.
  const registerNoticeCode = GOOGLE_REGISTER_REDIRECT_CODES.has(googleErrorCode)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  // A refused sign-in because an administrator deactivated the account. This
  // is an account-status condition, not a credentials mistake, so it gets a
  // dedicated modal and never the inline credential error.
  const [deactivated, setDeactivated] = useState(false)

  // OAuth failures come back as /login?google_error=… (see backend callback).
  // The deactivated-account code opens the modal instead; every other code
  // keeps its existing inline notice.
  useEffect(() => {
    const googleError = searchParams.get('google_error')
    if (googleError === 'account_deactivated') {
      setDeactivated(true)
      setError('')
    } else if (googleError) {
      setDeactivated(false)
      setError(GOOGLE_ERROR_MESSAGES[googleError] ?? 'Google sign-in failed. Please try again.')
    } else {
      setError('')
    }
  }, [searchParams])

  /** Dismiss the modal; scrub the OAuth error param so a retry starts clean. */
  function dismissDeactivated() {
    setDeactivated(false)
    if (searchParams.get('google_error')) navigate('/login', { replace: true })
  }

  if (user) return <Navigate to="/dashboard" replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(username.trim(), password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      // The backend only returns this condition when the submitted
      // credentials were actually correct, so the modal leaks nothing.
      if (isDeactivatedAccountError(err)) {
        setDeactivated(true)
        return
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
      // The secret never touches the frontend. Sending our actual origin
      // (localhost, 127.0.0.1, or the current Dev Tunnel) lets the backend
      // bind the OAuth flow to this environment — no hard-coded hostnames.
      const { authorize_url } = await api.googleStart(window.location.origin)
      window.location.href = authorize_url
    } catch {
      setError('Google sign-in is unavailable. Please use your username and password.')
      setGoogleLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-soft lg:grid lg:grid-cols-2">
      {/* Left — dark editorial brand panel (desktop) */}
      <AuthVisualPanel headline="Reserve spaces. Manage resources. Simplify events." />

      {/* Right — form */}
      <main className="relative flex min-h-screen flex-col px-5 py-6 sm:px-10 lg:px-16 lg:py-10">
        <div className="flex items-start justify-between">
          <BackHomeLink />
          <div className="lg:hidden">
            <BrandMark />
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[420px]">
            <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">
              Welcome back
            </h1>
            <p className="mt-2.5 text-[15px] leading-relaxed text-body">
              Sign in to manage your reservations, facilities, and resources.
            </p>

            <div className="mt-9">
              {registeredSuccess && (
                <div
                  role="status"
                  className="mb-6 flex items-start gap-2.5 rounded-xl border border-status-available/30 bg-status-available-bg px-3.5 py-3 text-[13px] text-status-available"
                >
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <p>
                    Registration successful! Please log in with your registered
                    account.
                  </p>
                </div>
              )}

              {registeredExternal && (
                <div
                  role="status"
                  className="mb-6 flex items-start gap-2.5 rounded-xl border border-status-available/30 bg-status-available-bg px-3.5 py-3 text-[13px] text-status-available"
                >
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <p>
                    Registration successful. Your organization registration is pending
                    administrator approval. Please wait for the administrator to approve
                    your organization before making a reservation. You can log in after
                    registration.
                  </p>
                </div>
              )}

              {registeredGoogle && (
                <div
                  role="status"
                  className="mb-6 flex items-start gap-2.5 rounded-xl border border-status-available/30 bg-status-available-bg px-3.5 py-3 text-[13px] text-status-available"
                >
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <p>
                    Registration successful. Please sign in with Google to continue — your
                    account is pending administrator approval.
                  </p>
                </div>
              )}

              {accountNoticeCode || registerNoticeCode ? (
                <div
                  role="alert"
                  className="rounded-xl border border-status-pending/25 bg-status-pending-bg px-4 py-4"
                >
                  <p className="text-sm leading-relaxed text-status-pending">{error}</p>
                  {accountNoticeCode ? (
                    <button
                      type="button"
                      onClick={() => navigate('/login')}
                      className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-brand px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-brand-dark"
                    >
                      Go to Login
                    </button>
                  ) : (
                    <Link
                      to="/register"
                      className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-brand px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-brand-dark"
                    >
                      Go to Registration
                    </Link>
                  )}
                </div>
              ) : (
                <>
                  <GoogleAuthButton onClick={handleGoogle} loading={googleLoading} />

                  <div className="my-6 flex items-center gap-3" aria-hidden>
                    <span className="h-px flex-1 bg-line" />
                    <span className="text-xs text-muted">or</span>
                    <span className="h-px flex-1 bg-line" />
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-5">
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
                      <p
                        role="alert"
                        className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected"
                      >
                        {error}
                      </p>
                    )}

                    <Button type="submit" loading={submitting} className="w-full" size="lg">
                      Sign in
                    </Button>
                  </form>
                </>
              )}
            </div>

            <p className="mt-9 flex items-center justify-center gap-1.5 text-xs text-muted">
              <ShieldCheck className="size-3.5" aria-hidden />
              Managed by the SAS Office — contact staff for account access
            </p>
          </div>
        </div>
      </main>

      {/* Deactivated account — shown for the password 403 and for the
          OAuth callback redirect (?google_error=account_deactivated). */}
      <DeactivatedAccountModal open={deactivated} onClose={dismissDeactivated} />

      {/* Public assistant — public knowledge only until the visitor signs in. */}
      <ChatWidget />
    </div>
  )
}