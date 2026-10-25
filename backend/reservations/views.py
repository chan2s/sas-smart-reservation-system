import datetime

from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import (
    IsAccountApprovedOrReadOnly,
    IsApprovalModuleScopeAllowed,
    IsSasStaff,
)
from facilities.models import Facility
from notifications.models import Notification
from notifications.services import notify, notify_staff
from .models import Reservation, ReservationEvent
from .serializers import (
    ReservationCreateSerializer,
    ReservationDetailSerializer,
    ReservationListSerializer,
    ReservationResubmitSerializer,
)
from .services import confirmations, expiration, workflow
from .services.availability import check_availability, find_alternatives
from .services.pricing import quote_fees, quote_to_dict, rates_payload
from .services.recommendations import recommend_resources_with_pricing


def _record_rebook_lineage(request, reservation):
    """Record a rebook / new-schedule link on the ORIGINAL expired reservation.

    The original is never otherwise mutated: this only appends a timeline event
    naming the new reservation, so history stays accurate and traceable. Staff
    rebooks read as "Rebooked"; a requester's own request as "New Schedule
    Requested".
    """
    original = reservation.rebooked_from
    if original is None:
        return
    event_type = (
        ReservationEvent.EventType.REBOOKED
        if request.user.is_sas_staff
        else ReservationEvent.EventType.NEW_SCHEDULE_REQUESTED
    )
    workflow.record_event(
        original,
        event_type,
        actor=request.user,
        from_status=Reservation.Status.EXPIRED,
        to_status=Reservation.Status.EXPIRED,
        message=(
            f"Created new reservation {reservation.reservation_id} from "
            f"expired reservation {original.reservation_id}."
        ),
    )


