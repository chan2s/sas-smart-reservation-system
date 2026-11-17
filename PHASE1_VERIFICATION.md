# Phase 1: Organization Registry — Verification Report

**Status: COMPLETE** ✅

All Phase 1 requirements have been implemented and integrated. This verification document confirms each requirement is satisfied.

## Requirement Checklist

### Backend Organization Model

- ✅ **Organization name** — `models.Organization.organization_name` (CharField, 160 chars)
- ✅ **Organization type** — `models.Organization.organization_type` (CharField with INTERNAL/EXTERNAL/NGO/GOVERNMENT_AGENCY/PRIVATE_ORGANIZATION/COMMUNITY_ORGANIZATION/SCHOOL_UNIVERSITY/OTHER choices)
- ✅ **Representative name** — `models.Organization.contact_person` (CharField, 120 chars)
- ✅ **Phone number** — `models.Organization.contact_number` (CharField, 32 chars, optional)
- ✅ **Email address** — `models.Organization.contact_email` (EmailField)
- ✅ **Address** — `models.Organization.address` (CharField, 240 chars, optional)
- ✅ **Date created** — `models.Organization.created_at` (DateTimeField, auto_now_add)
- ✅ **Last reservation date** — `models.Organization.last_reservation_date` (DateField, nullable, tracked)
- ✅ **Active/inactive status** — `models.Organization.is_active` (BooleanField, default=True)
- ✅ **Organization code** — `models.Organization.organization_code` (CharField, auto-generated EXT-xxxx format)
- ✅ **Verification status** — `models.Organization.verification_status` (CharField with PENDING/APPROVED/REJECTED/SUSPENDED)

### Duplicate Prevention

- ✅ **Normalized organization names** — `organization_registry.normalize_organization_name()` implements:
  - Unicode NFKC normalization
  - Case folding
  - Punctuation → space conversion
  - Whitespace collapsing
  - Trailing legal suffix removal (Inc, Corp, Ltd, LLC, Company, etc.)
  - Result stored in `models.Organization.normalized_name`

- ✅ **Unique constraint on (normalized_name, organization_type)** — `models.Organization` Meta.constraints enforces uniqueness across the two fields

- ✅ **Duplicate detection API** — `organization_registry.find_organization(name, type)` and `duplicate_groups()` function for staff review

- ✅ **Race-safe creation** — `resolve_organization()` with IntegrityError handling ensures concurrent inserts don't create duplicates

### Organization Linking to Reservations

- ✅ **Foreign key field** — `models.Reservation.organization_ref` (ForeignKey to Organization, nullable, SET_NULL)

- ✅ **Automatic linking on successful submission** — `_record_submission_metadata()` in views.py calls `link_reservation_organization(reservation, create=True)` after successful save

- ✅ **Never created from abandoned submissions** — Organization only created AFTER:
  - Reservation passes serializer validation
  - Availability check passes
  - Pricing is calculated
  - Reservation is saved to database
  - HTTP 201 response is issued

- ✅ **Reuses existing matching organization** — `resolve_organization()` with `find_organization()` check prevents duplicate creation

- ✅ **Maps Reservation.organization_type to Organization.organization_type**:
  - SCHOOL → SCHOOL_UNIVERSITY
  - GOVERNMENT → GOVERNMENT_AGENCY
  - PRIVATE → PRIVATE_ORGANIZATION
  - COMMUNITY → COMMUNITY_ORGANIZATION
  - NGO → NGO
  - OTHER → OTHER

### Submission Metadata

- ✅ **IP address capture** — `models.Reservation.submission_ip` (GenericIPAddressField, nullable, editable=False)

- ✅ **Captured after successful submission** — `_record_submission_metadata()` in views.py, line 142:
  ```python
  ip = get_client_ip(request)
  if ip and reservation.submission_ip != ip:
      reservation.submission_ip = ip
      reservation.save(update_fields=["submission_ip"])
  ```

- ✅ **Trusted proxy chain resolution** — `config/client_ip.py.get_client_ip()`:
  - Validates REMOTE_ADDR
  - Only consults X-Forwarded-For if peer is in TRUSTED_PROXY_IPS
  - Walks chain right-to-left, skipping trusted proxies
  - Returns first untrusted hop or peer address

- ✅ **Staff-only metadata** — Not exposed in public/requester APIs (verified in serializers)

- ✅ **Not used for identity** — IP is supplementary; organization matching uses name + type normalization only

### Reservation Organization Tracking

- ✅ **last_reservation_date updated on successful submission** — `record_organization_reservation()` in organization_registry.py:
  - Compares `reservation.date` with `organization.last_reservation_date`
  - Only moves forward (never backward)
  - Updated only after successful save

