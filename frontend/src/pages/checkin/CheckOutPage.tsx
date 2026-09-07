import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ClipboardCheck,
  ImagePlus,
  PackageCheck,
  TriangleAlert,
  X,
} from 'lucide-react'
import { useReservation, useReservationAction } from '@/hooks/queries'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, Select, Textarea } from '@/components/ui/Form'
import { Modal } from '@/components/ui/Modal'
import { Skeleton, EmptyState } from '@/components/ui/Misc'
import { cn } from '@/lib/utils'
import { useReportEquipmentIssue } from '@/hooks/queries'

const CONDITIONS = [
  { value: 'EXCELLENT', label: 'Excellent' },
  { value: 'GOOD', label: 'Good' },
  { value: 'FAIR', label: 'Fair' },
  { value: 'POOR', label: 'Poor' },
  { value: 'DAMAGED', label: 'Damaged' },
]

const ISSUE_TYPES = [
  { value: 'DAMAGE', label: 'Damage' },
  { value: 'MISSING', label: 'Missing item' },
  { value: 'MALFUNCTION', label: 'Malfunction' },
  { value: 'MAINTENANCE', label: 'Maintenance required' },
]

export function CheckOutPage() {
  const { id } = useParams()
  const reservationId = Number(id)
  const navigate = useNavigate()
  const { toast } = useToast()
  const { data: reservation, isLoading } = useReservation(reservationId)
  const action = useReservationAction(reservationId)

  const [facilityCondition, setFacilityCondition] = useState('GOOD')
  const [equipmentReturned, setEquipmentReturned] = useState(true)
  const [missingItems, setMissingItems] = useState('')
  const [notes, setNotes] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)

  const [damageModal, setDamageModal] = useState(false)
  const [damageEquipment, setDamageEquipment] = useState<number | null>(null)
  const [damageType, setDamageType] = useState('DAMAGE')
  const [damageDescription, setDamageDescription] = useState('')
  const [damagePhoto, setDamagePhoto] = useState<File | null>(null)
  const reportIssue = useReportEquipmentIssue(damageEquipment ?? 0)

  if (isLoading || !reservation) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-96" />
      </div>
    )
  }

  const currentReservation = reservation

  async function submitCheckout() {
    const payload = {
      facility_condition: facilityCondition,
      equipment_returned: equipmentReturned,
      missing_items: missingItems,
      notes,
    }
    try {
      if (photo) {
        const form = new FormData()
        for (const [key, value] of Object.entries(payload)) {
          form.append(key, String(value))
        }
        form.append('photo', photo)
        await endpointsReservationActionForm(currentReservation.id, 'check_out', form)
      } else {
        await action.mutateAsync({ action: 'check_out', body: payload })
      }
      toast('Reservation checked out successfully.')
      navigate(`/reservations/${currentReservation.id}`)
    } catch {
      toast('Check-out failed — please review the form.', 'error')
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Link
        to={`/reservations/${reservation.id}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> Back to reservation
      </Link>

      <div className="mt-4">
        <h1 className="text-[32px] font-semibold tracking-tight text-ink">Check out &amp; inspection</h1>
        <p className="mt-1.5 text-[15px] text-body">
          Confirm equipment was returned, record the facility condition, and report any issues.
        </p>
      </div>

      <div className="mt-8 space-y-6">
        {/* Equipment checklist */}
        <Card>
          <CardHeader
            title="Equipment checklist"
            description="Confirm each requested item was returned in the same condition."
          />
          {reservation.items.length === 0 ? (
            <EmptyState title="No equipment was requested" />
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {reservation.items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink">{item.equipment_name}</p>
                    <p className="text-xs text-muted">{item.category} · {item.quantity}×</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setDamageEquipment(item.equipment_id)}
                      className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-body transition-colors hover:border-status-maintenance/40 hover:text-status-maintenance"
                    >
                      <TriangleAlert className="size-3.5" />
                      Report issue
                    </button>
                    <span
                      className={cn(
                        'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold',
                        equipmentReturned
                          ? 'bg-status-available-bg text-status-available'
                          : 'bg-status-pending-bg text-status-pending',
                      )}
                    >
                      <PackageCheck className="size-3.5" />
                      {equipmentReturned ? 'Returned' : 'Pending'}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <label className="mt-5 flex cursor-pointer items-center gap-3 rounded-xl border border-line p-4 transition-colors hover:border-line-strong">
            <input
              type="checkbox"
              checked={equipmentReturned}
              onChange={(event) => setEquipmentReturned(event.target.checked)}
              className="size-4 accent-brand"
            />
            <div>
              <p className="text-sm font-medium text-ink">All equipment was returned</p>
              <p className="text-xs text-muted">
                If something is missing, uncheck this and list the items below.
              </p>
            </div>
          </label>

          {!equipmentReturned && (
            <div className="mt-4">
              <Field label="Missing items" htmlFor="missing-items">
                <Textarea
                  id="missing-items"
                  value={missingItems}
                  onChange={(event) => setMissingItems(event.target.value)}
                  placeholder="List the items that were not returned…"
                />
              </Field>
            </div>
          )}
        </Card>

        {/* Facility condition */}
        <Card>
          <CardHeader
            title="Facility condition"
            description="Record the state of the facility after the event."
          />
          <div className="mt-4 grid gap-5 sm:grid-cols-2">
            <Field label="Condition" htmlFor="facility-condition">
              <Select
                id="facility-condition"
                value={facilityCondition}
                onChange={(event) => setFacilityCondition(event.target.value)}
              >
                {CONDITIONS.map((condition) => (
                  <option key={condition.value} value={condition.value}>
                    {condition.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Notes" htmlFor="checkout-notes">
              <Textarea
                id="checkout-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Any observations for SAS staff…"
                className="min-h-[40px]"
              />
            </Field>
          </div>

          <div className="mt-5">
            <p className="mb-1.5 text-[13px] font-medium text-ink">Photo documentation</p>
            <PhotoUpload value={photo} onChange={setPhoto} />
          </div>
        </Card>

        <div className="flex items-center justify-end gap-3">
          <Button variant="ghost" onClick={() => navigate(`/reservations/${reservation.id}`)}>
            Cancel
          </Button>
          <Button
            onClick={() => void submitCheckout()}
            loading={action.isPending}
            icon={<ClipboardCheck className="size-4" />}
          >
            Complete check-out
          </Button>
        </div>
      </div>

      {/* Damage report modal */}
      <Modal
        open={damageModal || damageEquipment !== null}
        onClose={() => {
          setDamageModal(false)
          setDamageEquipment(null)
          setDamageDescription('')
          setDamagePhoto(null)
        }}
        title="Report equipment issue"
        description="Create a maintenance record so the item can be inspected."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDamageModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (damageEquipment == null) return
                const form = new FormData()
                form.append('equipment', String(damageEquipment))
                form.append('issue_type', damageType)
                form.append('description', damageDescription)
                form.append('quantity', '1')
                if (damagePhoto) form.append('photo', damagePhoto)
                reportIssue.mutate(form, {
                  onSuccess: () => {
                    toast('Issue reported to the maintenance queue.')
                    setDamageModal(false)
                    setDamageEquipment(null)
                    setDamageDescription('')
                    setDamagePhoto(null)
                  },
                  onError: () => toast('Unable to report the issue.', 'error'),
                })
              }}
              loading={reportIssue.isPending}
            >
              Report issue
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Issue type" htmlFor="issue-type">
            <Select id="issue-type" value={damageType} onChange={(event) => setDamageType(event.target.value)}>
              {ISSUE_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Description" htmlFor="issue-description">
            <Textarea
              id="issue-description"
              value={damageDescription}
              onChange={(event) => setDamageDescription(event.target.value)}
              placeholder="Describe what happened and where…"
            />
          </Field>
          <div>
            <p className="mb-1.5 text-[13px] font-medium text-ink">Damage photo</p>
            <PhotoUpload value={damagePhoto} onChange={setDamagePhoto} />
          </div>
        </div>
      </Modal>
    </div>
  )
}

// Kept tiny and local to avoid an import cycle with the api client.
async function endpointsReservationActionForm(id: number, action: string, form: FormData) {
  const token = localStorage.getItem('sas_access')
  const response = await fetch(`/api/reservations/${id}/${action}/`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!response.ok) throw new Error('Request failed')
  return response.json()
}

function PhotoUpload({ value, onChange }: { value: File | null; onChange: (file: File | null) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const previewUrl = value ? URL.createObjectURL(value) : null

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
      {value && previewUrl ? (
        <div className="relative inline-block">
          <img src={previewUrl} alt="Upload preview" className="h-36 rounded-xl border border-line object-cover" />
          <button
            type="button"
            onClick={() => onChange(null)}
            className="absolute -right-2 -top-2 flex size-6 items-center justify-center rounded-full bg-ink text-white shadow-card transition-transform hover:scale-105"
            aria-label="Remove photo"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex h-32 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line-strong text-muted transition-colors hover:border-brand hover:bg-brand-soft/40 hover:text-brand"
        >
          <ImagePlus className="size-6" aria-hidden />
          <span className="text-[13px] font-medium">Upload a photo</span>
        </button>
      )}
    </div>
  )
}