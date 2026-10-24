from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationViewSet,
    no_show_alert_acknowledge,
    no_show_alert_acknowledge_all,
    no_show_alert_list,
)

router = DefaultRouter()
# See facilities/urls.py — the DRF API root at "/api/" is not published.
router.include_root_view = False
router.register("notifications", NotificationViewSet, basename="notification")

# Static alert routes must precede the router's "<pk>/" detail pattern,
# otherwise "no-show-alerts" would be read as a notification primary key.
urlpatterns = [
    path(
        "notifications/no-show-alerts/",
        no_show_alert_list,
        name="no-show-alert-list",
    ),
    path(
        "notifications/no-show-alerts/acknowledge-all/",
        no_show_alert_acknowledge_all,
        name="no-show-alert-acknowledge-all",
    ),
    path(
        "notifications/no-show-alerts/<int:alert_id>/acknowledge/",
        no_show_alert_acknowledge,
        name="no-show-alert-acknowledge",
    ),
] + router.urls
