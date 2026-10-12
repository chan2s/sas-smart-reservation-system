from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet

router = DefaultRouter()
# See facilities/urls.py — the DRF API root at "/api/" is not published.
router.include_root_view = False
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = router.urls