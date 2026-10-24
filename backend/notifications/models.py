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


class PossibleNoShowAlert(models.Model):
    """Administrator-facing warning that an approved reservation looks unattended.

    One row per reservation (``OneToOneField``), so a scheduler run can never
    create a duplicate: the sweep updates the existing row instead. The alert is
    a WARNING only — it never changes the reservation status. Marking an actual
    no-show stays an explicit administrator action (``workflow.mark_no_show``).

    Lifecycle:

    * created when an APPROVED reservation with no check-in enters the warning
      window (``UPCOMING``) or passes its start time (``START_REACHED`` /
      ``NO_SHOW_RISK``);
    * ``stage`` is rewritten as time advances, and acknowledging is reset when
      the alert escalates so the more urgent state is unread again;
    * ``resolved_at`` is set once the reservation is no longer eligible (checked
      in, cancelled, rejected, completed, expired, marked no-show, or ended).
      Resolved rows are kept as history and are never shown as active.

    Notifications are in-app only: no email is sent, so an SMTP outage can never
    prevent an alert from being stored.
    """

    class Stage(models.TextChoices):
        #: Start time is within the warning window and nobody checked in yet.
        UPCOMING = "UPCOMING", "Starting soon"
        #: The scheduled start time has been reached without a check-in.
        START_REACHED = "START_REACHED", "Start time reached"
        #: Well past the start time with no check-in — investigate now.
        NO_SHOW_RISK = "NO_SHOW_RISK", "Possible no-show — action required"

    #: Escalation order used to decide whether an acknowledgement is reset.
    STAGE_ORDER = {
        "UPCOMING": 0,
        "START_REACHED": 1,
        "NO_SHOW_RISK": 2,
    }

    reservation = models.OneToOneField(
        "reservations.Reservation",
        on_delete=models.CASCADE,
        related_name="no_show_alert",
    )
    stage = models.CharField(max_length=20, choices=Stage.choices)
    detected_at = models.DateTimeField(
        help_text="When the alert was first created for this reservation."
    )
    stage_changed_at = models.DateTimeField(
        help_text="When ``stage`` last changed (equal to detected_at on creation)."
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_no_show_alerts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_reason = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["reservation__date", "reservation__start_time"]
        verbose_name = "possible no-show alert"
        verbose_name_plural = "possible no-show alerts"

    def __str__(self) -> str:
        reference = getattr(self.reservation, "reservation_id", self.reservation_id)
        return f"{reference}: {self.get_stage_display()}"

    @property
    def is_active(self) -> bool:
        return self.resolved_at is None

    @property
    def is_unread(self) -> bool:
        return self.resolved_at is None and self.acknowledged_at is None