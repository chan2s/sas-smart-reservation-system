import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  Search,
  Users,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  useAvailabilityCheck,
  useCampusUsers,
  useCreateReservation,
  useEquipment,
  useFacilities,
  useRecommendResources,
} from '@/hooks/queries'
import { useToast } from '@/components/ui/Toast'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Input, Select } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'
import { Stepper } from '@/components/reservations/Stepper'
import {
  StepFacility,
  StepSchedule,
  StepDetails,
  StepResources,
  StepReview,
  ConfirmationRow,
  type EventDetails,
} from '@/components/reservations/wizard-steps'
import { useAuth } from '@/hooks/useAuth'
import { cn, formatTime } from '@/lib/utils'
import { manilaCalendarDate } from '@/components/reservations/wizard-steps'
import type {
  AlternativeSlot,
  AvailabilityCheck as AvailabilityCheckResult,
  CampusUserOption,
  Recommendation,
  ReservationDetail,
} from '@/lib/types'

const CAMPUS_STEPS = [
  { key: 'facility', label: 'Facility' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'details', label: 'Event Details' },
  { key: 'resources', label: 'Resources' },
  { key: 'review', label: 'Review' },
]

const ADMIN_STEPS = [
  { key: 'requester', label: 'Requester' },
  ...CAMPUS_STEPS,
]

type StepKey = (typeof ADMIN_STEPS)[number]['key']

const EMPTY_DETAILS: EventDetails = {
  event_name: '',
  event_type: 'SEMINAR',
  organization: '',
  purpose: '',
  description: '',
  expected_participants: '',
  contact_person: '',
  special_requirements: '',
  notes: '',
}

const EMPTY_EXTERNAL = {
  organization: '',
  organization_type: 'SCHOOL',
  contact_person: '',
  contact_email: '',
}

