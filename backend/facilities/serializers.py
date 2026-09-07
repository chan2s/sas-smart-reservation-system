from rest_framework import serializers

from .models import Facility, OperatingHour
from .services import facility_availability_summary


class OperatingHourSerializer(serializers.ModelSerializer):
    day_label = serializers.SerializerMethodField()
    is_closed = serializers.BooleanField(read_only=True)

    class Meta:
        model = OperatingHour
        fields = ("id", "day_of_week", "day_label", "open_time", "close_time", "is_closed")

    def get_day_label(self, obj):
        return obj.day_label if hasattr(obj, "day_label") else OperatingHour.Day(obj.day_of_week).label


class FacilitySerializer(serializers.ModelSerializer):
    facility_type_label = serializers.CharField(source="get_facility_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    availability = serializers.SerializerMethodField()
    # Operating hours are needed by facility cards and the reservation wizard
    # (to build valid time-slot options), so they ship with the list payload.
    operating_hours = OperatingHourSerializer(many=True, read_only=True)

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
            "rules",
            "status",
            "status_label",
            "is_active",
            "availability",
            "operating_hours",
        )
        read_only_fields = ("availability", "operating_hours")

    def get_availability(self, obj):
        request = self.context.get("request")
        date = request.query_params.get("date") if request else None
        return facility_availability_summary(obj, date)


