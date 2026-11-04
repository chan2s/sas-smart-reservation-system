"""Shared in-app and best-effort Web Push notification delivery."""

import json
import logging
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from notifications.models import Notification, PushSubscription

logger = logging.getLogger(__name__)
User = get_user_model()


def _deliver_notification(notification_id):
    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        return
    send_push_to_user(
        notification.user_id,
        notification.type,
        notification.link,
        event_key=notification.event_key or f"notification:{notification.pk}",
    )


def create_notification(user, notification_type, title, message="", link="", event_key=None):
    if not user or not user.pk:
        return None
    defaults = {"user": user, "type": notification_type, "title": title, "message": message, "link": link}
    if event_key:
        # Stable keys make retried workflow callbacks idempotent.
        try:
            notification, created = Notification.objects.get_or_create(
                event_key=f"{user.pk}:{event_key}", defaults=defaults
            )
        except IntegrityError:
            notification = Notification.objects.get(event_key=f"{user.pk}:{event_key}")
            created = False
    else:
        notification = Notification.objects.create(**defaults)
        created = True
    if created:
        transaction.on_commit(lambda pk=notification.pk: _deliver_notification(pk))
    return notification


def notify(user, notification_type, title, message="", link="", event_key=None):
    """Create an in-app notification and queue best-effort push after commit."""
    return create_notification(user, notification_type, title, message, link, event_key)


def notify_staff(notification_type, title, message="", link="", exclude_user=None, event_key=None):
    """Notify administrators and SAS staff, optionally excluding the actor."""
    recipients = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.STAFF])
    if getattr(exclude_user, "pk", None):
        recipients = recipients.exclude(pk=exclude_user.pk)
    return [
        create_notification(
            recipient, notification_type, title, message, link,
            f"{event_key}:{recipient.pk}" if event_key else None,
        )
        for recipient in recipients
    ]


def send_push_to_user(user_id, notification_type, link="", event_key=None):
    """Send a deliberately generic payload to every active device independently."""
    try:
        from django.conf import settings
        from pywebpush import WebPushException, webpush

        if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
            return
        subscriptions = PushSubscription.objects.filter(user_id=user_id, active=True)
        for subscription in subscriptions.iterator():
            # Push is a wake-up and authenticated deep link, never a copy of the
            # in-app message (which may contain private workflow details).
            payload = json.dumps({
                "title": "SAS RESERVE",
                "body": "You have an update. Sign in to view it.",
                "url": _safe_destination(link),
                "tag": f"sas-{event_key}" if event_key else "sas-update",
            })
            try:
                endpoint_host = (urlparse(subscription.endpoint).hostname or "").lower()
                provider_headers = (
                    {"X-WNS-Type": "wns/toast"}
                    if endpoint_host.endswith(".notify.windows.com")
                    else {}
                )
                webpush(
                    subscription_info={
                        "endpoint": subscription.endpoint,
                        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                    },
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
                    headers=provider_headers,
                    ttl=3600,
                    timeout=8,
                )
                PushSubscription.objects.filter(pk=subscription.pk).update(
                    last_successful_delivery=timezone.now()
                )
            except WebPushException as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                if status_code in (404, 410):
                    PushSubscription.objects.filter(pk=subscription.pk).update(active=False)
                logger.warning(
                    "Web Push delivery failed (subscription id=%s, status=%s).",
                    subscription.pk, status_code or "unavailable",
                )
            except Exception as exc:
                logger.warning(
                    "Web Push delivery failed (subscription id=%s, error=%s).",
                    subscription.pk, type(exc).__name__,
                )
    except Exception as exc:
        # A push outage must never roll back or block the underlying workflow.
        logger.warning(
            "Web Push delivery could not be started for user id=%s (error=%s).",
            user_id, type(exc).__name__,
        )


def _safe_destination(link):
    if (
        isinstance(link, str)
        and link.startswith("/")
        and not link.startswith("//")
        and "\\" not in link
    ):
        return link[:200]
    return "/notifications"
