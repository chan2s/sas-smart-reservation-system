from django.urls import path
from rest_framework.routers import DefaultRouter

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
    # Authenticated endpoints.
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