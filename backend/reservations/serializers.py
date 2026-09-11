from django.contrib.auth import get_user_model
from rest_framework import serializers

from equipment.models import Equipment

from .models import InspectionReport, Reservation, ReservationEvent, ReservationItem
from .services.availability import check_availability

User = get_user_model()

# Public label map for organization types (also used by the public serializers
# module without importing account/user machinery).
ORGANIZATION_TYPE_LABELS = dict(Reservation.OrganizationType.choices)

REQUESTER_TYPE_LABELS = dict(Reservation.RequesterType.choices)


class ReservationItemSerializer(serializers.ModelSerializer):
    equipment_id = serializers.IntegerField(source="equipment.id", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    category = serializers.CharField(source="equipment.category.name", read_only=True)
    condition = serializers.CharField(source="equipment.condition", read_only=True)

    class Meta:
        model = ReservationItem
        fields = (
            "id",
            "equipment",
            "equipment_id",
            "equipment_name",
            "category",
            "condition",
            "quantity",
            "returned",
        )


class ReservationEventSerializer(serializers.ModelSerializer):
    event_type_label = serializers.CharField(source="get_event_type_display", read_only=True)
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ReservationEvent
        fields = (
            "id",
            "event_type",
            "event_type_label",
            "actor",
            "actor_name",
            "from_status",
            "to_status",
            "message",
            "created_at",
        )

    def get_actor_name(self, obj):
        # actor is nullable; external-submitted reservations have no account.
        return obj.actor.display_name if obj.actor else "Requester"


class InspectionReportSerializer(serializers.ModelSerializer):
    facility_condition_label = serializers.CharField(source="get_facility_condition_display", read_only=True)
    reported_by_name = serializers.CharField(source="reported_by.display_name", read_only=True, default="")

    class Meta:
        model = InspectionReport
        fields = (
            "id",
            "facility_condition",
            "facility_condition_label",
            "equipment_returned",
            "missing_items",
            "notes",
            "photo",
            "reported_by_name",
            "created_at",
        )


def _requester_fields(obj):
    """Requester identity resolved for campus and external reservations alike."""
    if obj.requester_type == Reservation.RequesterType.EXTERNAL:
        return {
            "requester": obj.organization or obj.contact_person or "External Requester",
            "requester_type": obj.requester_type,
            "requester_type_label": obj.get_requester_type_display(),
            "organization": obj.organization,
            "organization_type": obj.organization_type,
            "organization_type_label": obj.get_organization_type_display(),
            "contact_person": obj.contact_person,
            "contact_email": obj.contact_email,
        }
    return {
        "requester": obj.requester.display_name if obj.requester else "—",
        "requester_type": obj.requester_type,
        "requester_type_label": obj.get_requester_type_display(),
        "organization": obj.organization,
        "organization_type": "",
        "organization_type_label": "",
        "contact_person": obj.contact_person,
        "contact_email": obj.requester.email if obj.requester else "",
    }


class ReservationListSerializer(serializers.ModelSerializer):
    facility = serializers.CharField(source="facility.name", read_only=True)
    facility_id = serializers.IntegerField(source="facility.id", read_only=True)
    facility_type = serializers.CharField(source="facility.facility_type", read_only=True)
    requester = serializers.CharField(source="requester_display_name", read_only=True)
    requester_type = serializers.CharField(read_only=True)
    requester_type_label = serializers.CharField(read_only=True)
    organization_type = serializers.CharField(read_only=True)
    organization_type_label = serializers.CharField(read_only=True)
    contact_email = serializers.CharField(read_only=True)
    created_by_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    event_type_label = serializers.CharField(source="get_event_type_display", read_only=True)
    resources = serializers.SerializerMethodField()
    check_in_open_time = serializers.SerializerMethodField()
    check_in_window_open = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = (
            "id",
            "reservation_id",
            "event_name",
            "event_type",
            "event_type_label",
            "requester",
            "requester_type",
            "requester_type_label",
            "organization",
            "organization_type",
            "organization_type_label",
            "contact_person",
            "contact_email",
            "created_by_name",
            "expected_participants",
            "special_requirements",
            "facility",
            "facility_id",
            "facility_type",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_label",
            "check_in_open_time",
            "check_in_window_open",
            "checked_in_at",
            "checked_out_at",
            "resources",
            "created_at",
        )

    def get_created_by_name(self, obj):
        # "Who entered this?" is distinct from "who is it for?".
        if not obj.created_by:
            return ""
        if obj.created_by == obj.requester:
            return obj.created_by.display_name
        return f"{obj.created_by.display_name} (on behalf)"

    def get_resources(self, obj):
        return [f"{item.quantity}× {item.equipment.name}" for item in obj.items.all()]

    def get_check_in_open_time(self, obj):
        return obj.check_in_open_time.isoformat()

    def get_check_in_window_open(self, obj):
        from django.utils import timezone

        return timezone.now() >= obj.check_in_open_time

    def to_representation(self, instance):
        """Drop contact details for non-staff viewers of campus reservations.

        Staff need external contact details to coordinate events; requesters
        only ever see their own reservations, so their own fields are fine.
        Campus users listing reservations (their own) keep their data too.
        """
        data = super().to_representation(instance)
        request = self.context.get("request")
        is_staff = bool(request and request.user.is_authenticated and request.user.is_sas_staff)
        is_own = bool(
            request
            and request.user.is_authenticated
            and instance.requester_id == request.user.id
        )
        if not (is_staff or is_own):
            data["contact_email"] = ""
        return data


class ReservationDetailSerializer(ReservationListSerializer):
    description = serializers.CharField(read_only=True)
    purpose = serializers.CharField(read_only=True)
    notes = serializers.CharField(read_only=True)
    rejection_reason = serializers.CharField(read_only=True)
    checkin_code = serializers.UUIDField(read_only=True)
    early_check_in_override = serializers.BooleanField(read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    approved_at = serializers.DateTimeField(read_only=True)
    items = ReservationItemSerializer(many=True, read_only=True)
    events = ReservationEventSerializer(many=True, read_only=True)
    inspection = InspectionReportSerializer(read_only=True)
    availability = serializers.SerializerMethodField()

    class Meta(ReservationListSerializer.Meta):
        fields = ReservationListSerializer.Meta.fields + (
            "description",
            "purpose",
            "notes",
            "rejection_reason",
            "checkin_code",
            "early_check_in_override",
            "approved_by_name",
            "approved_at",
            "items",
            "events",
            "inspection",
            "availability",
        )

    def get_approved_by_name(self, obj):
        return obj.approved_by.display_name if obj.approved_by else ""

    def get_availability(self, obj):
        """Availability snapshot around this reservation's own window."""
        report = check_availability(
            obj.facility_id,
            obj.date,
            obj.start_time,
            obj.end_time,
            [
                {"equipment_id": item.equipment_id, "quantity": item.quantity}
                for item in obj.items.all()
            ],
            exclude_id=obj.id,
        )
        return {
            "ok": report["overall"]["ok"],
            "facility": report["facility"],
            "items": report["items"],
            "problems": report["problems"],
        }


class _ReservationCreateMixin:
    """Shared validation for authenticated and guest reservation creation.

    Event details drive the resource recommendation step, so they are required
    before a reservation can be created. Availability is checked against the
    requested window and the structured report is stashed so the view can
    surface it for conflict UI (HTTP 409).
    """

    def validate(self, attrs):
        from django.utils import timezone

        facility_id = attrs["facility_id"]
        target_date = attrs["date"]
        start = attrs["start_time"]
        end = attrs["end_time"]

        if end <= start:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        if target_date < timezone.localdate():
            raise serializers.ValidationError({"date": "Date cannot be in the past."})

        if not attrs.get("event_name", "").strip():
            raise serializers.ValidationError({"event_name": "Event name is required."})
        if not attrs.get("event_type"):
            raise serializers.ValidationError({"event_type": "Event type is required."})
        if not attrs.get("purpose", "").strip():
            raise serializers.ValidationError({"purpose": "Event purpose is required."})
        if (attrs.get("expected_participants") or 0) < 1:
            raise serializers.ValidationError(
                {"expected_participants": "Expected participants must be at least 1."}
            )

        # Item quantities are never trusted from the client: they must be
        # positive integers referencing active equipment. The availability
        # check below additionally rejects requests beyond what the window
        # can actually supply (409), so a forged "quantity: 99999" cannot
        # slip through by manipulating the recommendation prefill.
        for item in attrs.get("items", []):
            try:
                quantity = int(item.get("quantity", 1))
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    {"items": "Quantities must be whole numbers."}
                )
            if quantity < 1:
                raise serializers.ValidationError(
                    {"items": "Quantities must be at least 1."}
                )
            equipment_id = item.get("equipment_id")
            if not equipment_id or not Equipment.objects.filter(
                pk=equipment_id, is_active=True
            ).exists():
                raise serializers.ValidationError(
                    {"items": "One of the requested resources is not available for reservation."}
                )
            item["quantity"] = quantity

        report = check_availability(
            facility_id, target_date, start, end, attrs.get("items", [])
        )
        self._availability_report = report
        attrs["_availability_report"] = report
        if not report["overall"]["ok"]:
            raise serializers.ValidationError(
                {"availability": report}, code="conflict"
            )
        return attrs


class ReservationCreateSerializer(_ReservationCreateMixin, serializers.ModelSerializer):
    """Authenticated creation.

    The requester defaults to the signed-in user. Administrators may create on
    behalf of someone else (``requester_id``) or an external organization
    (``requester_type: EXTERNAL`` + contact fields). A client-supplied status
    is never accepted — the view/workflow decides approval.
    """

    items = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False
    )
    facility_id = serializers.IntegerField(write_only=True)
    requester_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )
    requester_type = serializers.ChoiceField(
        choices=Reservation.RequesterType.choices,
        required=False,
    )
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    organization_type = serializers.ChoiceField(
        choices=Reservation.OrganizationType.choices,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = Reservation
        fields = (
            "facility_id",
            "date",
            "start_time",
            "end_time",
            "event_name",
            "event_type",
            "organization",
            "organization_type",
            "purpose",
            "description",
            "expected_participants",
            "contact_person",
            "contact_email",
            "special_requirements",
            "notes",
            "items",
            "requester_id",
            "requester_type",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        requester_type = attrs.get("requester_type", Reservation.RequesterType.CAMPUS)

        if requester_type == Reservation.RequesterType.EXTERNAL:
            # Reservation on behalf of an organization without an account.
            # Restricted to staff on the authenticated endpoint — external
            # requesters themselves use the public guest endpoint.
            if not (user and user.is_authenticated and user.is_sas_staff):
                raise serializers.ValidationError(
                    {
                        "requester_type": (
                            "Only SAS staff can create external reservations here. "
                            "External requesters should use the public reservation page."
                        )
                    }
                )
            if not (attrs.get("organization") or "").strip():
                raise serializers.ValidationError(
                    {"organization": "Organization name is required for external reservations."}
                )
            if not (attrs.get("contact_person") or "").strip():
                raise serializers.ValidationError(
                    {"contact_person": "Contact person is required for external reservations."}
                )
            if not (attrs.get("contact_email") or "").strip():
                raise serializers.ValidationError(
                    {"contact_email": "Email address is required for external reservations."}
                )
            attrs.pop("requester_id", None)
        else:
            # Campus requester: defaults to the current user; staff may pick
            # another campus user to reserve on their behalf.
            requester_id = attrs.pop("requester_id", None)
            if requester_id:
                if not (user and user.is_sas_staff):
                    raise serializers.ValidationError(
                        {"requester_id": "Only SAS staff can create reservations for other users."}
                    )
                try:
                    target = User.objects.get(pk=requester_id)
                except User.DoesNotExist:
                    raise serializers.ValidationError(
                        {"requester_id": "Requested campus user not found."}
                    )
                attrs["_on_behalf_of"] = target
            else:
                if user is None or not user.is_authenticated:
                    raise serializers.ValidationError(
                        {"requester_id": "Authentication is required for campus reservations."}
                    )
        return attrs

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        facility_id = validated_data.pop("facility_id")
        validated_data.pop("_availability_report", None)  # validation artifact
        on_behalf_of = validated_data.pop("_on_behalf_of", None)
        requester_type = validated_data.pop(
            "requester_type", Reservation.RequesterType.CAMPUS
        )
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        # For campus reservations, use the user's email if not provided
        contact_email = validated_data.get("contact_email", "")
        if not contact_email and user and user.is_authenticated:
            contact_email = user.email
            validated_data["contact_email"] = contact_email

        reservation = Reservation.objects.create(
            **validated_data,
            facility_id=facility_id,
            requester=(
                on_behalf_of
                if on_behalf_of is not None
                else (
                    user
                    if user
                    and user.is_authenticated
                    and requester_type == Reservation.RequesterType.CAMPUS
                    else None
                )
            ),
            requester_type=requester_type,
            created_by=user if user and user.is_authenticated else None,
        )
        for item in items:
            ReservationItem.objects.create(
                reservation=reservation,
                equipment_id=item["equipment_id"],
                quantity=item.get("quantity", 1),
            )
        return reservation


class GuestReservationCreateSerializer(_ReservationCreateMixin, serializers.ModelSerializer):
    """Public reservation submission for external requesters (no account).

    Always creates an EXTERNAL reservation with the requester's contact
    details; the reservation enters the normal pending review queue.
    """

    items = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False
    )
    facility_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Reservation
        fields = (
            "facility_id",
            "date",
            "start_time",
            "end_time",
            "event_name",
            "event_type",
            "organization",
            "organization_type",
            "purpose",
            "description",
            "expected_participants",
            "contact_person",
            "contact_email",
            "special_requirements",
            "items",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # External reservations are always requester_type EXTERNAL and require
        # full contact details for tracking + coordination.
        attrs["requester_type"] = Reservation.RequesterType.EXTERNAL
        for field, label in (
            ("organization", "Organization / school name"),
            ("contact_person", "Contact person"),
            ("contact_email", "Email address"),
        ):
            if not (attrs.get(field) or "").strip():
                raise serializers.ValidationError({field: f"{label} is required."})
        if not attrs.get("organization_type"):
            # Optional but recommended; default sensibly instead of failing.
            attrs["organization_type"] = Reservation.OrganizationType.OTHER
        return attrs

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        facility_id = validated_data.pop("facility_id")
        validated_data.pop("_availability_report", None)
        validated_data.pop("requester_type", None)
        reservation = Reservation.objects.create(
            **validated_data,
            facility_id=facility_id,
            requester=None,  # external requesters have no account
            requester_type=Reservation.RequesterType.EXTERNAL,
        )
        for item in items:
            ReservationItem.objects.create(
                reservation=reservation,
                equipment_id=item["equipment_id"],
                quantity=item.get("quantity", 1),
            )
        return reservation


# ---------------------------------------------------------------------------
# Public (unauthenticated) payloads — deliberately minimal, never leaking
# other reservations or internal data.
# ---------------------------------------------------------------------------


class PublicTrackSerializer(serializers.Serializer):
    """Limited reservation view returned by the public tracking endpoint.

    Contains only what the requester already knows (their own contact details,
    event, schedule, resources, status) — never other reservations' data,
    internal notes, approval history, or check-in codes.
    """

    reservation_id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    status_label = serializers.CharField(read_only=True)
    event_name = serializers.CharField(read_only=True)
    event_type_label = serializers.CharField(read_only=True)
    organization = serializers.CharField(read_only=True)
    organization_type_label = serializers.CharField(read_only=True, default="")
    contact_person = serializers.CharField(read_only=True)
    contact_email = serializers.EmailField(read_only=True)
    facility = serializers.CharField(read_only=True)
    facility_id = serializers.IntegerField(read_only=True)
    date = serializers.DateField(read_only=True)
    start_time = serializers.TimeField(read_only=True)
    end_time = serializers.TimeField(read_only=True)
    expected_participants = serializers.IntegerField(read_only=True)
    purpose = serializers.CharField(read_only=True)
    resources = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def get_resources(self, obj):
        return [f"{item.quantity}× {item.equipment.name}" for item in obj.items.all()]
