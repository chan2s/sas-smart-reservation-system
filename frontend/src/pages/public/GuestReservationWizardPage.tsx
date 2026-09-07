import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, CheckCircle2 } from 'lucide-react'
import { format } from 'date-fns'
import {
  useCreateGuestReservation,
  usePublicAvailabilityCheck,
  usePublicEquipment,
  usePublicFacilities,
  usePublicRecommendResources,
} from '@/hooks/public-queries'
import { ApiError } from '@/lib/api'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
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
import { PublicShell } from '@/components/layout/PublicShell'
import { formatTime } from '@/lib/utils'
import type {
  AlternativeSlot,
  AvailabilityCheck as AvailabilityCheckResult,
  Recommendation,
} from '@/lib/types'

const STEPS = [
  { key: 'facility', label: 'Facility' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'details', label: 'Event Details' },
  { key: 'resources', label: 'Resources' },
  { key: 'review', label: 'Review' },
]

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

const EMPTY_REQUESTER = {
  organization: '',
  organization_type: 'SCHOOL',
  contact_person: '',
  contact_number: '',
  contact_email: '',
}

/**
 * Guest reservation wizard — the SAME shared workflow as the authenticated
 * wizard, but the requester identity is an external organization and the
 * submission goes to the public endpoint (no account required).
 */
