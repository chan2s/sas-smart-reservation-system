from rest_framework import serializers

from .models import Equipment, EquipmentCategory, MaintenanceRecord
from .services import (
    committed_quantity,
    equipment_availability,
    equipment_stats,
)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


def _validate_image_file(file):
    """Validate an uploaded equipment image.

    Returns ``(cleaned_file, original_name)`` on success, or raises
    ``serializers.ValidationError`` with a user-facing message.
    """
    if file is None:
        return None, None

    img_type = getattr(file, "content_type", None)
    allowed = img_type in ALLOWED_IMAGE_TYPES
    if not allowed:
        accepted = ", ".join(
            sorted(ext for _, ext in ALLOWED_IMAGE_TYPES.values())
        )
        raise serializers.ValidationError(
            f"Image must be JPG, PNG, or WEBP. The uploaded file uses ``{img_type or 'unknown'}``."
        )

    size = getattr(file, "size", 0)
    if size and size > MAX_IMAGE_SIZE:
        raise serializers.ValidationError(
            f"Image must be smaller than 5 MB. The uploaded file is {size / 1024 / 1024:.1f} MB."
        )

    return file, getattr(file, "name", None)


class EquipmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentCategory
        fields = ("id", "name", "icon", "description")


class EquipmentSerializer(serializers.ModelSerializer):
    category = EquipmentCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=EquipmentCategory.objects.all(), write_only=True
    )
    image = serializers.FileField(required=False, allow_null=True)
    condition_label = serializers.CharField(source="get_condition_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    availability = serializers.SerializerMethodField()
    has_history = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = Equipment
        fields = (
            "id",
            "name",
            "category",
            "category_id",
            "description",
            "total_quantity",
            "unit",
            "condition",
            "condition_label",
            "status",
            "status_label",
            "storage_location",
            "asset_code",
            "image",
            "notes",
            "is_active",
            "has_history",
            "availability",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("availability", "has_history")

    def validate_image(self, value):
        """Validate image format, size, and integrity.

        Accepts JPG, PNG, or WEBP and enforces a 5 MB limit. The file is also
        opened with Pillow to reject non-image or corrupt uploads, which gives a
        clear user-facing error rather than a generic Django message.
        """
        if value is None:
            return None

        img_type = getattr(value, "content_type", None)
        allowed = img_type in ALLOWED_IMAGE_TYPES
        if not allowed:
            accepted = ", ".join(
            sorted(ext for _, ext in ALLOWED_IMAGE_TYPES.values())
        )
            raise serializers.ValidationError(
                f"Image must be JPG, PNG, or WEBP. The uploaded file uses ``{img_type or 'unknown'}``."
            )

        size = getattr(value, "size", 0)
        if size and size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError(
                f"Image must be smaller than 5 MB. The uploaded file is {size / 1024 / 1024:.1f} MB."
            )

        try:
            import PIL.Image as _Image

            with _Image.open(value) as img:
                img.verify()
        except Exception as exc:
            raise serializers.ValidationError(
                f"Image must be JPG, PNG, or WEBP. The uploaded file could not be read as an image."
            ) from exc

        return value

    def get_availability(self, obj):
        request = self.context.get("request")
        return equipment_availability(obj, request)

    def get_has_history(self, obj):
        """True when the item must be archived (not hard-deleted) on removal.

        Matches the destroy() decision: reservation or maintenance history
        both preserve the record.
        """
        return bool(
            getattr(obj, "_has_reservation_history", obj.reservation_items.exists())
            or getattr(obj, "_has_maintenance_history", obj.maintenance_records.exists())
        )

    def validate(self, attrs):
        """Keep form-parsed writes from accidentally deactivating equipment.

        DRF's HTML form parsers (multipart/form-data, x-www-form-urlencoded)
        coerce a *missing* boolean checkbox to ``False``. The equipment form
        sends FormData (to support image uploads) without an ``is_active``
        field, so without this guard every create/edit via the form would
        silently archive the item. Creates always start active; updates keep
        the current value unless the caller explicitly changes it (JSON
        callers keep full control).
        """
        request = self.context.get("request")
        content_type = (request.content_type or "") if request else ""
        if "form" in content_type:
            if self.instance is not None:
                attrs["is_active"] = self.instance.is_active
            else:
                attrs["is_active"] = True
        return attrs

    def validate_total_quantity(self, value):
        """Inventory must never drop below what is already committed.

        Units currently reserved by active reservations or under open
        maintenance cannot simply disappear, otherwise existing reservations
        would be impossible to fulfill.
        """
        instance = self.instance
        if instance is not None and value < instance.total_quantity:
            committed = committed_quantity(instance)
            if value < committed:
                raise serializers.ValidationError(
                    f"Cannot reduce inventory to {value}. {committed} units are "
                    f"currently committed to reservations or maintenance. "
                    f"The total quantity must be at least {committed}."
                )
        return value

    def update(self, instance, validated_data):
        """Update equipment and clean up replaced/removed images.

        The old image is deleted from storage only when the update succeeds
        and the stored value actually changed away from the previous image.
        When equipment is archived rather than deleted, the image is preserved
        because it remains part of the historical record.
        """
        previous_image = instance.image
        new_image = validated_data.get("image", previous_image)
        result = super().update(instance, validated_data)

        if previous_image is not None and previous_image != new_image:
            if previous_image.name and hasattr(previous_image, "storage"):
                try:
                    previous_image.storage.delete(previous_image.name)
                except Exception:
                    pass

        return result


class EquipmentDetailSerializer(EquipmentSerializer):
    open_maintenance = serializers.SerializerMethodField()

    class Meta(EquipmentSerializer.Meta):
        fields = EquipmentSerializer.Meta.fields + ("open_maintenance",)

    def get_open_maintenance(self, obj):
        return obj.maintenance_records.filter(status=MaintenanceRecord.Status.OPEN).count()


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    issue_type_label = serializers.CharField(source="get_issue_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reported_by_name = serializers.CharField(source="reported_by.display_name", read_only=True, default="")

    class Meta:
        model = MaintenanceRecord
        fields = (
            "id",
            "equipment",
            "equipment_name",
            "quantity",
            "issue_type",
            "issue_type_label",
            "description",
            "photo",
            "reported_by",
            "reported_by_name",
            "status",
            "status_label",
            "created_at",
            "resolved_at",
        )
        read_only_fields = ("reported_by", "status", "resolved_at")

    def update(self, instance, validated_data):
        """Clean up replaced/removed maintenance photos on update."""
        previous_photo = instance.photo
        new_photo = validated_data.get("photo", previous_photo)
        result = super().update(instance, validated_data)

        if previous_photo is not None and previous_photo != new_photo:
            if previous_photo.name and hasattr(previous_photo, "storage"):
                try:
                    previous_photo.storage.delete(previous_photo.name)
                except Exception:
                    pass

        return result


class EquipmentStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    available = serializers.IntegerField()
    reserved = serializers.IntegerField()
    under_maintenance = serializers.IntegerField()
    unavailable = serializers.IntegerField()
    damaged = serializers.IntegerField()


class EquipmentStatsViewMixin:
    """Shared stats computation for equipment endpoints."""

    def get_stats(self, request):
        return equipment_stats(request)