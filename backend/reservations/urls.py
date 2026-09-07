from django.urls import path
from rest_framework.routers import DefaultRouter

from .public_views import (
    guest_reservation_create,
    public_availability_check,
    public_equipment,
    public_facilities,
    public_resources_recommendation,
    track_reservation,
)
from .views import (
    ReservationViewSet,
    availability_check,
    calendar_events,
    reservation_by_checkin_code,
    resources_recommendation,
)

router = DefaultRouter()
router.register("reservations", ReservationViewSet, basename="reservation")

urlpatterns = router.urls + [
    # Public, unauthenticated endpoints for external requesters.
    path("public/facilities/", public_facilities, name="public-facilities"),
    path("public/equipment/", public_equipment, name="public-equipment"),
    path(
        "public/availability/check/",
        public_availability_check,
        name="public-availability-check",
    ),
    path(
        "public/availability/resources/",
        public_resources_recommendation,
        name="public-availability-resources",
    ),
    path("public/reservations/", guest_reservation_create, name="guest-reservation-create"),
    path("public/track/", track_reservation, name="track-reservation"),
    # Authenticated endpoints (existing).
    path("availability/check/", availability_check, name="availability-check"),
    path(
        "availability/resources/",
        resources_recommendation,
        name="availability-resources",
    ),
    path("calendar/events/", calendar_events, name="calendar-events"),
    path(
        "reservations/checkin/<uuid:code>/",
        reservation_by_checkin_code,
        name="reservation-checkin",
    ),
]