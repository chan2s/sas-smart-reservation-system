from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        RESERVATION = "RESERVATION", "Reservation"
        EQUIPMENT = "EQUIPMENT", "Equipment"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.RESERVATION)
    title = models.CharField(max_length=160)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title