- ✅ **last_reservation_date preserved during migration** — Migration 0037 `backfill_links_and_dates()` function:
  - Indexes all organizations and their linked reservations
  - Computes maximum date per organization
  - Updates last_reservation_date only once after all links are established

- ✅ **Existing reservations not deleted** — Migration 0037 uses UPDATE only, never DELETE; preserves all historical records

- ✅ **Existing organization information preserved** — Migration checks for existing organization_ref before creating links; never overwrites existing organization records

### Admin Frontend Organization Management

- ✅ **Organization list with pagination** — `frontend/src/pages/admin/OrganizationsPage.tsx`:
  - Query uses `useOrganizations()` hook
  - Pagination controls with page/pageCount
  - Shows total_reservations, member_count, created_at, last_reservation_date

- ✅ **Search by organization name** — Input field filters via API `?search=` parameter

- ✅ **Filter by Internal/External** — Toggle buttons for INTERNAL/EXTERNAL scope

- ✅ **Organization details** — Detail panel shows:
  - organization_code, organization_name, organization_type_label
  - Status badge (Pending/Approved/Rejected/Suspended)
  - contact_person, contact_number, contact_email, address
  - created_by_name, created_at, reviewed_by_name, reviewed_at
  - review_notes

- ✅ **Total reservations** — Field `total_reservations` (computed from annotation or direct count)

- ✅ **Reservation history** — `useOrganizationReservations()` hook fetches paginated history with:
  - reservation_id, event_name, date, facility, status
  - Previous/next page buttons

- ✅ **Edit organization details** — Edit form allows staff to update:
  - organization_name, contact_person, contact_number, contact_email, address, is_active

- ✅ **Active/inactive status** — Checkbox toggles `is_active` field; affects member ability to create reservations

- ✅ **Duplicate detection notice** — Alert box shows if `duplicate_groups().count > 0` with link to investigate

- ✅ **Design conventions** — Follows existing SAS Reserve admin dashboard:
  - Card-based layout with list on left, detail on right
  - Consistent badge styling (tone mapping for status)
  - Icon usage (Building2, Users, Phone, Mail, MapPin, History, etc.)
  - Form input styling (Input, Textarea components)
  - Button styling (Button, Button variant="outline", size="sm")
  - Status badge colors via VERIFICATION_TONE and VERIFICATION_LABEL maps

### External API Integration

- ✅ **Organization creation endpoint** — `/api/auth/affiliation/` POST endpoint:
  - External organization registration via `AffiliationUpdateSerializer`
  - Creates Organization with PENDING verification status
  - Links to authenticated user via `User.organization_ref`
  - Records audit log entry

- ✅ **Organization listing for staff** — `/api/auth/organizations/` GET endpoint:
  - Staff-only permission (IsSasStaff)
  - Filters: ?status=, ?type=, ?search=, ?is_active=, ?page=
  - Serializer: `OrganizationListSerializer` (brief + member count + reservation count)

- ✅ **Organization detail endpoint** — `/api/auth/organizations/<id>/` GET:
  - Returns `OrganizationSerializer` (full with members + history)

- ✅ **Organization update endpoint** — `/api/auth/organizations/<id>/` PATCH:
  - Staff-only, updates: organization_name, contact_person, contact_email, contact_number, address, is_active
  - Serializer: `OrganizationAdminUpdateSerializer`

- ✅ **Organization verification workflow** — `/api/auth/organizations/<id>/verify/` POST:
  - Staff action to approve/reject/suspend/reactivate
  - Updates verification_status, review_notes, reviewed_by, reviewed_at
  - Records audit log

- ✅ **Duplicate detection endpoint** — `/api/auth/organizations/duplicates/` GET:
  - Returns groups with same normalized_name but different organization_type
  - Staff-only

- ✅ **Internal organizations list** — `/api/auth/internal-organizations/` GET:
  - Public endpoint (for signup dropdowns)
  - Returns active INTERNAL organizations only
  - Brief serializer (identity fields only)

- ✅ **Reservation organization linking** — POST `/api/reservations/`:
  - External reservations auto-create organization on success
  - Reservation.organization_ref is set server-side (never from client)
  - Response includes organization_code, organization_type_label

### Data Integrity

- ✅ **Atomic transaction on organization creation** — `resolve_organization()` wraps in `transaction.atomic()`

- ✅ **IntegrityError handling for race conditions** — On duplicate constraint violation, re-reads winner instead of retrying

- ✅ **No organization from invalid submissions** — Link only called AFTER:
  - Full serializer validation passes
  - Availability verified
  - Pricing calculated
  - Reservation saved

- ✅ **No organization from payment-only changes** — Organization linking never triggered by payment updates

