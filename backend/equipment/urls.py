from rest_framework.routers import DefaultRouter

from .views import (
    EquipmentCategoryViewSet,
    EquipmentViewSet,
    MaintenanceRecordViewSet,
)

router = DefaultRouter()
router.register("equipment", EquipmentViewSet, basename="equipment")
router.register("equipment-categories", EquipmentCategoryViewSet, basename="equipment-category")
router.register("maintenance", MaintenanceRecordViewSet, basename="maintenance")

urlpatterns = router.urls