export function ReservationWizardPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { toast } = useToast()
  const { user } = useAuth()
  const isAdmin = user?.role === 'ADMIN'

  const [step, setStep] = useState(0)
  const [facilityId, setFacilityId] = useState<number | null>(() => {
    const param = searchParams.get('facility')
    return param ? Number(param) : null
  })
  const [date, setDate] = useState<Date | null>(null)
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [details, setDetails] = useState<EventDetails>(EMPTY_DETAILS)
  const [items, setItems] = useState<Record<number, number>>({})
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null)
  const [recommendationDismissed, setRecommendationDismissed] = useState(false)
  const [recommendationsApplied, setRecommendationsApplied] = useState(false)
  const [stepError, setStepError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState<ReservationDetail | null>(null)

  // Requester identification — administrators choose who the reservation is
  // FOR (campus user or external organization). Non-admins are always their
  // own requester, so the whole step is skipped for them.
  const [requesterType, setRequesterType] = useState<'CAMPUS' | 'EXTERNAL'>('CAMPUS')
  const [selectedUser, setSelectedUser] = useState<CampusUserOption | null>(null)
  const [userSearch, setUserSearch] = useState('')
  const [external, setExternal] = useState(EMPTY_EXTERNAL)

  const steps = isAdmin ? ADMIN_STEPS : CAMPUS_STEPS
  const stepKey: StepKey = steps[Math.min(step, steps.length - 1)].key

  const { data: facilities } = useFacilities()
  const campusUsers = useCampusUsers(
    userSearch,
    Boolean(isAdmin && requesterType === 'CAMPUS' && stepKey === 'requester'),
  )
  const dateISO = date ? format(date, 'yyyy-MM-dd') : ''
  const equipmentParams = useMemo(() => {
    const params: Record<string, string> = {}
    if (dateISO) params.date = dateISO
    if (startTime) params.start = startTime
    if (endTime) params.end = endTime
    return params
  }, [dateISO, startTime, endTime])
  const { data: equipment } = useEquipment(Object.keys(equipmentParams).length ? equipmentParams : undefined)

  const availabilityCheck = useAvailabilityCheck()
  const recommendResources = useRecommendResources()
  const createReservation = useCreateReservation()

  const today = manilaCalendarDate()
  const dateInvalid = date != null && date <= today
  const scheduleComplete = Boolean(facilityId && date && startTime && endTime)
  // Only the final submission is gated on a clean availability report. Step
  // navigation stays clickable on every step and validates inline via goNext(),
  // so Continue can never silently dead-end the wizard as a disabled button.
  const canSubmit =
    scheduleComplete && !dateInvalid && availabilityCheck.data != null && availabilityCheck.data.overall.ok

  const facility = facilities?.find((item) => item.id === facilityId)
  const itemsList = useMemo(
    () => Object.entries(items).map(([equipmentId, quantity]) => ({ equipment_id: Number(equipmentId), quantity })),
    [items],
  )

  // Live availability check whenever the proposal changes.
  // Stale results are cleared the moment the schedule becomes invalid so the
  // UI never shows "Availability confirmed" for an unusable date/time.
  useEffect(() => {
    if (!scheduleComplete || dateInvalid) {
      if (dateInvalid) {
        availabilityCheck.reset()
      }
      return
    }
    const timer = window.setTimeout(() => {
      availabilityCheck.mutate({
        facility_id: facilityId!,
        date: dateISO,
        start_time: startTime,
        end_time: endTime,
        items: itemsList,
      })
    }, 350)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facilityId, dateISO, startTime, endTime, itemsList, dateInvalid])

  // Smart recommendations on the Resources step, using the completed event
  // details plus the proposed schedule so quantities are availability-capped.
  useEffect(() => {
    if (stepKey === 'resources' && !recommendationDismissed && recommendations === null && scheduleComplete && !dateInvalid) {
      recommendResources.mutate(
        {
          event_type: details.event_type,
          expected_participants: Number(details.expected_participants) || 0,
          facility_id: facilityId ?? undefined,
          purpose: details.purpose,
          special_requirements: details.special_requirements,
          date: dateISO,
          start_time: startTime,
          end_time: endTime,
        },
        { onSuccess: (data) => setRecommendations(data.recommendations) },
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  function applyRecommendations() {
    if (!recommendations) return
    const next: Record<number, number> = { ...items }
    for (const recommendation of recommendations) {
      // `recommended` is already capped server-side by availability.
      if (recommendation.recommended > 0) next[recommendation.equipment_id] = recommendation.recommended
    }
    setItems(next)
    setRecommendationsApplied(true)
  }

  function setQuantity(equipmentId: number, quantity: number, available: number) {
    setItems((current) => {
      const next = { ...current }
      if (quantity <= 0) delete next[equipmentId]
      else next[equipmentId] = Math.min(quantity, available)
      return next
    })
  }

  function useAlternative(alternative: AlternativeSlot) {
    setDate(new Date(`${alternative.date}T00:00:00`))
    setStartTime(alternative.start_time)
    setEndTime(alternative.end_time)
  }

  const participants = Number(details.expected_participants) || 0
  const missingDetails = useMemo(() => {
    const missing: string[] = []
    if (!details.event_name.trim()) missing.push('Event name')
    if (!details.event_type) missing.push('Event type')
    if (!details.purpose.trim()) missing.push('Event purpose')
    if (participants < 1) missing.push('Expected participants')
    return missing
  }, [details, participants])

  /**
   * Continue is always enabled. When a step's requirements are missing we
   * surface inline validation feedback instead of silently blocking the
   * button, so the user always knows what to do next.
   */
  function goNext() {
    if (stepKey === 'requester' && requesterType === 'CAMPUS' && !selectedUser) {
      setStepError('Search for and select the campus user this reservation is for.')
      return
    }
    if (stepKey === 'requester' && requesterType === 'EXTERNAL') {
      const missing: string[] = []
      if (!external.organization.trim()) missing.push('Organization / school name')
      if (!external.contact_person.trim()) missing.push('Contact person')
      if (!external.contact_email.trim()) missing.push('Email address')
      if (missing.length > 0) {
        setStepError(`Complete the requester information: ${missing.join(', ')}.`)
        return
      }
    }
    if (stepKey === 'facility' && facilityId == null) {
      setStepError('Select a facility to continue.')
      return
    }
    if (stepKey === 'schedule' && !scheduleComplete) {
      setStepError('Choose a date, start time, and end time to continue.')
      return
    }
    if (stepKey === 'schedule' && dateInvalid) {
      setStepError('Please choose a future date.')
      return
    }
    if (stepKey === 'schedule' && availabilityCheck.data == null) {
      setStepError('Check availability before continuing.')
      return
    }
    if (stepKey === 'details' && missingDetails.length > 0) {
      setStepError(`Complete the highlighted fields to continue: ${missingDetails.join(', ')}.`)
      return
    }
    setStepError(null)
    setStep(step + 1)
  }

  function goBack() {
    setStepError(null)
    if (step === 0) navigate('/reservations')
    else setStep(step - 1)
  }

  async function submit() {
    if (!facilityId || !scheduleComplete || dateInvalid || availabilityCheck.data == null || !availabilityCheck.data.overall.ok) return
    const requesterPayload = isAdmin
      ? requesterType === 'EXTERNAL'
        ? {
            requester_type: 'EXTERNAL' as const,
            organization: external.organization,
            organization_type: external.organization_type,
            contact_person: external.contact_person,
            contact_email: external.contact_email,
          }
        : { requester_type: 'CAMPUS' as const, requester_id: selectedUser!.id }
      : {}
    createReservation.mutate(
      {
        facility_id: facilityId,
        date: dateISO,
        start_time: startTime,
        end_time: endTime,
        event_name: details.event_name,
        event_type: details.event_type,
        organization: requesterType === 'EXTERNAL' ? external.organization : details.organization,
        purpose: details.purpose,
        description: details.description,
        expected_participants: participants,
        contact_person:
          requesterType === 'EXTERNAL' ? external.contact_person : details.contact_person,
        ...requesterPayload,
        special_requirements: details.special_requirements,
        notes: details.notes,
        items: itemsList,
      },
      {
        onSuccess: (reservation) => {
          setSubmitted(reservation)
          document.querySelector('main')?.scrollTo({ top: 0 })
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 409 && error.data) {
            const data = error.data as { availability?: AvailabilityCheckResult }
            if (data.availability) {
              availabilityCheck.mutate(
                {
                  facility_id: facilityId,
                  date: dateISO,
                  start_time: startTime,
                  end_time: endTime,
                  items: itemsList,
                },
                { onSuccess: () => setStep(1) },
              )
            }
          }
          toast('Unable to submit reservation. Please review the schedule.', 'error')
        },
      },
    )
  }

  // ------------------------------------------------------------------
  // Post-submit confirmation (uses the backend's actual status)
  // ------------------------------------------------------------------
  if (submitted) {
    const approved = submitted.status === 'APPROVED'
    return (
      <div className="mx-auto max-w-xl">
        <Card className="p-8 text-center">
          <span
            className={`mx-auto flex size-14 items-center justify-center rounded-2xl ${
              approved ? 'bg-status-available-bg text-status-available' : 'bg-brand-soft text-brand'
            }`}
          >
            <CheckCircle2 className="size-7" aria-hidden />
          </span>
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink">
            {approved ? 'Reservation approved' : 'Reservation submitted'}
          </h1>
          <p className="mx-auto mt-2 max-w-sm text-[15px] text-body">
            {approved
              ? 'Your reservation has been automatically approved and confirmed.'
              : 'Your reservation has been submitted for approval. You will be notified once SAS reviews it.'}
          </p>
          <div className="mt-4 flex justify-center">
            {approved ? (
              <Badge tone="emerald">Approved</Badge>
            ) : (
              <Badge tone="amber">Pending approval</Badge>
            )}
          </div>

          <dl className="mt-6 divide-y divide-line rounded-xl border border-line bg-soft/60 px-5 text-left">
            <ConfirmationRow label="Reservation ID" value={submitted.reservation_id} />
            <ConfirmationRow label="Facility" value={submitted.facility} />
            <ConfirmationRow
              label="Date"
              value={format(new Date(`${submitted.date}T00:00:00`), 'MMMM d, yyyy')}
            />
            <ConfirmationRow
              label="Time"
              value={`${formatTime(submitted.start_time)} – ${formatTime(submitted.end_time)}`}
            />
            <ConfirmationRow label="Event" value={submitted.event_name} />
            <ConfirmationRow label="Requester" value={submitted.requester} />
          </dl>

          <div className="mt-7 flex flex-col gap-2.5 sm:flex-row sm:justify-center">
            <Button onClick={() => navigate(`/reservations/${submitted.id}`)}>View reservation</Button>
            <Button variant="outline" onClick={() => navigate('/reservations')}>
              Back to reservations
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl">
      <Link
        to="/reservations"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> Back to reservations
      </Link>

      <div className="mt-4">
        <h1 className="text-[32px] font-semibold tracking-tight text-ink">New reservation</h1>
        <p className="mt-1.5 text-[15px] text-body">
          Reserve a facility and the resources you need for your event.
        </p>
      </div>

      <div className="mt-8">
        <Stepper
          steps={steps}
          current={step}
          onStepClick={(index) => {
            // Allow going back to any completed step; Resources (3) requires
            // completed event details, so jumping forward is never allowed.
            if (index < step) {
              setStepError(null)
              setStep(index)
            }
          }}
        />
      </div>

      <div className="mt-8">
        {stepKey === 'requester' && (
          <StepRequester
            requesterType={requesterType}
            onRequesterType={(type) => {
              setRequesterType(type)
              setStepError(null)
            }}
            selectedUser={selectedUser}
            onSelectUser={setSelectedUser}
            search={userSearch}
            onSearch={setUserSearch}
            searchResults={campusUsers.data?.results ?? []}
            searching={campusUsers.isFetching}
            external={external}
            onExternalChange={setExternal}
            showErrors={stepError != null}
          />
        )}

        {stepKey === 'facility' && (
          <StepFacility
            facilities={facilities ?? []}
            selected={facilityId}
            onSelect={(id) => setFacilityId(id)}
          />
        )}

        {stepKey === 'schedule' && (
          <StepSchedule
            facility={facility}
            date={date}
            onDateChange={setDate}
            startTime={startTime}
            endTime={endTime}
            onStartTime={setStartTime}
            onEndTime={setEndTime}
            report={availabilityCheck.data ?? null}
            checking={availabilityCheck.isPending}
            onUseAlternative={useAlternative}
            dateInvalid={dateInvalid}
          />
        )}

        {stepKey === 'details' && (
          <StepDetails
            details={details}
            onChange={setDetails}
            showErrors={stepError != null}
            missing={missingDetails}
          />
        )}

        {stepKey === 'resources' && (
          <StepResources
            equipment={equipment ?? []}
            items={items}
            onQuantity={setQuantity}
            recommendations={recommendations}
            recommendationLoading={recommendResources.isPending}
            recommendationApplied={recommendationsApplied}
            onAcceptRecommendations={applyRecommendations}
            onDismissRecommendations={() => setRecommendationDismissed(true)}
            eventContext={{
              eventName: details.event_name,
              participants: participants.toLocaleString(),
              facilityName: facility?.name ?? '',
              schedule: startTime && endTime ? `${formatTime(startTime)} – ${formatTime(endTime)}` : '',
            }}
          />
        )}

        {stepKey === 'review' && (
          <StepReview
            facilityName={facility?.name ?? ''}
            facilityType={facility?.facility_type ?? ''}
            dateISO={dateISO}
            startTime={startTime}
            endTime={endTime}
            details={details}
            participants={participants}
            equipment={equipment ?? []}
            items={items}
            report={availabilityCheck.data ?? null}
            checking={availabilityCheck.isPending}
            onUseAlternative={useAlternative}
            isAdmin={isAdmin}
            requesterSection={
              isAdmin ? (
                <Card>
                  <CardHeader
                    title="Requester"
                    description="Who this reservation is for — separate from who created it"
                  />
                  <div className="mt-4 flex items-center gap-3">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-sm font-semibold text-brand">
                      {requesterType === 'EXTERNAL'
                        ? (external.organization || 'E').slice(0, 2).toUpperCase()
                        : (selectedUser?.display_name || '?')
                            .split(' ')
                            .map((part) => part[0])
                            .slice(0, 2)
                            .join('')
                            .toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink">
                        {requesterType === 'EXTERNAL'
                          ? external.organization
                          : selectedUser?.display_name}
                      </p>
                      <p className="text-xs text-muted">
                        {requesterType === 'EXTERNAL'
                          ? `External Organization · ${external.contact_person} · ${external.contact_email}`
                          : `Campus User · ${selectedUser?.organization || selectedUser?.email || ''}`}
                      </p>
                    </div>
                  </div>
                </Card>
              ) : undefined
            }
          />
        )}
      </div>

      {isAdmin && (step === 3 || step === 4) && (
        <div className="mt-6 flex items-start gap-2.5 rounded-xl border border-brand/20 bg-brand-soft/50 px-4 py-3 text-sm text-brand">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <span className="font-semibold">Administrator reservation.</span>{' '}
            Reservations created by administrators are automatically approved.
          </p>
        </div>
      )}

      {/*
       * Sticky action footer. Pinned to the bottom of the scroll container
       * (<main>), so Back / Continue stay visible and clickable no matter how
       * far the user has scrolled through a long step. On mobile it clears
       * the fixed bottom navigation. Solid background + top border + z-index
       * keep it from overlapping content visually.
       */}
      <div className="sticky bottom-[calc(4rem_+_env(safe-area-inset-bottom))] z-10 -mx-4 mt-6 border-t border-line bg-soft px-4 py-4 sm:-mx-6 sm:px-6 lg:bottom-0 lg:-mx-10 lg:px-10">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3">
          {stepError && (
            <p
              role="alert"
              className="rounded-lg border border-status-pending/25 bg-status-pending-bg px-3.5 py-2.5 text-sm text-status-pending"
            >
              {stepError}
            </p>
          )}
          <div className="flex items-center justify-between gap-3">
            <Button
              variant="outline"
              onClick={goBack}
              disabled={createReservation.isPending}
            >
              <ArrowLeft className="size-4" /> Back
            </Button>
            {step < steps.length - 1 ? (
              <Button onClick={goNext}>
                Continue <ArrowRight className="size-4" />
              </Button>
            ) : (
              <Button
                onClick={submit}
                loading={createReservation.isPending}
                disabled={!canSubmit || createReservation.isPending}
                title={
                  availabilityCheck.data && !availabilityCheck.data.overall.ok
                    ? 'Resolve the conflicts above before submitting'
                    : undefined
                }
              >
                {isAdmin ? 'Create approved reservation' : 'Submit reservation'}{' '}
                <ArrowRight className="size-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Requester step (administrators only)
// ---------------------------------------------------------------------------

const ORGANIZATION_TYPE_OPTIONS: [string, string][] = [
  ['SCHOOL', 'School'],
  ['GOVERNMENT', 'Government Organization'],
  ['PRIVATE', 'Private Organization'],
  ['COMMUNITY', 'Community Organization'],
  ['SPORTS', 'Sports Organization'],
  ['COMPANY', 'Company'],
  ['INDIVIDUAL', 'Individual'],
  ['OTHER', 'Other'],
]

function StepRequester({
  requesterType,
  onRequesterType,
  selectedUser,
  onSelectUser,
  search,
  onSearch,
  searchResults,
  searching,
  external,
  onExternalChange,
  showErrors,
}: {
  requesterType: 'CAMPUS' | 'EXTERNAL'
  onRequesterType: (type: 'CAMPUS' | 'EXTERNAL') => void
  selectedUser: CampusUserOption | null
  onSelectUser: (user: CampusUserOption | null) => void
  search: string
  onSearch: (value: string) => void
  searchResults: CampusUserOption[]
  searching: boolean
  external: {
    organization: string
    organization_type: string
    contact_person: string
    contact_email: string
  }
  onExternalChange: (next: {
    organization: string
    organization_type: string
    contact_person: string
    contact_email: string
  }) => void
  showErrors: boolean
}) {
  const setExternal = (key: keyof typeof external, value: string) =>
    onExternalChange({ ...external, [key]: value })

  const externalFieldError = (label: string, empty: boolean) =>
    showErrors && empty ? `${label} is required.` : undefined

  return (
    <section aria-label="Who is this reservation for?">
      <h2 className="text-lg font-semibold text-ink">Who is this reservation for?</h2>
      <p className="mt-1 text-sm text-body">
        Choose the requester. This is separate from your administrator account —
        the reservation is recorded on their behalf.
      </p>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => onRequesterType('CAMPUS')}
          aria-pressed={requesterType === 'CAMPUS'}
          className={cn(
            'card text-left transition-shadow',
            requesterType === 'CAMPUS' && 'ring-2 ring-brand ring-offset-2',
          )}
        >
          <div className="flex items-start gap-3 p-4">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
              <Users className="size-4.5" aria-hidden />
            </span>
            <div>
              <p className="text-sm font-semibold text-ink">Campus User</p>
              <p className="mt-0.5 text-[13px] text-body">
                Reserve on behalf of a student, faculty, or staff account.
              </p>
            </div>
          </div>
        </button>
        <button
          type="button"
          onClick={() => onRequesterType('EXTERNAL')}
          aria-pressed={requesterType === 'EXTERNAL'}
          className={cn(
            'card text-left transition-shadow',
            requesterType === 'EXTERNAL' && 'ring-2 ring-brand ring-offset-2',
          )}
        >
          <div className="flex items-start gap-3 p-4">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
              <Building2 className="size-4.5" aria-hidden />
            </span>
            <div>
              <p className="text-sm font-semibold text-ink">External Organization</p>
              <p className="mt-0.5 text-[13px] text-body">
                Another school, government, company, or community group.
              </p>
            </div>
          </div>
        </button>
      </div>

      {requesterType === 'CAMPUS' ? (
        <Card className="mt-5">
          <CardHeader
            title="Search campus user"
            description="Find the account this reservation is for"
          />
          <div className="relative mt-4">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
              aria-hidden
            />
            <Input
              type="search"
              value={search}
              onChange={(event) => onSearch(event.target.value)}
              placeholder="Search name, username, or email…"
              className="pl-9"
              aria-label="Search campus users"
            />
          </div>
          {showErrors && !selectedUser && (
            <p className="mt-2 text-xs text-status-rejected">
              Select a campus user to continue.
            </p>
          )}
          <div className="mt-3 max-h-64 space-y-1.5 overflow-y-auto">
            {searching && searchResults.length === 0 && (
              <p className="px-1 py-3 text-sm text-muted">Searching…</p>
            )}
            {!searching && searchResults.length === 0 && search.trim() && (
              <p className="px-1 py-3 text-sm text-muted">No campus users match your search.</p>
            )}
            {searchResults.map((option) => {
              const isSelected = selectedUser?.id === option.id
              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => onSelectUser(option)}
                  aria-pressed={isSelected}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors',
                    isSelected
                      ? 'border-brand bg-brand-soft/40'
                      : 'border-line hover:border-line-strong hover:bg-soft',
                  )}
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand">
                    {option.display_name
                      .split(' ')
                      .map((part) => part[0])
                      .slice(0, 2)
                      .join('')
                      .toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{option.display_name}</p>
                    <p className="truncate text-xs text-muted">
                      {option.username}
                      {option.organization ? ` · ${option.organization}` : ''}
                    </p>
                  </div>
                  {isSelected && <Badge tone="brand">Selected</Badge>}
                </button>
              )
            })}
          </div>
        </Card>
      ) : (
        <Card className="mt-5">
          <CardHeader
            title="Requester information"
            description="Contact details for the external organization"
          />
          <div className="mt-4 grid gap-5 sm:grid-cols-2">
            <Field
              label="Organization / school name"
              htmlFor="ext-org"
              className="sm:col-span-2"
              error={externalFieldError('Organization / school name', !external.organization.trim())}
            >
              <Input
                id="ext-org"
                value={external.organization}
                onChange={(event) => setExternal('organization', event.target.value)}
                placeholder="e.g. ABC National High School"
              />
            </Field>
            <Field label="Organization type" htmlFor="ext-org-type">
              <Select
                id="ext-org-type"
                value={external.organization_type}
                onChange={(event) => setExternal('organization_type', event.target.value)}
              >
                {ORGANIZATION_TYPE_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Contact person"
              htmlFor="ext-contact"
              error={externalFieldError('Contact person', !external.contact_person.trim())}
            >
              <Input
                id="ext-contact"
                value={external.contact_person}
                onChange={(event) => setExternal('contact_person', event.target.value)}
                placeholder="e.g. Juan Dela Cruz"
              />
            </Field>
            <Field
              label="Email address"
              htmlFor="ext-email"
              error={externalFieldError('Email address', !external.contact_email.trim())}
              hint="Used to track the reservation."
            >
              <Input
                id="ext-email"
                type="email"
                value={external.contact_email}
                onChange={(event) => setExternal('contact_email', event.target.value)}
                placeholder="e.g. juan@example.com"
              />
            </Field>
          </div>
        </Card>
      )}
    </section>
  )
}