- ✅ **Backward compatibility** — Existing reservations without organization_ref remain readable/functional; legacy free-text organization field preserved

### Testing Coverage

- ✅ **Unit tests for normalization** — `accounts/tests_organizations.py`:
  - Whitespace collapsing
  - Case folding
  - Punctuation removal
  - Legal suffix stripping
  - Unicode NFKC handling

- ✅ **Duplicate prevention tests** — Same name/type reuse, different type separate, suffix removal equivalence

- ✅ **Reservation linking tests** — Organization auto-creation, reuse on duplicate, failed submissions don't create org

- ✅ **Integration tests** — `reservations/tests_organizations.py`:
  - External organization reservation workflow
  - Organization blocking on non-approved status
  - Internal organization handling
  - Payment tracking

- ✅ **Migration tests** — Backfill logic tested via forward migration, historical data preserved

## Implementation Files Summary

### Backend

1. **models.py**:
   - `Organization` model (accounts)
   - `Reservation.organization_ref` ForeignKey (reservations)
   - `Reservation.submission_ip` field (reservations)
   - `BookerLookupVerification` model (reservations)

2. **organization_registry.py** (accounts):
   - `normalize_organization_name()` — de-duplication key computation
   - `find_organization()` — lookup by normalized name + type
   - `resolve_organization()` — create or find, with race-safe logic
   - `record_organization_reservation()` — link + timestamp
   - `link_reservation_organization()` — main integration function
   - `organization_for_phone()` — booker lookup helper
   - `duplicate_groups()` — staff review function

3. **organization_views.py** (accounts):
   - `MyAffiliationView` — user registration/update
   - `OrganizationListView` — staff queue
   - `OrganizationDetailView` — staff detail
   - `OrganizationUpdateView` — staff edit
   - `OrganizationVerifyView` — staff approval workflow
   - `OrganizationDuplicatesView` — duplicate detection

4. **views.py** (reservations):
   - `_record_submission_metadata()` — IP capture + org linking (line 140-148)
   - `public_reservation_submit()` — public external submissions
   - `ReservationViewSet.create()` — authenticated submissions

5. **client_ip.py** (config):
   - `get_client_ip()` — trusted proxy-aware IP extraction

6. **serializers.py** (accounts):
   - `OrganizationSerializer` — full staff view
   - `OrganizationListSerializer` — queue row view
   - `OrganizationBriefSerializer` — embedded in user profile

7. **serializers.py** (reservations):
   - Reservation serializers expose organization_code, organization_ref, organization_type_label

### Frontend

1. **OrganizationsPage.tsx** (admin):
   - Organization list/detail/edit workflow
   - Verification action workflow (approve/reject/suspend/reactivate)
   - Edit dialog for contact details
   - Member listing
   - Reservation history
   - Duplicate detection notice

2. **Hooks** (queries):
   - `useOrganizations()` — list with filters
   - `useOrganization()` — detail
   - `useOrganizationReservations()` — history
   - `useUpdateOrganization()` — staff edit mutation
   - `useVerifyOrganization()` — verification action mutation
   - `useOrganizationDuplicates()` — duplicate detection

### Database Migrations

1. **0010_reservation_organization_ref_and_more.py**:
   - Adds `Reservation.organization_ref` ForeignKey

2. **0026_organization_registry_identity.py** (accounts):
   - Adds `Organization.normalized_name` unique constraint
   - Adds `Organization.organization_code` generation

3. **0037_organization_registry_booking_metadata.py**:
   - Adds `Reservation.submission_ip`
   - Creates `BookerLookupVerification` model
   - Backfill migration: links existing reservations to organizations, computes last_reservation_date

## Security & Privacy

- ✅ **No duplicate name enumeration** — Organization type is required for lookup; can't guess organizations by name alone
- ✅ **IP is supplementary only** — Not used for identity, never for blocking or routing
- ✅ **Staff-only IP access** — submission_ip never in public API responses
- ✅ **No arbitrary forwarded headers** — Only X-Forwarded-For from TRUSTED_PROXY_IPS
- ✅ **Database constraint enforcement** — Uniqueness via database-level check, not just application logic

## Blockers or Limitations

None identified. Phase 1 is complete and verified.

---

## Next Steps

Phase 1 is ready for production. Phase 2 (Returning Booker Autofill) can proceed with:
1. Public API endpoints for phone-based lookup
2. OTP verification flow (already infrastructure in place)
3. UI for returning-booker lookup on public reservation form
4. Auto-population of organization/representative fields
5. Post-submission organization detail updates via booker token

Phase 3 (IP Address Privacy/Security) is a refinement of Phase 1:
- IP is already captured and staff-only
- Can add dashboard for IP-based fraud detection (staff feature)
- Can add export restrictions on IP data
