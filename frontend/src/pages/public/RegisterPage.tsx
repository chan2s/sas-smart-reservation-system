import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Lock, ShieldCheck } from 'lucide-react'
import { api, apiErrorMessage } from '@/lib/api'
import { useInternalOrganizations } from '@/hooks/queries'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select } from '@/components/ui/Form'
import { AuthVisualPanel, BackHomeLink, BrandMark } from '@/components/auth/AuthPanel'
import { GoogleAuthButton } from '@/components/auth/GoogleAuthButton'
import { ChatWidget } from '@/components/chatbot/ChatWidget'
import { GOOGLE_ERROR_MESSAGES, GOOGLE_LOGIN_REDIRECT_CODES } from '@/lib/googleAuth'
import {
  INTERNAL_AFFILIATIONS,
  type ExternalOrganizationType,
  type SelectableAffiliation,
} from '@/lib/types'

const AFFILIATION_OPTIONS: { value: SelectableAffiliation; label: string }[] = [
  { value: 'NORSU_FACULTY_STAFF', label: 'NORSU Faculty/Staff' },
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
  const [affiliation, setAffiliation] = useState<SelectableAffiliation | ''>('')
  // Managed campus organization id, chosen from the seeded list. The backend
  // re-reads its type and active state — the client never sends a type.
  const [internalOrganizationId, setInternalOrganizationId] = useState<number | ''>('')
  const [external, setExternal] = useState(EMPTY_EXTERNAL)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [searchParams] = useSearchParams()

  const { data: internalOrganizations } = useInternalOrganizations()

  // OAuth failures from the registration flow come back as
  // /register?google_error=… (see the backend callback). The login page
  // handles the same codes for its own flow, so the copy stays in sync via
  // the shared GOOGLE_ERROR_MESSAGES map.
  useEffect(() => {
    const googleError = searchParams.get('google_error')
    if (googleError) {
      setError(
        GOOGLE_ERROR_MESSAGES[googleError] ?? 'Google sign-up failed. Please try again.',
      )
    }
  }, [searchParams])

  // "Continue with Google" that found an existing account reports back as
  // ?google_error=account_exists (or email_registered). Those get a direct
  // link to the login page instead of a plain inline error.
  const googleErrorCode = searchParams.get('google_error') ?? ''
  const accountNoticeCode = GOOGLE_LOGIN_REDIRECT_CODES.has(googleErrorCode)

  const isExternal = affiliation === 'EXTERNAL_ORGANIZATION'
  const isInternalAffiliation =
    affiliation !== '' && INTERNAL_AFFILIATIONS.includes(affiliation)

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
    if (isInternalAffiliation && internalOrganizationId === '') {
      setError('Please select your organization')
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
      const externalPayload = isExternal
        ? {
            organization_name: external.organization_name.trim(),
            organization_type: external.organization_type,
            contact_person: external.contact_person.trim(),
            contact_email: external.contact_email.trim().toLowerCase(),
            contact_number: external.contact_number.trim(),
            address: external.address.trim(),
            purpose: external.purpose.trim(),
          }
        : {}

      await api.register({
        username: formData.username.trim(),
        password: formData.password,
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        email: formData.email.trim().toLowerCase(),
        organization: isExternal ? '' : formData.organization.trim(),
        ...(affiliation ? { affiliation } : {}),
        ...(isInternalAffiliation && internalOrganizationId !== ''
          ? { organization_id: internalOrganizationId }
          : {}),
        ...externalPayload,
      })

      // Successful registration NEVER authenticates the new account. The
      // backend creates it (unapproved for external-organization sign-ups,
      // subject to administrator approval policy) and issues no tokens. The
      // user is redirected to the login page to sign in with the credentials
      // they just registered — never straight to the dashboard.
      const registeredCode = isExternal ? 'external' : 'success'
      navigate(`/login?registered=${registeredCode}`, { replace: true })
    } catch (err) {
      setError(apiErrorMessage(err, 'Registration failed. Please try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleGoogle() {
    setError('')
    setGoogleLoading(true)
    try {
      // The exact same backend OAuth flow the login page uses — there is only
      // one Google implementation. The `register` intent only keeps OAuth
      // errors on this page. Google sign-in NEVER creates a SAS RESERVE
      // account: an unregistered identity bounces back with
      // "No account found for this Google account. Please register first." An
      // already-registered one is sent to the login page instead.
      const { authorize_url } = await api.googleStart(window.location.origin, 'register')
      window.location.href = authorize_url
    } catch {
      setError('Google sign-up is unavailable. Please use the form below.')
      setGoogleLoading(false)
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

            <div className="mt-9">
              <GoogleAuthButton onClick={handleGoogle} loading={googleLoading} />

              <div className="my-6 flex items-center gap-3" aria-hidden>
                <span className="h-px flex-1 bg-line" />
                <span className="text-xs text-muted">or</span>
                <span className="h-px flex-1 bg-line" />
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
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
                  onChange={(event) =>
                    setAffiliation(event.target.value as SelectableAffiliation | '')
                  }
                >
                  <option value="">Campus user / not sure yet</option>
                  {AFFILIATION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>

              {isInternalAffiliation && (
                <Field
                  label="Organization / College"
                  htmlFor="internal_organization"
                  hint="Choose the organization you are authorized to represent."
                >
                  <Select
                    id="internal_organization"
                    value={internalOrganizationId}
                    onChange={(event) =>
                      setInternalOrganizationId(
                        event.target.value ? Number(event.target.value) : '',
                      )
                    }
                    required
                  >
                    <option value="">Select your organization…</option>
                    {(internalOrganizations ?? []).map((organization) => (
                      <option key={organization.id} value={organization.id}>
                        {organization.display_name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}

              {!isExternal && !isInternalAffiliation && (
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
                <div
                  role="alert"
                  className="rounded-lg bg-status-rejected-bg px-3 py-2 text-sm text-status-rejected"
                >
                  <p>{error}</p>
                  {accountNoticeCode && (
                    <Link
                      to="/login"
                      className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-surface px-3.5 py-1.5 text-xs font-semibold text-ink shadow-sm transition-colors duration-150 hover:bg-soft"
                    >
                      Go to Login
                    </Link>
                  )}
                </div>
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
