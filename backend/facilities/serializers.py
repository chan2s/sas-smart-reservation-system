from rest_framework import serializers

from .models import Facility, FacilityImage, OperatingHour
from .services import facility_availability_summary

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

#: Most files a single gallery upload request may carry.
MAX_IMAGES_PER_UPLOAD = 20


def validate_facility_image(value):
    """Validate one uploaded facility image.

    The single shared validator for every image entry point (the legacy
    ``Facility.image`` field and the gallery upload endpoint), so both paths
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


class OperatingHourSerializer(serializers.ModelSerializer):
    day_label = serializers.SerializerMethodField()
    is_closed = serializers.BooleanField(read_only=True)

    class Meta:
        model = OperatingHour
        fields = ("id", "day_of_week", "day_label", "open_time", "close_time", "is_closed")

    def get_day_label(self, obj):
        return obj.day_label if hasattr(obj, "day_label") else OperatingHour.Day(obj.day_of_week).label


class FacilityImageSerializer(serializers.ModelSerializer):
    """One gallery image, as the frontend consumes it."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = FacilityImage
        fields = ("id", "url", "is_primary", "order")

    def get_url(self, obj):
        return _absolute_image_url(obj.image, self.context.get("request"))


class FacilitySerializer(serializers.ModelSerializer):
    facility_type_label = serializers.CharField(source="get_facility_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    availability = serializers.SerializerMethodField()
    # Operating hours are needed by facility cards and the reservation wizard
    # (to build valid time-slot options), so they ship with the list payload.
    operating_hours = OperatingHourSerializer(many=True, read_only=True)
    image = serializers.ImageField(required=False, allow_null=True)
    images = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = (
            "id",
            "name",
            "facility_type",
            "facility_type_label",
            "description",
            "capacity",
            "location",
            "image",
            "images",
            "rules",
            "status",
            "status_label",
            "is_active",
            "availability",
            "operating_hours",
        )
        read_only_fields = ("availability", "operating_hours", "images")

    def get_images(self, obj):
        """The gallery, ordered by the model's ordering.

        Backward compatibility: a facility whose only picture lives in the
        legacy single-image field is exposed as a one-entry gallery (with a
        null id, because there is no gallery row to act on) instead of
        returning an empty collection. The frontend never has to special-case
        old records, and an empty list always means "no images at all".
        """
        gallery = list(obj.images.all())
        if gallery:
            return FacilityImageSerializer(gallery, many=True, context=self.context).data

        legacy_url = _absolute_image_url(getattr(obj, "image", None), self.context.get("request"))
        if not legacy_url:
            return []
        return [
            {
                "id": None,
                "url": legacy_url,
                "is_primary": True,
                "order": 0,
            }
        ]

    def validate_image(self, value):
        """Validate the legacy single-image field.

        Accepts JPG, PNG, or WEBP up to 5 MB and verifies the bytes with
        Pillow, so a renamed non-image file gets a clear error instead of a
        generic Django failure.
        """
        return validate_facility_image(value)

    def get_availability(self, obj):
        request = self.context.get("request")
        date = request.query_params.get("date") if request else None
        return facility_availability_summary(obj, date)
