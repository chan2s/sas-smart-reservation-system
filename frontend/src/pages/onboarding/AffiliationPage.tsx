import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Building2,
  Check,
  GraduationCap,
  Landmark,
  Briefcase,
  ArrowRight,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import { useMyAffiliation, useSetAffiliation } from '@/hooks/queries'
import { useToast } from '@/components/ui/Toast'
import { PageHeader, Skeleton } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Field, Input, Select, Textarea } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'
import {
  OrganizationStatusNotice,
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from '@/components/organizations/OrganizationStatusNotice'
import { cn } from '@/lib/utils'
import type { Affiliation, ExternalOrganizationType } from '@/lib/types'

const AFFILIATIONS: {
  value: Affiliation
  label: string
  description: string
  icon: typeof GraduationCap
}[] = [
  {
    value: 'NORSU_STUDENT',
    label: 'NORSU Student',
    description: 'Enrolled student reserving facilities for academic events.',
    icon: GraduationCap,
  },
  {
    value: 'NORSU_FACULTY_STAFF',
    label: 'NORSU Faculty/Staff',
    description: 'Teaching or non-teaching personnel of the university.',
    icon: Briefcase,
  },
  {
    value: 'NORSU_OFFICE',
    label: 'NORSU Office/Department',
    description: 'An office, college, or department booking on its behalf.',
    icon: Landmark,
  },
  {
    value: 'EXTERNAL_ORGANIZATION',
    label: 'External Organization',
    description:
      'An organization outside NORSU. Requires administrator verification before reserving.',
    icon: Building2,
  },
]

const ORGANIZATION_TYPES: { value: ExternalOrganizationType; label: string }[] = [
  { value: 'GOVERNMENT_AGENCY', label: 'Government Agency' },
  { value: 'NGO', label: 'NGO' },
  { value: 'PRIVATE_ORGANIZATION', label: 'Private Organization' },
  { value: 'COMMUNITY_ORGANIZATION', label: 'Community Organization' },
  { value: 'SCHOOL_UNIVERSITY', label: 'School/University' },
  { value: 'OTHER', label: 'Other' },
]

interface OrganizationForm {
  organization_name: string
  organization_type: ExternalOrganizationType
  contact_person: string
  contact_email: string
  contact_number: string
  address: string
  purpose: string
}

const EMPTY_ORGANIZATION: OrganizationForm = {
  organization_name: '',
  organization_type: 'NGO',
  contact_person: '',
  contact_email: '',
  contact_number: '',
  address: '',
  purpose: '',
}

/**
 * "How are you affiliated with NORSU?"
 *
 * Shown to accounts that have never chosen an affiliation (new Google
 * accounts are routed here by the OAuth callback). It only ever writes the
 * caller's OWN affiliation/registration — the backend derives the
 * organization from the authenticated profile, so there is no organization
 * id to tamper with here.
 */
export function AffiliationPage() {
  const { user, updateUser } = useAuth()
  const navigate = useNavigate()
  const { toast } = useToast()
  const { data, isLoading } = useMyAffiliation()
  const setAffiliation = useSetAffiliation()

  const [choice, setChoice] = useState<Affiliation>('NORSU_STUDENT')
  const [organizationText, setOrganizationText] = useState('')
  const [organization, setOrganization] = useState<OrganizationForm>(EMPTY_ORGANIZATION)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')

  const existingOrganization = data?.organization ?? null
  const status = data?.organization_verification_status || ''
  // A user already attached to an organization may only refine that
  // organization — the backend refuses a switch, so don't offer one.
  const lockedToOrganization = Boolean(existingOrganization)

  useEffect(() => {
    if (!data) return
    setOrganizationText(data.organization_text ?? '')
    if (data.affiliation) setChoice(data.affiliation)
    if (data.organization) {
      setOrganization({
        organization_name: data.organization.organization_name,
        organization_type: data.organization.organization_type,
        contact_person: data.organization.contact_person ?? '',
        contact_email: data.organization.contact_email ?? '',
        contact_number: data.organization.contact_number ?? '',
        address: data.organization.address ?? '',
        purpose: data.organization.purpose ?? '',
      })
    }
  }, [data])

  const isExternal = choice === 'EXTERNAL_ORGANIZATION'

  const missing = useMemo(() => {
    if (!isExternal || lockedToOrganization) return []
    const gaps: string[] = []
    if (!organization.organization_name.trim()) gaps.push('Organization name')
    if (!organization.contact_person.trim()) gaps.push('Representative / contact person')
    if (!organization.contact_email.trim()) gaps.push('Organization email')
    return gaps
  }, [isExternal, lockedToOrganization, organization])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFormError('')
    if (missing.length) {
      setFormError(`Please fill in: ${missing.join(', ')}.`)
      return
    }

    setSubmitting(true)
    try {
      const payload = isExternal
        ? {
            affiliation: choice,
            // The backend updates the caller's own organization record (never
            // a different one); a rejected organization returns to Pending.
            ...organization,
          }
        : { affiliation: choice, organization: organizationText.trim() }

      await setAffiliation.mutateAsync(payload)
      // Refresh the auth user so the profile, header, and wizard gating
      // reflect the new affiliation immediately.
      const me = await api.me()
      updateUser(me)
      toast(
        isExternal
          ? 'Organization details submitted.'
          : 'Affiliation saved.',
      )
      navigate('/dashboard', { replace: true })
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unable to save your affiliation.'
      setFormError(message)
      toast(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (!user) return null

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        eyebrow="Your account"
        title="How are you affiliated with NORSU?"
        description="Google confirms who you are. This tells SAS RESERVE who you represent when booking facilities."
      />

      {isLoading ? (
        <Card className="mt-8">
          <Skeleton className="h-56" />
        </Card>
      ) : (
        <>
          {/* Existing organization status — always visible for external users. */}
          {isExternal && status && (
            <OrganizationStatusNotice
              status={status}
              organization={existingOrganization}
              className="mt-6"
            />
          )}

          <form onSubmit={handleSubmit}>
            <Card className="mt-6">
              <CardHeader
                title="Affiliation"
                description="Choose the option that describes you best."
              />
              <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
                {AFFILIATIONS.map((option) => {
                  const Icon = option.icon
                  const selected = choice === option.value
                  const disabled = lockedToOrganization && option.value !== 'EXTERNAL_ORGANIZATION'
                  return (
                    <button
                      key={option.value}
                      type="button"
                      disabled={disabled}
                      onClick={() => setChoice(option.value)}
                      aria-pressed={selected}
                      className={cn(
                        'flex items-start gap-3 rounded-xl border p-3.5 text-left transition-colors duration-150',
                        selected
                          ? 'border-brand bg-brand-soft/40'
                          : 'border-line bg-surface hover:bg-soft',
                        disabled && 'cursor-not-allowed opacity-50 hover:bg-surface',
                      )}
                    >
                      <span
                        className={cn(
                          'flex size-9 shrink-0 items-center justify-center rounded-lg',
                          selected ? 'bg-brand text-white' : 'bg-soft text-muted',
                        )}
                      >
                        <Icon className="size-4.5" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
                          {option.label}
                          {selected && <Check className="size-3.5 text-brand" aria-hidden />}
                        </span>
                        <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                          {option.description}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>

              {lockedToOrganization && (
                <p className="mt-3 text-xs text-muted">
                  Your account is linked to {existingOrganization?.organization_name}. Contact the
                  SAS Office if you need to change organizations.
                </p>
              )}

              {!isExternal && (
                <div className="mt-5">
                  <Field
                    label="Office / Department"
                    htmlFor="affiliation-organization"
                    hint="Optional — the NORSU college, office, or department you belong to."
                  >
                    <Input
                      id="affiliation-organization"
                      value={organizationText}
                      onChange={(event) => setOrganizationText(event.target.value)}
                      placeholder="e.g. College of Engineering"
                    />
                  </Field>
                </div>
              )}
            </Card>

            {isExternal && (
              <>
                <Card className="mt-6">
                  <CardHeader
                    title="Organization information"
                    description="Tell us about the organization you represent."
                  />
                  <div className="mt-4 grid gap-5 sm:grid-cols-2">
                    <Field label="Organization name" htmlFor="organization-name">
                      <Input
                        id="organization-name"
                        value={organization.organization_name}
                        onChange={(event) =>
                          setOrganization((current) => ({
                            ...current,
                            organization_name: event.target.value,
                          }))
                        }
                        placeholder="e.g. ABC Foundation"
                        required
                      />
                    </Field>
                    <Field label="Organization type" htmlFor="organization-type">
                      <Select
                        id="organization-type"
                        value={organization.organization_type}
                        onChange={(event) =>
                          setOrganization((current) => ({
                            ...current,
                            organization_type: event.target.value as ExternalOrganizationType,
                          }))
                        }
                      >
                        {ORGANIZATION_TYPES.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                </Card>

                <Card className="mt-6">
                  <CardHeader
                    title="Contact information"
                    description="SAS staff use these details to verify your organization."
                  />
                  <div className="mt-4 grid gap-5 sm:grid-cols-2">
                    <Field label="Representative / Contact person" htmlFor="contact-person">
                      <Input
                        id="contact-person"
                        value={organization.contact_person}
                        onChange={(event) =>
                          setOrganization((current) => ({
                            ...current,
                            contact_person: event.target.value,
                          }))
                        }
                        placeholder="Full name"
                        required
                      />
                    </Field>
                    <Field label="Contact number" htmlFor="contact-number">
                      <Input
                        id="contact-number"
                        value={organization.contact_number}
                        onChange={(event) =>
                          setOrganization((current) => ({
                            ...current,
                            contact_number: event.target.value,
                          }))
                        }
                        placeholder="e.g. 0917 123 4567"
                      />
                    </Field>
                    <Field label="Organization email" htmlFor="contact-email">
                      <Input
                        id="contact-email"
                        type="email"
                        value={organization.contact_email}
                        onChange={(event) =>
                          setOrganization((current) => ({
                            ...current,
                            contact_email: event.target.value,
                          }))
                        }
                        placeholder="office@organization.org"
                        required
                      />
                    </Field>
                    <Field label="Organization address" htmlFor="contact-address">
                      <Input
                        id="contact-address"
                        value={organization.address}
                        onChange={(event) =>
                          setOrganization((current) => ({
                            ...current,
                            address: event.target.value,
                          }))
                        }
                        placeholder="Street, city"
                      />
                    </Field>
                  </div>
                </Card>

                <Card className="mt-6">
                  <CardHeader
                    title="Supporting information"
                    description="Why does your organization need to use NORSU facilities?"
                  />
                  <div className="mt-4">
                    <Field label="Purpose of requesting NORSU facilities" htmlFor="purpose">
                      <Textarea
                        id="purpose"
                        rows={4}
                        value={organization.purpose}
                        onChange={(event) =>
                          setOrganization((current) => ({
                            ...current,
                            purpose: event.target.value,
                          }))
                        }
                        placeholder="e.g. Community seminar for local barangay officials"
                      />
                    </Field>
                  </div>
                </Card>
              </>
            )}

            {formError && (
              <p
                role="alert"
                className="mt-5 rounded-lg bg-status-rejected-bg px-3 py-2 text-[13px] text-status-rejected"
              >
                {formError}
              </p>
            )}

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button type="submit" loading={submitting} icon={<ArrowRight className="size-4" />}>
                {isExternal
                  ? lockedToOrganization
                    ? 'Save changes'
                    : 'Submit for verification'
                  : 'Save affiliation'}
              </Button>
              {data?.has_affiliation && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => navigate('/dashboard')}
                >
                  Cancel
                </Button>
              )}
            </div>

            {isExternal && !lockedToOrganization && (
              <p className="mt-3 text-xs text-muted">
                Your organization will be reviewed by the SAS Office. You&apos;ll be able to
                submit reservations once it is approved.
              </p>
            )}

            {isExternal && status && (
              <p className="mt-3 text-xs text-muted">
                Current status:{' '}
                <Badge tone={VERIFICATION_TONE[status]}>{VERIFICATION_LABEL[status]}</Badge>
              </p>
            )}
          </form>
        </>
      )}
    </div>
  )
}
