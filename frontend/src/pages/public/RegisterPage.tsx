import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Lock, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Field, Input } from '@/components/ui/Form'
import { AuthVisualPanel, BackHomeLink, BrandMark } from '@/components/auth/AuthPanel'

export function RegisterPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [formData, setFormData] = useState({
    username: '',
    password: '',
    first_name: '',
    last_name: '',
    email: '',
    organization: '',
  })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = event.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')

    // Basic validation
    if (!formData.username.trim()) {
      setError('Username is required')
      return
    }
    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (!formData.email.trim()) {
      setError('Email is required')
      return
    }

    setSubmitting(true)
    try {
      await api.register({
        username: formData.username.trim(),
        password: formData.password,
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        email: formData.email.trim().toLowerCase(),
        organization: formData.organization.trim(),
      })

      // Auto-login after successful registration — `login` sets both the
      // stored tokens and the in-memory auth state, so the protected
      // dashboard is reachable immediately.
      await login(formData.username.trim(), formData.password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Registration failed. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-soft lg:grid lg:grid-cols-2">
      {/* Left — dark editorial brand panel (desktop) */}
      <AuthVisualPanel
        headline="One account for every campus reservation."
        benefits={['Facility reservations', 'Equipment management', 'Real-time availability']}
      />

      {/* Right — form */}
      <main className="relative flex min-h-screen flex-col px-5 py-6 sm:px-10 lg:px-16 lg:py-10">
        <div className="flex items-start justify-between">
          <BackHomeLink />
          <div className="lg:hidden">
            <BrandMark />
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[440px]">
            <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">
              Create your account
            </h1>
            <p className="mt-2.5 text-[15px] leading-relaxed text-body">
              Register to access the reservation system and manage campus facilities and resources.
            </p>

            <form onSubmit={handleSubmit} className="mt-9 space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <Field label="First name" htmlFor="first_name">
                  <Input
                    id="first_name"
                    name="first_name"
                    type="text"
                    autoComplete="given-name"
                    value={formData.first_name}
                    onChange={handleChange}
                    placeholder="Juan"
                    required
                  />
                </Field>

                <Field label="Last name" htmlFor="last_name">
                  <Input
                    id="last_name"
                    name="last_name"
                    type="text"
                    autoComplete="family-name"
                    value={formData.last_name}
                    onChange={handleChange}
                    placeholder="Dela Cruz"
                    required
                  />
                </Field>
              </div>

              <Field label="Username" htmlFor="username">
                <Input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  value={formData.username}
                  onChange={handleChange}
                  placeholder="jdelacruz"
                  required
                  autoFocus
                />
              </Field>

              <Field label="Email" htmlFor="email">
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="juan@university.edu"
                  required
                />
              </Field>

              <Field label="Organization" htmlFor="organization">
                <Input
                  id="organization"
                  name="organization"
                  type="text"
                  value={formData.organization}
                  onChange={handleChange}
                  placeholder="University of the Philippines"
                />
              </Field>

              <Field label="Password" htmlFor="password">
                <div className="relative">
                  <Input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="Min. 8 characters"
                    required
                    className="pr-10"
                  />
                  <Lock
                    className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted"
                    aria-hidden
                  />
                </div>
                <p className="mt-1.5 text-xs text-muted">Minimum 8 characters</p>
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
                Create Account
              </Button>

              <p className="text-center text-xs text-muted">
                By creating an account, you agree to use the reservation system responsibly.
              </p>
            </form>

            <div className="mt-7 border-t border-line pt-6">
              <p className="text-center text-sm text-body">
                Already have an account?{' '}
                <Link
                  to="/login"
                  className="font-semibold text-brand transition-colors hover:text-brand-dark"
                >
                  Sign in
                </Link>
              </p>
            </div>

            <p className="mt-8 flex items-center justify-center gap-1.5 text-xs text-muted">
              <ShieldCheck className="size-3.5" aria-hidden />
              Managed by the SAS Office — contact staff for account access
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}