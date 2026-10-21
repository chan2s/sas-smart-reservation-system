import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Check, Eye, EyeOff, ShieldCheck } from 'lucide-react'
import { ApiError, api, apiErrorMessage } from '@/lib/api'
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

/**
 * Field keys the registration form renders inline. Any other DRF error key
 * (``detail``, ``non_field_errors``, an unknown field) falls back to the
 * general alert so no backend message is silently swallowed.
 */
const RENDERED_ERROR_FIELDS = new Set([
  'username',
  'password',
  'first_name',
  'last_name',
  'email',
  'organization',
  'affiliation',
  'organization_id',
  'organization_name',
  'organization_type',
  'contact_person',
  'contact_email',
  'contact_number',
  'address',
  'purpose',
])

/** Field key → rendered input id, when the two differ. */
const ERROR_FIELD_IDS: Record<string, string> = {
  organization_id: 'internal_organization',
}

/** Splits a DRF 400 body into per-field messages and everything else. */
function readFieldErrors(error: unknown): {
  fields: Record<string, string>
  general: string
} {
  if (
    !(error instanceof ApiError) ||
    !error.data ||
    typeof error.data !== 'object' ||
    Array.isArray(error.data)
  ) {
    return { fields: {}, general: '' }
  }

  const fields: Record<string, string> = {}
  const general: string[] = []

  for (const [key, value] of Object.entries(error.data as Record<string, unknown>)) {
    const message =
      typeof value === 'string'
        ? value.trim()
        : Array.isArray(value)
          ? value.filter((item): item is string => typeof item === 'string').join(' ')
          : ''
    if (!message) continue
    if (RENDERED_ERROR_FIELDS.has(key)) fields[key] = message
    else general.push(message)
  }

  return { fields, general: general.join(' ') }
}

