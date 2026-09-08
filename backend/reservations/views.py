import datetime

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsSasStaff
from facilities.models import Facility
from notifications.models import Notification
from notifications.services import notify, notify_staff
from notifications.email_service import send_reservation_submitted
from .models import Reservation, ReservationEvent
from .serializers import (
    ReservationCreateSerializer,
    ReservationDetailSerializer,
    ReservationListSerializer,
)
from .services import workflow
from .services.availability import check_availability, find_alternatives
from .services.recommendations import recommend_resources


class ReservationViewSet(viewsets.ModelViewSet):
    """Administrative reservation management + requester self-service."""
    permission_classes = [IsAuthenticated]

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
        qs = Reservation.objects.select_related(
            "facility", "requester", "created_by", "approved_by"
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

        # The backend is the source of truth for status: reservations created
        # by an administrator are approved immediately (campus or external
        # requester alike); everyone else enters the normal pending review
        # queue. A status value sent by the client is never trusted (the
        # serializer does not even accept one).
        if request.user.is_admin:
            workflow.auto_approve(reservation, request.user)
        else:
            notify_staff(
                Notification.Type.RESERVATION,
                "New reservation request",
                f"{reservation.event_name} on {reservation.date} ({reservation.start_time:%H:%M}–{reservation.end_time:%H:%M}) is awaiting approval.",
                f"/reservations/{reservation.id}",
            )
        # Send email notification to the requester
        if reservation.requester and reservation.requester.email:
            send_reservation_submitted(
                user_email=reservation.requester.email,
                reservation_id=reservation.reservation_id,
                event_name=reservation.event_name,
                facility_name=reservation.facility.name,
                date=reservation.date.isoformat(),
                start_time=reservation.start_time.strftime("%H:%M"),
                end_time=reservation.end_time.strftime("%H:%M"),
            )

        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], permission_classes=[IsSasStaff])
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
        qs = Reservation.objects.all()
        if not request.user.is_sas_staff:
            qs = qs.filter(requester=request.user)
        statuses = dict(Reservation.Status.choices)
        result = {"ALL": qs.count()}
        for key, _ in statuses.items():
            result[key] = qs.filter(status=key).count()
        return Response(result)

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff])
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

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff])
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

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff])
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
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ReservationDetailSerializer(
                reservation, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def check_in(self, request, pk=None):
        """Check a reservation in.

        Authorization: the reservation owner or SAS staff.

        Time policy: check-in opens 3 hours before the event start. Anyone
        may check in once the window is open. Before it opens, only an
        administrator who explicitly confirms the override (``override: true``
        in the request body) may check in — the backend verifies the role, so
        a regular user cannot bypass the window by sending the flag. The
        override is recorded on the reservation.
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

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff])
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
@permission_classes([IsAuthenticated])
def availability_check(request):
    """Conflict analysis + alternative schedules for a proposed window."""
    data = request.data
    try:
        report = check_availability(
            data["facility_id"],
            datetime.date.fromisoformat(data["date"]),
            datetime.time.fromisoformat(data["start_time"]),
            datetime.time.fromisoformat(data["end_time"]),
            data.get("items", []),
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

    report["alternatives"] = find_alternatives(
        data["facility_id"],
        datetime.date.fromisoformat(data["date"]),
        datetime.time.fromisoformat(data["start_time"]),
        datetime.time.fromisoformat(data["end_time"]),
        data.get("items", []),
    )
    return Response(report)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
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

    recommendations = recommend_resources(
        event_type,
        participants,
        facility_id=data.get("facility_id"),
        purpose=data.get("purpose", ""),
        special_requirements=data.get("special_requirements", ""),
        target_date=target_date,
        start_time=start_time,
        end_time=end_time,
    )
    return Response({"recommendations": recommendations})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calendar_events(request):
    """Reservation events for calendar views within [start, end]."""
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