export function GuestReservationWizardPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [step, setStep] = useState(0)
  const [facilityId, setFacilityId] = useState<number | null>(null)
  const [date, setDate] = useState<Date | null>(null)
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [details, setDetails] = useState<EventDetails>(EMPTY_DETAILS)
  const [requester] = useState(EMPTY_REQUESTER)
  const [items, setItems] = useState<Record<number, number>>({})
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null)
  const [recommendationDismissed, setRecommendationDismissed] = useState(false)
  const [recommendationsApplied, setRecommendationsApplied] = useState(false)
  const [stepError, setStepError] = useState<string | null>(null)
  const [submittedCode, setSubmittedCode] = useState<string | null>(null)

  const { data: facilityData } = usePublicFacilities()
  const facilities = facilityData?.results ?? []

  const dateISO = date ? format(date, 'yyyy-MM-dd') : ''
  const equipmentParams = useMemo(() => {
    const params: Record<string, string> = {}
    if (dateISO) params.date = dateISO
    if (startTime) params.start = startTime
    if (endTime) params.end = endTime
    return params
  }, [dateISO, startTime, endTime])
  const { data: equipmentData } = usePublicEquipment(
    Object.keys(equipmentParams).length ? equipmentParams : undefined,
  )
  const equipment = equipmentData?.results ?? []

  const availabilityCheck = usePublicAvailabilityCheck()
  const recommendResources = usePublicRecommendResources()
  const createReservation = useCreateGuestReservation()

  const facility = facilities.find((item) => item.id === facilityId)
  const hasSchedule = Boolean(facilityId && dateISO && startTime && endTime)
  const itemsList = useMemo(
    () =>
      Object.entries(items).map(([equipmentId, quantity]) => ({
        equipment_id: Number(equipmentId),
        quantity,
      })),
    [items],
  )

  // Live availability check whenever the proposal changes.
  useEffect(() => {
    if (!hasSchedule) return
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
  }, [facilityId, dateISO, startTime, endTime, itemsList])

  // Recommendations on the Resources step, availability-capped server-side.
  useEffect(() => {
    if (step === 3 && !recommendationDismissed && recommendations === null && hasSchedule) {
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

  const missingRequester = useMemo(() => {
    const missing: string[] = []
    if (!requester.organization.trim()) missing.push('Organization / school name')
    if (!requester.contact_person.trim()) missing.push('Contact person')
    if (!requester.contact_number.trim()) missing.push('Contact number')
    if (!/^\S+@\S+\.\S+$/.test(requester.contact_email.trim())) missing.push('A valid email address')
    return missing
  }, [requester])

  function goNext() {
    if (step === 0 && facilityId == null) {
      setStepError('Select a facility to continue.')
      return
    }
    if (step === 1 && !hasSchedule) {
      setStepError('Choose a date, start time, and end time to continue.')
      return
    }
    if (step === 2 && missingDetails.length > 0) {
      setStepError(`Complete the highlighted fields to continue: ${missingDetails.join(', ')}.`)
      return
    }
    setStepError(null)
    setStep(step + 1)
  }

  function goBack() {
    setStepError(null)
    if (step === 0) navigate('/reserve')
    else setStep(step - 1)
  }

  function submit() {
    if (!facilityId || !hasSchedule) return
    if (missingRequester.length > 0) {
      setStepError(`Complete the requester information: ${missingRequester.join(', ')}.`)
      setStep(0)
      return
    }
    createReservation.mutate(
      {
        facility_id: facilityId,
        date: dateISO,
        start_time: startTime,
        end_time: endTime,
        event_name: details.event_name,
        event_type: details.event_type,
        organization: requester.organization,
        organization_type: requester.organization_type as never,
        purpose: details.purpose,
        description: details.description,
        expected_participants: participants,
        contact_person: requester.contact_person,
        contact_number: requester.contact_number,
        contact_email: requester.contact_email,
        special_requirements: details.special_requirements,
        items: itemsList,
      },
      {
        onSuccess: (result) => setSubmittedCode(result.reservation_id),
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
  // Post-submit confirmation — code is the external requester's handle
  // ------------------------------------------------------------------
  if (submittedCode) {
    return (
      <PublicShell>
        <div className="mx-auto max-w-xl">
          <Card className="p-8 text-center">
            <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-brand-soft text-brand">
              <CheckCircle2 className="size-7" aria-hidden />
            </span>
            <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink">
              Reservation submitted successfully
            </h1>
            <p className="mx-auto mt-2 max-w-sm text-[15px] text-body">
              Your reservation request has been submitted to the SAS Office. It is
              <span className="font-semibold"> not confirmed until approved</span> by SAS.
            </p>
            <div className="mt-4 flex justify-center">
              <Badge tone="amber">Pending approval</Badge>
            </div>

            <div className="mt-6 rounded-xl border border-brand/25 bg-brand-soft/50 px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-brand">
                Your reservation code
              </p>
              <p className="mt-1 text-2xl font-bold tracking-wide text-ink">{submittedCode}</p>
              <p className="mt-1.5 text-[13px] text-body">
                Save this code — you will need it with your email address to track
                your reservation.
              </p>
            </div>

            <dl className="mt-6 divide-y divide-line rounded-xl border border-line bg-soft/60 px-5 text-left">
              <ConfirmationRow label="Status" value="PENDING APPROVAL" />
              <ConfirmationRow label="Requester" value={requester.organization} />
              <ConfirmationRow label="Facility" value={facility?.name ?? '—'} />
              <ConfirmationRow
                label="Date"
                value={dateISO ? format(new Date(`${dateISO}T00:00:00`), 'MMMM d, yyyy') : '—'}
              />
              <ConfirmationRow
                label="Time"
                value={startTime && endTime ? `${formatTime(startTime)} – ${formatTime(endTime)}` : '—'}
              />
              <ConfirmationRow label="Event" value={details.event_name} />
            </dl>

            <div className="mt-7 flex flex-col gap-2.5 sm:flex-row sm:justify-center">
              <Button onClick={() => navigate('/track-reservation')}>Track reservation</Button>
              <Button variant="outline" onClick={() => navigate('/reserve')}>
                Back to reserve
              </Button>
            </div>
          </Card>
        </div>
      </PublicShell>
    )
  }

  return (
    <PublicShell>
      <div className="mx-auto max-w-5xl">
        <Link
          to="/reserve"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
        >
          <ArrowLeft className="size-4" /> Back
        </Link>

        <div className="mt-4">
          <h1 className="text-[32px] font-semibold tracking-tight text-ink">Guest reservation</h1>
          <p className="mt-1.5 text-[15px] text-body">
            No account needed — provide your organization details and submit for SAS review.
          </p>
        </div>

        <div className="mt-8">
          <Stepper
            steps={STEPS}
            current={step}
            onStepClick={(index) => {
              if (index < step) {
                setStepError(null)
                setStep(index)
              }
            }}
          />
        </div>

        <div className="mt-8">
          {step === 0 && (
            <StepFacility
              facilities={facilities}
              selected={facilityId}
              onSelect={(id) => setFacilityId(id)}
            />
          )}

          {step === 1 && (
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
            />
          )}

          {step === 2 && (
            <StepDetails
              details={details}
              onChange={setDetails}
              showErrors={stepError != null}
              missing={missingDetails}
            />
          )}

          {step === 3 && (
            <StepResources
              equipment={equipment}
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

          {step === 4 && (
            <StepReview
              facilityName={facility?.name ?? ''}
              facilityType={facility?.facility_type_label ?? ''}
              dateISO={dateISO}
              startTime={startTime}
              endTime={endTime}
              details={details}
              participants={participants}
              equipment={equipment}
              items={items}
              report={availabilityCheck.data ?? null}
              checking={availabilityCheck.isPending}
              onUseAlternative={useAlternative}
              isAdmin={false}
              requesterSection={
                <Card>
                  <div className="p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
                      Requester information
                    </p>
                    <dl className="mt-3 grid gap-x-8 gap-y-3 sm:grid-cols-2">
                      <ConfirmationRow label="Organization" value={requester.organization || '—'} />
                      <ConfirmationRow label="Contact person" value={requester.contact_person || '—'} />
                      <ConfirmationRow label="Contact number" value={requester.contact_number || '—'} />
                      <ConfirmationRow label="Email" value={requester.contact_email || '—'} />
                    </dl>
                    {missingRequester.length > 0 && (
                      <p className="mt-3 rounded-lg bg-status-pending-bg px-3 py-2 text-[13px] text-status-pending">
                        Missing: {missingRequester.join(', ')}. Use the Back button to complete your
                        details — they are collected at the start of the wizard.
                      </p>
                    )}
                  </div>
                </Card>
              }
            />
          )}
        </div>

        <div className="mt-6 flex items-start gap-2.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-body">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
          <p>
            <span className="font-semibold">No account required.</span> After submitting you will
            receive a reservation code — use it with your email to track your request.
          </p>
        </div>

        {/* Sticky action footer */}
        <div className="sticky bottom-0 z-10 -mx-4 mt-6 border-t border-line bg-soft px-4 py-4 sm:-mx-6 sm:px-6">
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
              <Button variant="outline" onClick={goBack} disabled={createReservation.isPending}>
                <ArrowLeft className="size-4" /> Back
              </Button>
              {step < 4 ? (
                <Button onClick={goNext}>
                  Continue <ArrowRight className="size-4" />
                </Button>
              ) : (
                <Button
                  onClick={submit}
                  loading={createReservation.isPending}
                  disabled={Boolean(availabilityCheck.data && !availabilityCheck.data.overall.ok)}
                  title={
                    availabilityCheck.data && !availabilityCheck.data.overall.ok
                      ? 'Resolve the conflicts above before submitting'
                      : undefined
                  }
                >
                  Submit reservation <ArrowRight className="size-4" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </PublicShell>
  )
}
