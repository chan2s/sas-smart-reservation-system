from rest_framework import serializers

from .models import Notification


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