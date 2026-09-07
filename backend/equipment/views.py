from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from reservations.models import ReservationItem

from accounts.models import AuditLog
from accounts.permissions import IsSasStaff, IsSasStaffOrReadOnly

from .models import Equipment, EquipmentCategory, MaintenanceRecord
from .serializers import (
    EquipmentCategorySerializer,
    EquipmentDetailSerializer,
    EquipmentSerializer,
    EquipmentStatsSerializer,
    MaintenanceRecordSerializer,
)
from .services import (
    equipment_stats,
    equipment_usage_history,
    reconcile_status,
)


class EquipmentCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EquipmentCategory.objects.all()
    serializer_class = EquipmentCategorySerializer
    pagination_class = None


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.select_related("category").prefetch_related("maintenance_records").all()
    serializer_class = EquipmentSerializer
    permission_classes = [IsSasStaffOrReadOnly]
    pagination_class = None
    search_fields = ("name", "description", "storage_location", "asset_code", "category__name")

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            _has_reservation_history=Exists(
                ReservationItem.objects.filter(equipment_id=OuterRef("pk"))
            ),
            _has_maintenance_history=Exists(
                MaintenanceRecord.objects.filter(equipment_id=OuterRef("pk"))
            ),
        )
        params = self.request.query_params

        # Archived equipment must not appear in reservation flows by default.
        # Only SAS staff may opt in to see archived lines (e.g. to restore
        # them), and only when they explicitly ask.
        if params.get("include_inactive") != "true" or not self.request.user.is_sas_staff:
            qs = qs.filter(is_active=True)

        if params.get("category"):
            qs = qs.filter(category_id=params["category"])
        if params.get("condition"):
            qs = qs.filter(condition=params["condition"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EquipmentDetailSerializer
        return EquipmentSerializer

    def perform_create(self, serializer):
        equipment = serializer.save()
        AuditLog.record(
            self.request.user,
            AuditLog.Action.EQUIPMENT_CREATED,
            object_type="equipment",
            object_id=equipment.id,
            object_repr=equipment.name,
        )

    def perform_update(self, serializer):
        previous_image = serializer.instance.image.name if serializer.instance.image else None
        equipment = serializer.save()
        AuditLog.record(
            self.request.user,
            AuditLog.Action.EQUIPMENT_EDITED,
            object_type="equipment",
            object_id=equipment.id,
            object_repr=equipment.name,
        )
        new_image = equipment.image.name if equipment.image else None
        if previous_image != new_image:
            AuditLog.record(
                self.request.user,
                AuditLog.Action.EQUIPMENT_IMAGE,
                object_type="equipment",
                object_id=equipment.id,
                object_repr=equipment.name,
                detail=(
                    f"Image replaced ({previous_image or 'none'} → {new_image or 'none'})"
                ),
            )

    def destroy(self, request, *args, **kwargs):
        """Safe deletion: archive equipment with history, hard-delete fresh items.

        Equipment that has ever been reserved (or has maintenance records)
        must never be hard-deleted — that would destroy historical reservation
        data. It is archived (``is_active = False``) instead, which removes it
        from new reservation flows while preserving all records.
        """
        equipment = self.get_object()
        has_history = (
            equipment.reservation_items.exists()
            or equipment.maintenance_records.exists()
        )
        if has_history:
            equipment.is_active = False
            equipment.save(update_fields=["is_active", "updated_at"])
            AuditLog.record(
                request.user,
                AuditLog.Action.EQUIPMENT_REMOVED,
                object_type="equipment",
                object_id=equipment.id,
                object_repr=equipment.name,
                detail="Archived (has reservation or maintenance history)",
            )
            return Response(
                {
                    "archived": True,
                    "id": equipment.id,
                    "detail": (
                        f"{equipment.name} was archived instead of deleted because "
                        "it has reservation or maintenance history. Existing "
                        "records remain intact."
                    ),
                },
                status=status.HTTP_200_OK,
            )
        AuditLog.record(
            request.user,
            AuditLog.Action.EQUIPMENT_REMOVED,
            object_type="equipment",
            object_id=equipment.id,
            object_repr=equipment.name,
            detail="Permanently deleted (no history)",
        )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        return Response(equipment_stats(request))

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Reservation usage history for one piece of equipment."""
        equipment = self.get_object()
        return Response(equipment_usage_history(equipment.id))

    @action(detail=True, methods=["get", "post"])
    def maintenance(self, request, pk=None):
        """GET: maintenance records. POST: mark N units under maintenance.

        Creating a maintenance record is a staff operation (the viewset's
        ``IsSasStaffOrReadOnly`` permission applies: safe methods are readable
        by any authenticated user, writes require staff). Each record takes a
        ``quantity`` of units out of service; when every unit is covered the
        item's status flips to MAINTENANCE automatically.
        """
        equipment = self.get_object()
        if request.method == "POST":
            data = request.data
            try:
                quantity = int(data.get("quantity", 1) or 1)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "Quantity must be a whole number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if quantity < 1:
                return Response(
                    {"detail": "Quantity must be at least 1."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if equipment.status in (
                Equipment.Status.UNAVAILABLE,
                Equipment.Status.RETIRED,
            ):
                return Response(
                    {
                        "detail": (
                            f"{equipment.name} is {equipment.get_status_display().lower()} "
                            "and cannot be placed under maintenance."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            quantity = min(quantity, equipment.total_quantity)
            record = MaintenanceRecord.objects.create(
                equipment=equipment,
                quantity=quantity,
                issue_type=MaintenanceRecord.IssueType.MAINTENANCE,
                description=data.get("reason", ""),
                reported_by=request.user,
            )
            reconcile_status(equipment)
            return Response(
                MaintenanceRecordSerializer(record).data,
                status=status.HTTP_201_CREATED,
            )
        records = equipment.maintenance_records.all()
        return Response(MaintenanceRecordSerializer(records, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff])
    def report_issue(self, request, pk=None):
        equipment = self.get_object()
        data = request.data.copy()
        data["equipment"] = equipment.id
        serializer = MaintenanceRecordSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        record = serializer.save(reported_by=request.user)
        reconcile_status(equipment)
        return Response(MaintenanceRecordSerializer(record).data, status=status.HTTP_201_CREATED)


class MaintenanceRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaintenanceRecord.objects.select_related("equipment", "reported_by").all()
    serializer_class = MaintenanceRecordSerializer
    search_fields = ("equipment__name", "description")

    @action(detail=True, methods=["post"], permission_classes=[IsSasStaff])
    def resolve(self, request, pk=None):
        record = self.get_object()
        record.status = MaintenanceRecord.Status.RESOLVED
        record.resolved_at = timezone.now()
        record.save(update_fields=["status", "resolved_at"])
        reconcile_status(record.equipment)
        return Response(MaintenanceRecordSerializer(record).data)


class EquipmentStatsView:
    """Used by the API root helper; stats are served through the viewset action."""