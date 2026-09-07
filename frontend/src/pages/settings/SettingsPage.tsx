import { useState, type FormEvent } from 'react'
import { Check, Copy, Download, Fingerprint, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import type { User } from '@/lib/types'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { Avatar } from '@/components/ui/Misc'
import { Button } from '@/components/ui/Button'
import { Field, Input } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'

type TwoFactorState =
  | { phase: 'idle'; enabled: boolean; backupCodesRemaining: number }
  | { phase: 'setup'; secret: string; otpauthUrl: string; qrPngDataUrl: string }
  | { phase: 'backup-codes'; codes: string[] }
  | { phase: 'disabling'; wasEnabled: boolean }

export function SettingsPage() {
  const { user, updateUser } = useAuth()
  const { toast } = useToast()
  const [firstName, setFirstName] = useState(user?.first_name ?? '')
  const [lastName, setLastName] = useState(user?.last_name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [organization, setOrganization] = useState(user?.organization ?? '')
  const [phone, setPhone] = useState(user?.phone ?? '')
  const [saving, setSaving] = useState(false)

  const [twoFactor, setTwoFactor] = useState<TwoFactorState | null>(null)
  const [twoFactorLoaded, setTwoFactorLoaded] = useState(false)
  const [verificationCode, setVerificationCode] = useState('')
  const [disablePassword, setDisablePassword] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  async function loadTwoFactor() {
    try {
      const status = await api.twoFactorStatus()
      setTwoFactor({ phase: 'idle', enabled: status.enabled, backupCodesRemaining: status.backup_codes_remaining })
    } catch {
      setTwoFactor(null)
    } finally {
      setTwoFactorLoaded(true)
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const updated = await api.patch<User>('/api/auth/me/', {
        first_name: firstName,
        last_name: lastName,
        email,
        organization,
        phone,
      })
      updateUser(updated)
      toast('Profile updated.')
    } catch {
      toast('Unable to save changes.', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function startSetup() {
    setBusy(true)
    try {
      const setup = await api.twoFactorSetup()
      setTwoFactor({
        phase: 'setup',
        secret: setup.secret,
        otpauthUrl: setup.otpauth_url,
        qrPngDataUrl: setup.qr_png_data_url,
      })
      setVerificationCode('')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not start 2FA setup.', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function confirmSetup(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const result = await api.twoFactorVerify(verificationCode.trim())
      setTwoFactor({ phase: 'backup-codes', codes: result.backup_codes })
      toast('Two-factor authentication enabled.')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Invalid code. Try again.', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function disableTwoFactor(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      await api.twoFactorDisable(disablePassword, disableCode || undefined)
      setTwoFactor({ phase: 'idle', enabled: false, backupCodesRemaining: 0 })
      setDisablePassword('')
      setDisableCode('')
      toast('Two-factor authentication disabled.')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not disable 2FA.', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function regenerateCodes() {
    setBusy(true)
    try {
      const result = await api.twoFactorBackupCodes(verificationCode.trim())
      setTwoFactor({ phase: 'backup-codes', codes: result.backup_codes })
      setVerificationCode('')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Enter a current 6-digit code first.', 'error')
    } finally {
      setBusy(false)
    }
  }

  function copyCodes() {
    if (!twoFactor || twoFactor.phase !== 'backup-codes') return
    void navigator.clipboard.writeText(twoFactor.codes.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function downloadCodes() {
    if (!twoFactor || twoFactor.phase !== 'backup-codes') return
    const blob = new Blob(
      [
        'SAS RESERVE — Two-Factor Backup Codes\n',
        'Each code can be used once.\n\n',
        twoFactor.codes.join('\n'),
        '\n',
      ],
      { type: 'text/plain' },
    )
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'sas-reserve-backup-codes.txt'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  if (!user) return null

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        eyebrow="SAS Settings"
        title="Settings"
        description="Manage your profile information, security, and preferences."
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
          <Field label="Organization" htmlFor="organization">
            <Input id="organization" value={organization} onChange={(event) => setOrganization(event.target.value)} />
          </Field>
          <Field label="Phone" htmlFor="phone">
            <Input id="phone" value={phone} onChange={(event) => setPhone(event.target.value)} />
          </Field>
          <div className="sm:col-span-2">
            <Button type="submit" loading={saving}>
              Save changes
            </Button>
          </div>
        </form>
      </Card>

      {/* ---------------------------------------------------------- */}
      {/* Security — Two-Factor Authentication                       */}
      {/* ---------------------------------------------------------- */}
      <Card className="mt-6">
        <CardHeader
          title="Security"
          description="Protect your account with two-factor authentication."
        />

        {!twoFactorLoaded && (
          <div className="mt-4 flex items-center justify-between gap-4 rounded-xl border border-line p-4">
            <div className="flex items-center gap-3">
              <Fingerprint className="size-5 text-muted" aria-hidden />
              <p className="text-sm text-muted">Checking two-factor status…</p>
            </div>
            <Button variant="secondary" size="sm" onClick={loadTwoFactor}>
              Retry
            </Button>
          </div>
        )}

        {twoFactorLoaded && !twoFactor && (
          <div className="mt-4">
            <Button size="sm" variant="secondary" onClick={loadTwoFactor}>
              Load status
            </Button>
          </div>
        )}

        {twoFactor?.phase === 'idle' && (
          <div className="mt-4 rounded-xl border border-line p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                {twoFactor.enabled ? (
                  <span className="flex size-10 items-center justify-center rounded-xl bg-status-available-bg text-status-available">
                    <ShieldCheck className="size-5" aria-hidden />
                  </span>
                ) : (
                  <span className="flex size-10 items-center justify-center rounded-xl bg-softer text-muted">
                    <ShieldAlert className="size-5" aria-hidden />
                  </span>
                )}
                <div>
                  <p className="text-sm font-medium text-ink">Two-Factor Authentication</p>
                  <p className="text-xs text-muted">
                    Status:{' '}
                    <span className={twoFactor.enabled ? 'font-semibold text-status-available' : 'font-semibold'}>
                      {twoFactor.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    {twoFactor.enabled && (
                      <> · {twoFactor.backupCodesRemaining} backup code{twoFactor.backupCodesRemaining === 1 ? '' : 's'} remaining</>
                    )}
                  </p>
                </div>
              </div>
              {twoFactor.enabled ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setTwoFactor({ phase: 'disabling', wasEnabled: true })}
                >
                  Disable 2FA
                </Button>
              ) : (
                <Button size="sm" onClick={startSetup} loading={busy}>
                  Enable 2FA
                </Button>
              )}
            </div>
          </div>
        )}

        {twoFactor?.phase === 'setup' && (
          <form onSubmit={confirmSetup} className="mt-4 space-y-4 rounded-xl border border-line p-4">
            <p className="text-sm font-medium text-ink">1. Scan this QR code with your authenticator app</p>
            <p className="text-xs text-muted">
              Works with Google Authenticator, Microsoft Authenticator, Authy, or any standard TOTP app.
            </p>
            <div className="rounded-xl bg-white p-3 inline-block">
              <img src={twoFactor.qrPngDataUrl} alt="2FA QR code" className="size-44" />
            </div>
            <details className="text-xs text-muted">
              <summary className="cursor-pointer select-none">Can't scan? Enter this code manually</summary>
              <code className="mt-1 block break-all rounded bg-soft px-2 py-1 font-mono text-ink">
                {twoFactor.secret}
              </code>
            </details>

            <p className="text-sm font-medium text-ink">2. Enter the 6-digit code to confirm</p>
            <Field label="Verification code" htmlFor="twofa-verify">
              <Input
                id="twofa-verify"
                value={verificationCode}
                onChange={(event) => setVerificationCode(event.target.value)}
                placeholder="000000"
                maxLength={6}
                required
                className="w-40 tracking-[0.3em]"
              />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" loading={busy}>Confirm &amp; enable</Button>
              <Button type="button" variant="secondary" onClick={() => setTwoFactor(null)}>
                Cancel
              </Button>
            </div>
          </form>
        )}

        {twoFactor?.phase === 'backup-codes' && (
          <div className="mt-4 space-y-4 rounded-xl border border-line p-4">
            <div>
              <p className="text-sm font-semibold text-ink">Save these backup codes somewhere secure.</p>
              <p className="mt-0.5 text-xs text-status-rejected">
                They can be used to access your account if you lose your authenticator device. Each code works
                only once, and they will not be shown again.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 rounded-xl bg-soft p-4 sm:grid-cols-5">
              {twoFactor.codes.map((code) => (
                <code key={code} className="text-center font-mono text-sm font-semibold text-ink">
                  {code}
                </code>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={copyCodes} icon={copied ? <Check className="size-4" /> : <Copy className="size-4" />}>
                {copied ? 'Copied' : 'Copy codes'}
              </Button>
              <Button size="sm" variant="secondary" onClick={downloadCodes} icon={<Download className="size-4" />}>
                Download
              </Button>
              <Button size="sm" onClick={() => setTwoFactor({ phase: 'idle', enabled: true, backupCodesRemaining: 10 })}>
                Done
              </Button>
            </div>
          </div>
        )}

        {twoFactor?.phase === 'disabling' && (
          <form onSubmit={disableTwoFactor} className="mt-4 space-y-4 rounded-xl border border-line p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-ink">
              <ShieldAlert className="size-4 text-status-rejected" aria-hidden />
              Disable two-factor authentication
            </div>
            <p className="text-xs text-muted">
              This lowers your account security. Confirm your password to continue
              {twoFactor.wasEnabled ? ', and optionally a current 6-digit code' : ''}.
            </p>
            <Field label="Current password" htmlFor="twofa-disable-password">
              <Input
                id="twofa-disable-password"
                type="password"
                autoComplete="current-password"
                value={disablePassword}
                onChange={(event) => setDisablePassword(event.target.value)}
                required
              />
            </Field>
            <Field label="6-digit code (optional)" htmlFor="twofa-disable-code">
              <Input
                id="twofa-disable-code"
                value={disableCode}
                onChange={(event) => setDisableCode(event.target.value)}
                placeholder="000000"
                maxLength={11}
                className="w-40 tracking-[0.3em]"
              />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" loading={busy} variant="secondary">
                Disable 2FA
              </Button>
              <Button type="button" variant="secondary" onClick={() => setTwoFactor(null)}>
                Cancel
              </Button>
            </div>
          </form>
        )}

        {/* Regenerate backup codes — available while enabled. */}
        {twoFactor?.phase === 'idle' && twoFactor.enabled && (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer select-none text-muted transition-colors hover:text-ink">
              View / regenerate backup codes
            </summary>
            <div className="mt-3 flex flex-wrap items-end gap-3 rounded-xl border border-line p-4">
              <Field label="Current 6-digit code" htmlFor="regen-code">
                <Input
                  id="regen-code"
                  value={verificationCode}
                  onChange={(event) => setVerificationCode(event.target.value)}
                  placeholder="000000"
                  maxLength={6}
                  className="w-40 tracking-[0.3em]"
                />
              </Field>
              <Button size="sm" variant="secondary" onClick={regenerateCodes} loading={busy}>
                Generate new codes
              </Button>
              <p className="text-xs text-muted">
                Generating a new batch invalidates all previous backup codes.
              </p>
            </div>
          </details>
        )}
      </Card>
    </div>
  )
}
