from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ReservationViewSet,
    availability_check,
    calendar_events,
    pricing_rates,
    public_availability_check,
    public_facility_resources,
    public_pricing_rates,
    public_reservation_catalog,
    public_reservation_submit,
    public_resource_recommendation,
    public_reservation_track,
    reservation_by_checkin_code,
    resources_recommendation,
)

router = DefaultRouter()
# See facilities/urls.py — the DRF API root at "/api/" is not published.
router.include_root_view = False
router.register("reservations", ReservationViewSet, basename="reservation")

urlpatterns = [
    # Token-protected status view for guest links sent before external
    # organizations moved into the shared authenticated workflow.
    path(
        "public/reservations/track/",
        public_reservation_track,
        name="public-reservation-track",
    ),
    path("public/reservations/catalog/", public_reservation_catalog, name="public-reservation-catalog"),
    path("public/reservations/submit/", public_reservation_submit, name="public-reservation-submit"),
    path("public/reservations/availability/", public_availability_check, name="public-reservation-availability"),
    path("public/reservations/recommendations/", public_resource_recommendation, name="public-reservation-recommendations"),
    path("public/reservations/pricing/", public_pricing_rates, name="public-reservation-pricing"),
    path("public/reservations/facilities/<int:facility_id>/resources/", public_facility_resources, name="public-facility-resources"),
] + router.urls + [
    # Authenticated endpoints.
    path("availability/check/", availability_check, name="availability-check"),
    path(
        "availability/resources/",
        resources_recommendation,
        name="availability-resources",
    ),
    path("calendar/events/", calendar_events, name="calendar-events"),
    path("pricing/rates/", pricing_rates, name="pricing-rates"),
    path(
        "reservations/checkin/<uuid:code>/",
        reservation_by_checkin_code,
        name="reservation-checkin",
    ),
]
