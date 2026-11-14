from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ReservationViewSet,
    availability_check,
    calendar_events,
    pricing_rates,
    public_availability_check,
    public_booked_dates,
    public_facility_resources,
    public_pricing_rates,
    public_reservation_catalog,
    public_reservation_submit,
    public_resource_recommendation,
    public_reservation_track,
    public_reservation_edit_details,
    public_reservation_request_edit_otp,
    public_reservation_resend_edit_otp,
    public_reservation_verify_edit_otp,
    public_reservation_upload_approval_letter,
    reservation_approval_letter_image,
    reservation_by_checkin_code,
    resources_recommendation,
)
from .approval_letter_settings import (
    approval_letter_settings,
    approval_letter_template_versions,
    preview_approval_letter,
    restore_approval_letter_template_version,
)

router = DefaultRouter()
# See facilities/urls.py — the DRF API root at "/api/" is not published.
router.include_root_view = False
router.register("reservations", ReservationViewSet, basename="reservation")

urlpatterns = [
    path(
        "admin/settings/approval-letter/",
        approval_letter_settings,
        name="admin-approval-letter-settings",
    ),
    path(
        "admin/settings/approval-letter/versions/",
        approval_letter_template_versions,
        name="admin-approval-letter-template-versions",
    ),
    path(
        "admin/settings/approval-letter/versions/<int:version>/restore/",
        restore_approval_letter_template_version,
        name="admin-approval-letter-template-restore",
    ),
    path(
        "admin/settings/approval-letter/preview/",
        preview_approval_letter,
        name="admin-approval-letter-preview",
    ),
    # Reference/email tracking plus support for previously emailed signed links.
    path(
        "public/reservations/track/",
        public_reservation_track,
        name="public-reservation-track",
    ),
    path("public/reservations/edit-details/", public_reservation_edit_details, name="public-reservation-edit-details"),
    path("public/reservations/request-edit-otp/", public_reservation_request_edit_otp, name="public-reservation-request-edit-otp"),
    path("public/reservations/resend-edit-otp/", public_reservation_resend_edit_otp, name="public-reservation-resend-edit-otp"),
    path("public/reservations/verify-edit-otp/", public_reservation_verify_edit_otp, name="public-reservation-verify-edit-otp"),
    path(
        "public/reservations/approval-letter/",
        public_reservation_upload_approval_letter,
        name="public-reservation-approval-letter",
    ),
    path(
        "reservations/<int:pk>/approval-letter-image/file/",
        reservation_approval_letter_image,
        name="reservation-approval-letter-image",
    ),
    path("public/reservations/catalog/", public_reservation_catalog, name="public-reservation-catalog"),
    path("public/reservations/submit/", public_reservation_submit, name="public-reservation-submit"),
    path("public/reservations/availability/", public_availability_check, name="public-reservation-availability"),
    path("public/reservations/booked-dates/", public_booked_dates, name="public-reservation-booked-dates"),
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
