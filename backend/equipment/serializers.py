from rest_framework import serializers

from .models import (
    Equipment,
    EquipmentCategory,
    EquipmentImage,
    FacilityResource,
    MaintenanceRecord,
)
from .services import (
    committed_quantity,
    equipment_availability,
    equipment_stats,
    facility_resource_availability,
)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

#: Most files a single gallery upload request may carry.
MAX_IMAGES_PER_UPLOAD = 20


def validate_equipment_image(value):
    """Validate one uploaded equipment image.

    The single shared validator for every image entry point (the legacy
    ``Equipment.image`` field and the gallery upload endpoint), so both paths
    accept exactly the same formats and reject with the same messages.

    Returns the file unchanged, or raises ``serializers.ValidationError``.
    Never trusts the client-provided content type on its own: the bytes are
    verified with Pillow so a renamed non-image file is rejected too.
    """
    if value is None:
        return None

    img_type = getattr(value, "content_type", None)
    if img_type not in ALLOWED_IMAGE_TYPES:
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
            "Image must be JPG, PNG, or WEBP. The uploaded file could not be read as an image."
        ) from exc

    return value


def _absolute_image_url(image, request):
    """Browser-usable URL for a stored image, or None when there is none."""
    if not image:
        return None
    url = image.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


class EquipmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentCategory
        fields = ("id", "name", "icon", "description")


