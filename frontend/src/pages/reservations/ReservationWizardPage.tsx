import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Building2, CheckCircle2, Search, Users } from 'lucide-react'
import { format } from 'date-fns'
import {
  useAvailabilityCheck,
  useCampusUser,
  useCampusUsers,
  useCreateReservation,
  useFacilities,
  useFacilityResources,
  useReservations,
} from '@/hooks/queries'
import { useSuggestedResources } from '@/hooks/useSuggestedResources'
import { useToast } from '@/components/ui/Toast'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Input, Select } from '@/components/ui/Form'
import { Badge } from '@/components/ui/Badge'
import { Stepper } from '@/components/reservations/Stepper'
import { DetailsStep } from '@/components/reservations/DetailsStep'
import type { OperatorConfig } from '@/components/reservations/OtherEquipmentPicker'
import type { FacilitySeatingMetadata } from '@/components/reservations/resourceSuggestions'
import {
  EARLIEST_START_TIME,
  StepFacility,
  StepSchedule,
  StepReview,
  ConfirmationRow,
  AVAILABILITY_STATUS_MESSAGE,
  type AvailabilityStatus,
} from '@/components/reservations/wizard-steps'
import {
  EMPTY_DETAILS,
  clearDraft,
  loadDraft,
  missingFieldLabels,
  reservationFieldErrors,
  saveDraft,
  toCreateReservationPayload,
  type ContactDraft,
  type EventDetailsDraft,
  type SubmitItems,
  type WizardDraft,
} from '@/lib/reservationDraft'
import { useAuth } from '@/hooks/useAuth'
import { OrganizationStatusNotice } from '@/components/organizations/OrganizationStatusNotice'
import { cn, formatTime } from '@/lib/utils'
import { manilaCalendarDate } from '@/components/reservations/wizard-steps'
import type {
  AlternativeSlot,
  AvailabilityCheck as AvailabilityCheckResult,
  CampusUserOption,
  ReservationDetail,
  ReservableResource,
} from '@/lib/types'

/**
 * The four-step reservation flow (staff see an extra "Requester" step first).
 *
 * Details and Resources are ONE step: the event form sits above the suggested
 * resources, so nothing captured in a previous step is ever asked for again.
 * Facility / date / time reappear only as a read-only summary on Review.
 */
const CAMPUS_STEPS = [
  { key: 'facility', label: 'Facility' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'details', label: 'Details & Resources' },
  { key: 'review', label: 'Review' },
]

const ADMIN_STEPS = [{ key: 'requester', label: 'Requester' }, ...CAMPUS_STEPS]

