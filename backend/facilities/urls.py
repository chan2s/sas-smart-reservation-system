from rest_framework.routers import DefaultRouter

from .views import FacilityViewSet

router = DefaultRouter()
# No API root at "/api/": four routers are mounted on the same prefix, so the
# DRF-generated root would list only this app's routes while inheriting the
# global IsAuthenticated permission. Anonymous browser visits (which never
# carry the localStorage JWT) hit it repeatedly and logged noisy 401s. The
# endpoint is not part of the product API, so it is not published at all.
router.include_root_view = False
router.register("facilities", FacilityViewSet, basename="facility")

urlpatterns = router.urls