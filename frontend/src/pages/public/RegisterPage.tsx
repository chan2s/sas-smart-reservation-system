import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Lock, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select } from '@/components/ui/Form'
import { AuthVisualPanel, BackHomeLink, BrandMark } from '@/components/auth/AuthPanel'
import { ChatWidget } from '@/components/chatbot/ChatWidget'
import type { Affiliation, ExternalOrganizationType } from '@/lib/types'

const AFFILIATION_OPTIONS: { value: Affiliation; label: string }[] = [
  { value: 'NORSU_STUDENT', label: 'NORSU Student' },
  { value: 'NORSU_FACULTY_STAFF', label: 'NORSU Faculty/Staff' },
  { value: 'NORSU_OFFICE', label: 'NORSU Office/Department' },
  { value: 'EXTERNAL_ORGANIZATION', label: 'External Organization' },
]

const ORGANIZATION_TYPE_OPTIONS: { value: ExternalOrganizationType; label: string }[] = [
  { value: 'GOVERNMENT_AGENCY', label: 'Government Agency' },
  { value: 'NGO', label: 'NGO' },
  { value: 'PRIVATE_ORGANIZATION', label: 'Private Organization' },
  { value: 'COMMUNITY_ORGANIZATION', label: 'Community Organization' },
  { value: 'SCHOOL_UNIVERSITY', label: 'School/University' },
  { value: 'OTHER', label: 'Other' },
]

const EMPTY_EXTERNAL = {
  organization_name: '',
  organization_type: 'NGO' as ExternalOrganizationType,
  contact_person: '',
  contact_email: '',
  contact_number: '',
  address: '',
  purpose: '',
}

export function RegisterPage() {
  const { login, logout } = useAuth()
  const navigate = useNavigate()

  const [formData, setFormData] = useState({
    username: '',
    password: '',
    first_name: '',
    last_name: '',
    email: '',
    organization: '',
  })
  // Blank affiliation keeps the legacy behavior (a plain campus account).
  const [affiliation, setAffiliation] = useState<Affiliation | ''>('')
  const [external, setExternal] = useState(EMPTY_EXTERNAL)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const isExternal = affiliation === 'EXTERNAL_ORGANIZATION'

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = event.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  function handleExternalChange(
    event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) {
    const { name, value } = event.target
    setExternal((prev) => ({ ...prev, [name]: value }))
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
    if (isExternal) {
      if (!external.organization_name.trim()) {
        setError('Organization name is required')
        return
      }
      if (!external.contact_person.trim()) {
        setError('Representative / contact person is required')
        return
      }
      if (!external.contact_email.trim()) {
        setError('Organization email is required')
        return
      }
    }

    setSubmitting(true)
    try {
      await api.register({
        username: formData.username.trim(),
        password: formData.password,
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        email: formData.email.trim().toLowerCase(),
        organization: isExternal ? '' : formData.organization.trim(),
        ...(affiliation ? { affiliation } : {}),
        ...(isExternal ? external : {}),
      })

      // External organizations must be verified by an administrator before
      // they can reserve. Do NOT authenticate the new account — clear any
      // tokens, leave the dashboard unreachable, and hand off to the login
      // page with the pending-approval notice.
      if (isExternal) {
        logout()
        navigate('/login?registered=external', { replace: true })
        return
      }

      // Everyone else keeps the existing flow: auto-login into the dashboard.
      // `login` sets both the stored tokens and the in-memory auth state, so
      // the protected dashboard is reachable immediately.
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

              <Field
                label="I am registering as"
                htmlFor="affiliation"
                hint="External organizations are verified by the SAS Office before they can reserve."
              >
                <Select
                  id="affiliation"
                  name="affiliation"
                  value={affiliation}
                  onChange={(event) => setAffiliation(event.target.value as Affiliation | '')}
                >
                  <option value="">Campus user / not sure yet</option>
                  {AFFILIATION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>

              {!isExternal && (
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
              )}

              {isExternal && (
                <fieldset className="space-y-5 rounded-xl border border-line bg-soft/40 p-4">
                  <legend className="px-1 text-sm font-semibold text-ink">
                    Organization details
                  </legend>

                  <Field label="Organization name" htmlFor="organization_name">
                    <Input
                      id="organization_name"
                      name="organization_name"
                      type="text"
                      value={external.organization_name}
                      onChange={handleExternalChange}
                      placeholder="e.g. Bayawan National High School"
                      required
                    />
                  </Field>

                  <Field label="Organization type" htmlFor="organization_type">
                    <Select
                      id="organization_type"
                      name="organization_type"
                      value={external.organization_type}
                      onChange={handleExternalChange}
                    >
                      {ORGANIZATION_TYPE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  </Field>

                  <Field label="Representative / Contact person" htmlFor="contact_person">
                    <Input
                      id="contact_person"
                      name="contact_person"
                      type="text"
                      value={external.contact_person}
                      onChange={handleExternalChange}
                      placeholder="Full name"
                      required
                    />
                  </Field>

                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                    <Field label="Contact number" htmlFor="contact_number">
                      <Input
                        id="contact_number"
                        name="contact_number"
                        type="text"
                        value={external.contact_number}
                        onChange={handleExternalChange}
                        placeholder="e.g. 0917 123 4567"
                      />
                    </Field>

                    <Field label="Organization email" htmlFor="contact_email">
                      <Input
                        id="contact_email"
                        name="contact_email"
                        type="email"
                        value={external.contact_email}
                        onChange={handleExternalChange}
                        placeholder="office@organization.org"
                        required
                      />
                    </Field>
                  </div>

                  <Field label="Organization address" htmlFor="address">
                    <Input
                      id="address"
                      name="address"
                      type="text"
                      value={external.address}
                      onChange={handleExternalChange}
                      placeholder="Street, city"
                    />
                  </Field>

                  <Field
                    label="Purpose of requesting NORSU facilities"
                    htmlFor="purpose"
                    hint="Optional — helps SAS verify your organization."
                  >
                    <Input
                      id="purpose"
                      name="purpose"
                      type="text"
                      value={external.purpose}
                      onChange={handleExternalChange}
                      placeholder="e.g. Community seminar"
                    />
                  </Field>
                </fieldset>
              )}

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

              {isExternal && (
                <p className="rounded-lg border border-status-pending/25 bg-status-pending-bg px-3 py-2 text-xs text-status-pending">
                  After registering you will be asked to sign in. Your organization will be
                  reviewed by the SAS Office, and you can reserve facilities once it is approved.
                </p>
              )}

              {error && (
                <p
                  role="alert"
                  className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected"
                >
                  {error}
                </p>
              )}

              <Button type="submit" loading={submitting} className="w-full" size="lg">
                {isExternal ? 'Register Organization' : 'Create Account'}
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

      {/* Public assistant — public knowledge only until the visitor signs in. */}
      <ChatWidget />
    </div>
  )
}