type StepKey = (typeof ADMIN_STEPS)[number]['key']

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
  const { user, isStaff, loading: authLoading } = useAuth()
  const isAdmin = user?.role === 'ADMIN'

  // A refresh must not wipe the wizard: the draft is restored from
  // sessionStorage on mount and written back on every change below.
  // A `?facility=` link from a facility page wins over the draft — but only
  // its facility-scoped selections are then dropped (they belong elsewhere).
  const initial = useMemo(() => {
    const draft = loadDraft()
    const param = searchParams.get('facility')
    const paramFacilityId = param ? Number(param) : null
    if (!draft) return { draft: null, facilityId: paramFacilityId }
    if (paramFacilityId == null || draft.facilityId === paramFacilityId) {
      return { draft, facilityId: draft.facilityId ?? paramFacilityId }
    }
    return {
      draft: {
        ...draft,
        facilityId: paramFacilityId,
        items: {},
        operatorSelections: {},
        userEditedItems: [],
      },
      facilityId: paramFacilityId,
    }
    // Read once on entry: the ?facility= param and the stored draft are the
    // wizard's starting point, not something to re-evaluate on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const restored = initial.draft

  // A rebook / "request new schedule" opens this same wizard from an expired
  // reservation. The schedule is intentionally blank (a new, still-available
  // slot must be chosen); everything else is prefilled by the draft.
  const rebookedFromId = restored?.rebookedFromId ?? null
  const isRebook = rebookedFromId != null

  const [step, setStep] = useState(0)
  const [facilityId, setFacilityId] = useState<number | null>(() => initial.facilityId)
  const [date, setDate] = useState<Date | null>(() =>
    restored?.dateISO ? new Date(`${restored.dateISO}T00:00:00`) : null,
  )
  // A new schedule starts at the system-wide earliest slot (8:00 AM). A valid
  // restored draft selection is preserved; an empty one falls back to 8:00.
  const [startTime, setStartTime] = useState(restored?.startTime || EARLIEST_START_TIME)
  const [endTime, setEndTime] = useState(restored?.endTime ?? '')
  const [details, setDetails] = useState<EventDetailsDraft>(restored?.details ?? EMPTY_DETAILS)
  const [contact, setContact] = useState<ContactDraft>(
    restored?.contact ?? { name: '', phone: '' },
  )
  const [items, setItems] = useState<Record<number, number>>(restored?.items ?? {})
  // Operator/service opt-in per equipment id (e.g. the Gymnasium sound system
  // operator). Only resources the facility marks operator-available appear.
  const [operatorSelections, setOperatorSelections] = useState<Record<number, boolean>>(
    restored?.operatorSelections ?? {},
  )
  // Equipment ids the requester has manually adjusted. Their quantity is kept
  // across recalculation — suggestions never overwrite user edits.
  const [userEditedItems, setUserEditedItems] = useState<Set<number>>(
    () => new Set(restored?.userEditedItems ?? []),
  )
  const [stepError, setStepError] = useState<string | null>(null)
  // Bumped on a failed Continue so the Details step can focus the first error.
  const [focusAttempt, setFocusAttempt] = useState(0)
  const [submitted, setSubmitted] = useState<ReservationDetail | null>(null)

  // Requester identification — administrators choose who the reservation is
  // FOR (campus user or external organization). Non-admins are always their
  // own requester, so the whole step is skipped for them.
  const [requesterType, setRequesterType] = useState<'CAMPUS' | 'EXTERNAL'>(
    () => restored?.rebooker?.type ?? 'CAMPUS',
  )
  const [selectedUser, setSelectedUser] = useState<CampusUserOption | null>(null)
  const [userSearch, setUserSearch] = useState('')
  const [external, setExternal] = useState(
    () => restored?.rebooker?.external ?? EMPTY_EXTERNAL,
  )
  // Rebook: resolve the original requester account so the "who is it for" step
  // is already satisfied for staff.
  const seedRequester =
    restored?.rebooker?.type === 'CAMPUS' ? restored?.rebooker?.user : undefined
  const seedRequesterId = seedRequester?.id ?? null
  const seededRequester = useCampusUser(seedRequesterId)
  useEffect(() => {
    if (!selectedUser && seededRequester.data) setSelectedUser(seededRequester.data)
  }, [selectedUser, seededRequester.data])

  const steps = isAdmin ? ADMIN_STEPS : CAMPUS_STEPS
  const stepKey: StepKey = steps[Math.min(step, steps.length - 1)].key

  const { data: facilities } = useFacilities()
  const campusUsers = useCampusUsers(
    userSearch,
    Boolean(isAdmin && requesterType === 'CAMPUS' && stepKey === 'requester'),
  )
  const dateISO = date ? format(date, 'yyyy-MM-dd') : ''
  const participantsRaw = Number(details.expectedParticipants)
  const participants = Number.isFinite(participantsRaw) && participantsRaw > 0 ? participantsRaw : 0
  const equipmentParams = useMemo(() => {
    const params: Record<string, string> = {}
    if (dateISO) params.date = dateISO
    if (startTime) params.start = startTime
    if (endTime) params.end = endTime
    return params
  }, [dateISO, startTime, endTime])
  // Resources come from the SELECTED FACILITY, not a global equipment list.
  // The backend is the source of truth; changing the facility replaces the
  // list. Availability reflects the date/time window when set.
  const { data: resourcesData, isFetching: resourcesLoading } = useFacilityResources(
    facilityId,
    Object.keys(equipmentParams).length ? equipmentParams : undefined,
  )
  const resources = resourcesData?.resources ?? []
  const equipment = useMemo<ReservableResource[]>(
    () =>
      resources.map((resource) => ({
        id: resource.equipment_id,
        name: resource.name,
        category: resource.category,
        description: resource.description || resource.equipment_description,
        total_quantity: resource.total_quantity,
        unit: resource.unit,
        status: resource.equipment_status,
        status_label: resource.status_label,
        image: resource.image,
        images: resource.images,
        availability: resource.availability,
      })),
    [resources],
  )
  const operatorConfig = useMemo<Record<number, OperatorConfig>>(() => {
    const config: Record<number, OperatorConfig> = {}
    for (const resource of resources) {
      if (resource.operator_available || resource.operator_required) {
        config[resource.equipment_id] = {
          available: resource.operator_available,
          required: resource.operator_required,
          fee: resource.operator_fee,
        }
      }
    }
    return config
  }, [resources])

  const availabilityCheck = useAvailabilityCheck()
  const createReservation = useCreateReservation()

  const today = manilaCalendarDate()
  // Only past dates are invalid. Today IS bookable, but dates within the
  // 2-day cancellation window (today/tomorrow) trigger a non-cancellable
  // policy notice (the backend enforces the same rule).
  const dateInvalid = date != null && date < today
  const dayDiff = date != null ? Math.round((date.getTime() - today.getTime()) / 86_400_000) : -1
  const inCancellationWindow = dayDiff >= 0 && dayDiff <= 1
  const scheduleComplete = Boolean(facilityId && date && startTime && endTime)
  // A member of an organization that is not Approved cannot continue or
  // submit at all — the backend enforces this regardless, but say so up front.
  const canCreateReservations = user?.can_create_reservations ?? true

  const facility = facilities?.find((item) => item.id === facilityId)

  // ------------------------------------------------------------------
  // Contact person — prefilled from the profile / most recent reservation
  // ------------------------------------------------------------------
  // The organization is never typed: it always comes from the account (or,
  // for staff, from the selected campus requester).
  const accountOrganization = useMemo(() => {
    // Managed internal organizations carry a display_name of the form
    // "CAS — College of Arts and Sciences"; prefer it so the "Reserving as"
    // line and the reservation snapshot a human-readable value.
    const linked =
      user?.organization_ref?.display_name?.trim() ||
      user?.organization_ref?.organization_name?.trim()
    return linked || user?.organization?.trim() || ''
  }, [user])
  const reservingAs = isAdmin
    ? requesterType === 'CAMPUS'
      ? selectedUser?.organization?.trim() || ''
      : external.organization.trim()
    : accountOrganization

  // The requester's own most recent reservation carries the last phone number
  // they used — the only place a phone number is stored (there is no phone
  // field on the account, by design).
  const myReservations = useReservations({ requester: user?.id, page: 1 }, Boolean(user?.id))
  const contactPrefilled = useRef(false)
  useEffect(() => {
    if (!user) return
    setContact((current) =>
      current.name ? current : { ...current, name: user.display_name || user.username },
    )
  }, [user])
  useEffect(() => {
    if (!user || contactPrefilled.current) return
    if (!myReservations.isSuccess && !myReservations.isError) return
    contactPrefilled.current = true
    const lastPhone = (myReservations.data?.results ?? []).find(
      (reservation) => reservation.requester_id === user.id && reservation.contact_phone,
    )?.contact_phone
    if (!lastPhone) return
    setContact((current) => (current.phone ? current : { ...current, phone: lastPhone }))
  }, [user, myReservations.isSuccess, myReservations.isError, myReservations.data])

  // ------------------------------------------------------------------
  // Details validation (single source of truth for the Continue gate)
  // ------------------------------------------------------------------
  const fieldErrors = useMemo(
    () =>
      reservationFieldErrors({
        details,
        contact,
        capacity: facility?.capacity ?? 0,
        facilityName: facility?.name ?? '',
      }),
    [details, contact, facility],
  )
  const missingDetails = useMemo(() => missingFieldLabels(fieldErrors), [fieldErrors])

  // ------------------------------------------------------------------
  // Suggested resources (rule config + the backend recommender)
  // ------------------------------------------------------------------
  // What the chosen facility already provides, so suggestions subtract it.
  const facilityMetadata = useMemo<FacilitySeatingMetadata>(
    () => ({
      seatingType: facility?.seating_type ?? null,
      builtInSeats: facility?.built_in_seats ?? null,
      builtIns: facility?.built_ins ?? [],
    }),
    [facility],
  )

  const {
    suggestions,
    unmatched,
    included,
    loading: suggestionsLoading,
  } = useSuggestedResources({
    // Only fetch while the step that shows the suggestions is on screen — the
    // recommender takes the free-text purpose/notes, so it must not fire on
    // every keystroke while the requester is still on an earlier step.
    active: stepKey === 'details',
    eventType: details.eventType,
    participants,
    equipment,
    facility: facilityMetadata,
    facilityId,
    dateISO,
    startTime,
    endTime,
    purpose: details.purpose,
    staffNotes: details.staffNotes,
    requesterType,
  })

  // Suggestions are checked by default: seed the quantities, but never touch a
  // resource the requester has edited by hand (including one they unchecked).
  const suggestionFingerprint = suggestions
    .map((suggestion) => `${suggestion.equipmentId}:${suggestion.quantity}`)
    .join(',')
  useEffect(() => {
    if (!suggestionFingerprint) return
    setItems((current) => {
      let changed = false
      const next = { ...current }
      for (const suggestion of suggestions) {
        if (userEditedItems.has(suggestion.equipmentId)) continue
        // Rows the requester must opt into (unverified seating) seed to zero.
        const target = suggestion.checkedByDefault ? suggestion.quantity : 0
        if (target > 0) {
          if (next[suggestion.equipmentId] !== target) {
            next[suggestion.equipmentId] = target
            changed = true
          }
        } else if (next[suggestion.equipmentId]) {
          delete next[suggestion.equipmentId]
          changed = true
        }
      }
      return changed ? next : current
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestionFingerprint, userEditedItems])

  const itemsList = useMemo<SubmitItems[]>(
    () =>
      Object.entries(items).map(([equipmentId, quantity]) => {
        const id = Number(equipmentId)
        return {
          equipment_id: id,
          quantity,
          // Explicit opt-in/out so the backend never adds the operator fee
          // unless it was actually requested (or the resource requires it).
          operator: operatorSelections[id] ?? Boolean(operatorConfig[id]?.required),
        }
      }),
    [items, operatorSelections, operatorConfig],
  )

  // Changing the facility replaces its resource list: clear any selection made
  // for the previous facility so Gymnasium resources never linger for the AVR.
  // The very first run is skipped: on mount the items were restored from the
  // draft and belong to the restored facility.
  const facilityResetDone = useRef(false)
  useEffect(() => {
    if (!facilityResetDone.current) {
      facilityResetDone.current = true
      return
    }
    setItems({})
    setOperatorSelections({})
    setUserEditedItems(new Set())
  }, [facilityId])

  // ------------------------------------------------------------------
  // Availability state machine
  //
  // "Not yet checked" (IDLE) must never be confused with "checked and
  // available" (AVAILABLE). The request is derived from exactly the inputs
  // that affect availability (facility, date, start/end time, resources), so
  // ANY change produces a new request key and immediately invalidates the
  // previous result — a stale report can never authorise Continue.
  // ------------------------------------------------------------------
  const availabilityRequest = useMemo(() => {
    if (!scheduleComplete || dateInvalid || facilityId == null) return null
    return {
      facility_id: facilityId,
      date: dateISO,
      start_time: startTime,
      end_time: endTime,
      items: itemsList,
      // Trusted server-side: only staff can actually enable external fees.
      requester_type: requesterType,
    }
  }, [
    scheduleComplete,
    dateInvalid,
    facilityId,
    dateISO,
    startTime,
    endTime,
    itemsList,
    requesterType,
  ])

  const availabilityKey = useMemo(
    () => (availabilityRequest ? JSON.stringify(availabilityRequest) : null),
    [availabilityRequest],
  )

  const [availabilityStatus, setAvailabilityStatus] = useState<AvailabilityStatus>('IDLE')
  const [availabilityReport, setAvailabilityReport] = useState<AvailabilityCheckResult | null>(null)
  // Latest request key. A response that resolves after the inputs have changed
  // belongs to a superseded configuration and must be discarded.
  const availabilityKeyRef = useRef<string | null>(null)

  useEffect(() => {
    availabilityKeyRef.current = availabilityKey
    if (!availabilityRequest) {
      // Incomplete or invalid schedule → there is nothing to check yet.
      setAvailabilityStatus('IDLE')
      setAvailabilityReport(null)
      return
    }
    // Invalidate whatever was on screen: the previous result no longer
    // describes this configuration, so it is unchecked until the new
    // response lands.
    setAvailabilityStatus('CHECKING')
    setAvailabilityReport(null)

    let cancelled = false
    const timer = window.setTimeout(() => {
      availabilityCheck.mutate(availabilityRequest, {
        onSuccess: (data) => {
          if (cancelled || availabilityKeyRef.current !== availabilityKey) return
          setAvailabilityReport(data)
          setAvailabilityStatus(data.overall.ok ? 'AVAILABLE' : 'UNAVAILABLE')
        },
        onError: () => {
          if (cancelled || availabilityKeyRef.current !== availabilityKey) return
          setAvailabilityReport(null)
          setAvailabilityStatus('ERROR')
        },
      })
    }, 350)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availabilityKey])

  // ------------------------------------------------------------------
  // Draft persistence — restored on mount, saved on every change
  // ------------------------------------------------------------------
  useEffect(() => {
    saveDraft({
      facilityId,
      dateISO,
      startTime,
      endTime,
      details,
      contact,
      items,
      operatorSelections,
      userEditedItems: [...userEditedItems],
      stepKey,
      // Preserve the rebook lineage across a refresh mid-wizard.
      rebookedFromId,
      rebooker: restored?.rebooker ?? null,
    })
  }, [
    facilityId,
    dateISO,
    startTime,
    endTime,
    details,
    contact,
    items,
    operatorSelections,
    userEditedItems,
    stepKey,
  ])

  // Restore the step once the account is known (the step list differs for
  // staff, so this must wait for auth to settle).
  const stepRestored = useRef(false)
  useEffect(() => {
    if (stepRestored.current || authLoading) return
    stepRestored.current = true
    const index = steps.findIndex((item) => item.key === restored?.stepKey)
    if (index > 0) setStep(index)
  }, [authLoading, steps, restored])

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------
  function toggleOperator(equipmentId: number, selected: boolean) {
    setOperatorSelections((current) => ({ ...current, [equipmentId]: selected }))
  }

  function setQuantity(equipmentId: number, quantity: number, available: number) {
    setUserEditedItems((current) => new Set(current).add(equipmentId))
    setItems((current) => {
      const next = { ...current }
      if (quantity <= 0) delete next[equipmentId]
      else next[equipmentId] = Math.min(quantity, available)
      return next
    })
  }

  /** Checkbox on a suggested row: unchecking clears the quantity and is remembered. */
  function toggleSuggestion(equipmentId: number, checked: boolean, suggestedQuantity: number) {
    setUserEditedItems((current) => new Set(current).add(equipmentId))
    setItems((current) => {
      const next = { ...current }
      if (checked) next[equipmentId] = Math.max(1, suggestedQuantity)
      else delete next[equipmentId]
      return next
    })
  }

  function useAlternative(alternative: AlternativeSlot) {
    setDate(new Date(`${alternative.date}T00:00:00`))
    setStartTime(alternative.start_time)
    setEndTime(alternative.end_time)
  }

  const availabilityOk = availabilityStatus === 'AVAILABLE'
  const scheduleStepIndex = steps.findIndex((item) => item.key === 'schedule')

  // Once the step is valid again, an old "complete these fields" banner is
  // stale — clear it so the footer never nags about work already done.
  useEffect(() => {
    if (stepError && stepKey === 'details' && missingDetails.length === 0 && availabilityOk) {
      setStepError(null)
    }
  }, [stepError, stepKey, missingDetails, availabilityOk])

  // Final submission additionally re-validates on the backend (HTTP 409 on
  // conflict), but the button stays disabled until a check for the CURRENT
  // configuration has actually succeeded.
  const canSubmit = scheduleComplete && !dateInvalid && canCreateReservations && availabilityOk

  // Per-step Continue gate. Required fields must be valid AND, on the steps
  // where availability matters, the check must have succeeded for the current
  // configuration. Users not allowed to reserve (e.g. a pending external
  // organization) can never continue regardless of availability.
  const requesterStepValid = !isAdmin
    ? true
    : requesterType === 'CAMPUS'
      ? selectedUser != null
      : Boolean(external.organization.trim() && external.contact_person.trim())
  const stepFieldsValid =
    stepKey === 'requester'
      ? requesterStepValid
      : stepKey === 'facility'
        ? facilityId != null
        : stepKey === 'schedule'
          ? scheduleComplete && !dateInvalid
          : stepKey === 'details'
            ? missingDetails.length === 0
            : true
  const availabilityRequired = stepKey === 'schedule' || stepKey === 'details'
  const canContinue =
    canCreateReservations && stepFieldsValid && (!availabilityRequired || availabilityOk)

  // Always keep a human-readable reason for a disabled Continue available.
  const continueBlockedReason = !canCreateReservations
    ? user?.reservation_block_reason ||
      'Your organization must be approved before you can reserve a facility.'
    : availabilityRequired && !availabilityOk
      ? AVAILABILITY_STATUS_MESSAGE[availabilityStatus]
      : stepKey === 'details' && missingDetails.length > 0
        ? `Complete these fields: ${missingDetails.join(', ')}.`
        : stepKey === 'facility' && facilityId == null
          ? 'Select a facility to continue.'
          : stepKey === 'schedule' && !scheduleComplete
            ? 'Choose a date, start time, and end time to continue.'
            : undefined

  /**
   * Advance one step. Members of an unapproved external organization are
   * blocked outright (the Continue button is disabled for them too). For
   * everyone else, a step's missing requirements surface inline validation
   * feedback instead of silently blocking the button, so the user always
   * knows what to do next.
   */
  function goNext() {
    // External organizations must be APPROVED before any step can proceed.
    // The Continue button is disabled, but guard here too so the rule holds
    // even if the disabled state is bypassed with dev tools.
    if (!canCreateReservations) {
      setStepError(
        user?.reservation_block_reason ||
          'Your organization must be approved by an administrator before you can reserve a facility.',
      )
      return
    }
    if (stepKey === 'requester' && requesterType === 'CAMPUS' && !selectedUser) {
      setStepError('Search for and select the campus user this reservation is for.')
      return
    }
    if (stepKey === 'requester' && requesterType === 'EXTERNAL') {
      const missing: string[] = []
      if (!external.organization.trim()) missing.push('Organization / school name')
      if (!external.contact_person.trim()) missing.push('Contact person')
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
    if (stepKey === 'schedule' && !availabilityOk) {
      setStepError(AVAILABILITY_STATUS_MESSAGE[availabilityStatus])
      return
    }
    if (stepKey === 'details' && missingDetails.length > 0) {
      setStepError(`Complete the highlighted fields to continue: ${missingDetails.join(', ')}.`)
      // Focus + scroll to the first invalid field (handled in DetailsStep).
      setFocusAttempt((attempt) => attempt + 1)
      return
    }
    if (stepKey === 'details' && !availabilityOk) {
      setStepError(AVAILABILITY_STATUS_MESSAGE[availabilityStatus])
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

  /** Jump to the step that owns a read-only value shown on Review. */
  function goToStep(key: StepKey) {
    const index = steps.findIndex((item) => item.key === key)
    if (index >= 0 && index < step) {
      setStepError(null)
      setStep(index)
    }
  }

  async function submit() {
    // Defence in depth: the backend re-validates availability on create and
    // returns 409, but never send a request for a configuration that has not
    // passed the current availability check.
    if (!canSubmit || facilityId == null || missingDetails.length > 0) return
    const isExternalRequester = isAdmin && requesterType === 'EXTERNAL'
    const payload = toCreateReservationPayload(
      {
        facilityId,
        dateISO,
        startTime,
        endTime,
        details,
        contact,
        items,
        operatorSelections,
        userEditedItems: [...userEditedItems],
        stepKey,
      } satisfies WizardDraft,
      {
        items: itemsList,
        // The backend resolves the same value from the authenticated user;
        // sending it only keeps the payload self-describing.
        organization: isExternalRequester ? external.organization : reservingAs,
        ...(isAdmin && requesterType === 'CAMPUS' && selectedUser
          ? { requesterId: selectedUser.id }
          : {}),
        ...(isExternalRequester ? { external } : {}),
      },
    )

    createReservation.mutate(payload, {
      onSuccess: (reservation) => {
        clearDraft()
        setSubmitted(reservation)
        document.querySelector('main')?.scrollTo({ top: 0 })
      },
      onError: (error) => {
        // The backend refused the create because the facility/resources are
        // no longer available (someone else booked first). Surface that
        // report and send the requester back to the schedule step.
        if (error instanceof ApiError && error.status === 409 && error.data) {
          const data = error.data as { availability?: AvailabilityCheckResult }
          if (data.availability) {
            setAvailabilityReport(data.availability)
            setAvailabilityStatus(data.availability.overall.ok ? 'AVAILABLE' : 'UNAVAILABLE')
            if (scheduleStepIndex >= 0) setStep(scheduleStepIndex)
          }
        }
        toast('Unable to submit reservation. Please review the schedule.', 'error')
      },
    })
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

  // Equipment that is NOT already listed as a suggestion — rendered by the
  // "Add other equipment" picker so nothing appears twice on the step.
  const suggestedIds = new Set(suggestions.map((suggestion) => suggestion.equipmentId))
  const otherEquipment = equipment.filter((item) => !suggestedIds.has(item.id))

  return (
    <div className="mx-auto max-w-5xl">
      <Link
        to="/reservations"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> Back to reservations
      </Link>

      <div className="mt-4">
        <h1 className="text-[32px] font-semibold tracking-tight text-ink">
          {isRebook
            ? isStaff
              ? 'Rebook reservation'
              : 'Request new schedule'
            : 'New reservation'}
        </h1>
        <p className="mt-1.5 text-[15px] text-body">
          {isRebook
            ? 'This creates a new reservation that still needs approval. Choose a new date and time — the expired reservation is kept unchanged for history.'
            : 'Reserve a facility and the resources you need for your event.'}
        </p>
      </div>

      {!canCreateReservations && (
        <div className="mt-6">
          {user?.organization_verification_status ? (
            <OrganizationStatusNotice
              status={user.organization_verification_status}
              organization={user.organization_ref}
            />
          ) : (
            <p
              role="alert"
              className="rounded-xl border border-status-pending/25 bg-status-pending-bg px-3.5 py-2.5 text-sm text-status-pending"
            >
              {user?.reservation_block_reason}{' '}
              <Link to="/onboarding/affiliation" className="font-medium underline">
                Complete your organization registration
              </Link>
            </p>
          )}
        </div>
      )}

      <div className="mt-8">
        <Stepper
          steps={steps}
          current={step}
          onStepClick={(index) => {
            // Allow going back to any completed step; moving forward is only
            // ever done through Continue so each step is validated in order.
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
            report={availabilityReport}
            checking={availabilityStatus === 'CHECKING'}
            availabilityStatus={availabilityStatus}
            onUseAlternative={useAlternative}
            dateInvalid={dateInvalid}
            isCancellationRestricted={inCancellationWindow}
          />
        )}

        {stepKey === 'details' && (
          <DetailsStep
            details={details}
            onDetailsChange={setDetails}
            contact={contact}
            onContactChange={setContact}
            reservingAs={reservingAs}
            capacity={facility?.capacity ?? 0}
            facilityName={facility?.name ?? ''}
            suggestions={suggestions}
            suggestionsLoading={suggestionsLoading}
            unmatched={unmatched}
            included={included}
            items={items}
            onQuantity={setQuantity}
            onToggleSuggestion={toggleSuggestion}
            equipment={otherEquipment}
            operatorConfig={operatorConfig}
            operatorSelections={operatorSelections}
            onOperatorChange={toggleOperator}
            resourcesLoading={resourcesLoading}
            focusAttempt={focusAttempt}
            showAllErrors={stepError != null}
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
            contact={contact}
            reservingAs={reservingAs}
            participants={participants}
            equipment={equipment}
            items={items}
            report={availabilityReport}
            checking={availabilityStatus === 'CHECKING'}
            onUseAlternative={useAlternative}
            isAdmin={isAdmin}
            isCancellationRestricted={inCancellationWindow}
            pricing={availabilityReport?.pricing ?? null}
            onEditStep={(key) => goToStep(key)}
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
                          ? `External Organization · ${external.contact_person}`
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

      {isAdmin && (stepKey === 'details' || stepKey === 'review') && (
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
            <Button variant="outline" onClick={goBack} disabled={createReservation.isPending}>
              <ArrowLeft className="size-4" /> Back
            </Button>
            {step < steps.length - 1 ? (
              <div className="flex flex-col items-end gap-1">
                <Button
                  onClick={goNext}
                  disabled={!canContinue}
                  title={continueBlockedReason}
                  aria-describedby="continue-reason"
                >
                  Continue <ArrowRight className="size-4" />
                </Button>
                {continueBlockedReason && (
                  <p id="continue-reason" className="max-w-xs text-right text-xs text-muted">
                    {continueBlockedReason}
                  </p>
                )}
              </div>
            ) : (
              <Button
                onClick={submit}
                loading={createReservation.isPending}
                disabled={!canSubmit || createReservation.isPending}
                title={
                  !canCreateReservations
                    ? user?.reservation_block_reason
                    : !availabilityOk
                      ? AVAILABILITY_STATUS_MESSAGE[availabilityStatus]
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
          </div>
        </Card>
      )}
    </section>
  )
}