def _trusted_requester_type(request, requested) -> str:
    """Decide the pricing context from trusted data, never a client flag.

    External-organization pricing applies to SAS staff (who create external
    reservations on an organization's behalf) and to members of an approved
    external organization booking for their own organization. Everyone else
    is treated as an internal campus requester, whose reservations are free.
    A forged ``requester_type=EXTERNAL`` from an ordinary requester therefore
    cannot switch on external fees.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return Reservation.RequesterType.CAMPUS
    if requested == Reservation.RequesterType.EXTERNAL and user.is_sas_staff:
        return Reservation.RequesterType.EXTERNAL
    # Everyone else is decided by the authenticated profile: only a member of
    # an external, approved, active organization is priced as external.
    # Internal managed organizations (CAS, CTED, …) always read as CAMPUS, so
    # they never receive external facility/resource fees.
    if user.trusted_requester_type == Reservation.RequesterType.EXTERNAL:
        return Reservation.RequesterType.EXTERNAL
    return Reservation.RequesterType.CAMPUS


class ReservationViewSet(viewsets.ModelViewSet):
    """Administrative reservation management + requester self-service.

    A not-approved account may list and read reservations it is authorized to
    see, but every write — create, resubmit, cancel, check-in/out, approval —
    is a state change refused by ``IsAccountApprovedOrReadOnly`` (and, for the
    staff-only actions, by ``IsSasStaff`` on top).
    """
    permission_classes = [IsAuthenticated, IsAccountApprovedOrReadOnly]

    search_fields = (
        "event_name",
        "organization",
        "contact_person",
        "contact_email",
        "requester__first_name",
        "requester__last_name",
        "reservation_id",
    )
    ordering_fields = ("date", "created_at", "start_time", "status")

    def get_queryset(self):
        # Synchronise expiration before anything is read, so a stale PENDING
        # never reaches the list, the detail view, or an action endpoint (the
        # approval and check-in paths re-check their own object as well).
        expiration.expire_overdue_reservations()
        qs = Reservation.objects.select_related(
            "facility",
            "requester",
            "created_by",
            "approved_by",
            "no_show_marked_by",
            "organization_ref",
        ).prefetch_related("items__equipment__category", "events")
        user = self.request.user

        if not user.is_sas_staff:
            qs = qs.filter(requester=user)

        params = self.request.query_params
        status_filter = params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        # Requester-type filter: campus vs external usage at a glance.
        requester_type = params.get("requester_type")
        if requester_type:
            qs = qs.filter(requester_type=requester_type)
        # Organization filter: a managed internal organization's acronym/code
        # (CAS, CTED, …), or "EXTERNAL" for any external requester.
        organization = (params.get("organization") or "").strip()
        if organization and organization.lower() not in ("undefined", "null", "all"):
            if organization.upper() == Reservation.RequesterType.EXTERNAL:
                qs = qs.filter(requester_type=Reservation.RequesterType.EXTERNAL)
            else:
                from django.db.models import Q

                qs = qs.filter(
                    Q(organization_ref__acronym__iexact=organization)
                    | Q(organization_ref__organization_code__iexact=organization)
                )
        if params.get("date"):
            qs = qs.filter(date=params["date"])
        if params.get("from"):
            qs = qs.filter(date__gte=params["from"])
        if params.get("to"):
            qs = qs.filter(date__lte=params["to"])
        facility = params.get("facility")
        if facility and facility not in ("undefined", "null", "all", ""):
            try:
                qs = qs.filter(facility_id=int(facility))
            except (TypeError, ValueError):
                pass
        if params.get("requester"):
            qs = qs.filter(requester_id=params["requester"])
        equipment = params.get("equipment")
        if equipment and equipment not in ("undefined", "null", "all", ""):
            try:
                qs = qs.filter(items__equipment_id=int(equipment))
            except (TypeError, ValueError):
                pass
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ReservationCreateSerializer
        if self.action == "retrieve":
            return ReservationDetailSerializer
        return ReservationListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            if exc.get_codes().get("availability"):
                # Surface the structured availability report for conflict UI.
                report = getattr(serializer, "_availability_report", {})
                return Response(
                    {
                        "detail": "Resource conflict detected",
                        "availability": report,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            raise
        reservation = serializer.save()
        is_rebook = reservation.rebooked_from_id is not None
        workflow.record_event(
            reservation,
            ReservationEvent.EventType.CREATED,
            actor=request.user,
            message=(
                "Reservation created by SAS administrator."
                if request.user.is_sas_staff
                else "Reservation submitted for approval."
            ),
        )

        if is_rebook:
            _record_rebook_lineage(request, reservation)

        # The backend is the source of truth for status: reservations created
        # by an administrator are approved immediately (campus or external
        # requester alike); everyone else enters the normal pending review
        # queue. A status value sent by the client is never trusted (the
        # serializer does not even accept one).
        #
        # Exception: a rebook / request-new-schedule is deliberately NOT
        # auto-approved even for an administrator — recreating an expired
        # reservation must go through the normal review (Requirement: the new
        # reservation always starts PENDING).
        if request.user.is_admin and not is_rebook:
            workflow.auto_approve(reservation, request.user)
        else:
            notify_staff(
                Notification.Type.RESERVATION,
                "New reservation request",
                f"{reservation.event_name} on {reservation.date} ({reservation.start_time:%H:%M}–{reservation.end_time:%H:%M}) is awaiting approval.",
                f"/reservations/{reservation.id}",
            )
        # Booking confirmation email. Scheduled AFTER the creation has been
        # saved and the final status has been decided above, so the message
        # always describes the status that was actually persisted (pending or
        # auto-approved). It is dispatched by the backend via
        # transaction.on_commit, never by the React frontend, and delivery is
        # idempotent + best-effort: a failed send is logged and can never undo
        # or alter this reservation.
        confirmations.schedule_booking_confirmation(reservation)

        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], permission_classes=[IsSasStaff, IsAccountApprovedOrReadOnly])
    def users(self, request):
        """Campus-user directory for admin "reserve on behalf of" search.

        Staff-only. Supports ?search= over name/username/email and ?id= for a
        single fetch. Returns a compact profile list.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        qs = User.objects.all().order_by("first_name", "last_name", "username")

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(username__icontains=search)
                | Q(email__icontains=search)
            )
        user_id = request.query_params.get("id")
        if user_id:
            qs = qs.filter(pk=user_id)

        qs = qs[:20]
        results = [
            {
                "id": u.id,
                "display_name": u.display_name,
                "username": u.username,
                "email": u.email,
                "organization": u.organization,
                "role": u.role,
            }
            for u in qs
        ]
        return Response({"results": results})

    @action(detail=False, methods=["get"])
    def counts(self, request):
        """Per-status reservation counts for tab badges."""
        expiration.expire_overdue_reservations()
        qs = Reservation.objects.all()
        if not request.user.is_sas_staff:
            qs = qs.filter(requester=request.user)
        statuses = dict(Reservation.Status.choices)
        result = {"ALL": qs.count()}
        for key, _ in statuses.items():
            result[key] = qs.filter(status=key).count()
        return Response(result)

    def update(self, request, *args, **kwargs):
        """Reservations are never edited through the generic write endpoint.

        PUT/PATCH here would run through the list serializer, which was never
        designed for writes — it would even accept a client-supplied status,
        letting the owner approve their own reservation. The only edit path
        is the validated ``resubmit`` action: owner/staff only, PENDING only,
        with the full availability revalidation.
        """
        return Response(
            {
                "detail": (
                    "Reservations cannot be edited with this endpoint. "
                    "Use POST /api/reservations/{id}/resubmit/ instead."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        reservation = self.get_object()
        if reservation.status == Reservation.Status.EXPIRED:
            return Response(
                {
                    "detail": (
                        "This reservation has expired and must be kept for "
                        "history. It cannot be deleted."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff, IsAccountApprovedOrReadOnly])
    def approve(self, request, pk=None):
        reservation = self.get_object()
        try:
            workflow.approve_reservation(
                reservation, request.user, request.data.get("comment", "")
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff, IsAccountApprovedOrReadOnly])
    def retry_approval_email(self, request, pk=None):
        """Re-send the approval notification email for an approved reservation.

        Staff-only diagnostic/retry helper. Only ever sends when the
        reservation is APPROVED and the approval email was not already
        delivered successfully. SMTP details are never returned.
        """
        reservation = self.get_object()
        already_sent = (
            reservation.approval_email_status
            == Reservation.ApprovalEmailStatus.SENT
        )
        try:
            status_code = workflow.resend_approval_email(reservation, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if status_code == Reservation.ApprovalEmailStatus.SENT:
            detail = (
                "Approval email already sent."
                if already_sent
                else "Approval email sent."
            )
        else:
            detail = "Approval email not sent."
        return Response(
            {
                "detail": detail,
                "approval_email_status": status_code,
                "approval_email_status_label": reservation.get_approval_email_status_display(),
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff, IsAccountApprovedOrReadOnly])
    def reject(self, request, pk=None):
        reservation = self.get_object()
        try:
            workflow.reject_reservation(
                reservation, request.user, request.data.get("reason", "")
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff, IsAccountApprovedOrReadOnly])
    def request_changes(self, request, pk=None):
        reservation = self.get_object()
        try:
            workflow.request_changes(
                reservation, request.user, request.data.get("message", "")
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["post"])
    def resubmit(self, request, pk=None):
        """Revise and resubmit a reservation that is awaiting review.

        Authorization: the reservation owner or SAS staff — enforced here, on
        top of the queryset (a non-staff user can never even resolve another
        requester's reservation). Status policy: only a PENDING reservation —
        the state an administrator's "request changes" leaves it in — can be
        resubmitted; approved, active, completed, cancelled, rejected, and
        expired reservations are refused. The payload is revalidated exactly
        like a fresh submission (HTTP 409 with the structured report on an
        availability conflict), and the resubmission itself never changes the
        status: it stays in the review queue with an UPDATED timeline entry.

        The status re-check, the write, and the timeline entry run in one
        transaction under a row lock, so an administrator approving (or
        rejecting) the reservation at the same instant cannot race the
        requester's revision: exactly one of the two wins.
        """
        with transaction.atomic():
            reservation = Reservation.objects.select_for_update().get(
                pk=self.get_object().pk
            )
            is_owner = reservation.requester_id == request.user.id
            if not (is_owner or request.user.is_sas_staff):
                return Response(
                    {"detail": "You do not have permission to edit this reservation."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if reservation.status != Reservation.Status.PENDING:
                return Response(
                    {
                        "detail": (
                            "Only a reservation that is awaiting review can be "
                            "edited and resubmitted."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer = ReservationResubmitSerializer(
                reservation, data=request.data, context={"request": request}
            )
            try:
                serializer.is_valid(raise_exception=True)
            except ValidationError as exc:
                if exc.get_codes().get("availability"):
                    # Surface the structured availability report for conflict UI.
                    report = getattr(serializer, "_availability_report", {})
                    return Response(
                        {
                            "detail": "Resource conflict detected",
                            "availability": report,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                raise
            reservation = serializer.save()
            try:
                workflow.resubmit_reservation(reservation, request.user)
            except ValueError as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
                )
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        is_owner = reservation.requester_id == request.user.id
        if not (is_owner or request.user.is_sas_staff):
            return Response(
                {"detail": "You do not have permission to cancel this reservation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            workflow.cancel_reservation(
                reservation, request.user, request.data.get("reason", "")
            )
        except workflow.CancellationWindowError as exc:
            return Response(
                {"detail": str(exc), "code": "cancellation_window"},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsAccountApprovedOrReadOnly],
    )
    def check_in(self, request, pk=None):
        """Check a reservation in.

        Authorization: the reservation owner or SAS staff.

        Time policy: check-in opens 3 hours before the event start. Anyone
        may check in once the window is open. Before it opens, only an
        administrator who explicitly confirms the override (``override: true``
        in the request body) may check in — the backend verifies the role, so
        a regular user cannot bypass the window by sending the flag. The
        override is recorded on the reservation. Check-in is refused once the
        reservation's calendar date has passed (from the next day onward the
        reservation enters its no-show window), and for cancelled, no-show,
        rejected, completed, or expired reservations.
        """
        reservation = self.get_object()
        is_owner = reservation.requester_id == request.user.id
        if not (is_owner or request.user.is_sas_staff):
            return Response(
                {"detail": "You do not have permission to check in this reservation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        override = bool(request.data.get("override"))
        try:
            workflow.check_in_reservation(reservation, request.user, override=override)
        except workflow.CheckInNotOpenError as exc:
            return Response(
                {
                    "detail": "Check-in is not available yet. It opens 3 hours before the event start.",
                    "code": "check_in_not_open",
                    "check_in_open_time": exc.check_in_open_time.isoformat(),
                    "requires_override": request.user.is_admin,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="mark-no-show",
        permission_classes=[IsSasStaff, IsAccountApprovedOrReadOnly],
    )
    def mark_no_show(self, request, pk=None):
        """Explicitly mark a past-date, approved reservation as a no-show.

        Staff-only on top of the account-approval policy. The eligibility
        rules (APPROVED status, never checked in, reservation calendar date at
        least one day in the past in the project's timezone) are enforced by
        ``services.workflow.no_show_eligibility`` — the same helper that drives
        the frontend's ``can_mark_no_show`` flag. The status write, timeline
        entry, and audit record run under a row lock, so a concurrent check-in
        cannot also succeed. The action is never automatic: an administrator
        must confirm it.
        """
        reservation = self.get_object()
        try:
            workflow.mark_no_show(reservation, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        data = ReservationDetailSerializer(
            reservation, context={"request": request}
        ).data
        # The updated reservation is the response body (matching the other
        # action endpoints); ``message`` is an additive convenience field.
        data["message"] = "Reservation successfully marked as no-show."
        return Response(data)

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff, IsAccountApprovedOrReadOnly])
    def check_out(self, request, pk=None):
        reservation = self.get_object()
        try:
            workflow.check_out_reservation(reservation, request.user, request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )


@api_view(["GET"])
@permission_classes([IsSasStaff])
def reservation_by_checkin_code(request, code):
    """Staff scanning interface: resolve a reservation from its QR code."""
    expiration.expire_overdue_reservations()
    reservation = (
        Reservation.objects.select_related("facility", "requester")
        .prefetch_related("items__equipment__category", "events")
        .filter(checkin_code=code)
        .first()
    )
    if not reservation:
        return Response(
            {"detail": "No reservation found for this code."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(
        ReservationDetailSerializer(reservation, context={"request": request}).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovalModuleScopeAllowed])
def availability_check(request):
    """Conflict analysis + alternative schedules for a proposed window."""
    data = request.data
    # Optional: a reservation to exclude from the conflict analysis. Used when
    # the OWNER edits a reservation that is awaiting review — its own current
    # slot moves with the reservation, so it must not count against itself.
    # Honoured only for the owner or staff, and never trusted at submit time:
    # the resubmit endpoint re-checks availability excluding only itself.
    exclude_id = data.get("exclude_id")
    if exclude_id:
        try:
            exclude_id = int(exclude_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid exclude_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = Reservation.objects.filter(pk=exclude_id).first()
        if target is None:
            return Response(
                {"detail": "The reservation to exclude was not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not (
            target.requester_id == request.user.id or request.user.is_sas_staff
        ):
            return Response(
                {
                    "detail": (
                        "You can only exclude your own reservation from the "
                        "availability check."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
    try:
        report = check_availability(
            data["facility_id"],
            datetime.date.fromisoformat(data["date"]),
            datetime.time.fromisoformat(data["start_time"]),
            datetime.time.fromisoformat(data["end_time"]),
            data.get("items", []),
            exclude_id=exclude_id or None,
        )
    except (KeyError, ValueError) as exc:
        return Response(
            {"detail": f"Invalid request: {exc}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Facility.DoesNotExist:
        return Response(
            {"detail": "Facility not found."}, status=status.HTTP_404_NOT_FOUND
        )

    requester_type = _trusted_requester_type(request, data.get("requester_type"))
    facility = Facility.objects.filter(pk=data["facility_id"]).first()

    def _quote(target_date, start, end):
        quote = quote_fees(
            requester_type,
            facility=facility,
            items=data.get("items", []),
            start_time=start,
            end_time=end,
        )
        return quote_to_dict(quote)

    # Current estimate for the requested window...
    report["pricing"] = _quote(
        datetime.date.fromisoformat(data["date"]),
        datetime.time.fromisoformat(data["start_time"]),
        datetime.time.fromisoformat(data["end_time"]),
    )

    alternatives = find_alternatives(
        data["facility_id"],
        datetime.date.fromisoformat(data["date"]),
        datetime.time.fromisoformat(data["start_time"]),
        datetime.time.fromisoformat(data["end_time"]),
        data.get("items", []),
        exclude_id=exclude_id or None,
    )
    # ...and a fresh estimate for every proposed alternative, so a rescheduled
    # slot never displays a stale total.
    for slot in alternatives:
        slot["pricing"] = _quote(
            datetime.date.fromisoformat(slot["date"]),
            datetime.time.fromisoformat(slot["start_time"]),
            datetime.time.fromisoformat(slot["end_time"]),
        )
    report["alternatives"] = alternatives
    return Response(report)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovalModuleScopeAllowed])
def resources_recommendation(request):
    """Smart resource recommendations for an event profile.

    Consumes the event details (type, purpose, participants, facility) plus
    the proposed schedule so every suggestion is capped by what is actually
    available during the window.
    """
    data = request.data
    event_type = data.get("event_type", Reservation.EventType.OTHER)
    try:
        participants = int(data.get("expected_participants", 0) or 0)
        target_date = (
            datetime.date.fromisoformat(data["date"]) if data.get("date") else None
        )
        start_time = (
            datetime.time.fromisoformat(data["start_time"]) if data.get("start_time") else None
        )
        end_time = (
            datetime.time.fromisoformat(data["end_time"]) if data.get("end_time") else None
        )
    except (TypeError, ValueError) as exc:
        return Response(
            {"detail": f"Invalid request: {exc}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Resources are chosen from the event profile first; the applicable
    # external-organization cost is calculated afterwards from the trusted
    # requester context, never from price.
    result = recommend_resources_with_pricing(
        event_type,
        participants,
        facility_id=data.get("facility_id"),
        purpose=data.get("purpose", ""),
        special_requirements=data.get("special_requirements", ""),
        target_date=target_date,
        start_time=start_time,
        end_time=end_time,
        requester_type=_trusted_requester_type(request, data.get("requester_type")),
    )
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovalModuleScopeAllowed])
def pricing_rates(request):
    """Active external-organization rates.

    Served from the database so the frontend can display amounts (and label
    quantities) without hardcoding any price in React. Staff-only edits in
    Django admin flow straight through.
    """
    return Response({"currency": "PHP", "rates": rates_payload()})


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovalModuleScopeAllowed])
def calendar_events(request):
    """Reservation events for calendar views within [start, end]."""
    expiration.expire_overdue_reservations()
    start = request.query_params.get("start")
    end = request.query_params.get("end")
    if not start or not end:
        return Response(
            {"detail": "start and end dates are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    qs = Reservation.objects.filter(
        date__gte=start,
        date__lte=end,
    ).select_related("facility", "requester")
    if not request.user.is_sas_staff:
        qs = qs.filter(requester=request.user)
    facility = request.query_params.get("facility")
    if facility and facility not in ("undefined", "null", "all", ""):
        try:
            qs = qs.filter(facility_id=int(facility))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid facility filter."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    if request.query_params.get("status"):
        qs = qs.filter(status=request.query_params["status"])
    equipment = request.query_params.get("equipment")
    if equipment and equipment not in ("undefined", "null", "all", ""):
        try:
            qs = qs.filter(items__equipment_id=int(equipment))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid equipment filter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    is_staff = request.user.is_sas_staff
    events = []
    for r in qs:
        event = {
            "id": r.id,
            "reservation_id": r.reservation_id,
            "title": r.event_name,
            "start": f"{r.date}T{r.start_time}",
            "end": f"{r.date}T{r.end_time}",
            "facility_id": r.facility_id,
            "facility": r.facility.name,
            "status": r.status,
            "requester": r.requester_display_name,
            "is_sas_staff": is_staff,
        }
        if is_staff and r.requester_type:
            event["requester_type"] = r.requester_type
            event["organization"] = r.organization or ""
            event["contact_person"] = r.contact_person or ""
            event["contact_email"] = r.contact_email or ""
        if is_staff and r.created_by:
            event["created_by"] = r.created_by.display_name
        events.append(event)
    return Response(events)