class EquipmentImageSerializer(serializers.ModelSerializer):
    """One gallery image, as the frontend consumes it."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentImage
        fields = ("id", "url", "caption", "display_order", "is_primary")

    def get_url(self, obj):
        return _absolute_image_url(obj.image, self.context.get("request"))


class EquipmentSerializer(serializers.ModelSerializer):
    category = EquipmentCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=EquipmentCategory.objects.all(), write_only=True
    )
    image = serializers.FileField(required=False, allow_null=True)
    images = serializers.SerializerMethodField()
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
            "images",
            "notes",
            "is_active",
            "has_history",
            "availability",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("availability", "has_history")

    def get_images(self, obj):
        """The gallery, ordered by the model's ordering.

        Backward compatibility: equipment whose only picture lives in the
        legacy single-image field is exposed as a one-entry gallery (with a
        null id, because there is no gallery row to act on) instead of
        returning an empty collection. The frontend never has to special-case
        old records, and an empty list always means "no images at all".
        """
        gallery = list(obj.equipment_images.all())
        if gallery:
            return EquipmentImageSerializer(
                gallery, many=True, context=self.context
            ).data

        legacy_url = _absolute_image_url(getattr(obj, "image", None), self.context.get("request"))
        if not legacy_url:
            return []
        return [
            {
                "id": None,
                "url": legacy_url,
                "caption": "",
                "display_order": 0,
                "is_primary": True,
            }
        ]

    def validate_image(self, value):
        """Validate the legacy single-image field.

        Accepts JPG, PNG, or WEBP up to 5 MB and verifies the bytes with
        Pillow, so a renamed non-image file gets a clear error instead of a
        generic Django failure.
        """
        return validate_equipment_image(value)

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


class FacilityResourceSerializer(serializers.ModelSerializer):
    """A facility's own resource, as the reservation form consumes it.

    Piictures come from the equipment gallery (legacy single image included as
    a fallback), so the existing image feature is preserved. ``availability``
    is window-aware via ``date``/``start``/``end`` query params and is capped
    by the facility's assigned quantity.
    """

    equipment_id = serializers.IntegerField(source="equipment.id", read_only=True)
    name = serializers.CharField(source="equipment.name", read_only=True)
    equipment_description = serializers.CharField(
        source="equipment.description", read_only=True
    )
    category = EquipmentCategorySerializer(source="equipment.category", read_only=True)
    unit = serializers.CharField(source="equipment.unit", read_only=True)
    condition = serializers.CharField(source="equipment.condition", read_only=True)
    condition_label = serializers.CharField(
        source="equipment.get_condition_display", read_only=True
    )
    equipment_status = serializers.CharField(source="equipment.status", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    quantity = serializers.IntegerField(source="effective_quantity", read_only=True)
    total_quantity = serializers.IntegerField(
        source="equipment.total_quantity", read_only=True
    )
    additional_fee = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    operator_fee = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    availability = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    class Meta:
        model = FacilityResource
        fields = (
            "id",
            "facility",
            "equipment_id",
            "name",
            "equipment_description",
            "category",
            "unit",
            "condition",
            "condition_label",
            "equipment_status",
            "status",
            "status_label",
            "quantity",
            "total_quantity",
            "description",
            "notes",
            "additional_fee",
            "operator_available",
            "operator_required",
            "operator_fee",
            "display_order",
            "is_active",
            "availability",
            "image",
            "images",
        )

    def _window(self):
        request = self.context.get("request")
        if request is None:
            return None, None, None
        params = request.query_params
        return params.get("date"), params.get("start"), params.get("end")

    def get_availability(self, obj):
        date_str, start, end = self._window()
        return facility_resource_availability(obj, date_str, start, end)

    def _gallery(self, equipment):
        gallery = list(equipment.equipment_images.all())
        if gallery:
            return EquipmentImageSerializer(
                gallery, many=True, context=self.context
            ).data
        legacy_url = _absolute_image_url(
            getattr(equipment, "image", None), self.context.get("request")
        )
        if not legacy_url:
            return []
        return [
            {
                "id": None,
                "url": legacy_url,
                "caption": "",
                "display_order": 0,
                "is_primary": True,
            }
        ]

    def get_images(self, obj):
        return self._gallery(obj.equipment)

    def get_image(self, obj):
        images = self._gallery(obj.equipment)
        if images:
            return images[0]["url"]
        return None


class FacilityResourceWriteSerializer(serializers.ModelSerializer):
    """Writable admin view of one facility <-> equipment assignment.

    The read serializer (:class:`FacilityResourceSerializer`) carries a lot of
    derived/display data for the reservation form; this one exposes only what
    an administrator configures. ``FacilityResourceViewSet`` still answers
    create/update with the read serializer, so the admin UI always receives
    the complete row.
    """

    class Meta:
        model = FacilityResource
        fields = (
            "id",
            "facility",
            "equipment",
            "quantity",
            "status",
            "additional_fee",
            "operator_available",
            "operator_required",
            "operator_fee",
            "description",
            "notes",
            "display_order",
            "is_active",
        )
        # Suppress DRF's generic unique-together message; ``validate`` below
        # explains exactly which item is already assigned to which facility.
        validators = []

    def validate(self, attrs):
        facility = attrs.get("facility") or getattr(self.instance, "facility", None)
        equipment = attrs.get("equipment") or getattr(self.instance, "equipment", None)
        if facility and equipment:
            clash = FacilityResource.objects.filter(
                facility=facility, equipment=equipment
            )
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {
                        "equipment": (
                            f"{equipment.name} is already assigned to "
                            f"{facility.name}. Edit that assignment instead."
                        )
                    }
                )

        # A required operator service must also be selectable, otherwise the
        # fee would be charged for a line the reservation form never shows.
        operator_required = attrs.get(
            "operator_required", getattr(self.instance, "operator_required", False)
        )
        if operator_required:
            attrs["operator_available"] = True
        return attrs


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
    equipment_types = serializers.IntegerField()
    total_units = serializers.IntegerField()
    available_units = serializers.IntegerField()
    reserved_units = serializers.IntegerField()
    under_maintenance_units = serializers.IntegerField()
    unavailable_units = serializers.IntegerField()
    damaged_records = serializers.IntegerField()


class EquipmentStatsViewMixin:
    """Shared stats computation for equipment endpoints."""

    def get_stats(self, request):
        return equipment_stats(request)