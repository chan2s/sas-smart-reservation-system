import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import {
  OrganizationStatusNotice,
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from '@/components/organizations/OrganizationStatusNotice'
import { ViewOnlyNotice } from '@/components/auth/ViewOnlyNotice'
import { InstallAppSection } from '@/components/pwa/InstallAppSection'
import type { User } from '@/lib/types'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { Avatar } from '@/components/ui/Misc'
import { Button } from '@/components/ui/Button'
import { Field, Input } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'

export function SettingsPage() {
  const { user, updateUser, isViewOnly } = useAuth()
  const { toast } = useToast()
  const [firstName, setFirstName] = useState(user?.first_name ?? '')
  const [lastName, setLastName] = useState(user?.last_name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [organization, setOrganization] = useState(user?.organization ?? '')
  const [saving, setSaving] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    // A pending-approval account cannot change its profile; the backend
    // refuses it too (403 account_not_approved).
    if (isViewOnly) return
    setSaving(true)
    try {
      const updated = await api.patch<User>('/api/auth/me/', {
        first_name: firstName,
        last_name: lastName,
        email,
        organization,
      })
      updateUser(updated)
      toast('Profile updated.')
    } catch {
      toast('Unable to save changes.', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (!user) return null

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        eyebrow="SAS Settings"
        title="Settings"
        description="Manage your profile information, affiliation, and preferences."
      />

      <Card className="mt-8">
        <div className="flex items-center gap-4">
          <Avatar name={user.display_name} size="lg" />
          <div>
            <p className="text-lg font-semibold text-ink">{user.display_name}</p>
            <p className="text-sm text-muted">@{user.username}</p>
            <div className="mt-1.5">
              <Badge tone={user.role === 'ADMIN' ? 'brand' : user.role === 'STAFF' ? 'sky' : 'neutral'}>
                {user.role === 'ADMIN' ? 'Administrator' : user.role === 'STAFF' ? 'SAS Staff' : 'Requester'}
              </Badge>
            </div>
          </div>
        </div>

        {isViewOnly && (
          <ViewOnlyNotice
            action="Editing your profile is unavailable"
            className="mt-6"
          />
        )}

        <form onSubmit={save} className="mt-8 grid gap-5 sm:grid-cols-2">
          <Field label="First name" htmlFor="first-name">
            <Input id="first-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} />
          </Field>
          <Field label="Last name" htmlFor="last-name">
            <Input id="last-name" value={lastName} onChange={(event) => setLastName(event.target.value)} />
          </Field>
          <Field label="Email" htmlFor="email" className="sm:col-span-2">
            <Input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </Field>
          <Field
            label="Organization"
            htmlFor="organization"
            hint={
              user?.organization_ref
                ? 'Linked to your account — change it under Affiliation below.'
                : undefined
            }
          >
            <Input
              id="organization"
              value={
                user?.organization_ref?.display_name ??
                user?.organization_ref?.organization_name ??
                organization
              }
              onChange={(event) => setOrganization(event.target.value)}
              disabled={Boolean(user?.organization_ref)}
            />
          </Field>
          {!isViewOnly && (
            <div className="sm:col-span-2">
              <Button type="submit" loading={saving}>
                Save changes
              </Button>
            </div>
          )}
        </form>
      </Card>

      {/* ---------------------------------------------------------- */}
      {/* Installable app                                            */}
      {/* ---------------------------------------------------------- */}
      <InstallAppSection />

      {/* ---------------------------------------------------------- */}
      {/* Affiliation & organization                                */}
      {/* ---------------------------------------------------------- */}
      <Card className="mt-6">
        <CardHeader
          title="Affiliation"
          description="Google confirms who you are — your affiliation tells SAS RESERVE who you represent."
        />

        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-line p-3.5">
            <dt className="text-xs font-medium uppercase tracking-wide text-muted">Affiliation</dt>
            <dd className="mt-1 text-sm text-ink">
              {user.affiliation_label || 'Not set'}
            </dd>
          </div>
          <div className="rounded-xl border border-line p-3.5">
            <dt className="text-xs font-medium uppercase tracking-wide text-muted">Organization</dt>
            <dd className="mt-1 text-sm text-ink">
              {user.organization_ref?.display_name ||
                user.organization_ref?.organization_name ||
                user.organization ||
                '—'}
              {user.organization_ref && (
                <span className="block text-xs text-muted">
                  {user.organization_ref.acronym || user.organization_ref.organization_code} ·{' '}
                  {user.organization_ref.organization_type_label}
                  {user.organization_ref.is_internal && user.organization_ref.is_active === false
                    ? ' · Inactive'
                    : ''}
                </span>
              )}
            </dd>
          </div>
          <div className="rounded-xl border border-line p-3.5 sm:col-span-2">
            <dt className="text-xs font-medium uppercase tracking-wide text-muted">
              Verification status
            </dt>
            <dd className="mt-1 text-sm text-ink">
              {user.organization_verification_status ? (
                <Badge tone={VERIFICATION_TONE[user.organization_verification_status]}>
                  {VERIFICATION_LABEL[user.organization_verification_status]}
                </Badge>
              ) : (
                'Not applicable'
              )}
            </dd>
          </div>
        </dl>

        {user.organization_verification_status && (
          <OrganizationStatusNotice
            status={user.organization_verification_status}
            organization={user.organization_ref}
            className="mt-4"
          />
        )}

        {!isViewOnly && (
          <div className="mt-4">
            <Link
              to="/onboarding/affiliation"
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-ink transition-colors hover:bg-soft"
            >
              {user.has_affiliation ? 'Update affiliation' : 'Complete your affiliation'}
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
        )}
      </Card>
    </div>
  )
}
