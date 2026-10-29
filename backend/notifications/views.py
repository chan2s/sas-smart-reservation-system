import logging

from django.utils import timesince
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsSasStaff

from . import no_show_alerts as alerts_service
from .models import Notification, PossibleNoShowAlert
from .serializers import (
    AwaitingNoShowReviewSerializer,
    NotificationSerializer,
    PossibleNoShowAlertSerializer,
)

logger = logging.getLogger(__name__)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    search_fields = ("title", "message")

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        unread_only = self.request.query_params.get("unread") == "true"
        if unread_only:
            qs = qs.filter(read=False)
        return qs

    def list(self, request, *args, **kwargs):
        """Return the administrator's unified feed, including active alerts.

        Requesters keep their existing user-scoped notification response.
        Staff receive persisted notifications plus active possible-no-show
        records from the same source used by the dashboard.
        """
        if not getattr(request.user, "is_sas_staff", False):
            return super().list(request, *args, **kwargs)

        # Alert evaluation is idempotent. Let a database failure reach the API
        # error handler so the UI can show an error instead of a false empty feed.
        alerts_service.refresh_alerts()

        items = []
        notifications = self.filter_queryset(self.get_queryset()).order_by("-created_at")
        for notification in notifications:
            row = dict(NotificationSerializer(notification).data)
            row["source"] = "notification"
            items.append((notification.created_at, row))

        for alert in alerts_service.active_alerts():
            stage_label = alert.get_stage_display()
            reservation = alert.reservation
            alert_data = PossibleNoShowAlertSerializer(alert).data
            row = {
                "id": alert.pk,
                "source": "possible_no_show",
                "type": Notification.Type.RESERVATION,
                "type_label": "Possible no-show",
                "title": f"{stage_label}: {reservation.reservation_id}",
                "message": (
                    f"{reservation.event_name} at {reservation.facility.name}; "
                    f"requester: {alert_data['requester'] or 'Unknown'}; "
                    f"{alert_data['time_label']}. No check-in recorded."
                ),
                "link": alert_data["link"],
                "read": not alert.is_unread,
                "created_at": alert.stage_changed_at,
                "time_ago": timesince.timesince(alert.stage_changed_at),
                "stage": alert.stage,
                "stage_label": stage_label,
                "reference": reservation.reservation_id,
                "event_name": reservation.event_name,
                "facility": reservation.facility.name,
                "requester": alert_data["requester"],
                "date": alert_data["date"],
                "start_time": alert_data["start_time"],
                "time_label": alert_data["time_label"],
                "no_check_in_label": alert_data["no_check_in_label"],
            }
            if request.query_params.get("unread") != "true" or not row["read"]:
                items.append((alert.stage_changed_at, row))

        if request.query_params.get("unread") == "true":
            items = [(created_at, row) for created_at, row in items if not row["read"]]

        # Unread first; newest first within both read groups.
        items.sort(key=lambda item: (item[1]["read"], -item[0].timestamp()))
        rows = [row for _, row in items]
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(rows)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Badge count: the user's unread notifications (+ staff alerts).

        For administrators the possible-no-show alerts are counted too, because
        the badge is the only always-visible entry point to them. The sweep runs
        here so the badge — and therefore the dashboard — reflects reservations
        that are already inside the warning window, without waiting for cron.
        """
        count = Notification.objects.filter(user=request.user, read=False).count()
        alert_count = 0
        if getattr(request.user, "is_sas_staff", False):
            alerts_service.refresh_alerts()
            alert_count = alerts_service.unread_count()
        return Response(
            {
                "count": count + alert_count,
                "notifications": count,
                "alerts": alert_count,
            }
        )

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        if getattr(request.user, "is_sas_staff", False):
            alerts_service.acknowledge_all(request.user)
        return Response({"count": 0})

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.read = True
        notification.save(update_fields=["read"])
        return Response(NotificationSerializer(notification).data)


# ---------------------------------------------------------------------------
# Possible no-show alerts (administrator only)
# ---------------------------------------------------------------------------
# Deliberately NOT exposed through the NotificationViewSet: these are shared,
# reservation-scoped records rather than per-user messages, and every endpoint
# must be denied to requesters at the API level — not merely hidden in the UI.


@api_view(["GET"])
@permission_classes([IsSasStaff])
def no_show_alert_list(request):
    """Active possible-no-show alerts plus overdue reservations to review.

    Two distinct groups, never merged: ``results`` are reservations inside the
    existing no-show warning window, while ``awaiting_review`` are reservations
    whose scheduled end time has already passed and that nobody has checked in,
    completed, cancelled, or marked ``NO_SHOW``. The latter are review prompts
    only — listing them never changes their status. ``awaiting_review`` already
    excludes any reservation that appears in ``results``, so no reservation is
    shown twice.
    """
    try:
        alerts_service.refresh_alerts()
    except Exception:  # noqa: BLE001 — serve what is already persisted
        logger.exception("Possible no-show refresh failed while listing alerts.")

    alerts = list(alerts_service.active_alerts())
    payload = PossibleNoShowAlertSerializer(alerts, many=True).data
    review = list(alerts_service.awaiting_review())
    review_payload = AwaitingNoShowReviewSerializer(
        review, many=True, context={"request": request}
    ).data
    return Response(
        {
            "count": len(payload),
            "unread": sum(1 for alert in alerts if alert.is_unread),
            "results": payload,
            "review_count": len(review_payload),
            "awaiting_review": review_payload,
        }
    )


@api_view(["POST"])
@permission_classes([IsSasStaff])
def no_show_alert_acknowledge(request, alert_id):
    """Mark one active alert as read."""
    alert = get_object_or_404(PossibleNoShowAlert, pk=alert_id, resolved_at__isnull=True)
    alerts_service.acknowledge(alert, request.user)
    return Response(PossibleNoShowAlertSerializer(alert).data)


@api_view(["POST"])
@permission_classes([IsSasStaff])
def no_show_alert_acknowledge_all(request):
    """Mark every active alert as read."""
    acknowledged = alerts_service.acknowledge_all(request.user)
    return Response(
        {"acknowledged": acknowledged, "unread": alerts_service.unread_count()}
    )
