from rest_framework.routers import DefaultRouter

from .views import (
    EquipmentCategoryViewSet,
    EquipmentViewSet,
    FacilityResourceViewSet,
    MaintenanceRecordViewSet,
)

router = DefaultRouter()
# See facilities/urls.py — the DRF API root at "/api/" is not published.
router.include_root_view = False
router.register("equipment", EquipmentViewSet, basename="equipment")
router.register("equipment-categories", EquipmentCategoryViewSet, basename="equipment-category")
router.register("facility-resources", FacilityResourceViewSet, basename="facility-resource")
router.register("maintenance", MaintenanceRecordViewSet, basename="maintenance")

urlpatterns = router.urls
