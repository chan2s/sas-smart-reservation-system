from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import AuditLog
from accounts.permissions import IsSasStaffOrReadOnly

from .models import Facility, FacilityImage
from .serializers import (
    MAX_IMAGES_PER_UPLOAD,
    FacilityImageSerializer,
    FacilitySerializer,
    validate_facility_image,
)


class FacilityViewSet(viewsets.ModelViewSet):
    queryset = (
        Facility.objects.prefetch_related("operating_hours", "images").all()
    )
    serializer_class = FacilitySerializer
    permission_classes = [IsSasStaffOrReadOnly]
    pagination_class = None
    search_fields = ("name", "location", "description")
    filterset_fields = ("facility_type", "status", "is_active")

    def get_queryset(self):
        qs = super().get_queryset()
        facility_type = self.request.query_params.get("type")
        if facility_type:
            qs = qs.filter(facility_type=facility_type)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    # ------------------------------------------------------------------
    # Image gallery
    # ------------------------------------------------------------------

    @staticmethod
    def _gallery(facility):
        """The gallery as it is stored right now.

        Deliberately a fresh query rather than ``facility.images``: the
        facility queryset is prefetched, so the related manager would return
        rows cached before this request's mutations (deleted images included)
        and every gallery response would be one step behind.
        """
        return FacilityImage.objects.filter(facility=facility)

    def _gallery_response(self, facility, images=None, status_code=status.HTTP_200_OK):
        """Serialize a gallery (or a subset of it) as ``{"images": [...]}``."""
        payload = self._gallery(facility) if images is None else images
        data = FacilityImageSerializer(
            payload, many=True, context={"request": self.request}
        ).data
        return Response({"images": data}, status=status_code)

    def _ensure_primary(self, facility):
        """Keep exactly one primary image whenever the gallery is non-empty."""
        gallery = self._gallery(facility)
        if gallery.filter(is_primary=True).exists():
            return
        promoted = gallery.first()
        if promoted is not None:
            promoted.is_primary = True
            promoted.save(update_fields=["is_primary"])

    def _adopt_legacy_image(self, facility):
        """Move a legacy single image into the gallery.

        Returns the new gallery entry, or None when there is nothing to adopt
        (no legacy image, or the gallery already has images). Keeping this in
        the gallery keeps the API response complete for records whose image was
        set through the legacy field after the backfill migration ran.
        """
        if self._gallery(facility).exists() or not facility.image:
            return None
        return FacilityImage.objects.create(
            facility=facility,
            # Same stored file: a reference, never a copy.
            image=facility.image.name,
            order=0,
            is_primary=True,
        )

    def _log_image_change(self, facility, detail):
        AuditLog.record(
            self.request.user,
            AuditLog.Action.FACILITY_IMAGE,
            object_type="facility",
            object_id=facility.id,
            object_repr=facility.name,
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
        facility = self.get_object()

        if request.method == "GET":
            return self._gallery_response(facility)

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
                validate_facility_image(file)
            except serializers.ValidationError as exc:
                label = f"Image {index}" if len(files) > 1 else "Image"
                messages = " ".join(str(item) for item in exc.detail)
                errors.append(f"{label}: {messages}")
        if errors:
            return Response({"images": errors}, status=status.HTTP_400_BAD_REQUEST)

        self._adopt_legacy_image(facility)

        gallery = self._gallery(facility)
        last_order = gallery.order_by("-order").values_list("order", flat=True).first()
        next_order = 0 if last_order is None else last_order + 1
        has_primary = gallery.filter(is_primary=True).exists()

        with transaction.atomic():
            created = [
                FacilityImage.objects.create(
                    facility=facility,
                    image=file,
                    order=next_order + offset,
                    # The very first image of a gallery becomes its primary one.
                    is_primary=not has_primary and offset == 0,
                )
                for offset, file in enumerate(files)
            ]

        self._log_image_change(facility, f"Added {len(created)} gallery image(s)")
        return self._gallery_response(
            facility, images=created, status_code=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_id>\d+)")
    def delete_image(self, request, pk=None, image_id=None):
        """Remove one gallery image (staff only) and clean up its stored file."""
        facility = self.get_object()
        image = get_object_or_404(facility.images, pk=image_id)
        stored_name = image.image.name
        storage = image.image.storage

        with transaction.atomic():
            image.delete()

            # The gallery owns the file now. Delete it only once nothing else
            # references the same stored name, and clear the legacy single
            # image field when it mirrored this picture — otherwise the
            # backward-compatibility fallback would resurrect a deleted image.
            gallery = self._gallery(facility)
            if stored_name and not gallery.filter(image=stored_name).exists():
                if facility.image and facility.image.name == stored_name:
                    facility.image = None
                    facility.save(update_fields=["image", "updated_at"])
                storage.delete(stored_name)

            # Emptying the gallery is an explicit "this facility has no images"
            # action, so a legacy image must not resurface through the
            # backward-compatibility fallback.
            if not gallery.exists() and facility.image:
                legacy_name = facility.image.name
                legacy_storage = facility.image.storage
                facility.image = None
                facility.save(update_fields=["image", "updated_at"])
                if legacy_name and legacy_name != stored_name:
                    legacy_storage.delete(legacy_name)

            self._ensure_primary(facility)

        self._log_image_change(facility, "Removed a gallery image")
        return self._gallery_response(facility)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"images/(?P<image_id>\d+)/primary",
    )
    def set_primary_image(self, request, pk=None, image_id=None):
        """Make one gallery image the primary one (staff only)."""
        facility = self.get_object()
        image = get_object_or_404(facility.images, pk=image_id)

        with transaction.atomic():
            facility.images.exclude(pk=image.pk).update(is_primary=False)
            image.is_primary = True
            image.save(update_fields=["is_primary"])

        self._log_image_change(facility, "Changed the primary gallery image")
        return self._gallery_response(facility)

    @action(detail=True, methods=["post"], url_path="images/order")
    def reorder_images(self, request, pk=None):
        """Reorder the gallery. Body: ``{"order": [image_id, ...]}`` (staff only).

        The list must contain every current gallery image id exactly once.
        Missing ids are rejected rather than silently reordered, so a stale
        client can never scramble the gallery.
        """
        facility = self.get_object()
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

        existing_ids = set(self._gallery(facility).values_list("id", flat=True))
        if len(order) != len(set(order)) or set(order) != existing_ids:
            return Response(
                {"order": ["Send every gallery image id exactly once."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for position, image_id in enumerate(order):
                FacilityImage.objects.filter(pk=image_id).update(order=position)

        self._log_image_change(facility, "Reordered the gallery images")
        return self._gallery_response(facility)
