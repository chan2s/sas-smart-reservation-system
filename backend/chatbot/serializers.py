from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        max_length=1000, trim_whitespace=True, allow_blank=False
    )
