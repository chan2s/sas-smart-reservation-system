import logging

from django.utils import timesince
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework import viewsets, status as http_status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAccountApprovedOrReadOnly, IsSasStaff
from config.frontend import request_origin

from . import no_show_alerts as alerts_service
from .models import Notification, PossibleNoShowAlert, PushSubscription
from .serializers import (
    AwaitingNoShowReviewSerializer,
    NotificationSerializer,
    PossibleNoShowAlertSerializer,
    PushSubscriptionSerializer,
)
from .services import normalize_app_origin, validate_vapid_configuration

logger = logging.getLogger(__name__)


def _subscription_origin(request) -> str:
    """The app origin that registered a device, or ``""`` when unknown.

    Only ``Origin``/``Referer`` describe the application the browser is
    running: the host Django sees is the backend (the Vite dev proxy rewrites
    it), never the page the user is on. The value is validated and normalized
    by the shared origin helpers, so it is always a bare ``scheme://host``.
    """
    if not (request.headers.get("Origin") or request.headers.get("Referer")):
        return ""
    return normalize_app_origin(request_origin(request))


class VapidPublicKeyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            public_key = validate_vapid_configuration()
        except Exception as exc:
            logger.error(
                "VAPID public-key request rejected: configuration error=%s detail=%s",
                type(exc).__name__,
                str(exc),
            )
            return Response(
                {"detail": "Web Push is not configured correctly."},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"public_key": public_key})


class PushSubscriptionListView(APIView):
    permission_classes = [IsAuthenticated, IsAccountApprovedOrReadOnly]

    def get(self, request):
        rows = PushSubscription.objects.filter(user=request.user)
        return Response(PushSubscriptionSerializer(rows, many=True).data)

    def post(self, request):
        serializer = PushSubscriptionSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.validated_data["endpoint"]
        app_origin = _subscription_origin(request)
        subscription_values = {
            key: value
            for key, value in serializer.validated_data.items()
            if key != "endpoint"
        }
        with transaction.atomic():
            subscription, created = PushSubscription.objects.select_for_update().get_or_create(
                endpoint=endpoint,
                defaults={
                    **subscription_values,
                    "user": request.user,
                    "app_origin": app_origin,
                },
            )
        if subscription and subscription.user_id != request.user.pk:
            return Response({"detail": "This device is already registered to another account."}, status=http_status.HTTP_409_CONFLICT)
        if not created:
            for key, value in subscription_values.items():
                setattr(subscription, key, value)
            subscription.user = request.user
            # Keep the origin current on re-registration; never erase a known
            # origin because a later request omitted the header.
            subscription.app_origin = app_origin or subscription.app_origin
            subscription.active = True
            subscription.save()
        logger.info(
            "Push subscription %s: subscription_id=%s user_id=%s active=%s",
            "created" if created else "updated",
            subscription.pk,
            request.user.pk,
            subscription.active,
        )
        return Response(PushSubscriptionSerializer(subscription).data, status=http_status.HTTP_201_CREATED)


class PushSubscriptionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAccountApprovedOrReadOnly]

    def patch(self, request, pk):
        if not isinstance(request.data.get("active"), bool):
            return Response({"active": ["A boolean value is required."]}, status=http_status.HTTP_400_BAD_REQUEST)
        subscription = PushSubscription.objects.filter(user=request.user, pk=pk).first()
        if not subscription:
            return Response(status=http_status.HTTP_404_NOT_FOUND)
        subscription.active = request.data["active"]
        subscription.save(update_fields=["active", "updated_at"])
        return Response(PushSubscriptionSerializer(subscription).data)

    def delete(self, request, pk):
        deleted, _ = PushSubscription.objects.filter(user=request.user, pk=pk).delete()
        return Response(status=http_status.HTTP_204_NO_CONTENT if deleted else http_status.HTTP_404_NOT_FOUND)


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
