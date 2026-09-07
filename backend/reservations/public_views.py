"""Public (unauthenticated) reservation endpoints for external requesters.

Security model:
* Guest submissions always create EXTERNAL reservations that enter the normal
  pending queue — nothing is auto-approved without an account.
* Tracking requires BOTH the reservation code AND the email used on the
  reservation, and returns a restricted payload (PublicTrackSerializer) that
  never exposes other reservations, internal notes, or check-in codes.
* Availability/recommendation endpoints are read-only and leak nothing about
  who reserved what (only aggregate counts).
"""

from datetime import date as date_cls, datetime, time as time_cls

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from facilities.models import Facility
from notifications.models import Notification
from notifications.services import notify_staff
from reservations.models import Reservation
from reservations.services.availability import check_availability, find_alternatives
from reservations.services.recommendations import recommend_resources
from reservations.serializers import (
    GuestReservationCreateSerializer,
    PublicTrackSerializer,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_facilities(request):
    """Active, operational facilities for the public reservation page."""
    qs = Facility.objects.filter(is_active=True).order_by("name")
    facilities = [
        {
            "id": f.id,
            "name": f.name,
            "facility_type": f.facility_type,
            "facility_type_label": f.get_facility_type_display(),
            "description": f.description,
            "capacity": f.capacity,
            "location": f.location,
            "image": f.image.url if f.image else None,
            "status": f.status,
        }
        for f in qs
    ]
    return Response({"results": facilities})


@api_view(["GET"])
@permission_classes([AllowAny])
def public_equipment(request):
    """Active equipment with schedule-aware availability for guests.

    Read-only inventory view: names, categories, and available quantities.
    No internal data (storage locations, asset codes, notes, costs).
    """
    from equipment.models import Equipment
    from reservations.services.availability import equipment_availability_map

    target_date = request.query_params.get("date")
    start = request.query_params.get("start")
    end = request.query_params.get("end")

    import datetime as dt

    try:
        target = dt.date.fromisoformat(target_date) if target_date else None
        start_t = dt.time.fromisoformat(start) if start else None
        end_t = dt.time.fromisoformat(end) if end else None
    except ValueError:
        return Response(
            {"detail": "Invalid date or time."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    availability = equipment_availability_map(target, start_t, end_t)
    results = []
    for eq in (
        Equipment.objects.filter(is_active=True)
        .select_related("category")
        .order_by("category__name", "name")
    ):
        info = availability.get(eq.id, {})
        results.append(
            {
                "id": eq.id,
                "name": eq.name,
                "category": {"id": eq.category_id, "name": eq.category.name},
                "description": eq.description,
                "image": eq.image.url if eq.image else None,
                "total_quantity": eq.total_quantity,
                "availability": {
                    "total": info.get("total", eq.total_quantity),
                    "available": info.get("available", 0),
                    "reserved": info.get("reserved", 0),
                    "under_maintenance": info.get("under_maintenance", 0),
                    "status": (
                        "UNAVAILABLE"
                        if info.get("available", 0) == 0
                        else "PARTIAL"
                        if info.get("available", 0) < eq.total_quantity
                        else "AVAILABLE"
                    ),
                },
            }
        )
    return Response({"results": results})


@api_view(["POST"])
@permission_classes([AllowAny])
def public_availability_check(request):
    """Conflict analysis for a proposed window — same engine as the app."""
    data = request.data
    try:
        report = check_availability(
            data["facility_id"],
            date_cls.fromisoformat(data["date"]),
            time_cls.fromisoformat(data["start_time"]),
            time_cls.fromisoformat(data["end_time"]),
            data.get("items", []),
        )
        report["alternatives"] = find_alternatives(
            data["facility_id"],
            date_cls.fromisoformat(data["date"]),
            time_cls.fromisoformat(data["start_time"]),
            time_cls.fromisoformat(data["end_time"]),
            data.get("items", []),
        )
    except (KeyError, ValueError, TypeError) as exc:
        return Response(
            {"detail": f"Invalid request: {exc}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Facility.DoesNotExist:
        return Response(
            {"detail": "Facility not found."}, status=status.HTTP_404_NOT_FOUND
        )
    return Response(report)


@api_view(["POST"])
@permission_classes([AllowAny])
def public_resources_recommendation(request):
    """Smart resource recommendations for an event profile (public page)."""
    data = request.data
    event_type = data.get("event_type", Reservation.EventType.OTHER)
    try:
        participants = int(data.get("expected_participants", 0) or 0)
        target_date = (
            date_cls.fromisoformat(data["date"]) if data.get("date") else None
        )
        start_time = (
            time_cls.fromisoformat(data["start_time"]) if data.get("start_time") else None
        )
        end_time = (
            time_cls.fromisoformat(data["end_time"]) if data.get("end_time") else None
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


@api_view(["POST"])
@permission_classes([AllowAny])
def guest_reservation_create(request):
    """External requesters submit a reservation without an account.

    Response includes the generated reservation code so the confirmation page
    can offer tracking. The reservation is PENDING until SAS reviews it.
    """
    serializer = GuestReservationCreateSerializer(data=request.data)
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        if exc.get_codes().get("availability"):
            report = getattr(serializer, "_availability_report", {})
            return Response(
                {"detail": "Resource conflict detected", "availability": report},
                status=status.HTTP_409_CONFLICT,
            )
        raise

    reservation = serializer.save()
    notify_staff(
        Notification.Type.RESERVATION,
        "New external reservation request",
        (
            f"{reservation.requester_display_name} ({reservation.get_organization_type_display() or 'External'}) "
            f"requested {reservation.facility.name} on {reservation.date} "
            f"({reservation.start_time:%H:%M}–{reservation.end_time:%H:%M}) — {reservation.reservation_id}."
        ),
        f"/reservations/{reservation.id}",
    )
    return Response(
        {
            "detail": "Reservation submitted successfully.",
            "reservation_id": reservation.reservation_id,
            "status": reservation.status,
            "status_label": reservation.get_status_display(),
            "track": {
                "code": reservation.reservation_id,
                "email": reservation.contact_email,
            },
        },
        status=status.HTTP_201_CREATED,
    )


def _tracking_status_payload(reservation: Reservation) -> dict:
    """Map a reservation onto the public tracking states."""
    # ACTIVE is shown as CHECKED IN / IN PROGRESS for external requesters.
    if reservation.status == Reservation.Status.ACTIVE:
        label = "Checked in" if not reservation.checked_out_at else "In progress"
        status_key = "CHECKED_IN"
    else:
        status_key = reservation.status
        label = reservation.get_status_display()
    return {
        "status": status_key,
        "status_label": label,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def track_reservation(request):
    """Track a reservation with code + email verification.

    Both fields must match the reservation. The response is intentionally
    limited (PublicTrackSerializer): no other reservations, no internal notes,
    no approval timeline, no check-in codes.
    """
    code = (request.data.get("reservation_code") or "").strip()
    email = (request.data.get("email") or "").strip().lower()

    if not code or not email:
        return Response(
            {"detail": "Reservation code and email address are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reservation = (
        Reservation.objects.select_related("facility")
        .prefetch_related("items__equipment")
        .filter(
            reservation_id__iexact=code,
            contact_email__iexact=email,
        )
        .first()
    )

    if not reservation:
        # Deliberately generic: do not reveal whether the code or email was
        # wrong, and never confirm other organizations' reservations exist.
        return Response(
            {"detail": "No reservation found matching that code and email."},
            status=status.HTTP_404_NOT_FOUND,
        )

    data = PublicTrackSerializer(reservation).data
    data.update(_tracking_status_payload(reservation))
    return Response(data)
