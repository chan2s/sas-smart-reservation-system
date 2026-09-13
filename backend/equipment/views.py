from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from reservations.models import ReservationItem

from accounts.models import AuditLog
from accounts.permissions import IsSasStaff, IsSasStaffOrReadOnly

from .models import Equipment, EquipmentCategory, EquipmentImage, MaintenanceRecord
from .serializers import (
    MAX_IMAGES_PER_UPLOAD,
    EquipmentCategorySerializer,
    EquipmentDetailSerializer,
    EquipmentImageSerializer,
    EquipmentSerializer,
    EquipmentStatsSerializer,
    MaintenanceRecordSerializer,
    validate_equipment_image,
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
    queryset = (
        Equipment.objects.select_related("category")
        .prefetch_related("maintenance_records", "equipment_images")
        .all()
    )
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

    # ------------------------------------------------------------------
    # Image gallery
    # ------------------------------------------------------------------

    @staticmethod
    def _gallery(equipment):
        """The gallery as it is stored right now.

        Deliberately a fresh query rather than ``equipment.equipment_images``:
        the equipment queryset is prefetched, so the related manager would
        return rows cached before this request's mutations (deleted images
        included) and every gallery response would be one step behind.
        """
        return EquipmentImage.objects.filter(equipment=equipment)

    def _gallery_response(self, equipment, images=None, status_code=status.HTTP_200_OK):
        """Serialize a gallery (or a subset of it) as ``{"images": [...]}``."""
        payload = self._gallery(equipment) if images is None else images
        data = EquipmentImageSerializer(
            payload, many=True, context={"request": self.request}
        ).data
        return Response({"images": data}, status=status_code)

    def _ensure_primary(self, equipment):
        """Keep exactly one primary image whenever the gallery is non-empty."""
        gallery = self._gallery(equipment)
        if gallery.filter(is_primary=True).exists():
            return
        promoted = gallery.first()
        if promoted is not None:
            promoted.is_primary = True
            promoted.save(update_fields=["is_primary", "updated_at"])

    def _adopt_legacy_image(self, equipment):
        """Move a legacy single image into the gallery.

        Returns the new gallery entry, or None when there is nothing to adopt
        (no legacy image, or the gallery already has images). Keeping this in
        the gallery keeps the API response complete for records whose image was
        set through the legacy field after the backfill migration ran.
        """
        if self._gallery(equipment).exists() or not equipment.image:
            return None
        return EquipmentImage.objects.create(
            equipment=equipment,
            # Same stored file: a reference, never a copy.
            image=equipment.image.name,
            display_order=0,
            is_primary=True,
        )

    def _log_image_change(self, equipment, detail):
        AuditLog.record(
            self.request.user,
            AuditLog.Action.EQUIPMENT_IMAGE,
            object_type="equipment",
            object_id=equipment.id,
            object_repr=equipment.name,
            detail=detail,
        )

    @action(detail=True, methods=["get", "post"], url_path="images")
    def images(self, request, pk=None):
        """GET the image gallery; POST one or more new gallery images.

        Uploads are multipart/form-data and repeat the ``images`` key once per
        file — ``formData.append("images", file)`` for each File. Every file
        goes through the same validator as the legacy single-image field
        (JPG/PNG/WEBP, at most 5 MB, verified bytes).

        Writes require SAS staff; any authenticated user may read the gallery.
        """
        equipment = self.get_object()

        if request.method == "GET":
            return self._gallery_response(equipment)

        files = request.FILES.getlist("images")
        if not files:
            return Response(
                {
                    "images": [
                        "No files were uploaded. Send one or more images under the 'images' field."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(files) > MAX_IMAGES_PER_UPLOAD:
            return Response(
                {"images": [f"Upload at most {MAX_IMAGES_PER_UPLOAD} images at a time."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate everything before storing anything: a bad file must not
        # leave a half-finished gallery behind.
        errors = []
        for index, file in enumerate(files, start=1):
            try:
                validate_equipment_image(file)
            except serializers.ValidationError as exc:
                label = f"Image {index}" if len(files) > 1 else "Image"
                messages = " ".join(str(item) for item in exc.detail)
                errors.append(f"{label}: {messages}")
        if errors:
            return Response({"images": errors}, status=status.HTTP_400_BAD_REQUEST)

        self._adopt_legacy_image(equipment)

        gallery = self._gallery(equipment)
        last_order = gallery.order_by("-display_order").values_list(
            "display_order", flat=True
        ).first()
        next_order = 0 if last_order is None else last_order + 1
        has_primary = gallery.filter(is_primary=True).exists()

        with transaction.atomic():
            created = [
                EquipmentImage.objects.create(
                    equipment=equipment,
                    image=file,
                    display_order=next_order + offset,
                    # The very first image of a gallery becomes its primary one.
                    is_primary=not has_primary and offset == 0,
                )
                for offset, file in enumerate(files)
            ]

        self._log_image_change(
            equipment,
            f"Added {len(created)} gallery image(s)",
        )
        return self._gallery_response(
            equipment, images=created, status_code=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_id>\d+)")
    def delete_image(self, request, pk=None, image_id=None):
        """Remove one gallery image (staff only) and clean up its stored file."""
        equipment = self.get_object()
        image = get_object_or_404(equipment.equipment_images, pk=image_id)
        stored_name = image.image.name
        storage = image.image.storage

        with transaction.atomic():
            image.delete()

            # The gallery owns the file now. Delete it only once nothing else
            # references the same stored name, and clear the legacy single
            # image field when it mirrored this picture — otherwise the
            # backward-compatibility fallback would resurrect a deleted image.
            gallery = self._gallery(equipment)
            if stored_name and not gallery.filter(image=stored_name).exists():
                if equipment.image and equipment.image.name == stored_name:
                    equipment.image = None
                    equipment.save(update_fields=["image", "updated_at"])
                storage.delete(stored_name)

            # Emptying the gallery is an explicit "this item has no images"
            # action, so a legacy image must not resurface through the
            # backward-compatibility fallback.
            if not gallery.exists() and equipment.image:
                legacy_name = equipment.image.name
                legacy_storage = equipment.image.storage
                equipment.image = None
                equipment.save(update_fields=["image", "updated_at"])
                if legacy_name and legacy_name != stored_name:
                    legacy_storage.delete(legacy_name)

            self._ensure_primary(equipment)

        self._log_image_change(equipment, "Removed a gallery image")
        return self._gallery_response(equipment)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"images/(?P<image_id>\d+)/primary",
    )
    def set_primary_image(self, request, pk=None, image_id=None):
        """Make one gallery image the primary one (staff only)."""
        equipment = self.get_object()
        image = get_object_or_404(equipment.equipment_images, pk=image_id)

        with transaction.atomic():
            equipment.equipment_images.exclude(pk=image.pk).update(is_primary=False)
            image.is_primary = True
            image.save(update_fields=["is_primary", "updated_at"])

        self._log_image_change(equipment, "Changed the primary gallery image")
        return self._gallery_response(equipment)

    @action(detail=True, methods=["post"], url_path="images/order")
    def reorder_images(self, request, pk=None):
        """Reorder the gallery. Body: ``{"order": [image_id, ...]}`` (staff only).

        The list must contain every current gallery image id exactly once.
        Missing ids are rejected rather than silently reordered, so a stale
        client can never scramble the gallery.
        """
        equipment = self.get_object()
        raw_order = request.data.get("order")
        if not isinstance(raw_order, (list, tuple)):
            return Response(
                {"order": ["Send the gallery image ids as a list."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            order = [int(item) for item in raw_order]
        except (TypeError, ValueError):
            return Response(
                {"order": ["Image ids must be whole numbers."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_ids = set(self._gallery(equipment).values_list("id", flat=True))
        if len(order) != len(set(order)) or set(order) != existing_ids:
            return Response(
                {"order": ["Send every gallery image id exactly once."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for position, image_id in enumerate(order):
                EquipmentImage.objects.filter(pk=image_id).update(display_order=position)

        self._log_image_change(equipment, "Reordered the gallery images")
        return self._gallery_response(equipment)

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