/** Length and “entirely numeric” mirror the configured Django validators. */
function passwordRequirements(password: string) {
  return [
    { label: 'At least 8 characters', met: password.length >= 8 },
    { label: 'Not entirely numeric', met: password.length > 0 && !/^\d+$/.test(password) },
  ]
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
  const [confirmPassword, setConfirmPassword] = useState('')
  const [confirmTouched, setConfirmTouched] = useState(false)
  // One toggle per password input so the two fields reveal independently.
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  // Blank affiliation keeps the legacy behavior (a plain campus account).
  const [affiliation, setAffiliation] = useState<SelectableAffiliation | ''>('')
  // Managed campus organization id, chosen from the seeded list. The backend
  // re-reads its type and active state — the client never sends a type.
  const [internalOrganizationId, setInternalOrganizationId] = useState<number | ''>('')
  const [external, setExternal] = useState(EMPTY_EXTERNAL)
  // ``error`` holds the alert-level message (network, throttle, non-field
  // backend errors); ``fieldErrors`` renders beside the field it belongs to.
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
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

  // Derived on every render, so editing *either* password field instantly
  // re-evaluates the match without extra bookkeeping.
  const passwordsMatch = confirmPassword === formData.password
  const confirmPasswordError =
    confirmPassword !== ''
      ? passwordsMatch
        ? ''
        : 'Passwords do not match'
      : confirmTouched
        ? 'Please confirm your password'
        : ''

  function clearFieldError(name: string) {
    setFieldErrors((prev) => {
      if (!prev[name]) return prev
      const next = { ...prev }
      delete next[name]
      return next
    })
  }

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = event.target
    setFormData((prev) => ({ ...prev, [name]: value }))
    clearFieldError(name)
  }

  function handleConfirmPasswordChange(event: React.ChangeEvent<HTMLInputElement>) {
    setConfirmPassword(event.target.value)
    setConfirmTouched(true)
    clearFieldError('confirm_password')
  }

  function handleExternalChange(
    event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) {
    const { name, value } = event.target
    setExternal((prev) => ({ ...prev, [name]: value }))
    clearFieldError(name)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    // Guards a double click that lands between the click and the re-render
    // that disables the button.
    if (submitting) return
    setError('')

    const nextErrors: Record<string, string> = {}
    if (!formData.username.trim()) nextErrors.username = 'Username is required'
    if (!formData.first_name.trim()) nextErrors.first_name = 'First name is required'
    if (!formData.last_name.trim()) nextErrors.last_name = 'Last name is required'
    if (!formData.email.trim()) nextErrors.email = 'Email is required'

    if (!formData.password) {
      nextErrors.password = 'Password is required'
    } else if (formData.password.length < 8) {
      nextErrors.password =
        'This password is too short. It must contain at least 8 characters.'
    } else if (/^\d+$/.test(formData.password)) {
      nextErrors.password = 'This password is entirely numeric.'
    }

    setConfirmTouched(true)
    if (!confirmPassword) {
      nextErrors.confirm_password = 'Please confirm your password'
    } else if (confirmPassword !== formData.password) {
      nextErrors.confirm_password = 'Passwords do not match'
    }

    if (isInternalAffiliation && internalOrganizationId === '') {
      nextErrors.organization_id = 'Please select your organization'
    }
    if (isExternal) {
      if (!external.organization_name.trim()) {
        nextErrors.organization_name = 'Organization name is required'
      }
      if (!external.contact_person.trim()) {
        nextErrors.contact_person = 'Representative / contact person is required'
      }
      if (!external.contact_email.trim()) {
        nextErrors.contact_email = 'Organization email is required'
      }
    }

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      // Move focus to the first problem so a keyboard/screen-reader user does
      // not have to hunt for the error.
      const firstInvalid = Object.keys(nextErrors)[0]
      document.getElementById(ERROR_FIELD_IDS[firstInvalid] ?? firstInvalid)?.focus()
      return
    }

    setFieldErrors({})
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

      // ``confirmPassword`` is validated here only — the registration API has
      // no such field and the backend never receives it.
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
      const { fields, general } = readFieldErrors(err)
      setFieldErrors(fields)
      setError(
        general ||
          (Object.keys(fields).length > 0
            ? ''
            : apiErrorMessage(err, 'Registration failed. Please try again.')),
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function handleGoogle() {
    setError('')
    setGoogleLoading(true)
    try {
      // The exact same backend OAuth flow the login page uses — there is only
      // one Google implementation. The signed `register` intent tells the
      // backend to CREATE the account from Google's verified identity (it
      // stays unapproved, exactly like a form registration). An identity that
      // is already registered is never duplicated: it is sent to the login
      // page instead. Registration never authenticates, so the backend returns
      // here via /login?registered=google.
      const { authorize_url } = await api.googleStart(window.location.origin, 'register')
      window.location.href = authorize_url
    } catch {
      setError('Google sign-up is unavailable. Please use the form below.')
      setGoogleLoading(false)
    }
  }

  const passwordChecks = passwordRequirements(formData.password)

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

            <p className="mb-4 text-xs text-muted">
              Fields marked <span className="text-status-rejected">*</span> are required.
            </p>

            <form onSubmit={handleSubmit} className="space-y-7">
              <fieldset className="space-y-5">
                <legend className="mb-1 text-sm font-semibold text-ink">Account details</legend>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="First name" htmlFor="first_name" required error={fieldErrors.first_name}>
                    <Input
                      id="first_name"
                      name="first_name"
                      type="text"
                      autoComplete="given-name"
                      value={formData.first_name}
                      onChange={handleChange}
                      placeholder="Juan"
                      required
                      aria-invalid={fieldErrors.first_name ? true : undefined}
                      aria-describedby={fieldErrors.first_name ? 'first_name-error' : undefined}
                    />
                  </Field>

                  <Field label="Last name" htmlFor="last_name" required error={fieldErrors.last_name}>
                    <Input
                      id="last_name"
                      name="last_name"
                      type="text"
                      autoComplete="family-name"
                      value={formData.last_name}
                      onChange={handleChange}
                      placeholder="Dela Cruz"
                      required
                      aria-invalid={fieldErrors.last_name ? true : undefined}
                      aria-describedby={fieldErrors.last_name ? 'last_name-error' : undefined}
                    />
                  </Field>
                </div>

                <Field label="Username" htmlFor="username" required error={fieldErrors.username}>
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
                    aria-invalid={fieldErrors.username ? true : undefined}
                    aria-describedby={fieldErrors.username ? 'username-error' : undefined}
                  />
                </Field>

                <Field label="Email" htmlFor="email" required error={fieldErrors.email}>
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="juan@university.edu"
                    required
                    aria-invalid={fieldErrors.email ? true : undefined}
                    aria-describedby={fieldErrors.email ? 'email-error' : undefined}
                  />
                </Field>
              </fieldset>

              <fieldset className="space-y-5">
                <legend className="mb-1 text-sm font-semibold text-ink">
                  Affiliation
                </legend>

                <Field
                  label="I am registering as"
                  htmlFor="affiliation"
                  hint="External organizations are verified by the SAS Office before they can reserve."
                >
                  <Select
                    id="affiliation"
                    name="affiliation"
                    value={affiliation}
                    onChange={(event) => {
                      setAffiliation(event.target.value as SelectableAffiliation | '')
                      clearFieldError('affiliation')
                    }}
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
                    required
                    error={fieldErrors.organization_id}
                  >
                    <Select
                      id="internal_organization"
                      value={internalOrganizationId}
                      onChange={(event) => {
                        setInternalOrganizationId(
                          event.target.value ? Number(event.target.value) : '',
                        )
                        clearFieldError('organization_id')
                      }}
                      required
                      aria-invalid={fieldErrors.organization_id ? true : undefined}
                      aria-describedby={
                        fieldErrors.organization_id ? 'internal_organization-error' : undefined
                      }
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
                      autoComplete="organization"
                      value={formData.organization}
                      onChange={handleChange}
                      placeholder="University of the Philippines"
                    />
                  </Field>
                )}

                {isExternal && (
                  <div className="space-y-5 rounded-xl border border-line bg-soft/40 p-4">
                    <p className="text-sm font-semibold text-ink">Organization details</p>

                    <Field
                      label="Organization name"
                      htmlFor="organization_name"
                      required
                      error={fieldErrors.organization_name}
                    >
                      <Input
                        id="organization_name"
                        name="organization_name"
                        type="text"
                        autoComplete="organization"
                        value={external.organization_name}
                        onChange={handleExternalChange}
                        placeholder="e.g. Bayawan National High School"
                        required
                        aria-invalid={fieldErrors.organization_name ? true : undefined}
                        aria-describedby={
                          fieldErrors.organization_name ? 'organization_name-error' : undefined
                        }
                      />
                    </Field>

                    <Field
                      label="Organization type"
                      htmlFor="organization_type"
                      required
                      error={fieldErrors.organization_type}
                    >
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

                    <Field
                      label="Representative / Contact person"
                      htmlFor="contact_person"
                      required
                      error={fieldErrors.contact_person}
                    >
                      <Input
                        id="contact_person"
                        name="contact_person"
                        type="text"
                        value={external.contact_person}
                        onChange={handleExternalChange}
                        placeholder="Full name"
                        required
                        aria-invalid={fieldErrors.contact_person ? true : undefined}
                        aria-describedby={
                          fieldErrors.contact_person ? 'contact_person-error' : undefined
                        }
                      />
                    </Field>

                    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                      <Field label="Contact number" htmlFor="contact_number">
                        <Input
                          id="contact_number"
                          name="contact_number"
                          type="tel"
                          inputMode="tel"
                          autoComplete="tel"
                          value={external.contact_number}
                          onChange={handleExternalChange}
                          placeholder="e.g. 0917 123 4567"
                        />
                      </Field>

                      <Field
                        label="Organization email"
                        htmlFor="contact_email"
                        required
                        error={fieldErrors.contact_email}
                      >
                        <Input
                          id="contact_email"
                          name="contact_email"
                          type="email"
                          autoComplete="email"
                          value={external.contact_email}
                          onChange={handleExternalChange}
                          placeholder="office@organization.org"
                          required
                          aria-invalid={fieldErrors.contact_email ? true : undefined}
                          aria-describedby={
                            fieldErrors.contact_email ? 'contact_email-error' : undefined
                          }
                        />
                      </Field>
                    </div>

                    <Field label="Organization address" htmlFor="address">
                      <Input
                        id="address"
                        name="address"
                        type="text"
                        autoComplete="street-address"
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
                  </div>
                )}
              </fieldset>

              <fieldset className="space-y-5">
                <legend className="mb-1 text-sm font-semibold text-ink">Security</legend>

                <div className="space-y-2">
                  <Field
                    label="Password"
                    htmlFor="password"
                    required
                    error={fieldErrors.password}
                  >
                    <div className="relative">
                      <Input
                        id="password"
                        name="password"
                        type={showPassword ? 'text' : 'password'}
                        autoComplete="new-password"
                        value={formData.password}
                        onChange={handleChange}
                        placeholder="Min. 8 characters"
                        required
                        className="pr-10"
                        aria-invalid={fieldErrors.password ? true : undefined}
                        aria-describedby={
                          `${fieldErrors.password ? 'password-error ' : ''}password-requirements`
                        }
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((value) => !value)}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                        aria-pressed={showPassword}
                      >
                        {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                      </button>
                    </div>
                  </Field>

                  <ul id="password-requirements" className="space-y-1">
                    {passwordChecks.map((rule) => (
                      <li key={rule.label} className="flex items-center gap-2 text-xs">
                        <span
                          className={
                            'flex size-3.5 shrink-0 items-center justify-center rounded-full ' +
                            (rule.met
                              ? 'bg-status-available text-white'
                              : 'border border-line-strong')
                          }
                          aria-hidden
                        >
                          {rule.met && <Check className="size-2.5" />}
                        </span>
                        <span className={rule.met ? 'text-status-available' : 'text-muted'}>
                          {rule.label}
                        </span>
                      </li>
                    ))}
                    <li className="flex items-start gap-2 text-xs text-muted">
                      <span
                        className="mt-1 flex size-3.5 shrink-0 items-center justify-center"
                        aria-hidden
                      >
                        <span className="size-1 rounded-full bg-muted" />
                      </span>
                      Not too similar to your name, username, or email — and not a commonly used
                      password.
                    </li>
                  </ul>
                </div>

                <Field
                  label="Confirm password"
                  htmlFor="confirm_password"
                  required
                  error={confirmPasswordError || fieldErrors.confirm_password}
                >
                  <div className="relative">
                    <Input
                      id="confirm_password"
                      name="confirm_password"
                      type={showConfirmPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={handleConfirmPasswordChange}
                      onBlur={() => setConfirmTouched(true)}
                      placeholder="Re-enter your password"
                      required
                      className="pr-10"
                      aria-invalid={
                        confirmPasswordError || fieldErrors.confirm_password ? true : undefined
                      }
                      aria-describedby={
                        confirmPasswordError || fieldErrors.confirm_password
                          ? 'confirm_password-error'
                          : undefined
                      }
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword((value) => !value)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                      aria-label={
                        showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'
                      }
                      aria-pressed={showConfirmPassword}
                    >
                      {showConfirmPassword ? (
                        <EyeOff className="size-4" />
                      ) : (
                        <Eye className="size-4" />
                      )}
                    </button>
                  </div>
                </Field>
              </fieldset>

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

              <Button
                type="submit"
                loading={submitting}
                disabled={!passwordsMatch}
                className="w-full"
                size="lg"
              >
                {submitting
                  ? 'Creating account...'
                  : isExternal
                    ? 'Register Organization'
                    : 'Create Account'}
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
                  Log in
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
