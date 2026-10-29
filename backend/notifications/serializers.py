from rest_framework import serializers

from notifications import no_show_alerts
from reservations.models import Reservation

from .models import Notification, PossibleNoShowAlert


class NotificationSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id",
            "type",
            "type_label",
            "title",
            "message",
            "link",
            "read",
            "created_at",
            "time_ago",
        )

    def get_time_ago(self, obj):
        from django.utils import timesince

        return timesince.timesince(obj.created_at)


class PossibleNoShowAlertSerializer(serializers.ModelSerializer):
    """Everything the bell and dashboard need, so they never recompute policy.

    Stage, minutes and the human label come from the backend; the frontend only
    renders them. ``no_check_in_label`` states the fact ("No check-in
    recorded") rather than asserting that the requester is absent.
    """

    reservation = serializers.PrimaryKeyRelatedField(read_only=True)
    reference = serializers.CharField(source="reservation.reservation_id", read_only=True)
    event_name = serializers.CharField(source="reservation.event_name", read_only=True)
    facility = serializers.CharField(source="reservation.facility.name", read_only=True)
    facility_id = serializers.IntegerField(source="reservation.facility_id", read_only=True)
    requester = serializers.SerializerMethodField()
    requester_id = serializers.IntegerField(
        source="reservation.requester_id", read_only=True
    )
    date = serializers.DateField(source="reservation.date", read_only=True)
    start_time = serializers.TimeField(source="reservation.start_time", read_only=True)
    end_time = serializers.TimeField(source="reservation.end_time", read_only=True)
    status = serializers.CharField(source="reservation.status", read_only=True)
    status_label = serializers.CharField(
        source="reservation.get_status_display", read_only=True
    )
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    acknowledged = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()
    minutes_until_start = serializers.SerializerMethodField()
    minutes_since_start = serializers.SerializerMethodField()
    time_label = serializers.SerializerMethodField()
    no_check_in_label = serializers.SerializerMethodField()

    class Meta:
        model = PossibleNoShowAlert
        fields = (
            "id",
            "reservation",
            "reference",
            "event_name",
            "facility",
            "facility_id",
            "requester",
            "requester_id",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_label",
            "stage",
            "stage_label",
            "acknowledged",
            "acknowledged_at",
            "detected_at",
            "stage_changed_at",
            "updated_at",
            "link",
            "minutes_until_start",
            "minutes_since_start",
            "time_label",
            "no_check_in_label",
        )

    def get_requester(self, obj):
        requester = obj.reservation.requester
        if requester is None:
            # Staff-entered external reservations have no account.
            return obj.reservation.contact_person or obj.reservation.organization or ""
        return getattr(requester, "display_name", "") or requester.get_username()

    def get_acknowledged(self, obj):
        return obj.acknowledged_at is not None

    def get_link(self, obj):
        return f"/reservations/{obj.reservation_id}"

    def _timing(self, obj):
        # Cached on the instance for the duration of this serialization pass, so
        # every timing field agrees on the same "now".
        cached = getattr(obj, "_timing_cache", None)
        if cached is None:
            cached = no_show_alerts.timing(obj.reservation)
            obj._timing_cache = cached
        return cached

    def get_minutes_until_start(self, obj):
        return self._timing(obj)["minutes_until_start"]

    def get_minutes_since_start(self, obj):
        return self._timing(obj)["minutes_since_start"]

    def get_time_label(self, obj):
        return self._timing(obj)["time_label"]

    def get_no_check_in_label(self, obj):
        return self._timing(obj)["no_check_in_label"]


class AwaitingNoShowReviewSerializer(serializers.ModelSerializer):
    """An overdue reservation an administrator has not yet judged.

    Deliberately reports the facts (scheduled slot, requester, facility,
    "no check-in recorded") and the backend-computed ``can_mark_no_show`` flag.
    The dashboard links to the reservation detail page, where the existing
    administrator action performs the status change; this serializer never
    changes anything.
    """

    reservation = serializers.IntegerField(source="id", read_only=True)
    reference = serializers.CharField(source="reservation_id", read_only=True)
    facility = serializers.CharField(source="facility.name", read_only=True)
    facility_id = serializers.IntegerField(read_only=True)
    requester = serializers.SerializerMethodField()
    requester_id = serializers.IntegerField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    link = serializers.SerializerMethodField()
    time_label = serializers.SerializerMethodField()
    minutes_since_end = serializers.SerializerMethodField()
    no_check_in_label = serializers.SerializerMethodField()
    can_mark_no_show = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = (
            "reservation",
            "reference",
            "event_name",
            "facility",
            "facility_id",
            "requester",
            "requester_id",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_label",
            "link",
            "time_label",
            "minutes_since_end",
            "no_check_in_label",
            "can_mark_no_show",
        )

    def get_requester(self, obj):
        return obj.requester_display_name

    def get_link(self, obj):
        return f"/reservations/{obj.pk}"

    def _timing(self, obj):
        cached = getattr(obj, "_review_timing_cache", None)
        if cached is None:
            cached = no_show_alerts.review_timing(obj)
            obj._review_timing_cache = cached
        return cached

    def get_time_label(self, obj):
        return self._timing(obj)["time_label"]

    def get_minutes_since_end(self, obj):
        return self._timing(obj)["minutes_since_end"]

    def get_no_check_in_label(self, obj):
        return "No check-in recorded"

    def get_can_mark_no_show(self, obj):
        # Imported lazily to keep this module independent of the reservation
        # workflow module at import time.
        from reservations.services import workflow

        request = self.context.get("request")
        user = getattr(request, "user", None)
        allowed, _code, _reason = workflow.no_show_eligibility(obj, user)
        return allowed
