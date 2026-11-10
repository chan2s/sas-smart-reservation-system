"""Shared in-app and best-effort Web Push notification delivery."""

import base64
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from config.frontend import frontend_origin_allowed
from notifications.models import Notification, PushSubscription

logger = logging.getLogger(__name__)
User = get_user_model()

#: Longest route stored on a notification (matches ``Notification.link``) and
#: the longest origin stored on a push device.
MAX_NOTIFICATION_PATH_LENGTH = 200
MAX_APP_ORIGIN_LENGTH = 255


def normalize_app_origin(value) -> str:
    """Return a bare ``scheme://host[:port]`` origin, or ``""``.

    Only http(s) origins with a host are accepted. The value is stored on the
    device row and later compared with ``PUBLIC_FRONTEND_URL``, so anything
    that is not a navigation origin (paths, credentials, ``javascript:``) is
    discarded instead of being normalized into something usable.
    """
    parsed = urlparse((value or "").strip())
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}".rstrip("/")
    return origin[:MAX_APP_ORIGIN_LENGTH]


def push_origin_allowed(app_origin) -> bool:
    """Whether this deployment may deliver push to a device registered on ``app_origin``.

    ``PUBLIC_FRONTEND_URL`` is the single source of truth for the deployed
    application origin (the same setting that builds email links). A device
    registered on a different origin - typically the Vite dev server,
    ``localhost:5173`` - must not receive production push: the browser
    attributes the notification to the service worker that showed it, so that
    device would display (and open) the local development application instead
    of the deployed one.

    Devices registered before the origin was recorded (``""``) carry no
    evidence of a mismatched deployment and keep receiving push. When the
    public origin is not configured there is nothing to compare against, so
    delivery is not silently disabled by a missing setting.
    """
    origin = normalize_app_origin(app_origin)
    if not origin:
        return True
    configured = normalize_app_origin(getattr(settings, "PUBLIC_FRONTEND_URL", ""))
    if not configured:
        return True
    if origin == configured:
        return True
    # Development origins (localhost, Dev Tunnels) and explicitly allowlisted
    # origins stay valid in local and staged environments.
    return frontend_origin_allowed(origin)


def _deliver_notification(notification_id):
    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning("Push dispatch skipped: notification_id=%s no longer exists.", notification_id)
        return
    try:
        send_push_to_user(
            notification.user_id,
            notification.type,
            notification.link,
            event_key=notification.event_key or f"notification:{notification.pk}",
        )
    except Exception:
        # on_commit delivery is strictly best-effort; the action and its
        # persisted in-app notification have already committed.
        logger.exception("Push dispatch callback failed: notification_id=%s", notification_id)


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
        logger.info(
            "In-app notification created: notification_id=%s user_id=%s type=%s event_key=%s",
            notification.pk,
            user.pk,
            notification_type,
            notification.event_key or "unkeyed",
        )
        transaction.on_commit(
            lambda pk=notification.pk: _deliver_notification(pk),
            robust=True,
        )
    return notification


def notify(user, notification_type, title, message="", link="", event_key=None):
    """Create an in-app notification and queue best-effort push after commit."""
    return create_notification(user, notification_type, title, message, link, event_key)


def notify_staff(notification_type, title, message="", link="", exclude_user=None, event_key=None):
    """Notify administrators and SAS staff, optionally excluding the actor."""
    recipients = User.objects.filter(
        role__in=[User.Role.ADMIN, User.Role.STAFF],
        is_active=True,
    )
    if getattr(exclude_user, "pk", None):
        recipients = recipients.exclude(pk=exclude_user.pk)
    recipient_rows = list(recipients)
    logger.info(
        "Staff notification event: type=%s event_key=%s recipient_ids=%s",
        notification_type,
        event_key or "unkeyed",
        [recipient.pk for recipient in recipient_rows],
    )
    return [
        create_notification(
            recipient, notification_type, title, message, link,
            f"{event_key}:{recipient.pk}" if event_key else None,
        )
        for recipient in recipient_rows
    ]


def notify_admins(notification_type, title, message="", link="", event_key=None):
    """Notify active administrators for events that require admin authority."""
    recipients = list(
        User.objects.filter(role=User.Role.ADMIN, is_active=True)
    )
    logger.info(
        "Administrator notification event: type=%s event_key=%s recipient_ids=%s",
        notification_type,
        event_key or "unkeyed",
        [recipient.pk for recipient in recipients],
    )
    return [
        create_notification(
            recipient,
            notification_type,
            title,
            message,
            link,
            f"{event_key}:{recipient.pk}" if event_key else None,
        )
        for recipient in recipients
    ]


def validate_vapid_configuration():
    """Validate the VAPID pair without returning private key material.

    A missing PEM path is an error: py_vapid can otherwise generate a new key
    at that path, which silently disagrees with the public key already given to
    browsers. Inline private keys are accepted as URL-safe base64 scalars.
    """
    public_value = getattr(settings, "VAPID_PUBLIC_KEY", "").strip()
    private_value = getattr(settings, "VAPID_PRIVATE_KEY", "").strip()
    subject = getattr(
        settings,
        "VAPID_SUBJECT",
        getattr(settings, "VAPID_CLAIMS_EMAIL", ""),
    ).strip()
    if not public_value or not private_value:
        raise ValueError("VAPID public or private key is not configured.")
    if not subject.startswith(("mailto:", "https://")):
        raise ValueError("VAPID subject must be a mailto: or https: URI.")

    encoded_public = public_value.replace("-", "+").replace("_", "/")
    public_bytes = base64.b64decode(encoded_public + "=" * (-len(encoded_public) % 4))
    if len(public_bytes) != 65 or public_bytes[0] != 4:
        raise ValueError("VAPID public key is not an uncompressed P-256 key.")
    configured_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_bytes)

    private_path = Path(private_value)
    if private_path.is_file():
        raw_private = private_path.read_bytes()
        try:
            private_key = serialization.load_pem_private_key(raw_private, password=None)
        except ValueError:
            private_key = serialization.load_der_private_key(raw_private, password=None)
        if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(
            private_key.curve, ec.SECP256R1
        ):
            raise ValueError("VAPID private key must use the P-256 curve.")
    elif private_path.is_absolute() or private_value.lower().endswith((".pem", ".der")):
        raise ValueError("Configured VAPID private-key file does not exist.")
    else:
        encoded_private = private_value.replace("-", "+").replace("_", "/")
        private_bytes = base64.b64decode(encoded_private + "=" * (-len(encoded_private) % 4))
        if len(private_bytes) != 32:
            raise ValueError("Inline VAPID private key must be a 32-byte P-256 scalar.")
        private_key = ec.derive_private_key(int.from_bytes(private_bytes, "big"), ec.SECP256R1())

    derived_public = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    expected_public = configured_public.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    if derived_public != expected_public:
        raise ValueError("Configured VAPID public and private keys do not match.")
    return public_value


def send_push_to_user(user_id, notification_type, link="", event_key=None):
    """Send a deliberately generic payload to every active device independently."""
    try:
        from pywebpush import WebPushException, webpush

        try:
            validate_vapid_configuration()
        except Exception as exc:
            logger.error(
                "Web Push VAPID configuration error (user_id=%s, error=%s).",
                user_id,
                type(exc).__name__,
            )
            return
        subscriptions = PushSubscription.objects.filter(user_id=user_id, active=True)
        subscription_count = subscriptions.count()
        if not subscription_count:
            logger.info(
                "Web Push has no active subscriptions: user_id=%s event_key=%s",
                user_id,
                event_key or "unkeyed",
            )
            return
        logger.info(
            "Web Push subscriptions found: user_id=%s count=%s event_key=%s",
            user_id,
            subscription_count,
            event_key or "unkeyed",
        )
        for subscription in subscriptions.iterator():
            if not push_origin_allowed(subscription.app_origin):
                logger.warning(
                    "Web Push skipped for subscription id=%s: it was registered "
                    "from %r, which is not the configured public origin %r.",
                    subscription.pk,
                    subscription.app_origin,
                    getattr(settings, "PUBLIC_FRONTEND_URL", ""),
                )
                continue
            # Push is a wake-up and authenticated deep link, never a copy of the
            # in-app message (which may contain private workflow details).
            payload = json.dumps({
                "title": "SAS RESERVE",
                "body": "You have an update. Sign in to view it.",
                "url": notification_path(link),
                "tag": f"sas-{event_key}" if event_key else "sas-update",
            })
            try:
                logger.info(
                    "Web Push dispatch attempted: subscription_id=%s user_id=%s event_key=%s",
                    subscription.pk,
                    user_id,
                    event_key or "unkeyed",
                )
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
                logger.info(
                    "Web Push delivery succeeded: subscription_id=%s user_id=%s",
                    subscription.pk,
                    user_id,
                )
            except WebPushException as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                if status_code in (404, 410):
                    PushSubscription.objects.filter(pk=subscription.pk).delete()
                    logger.warning(
                        "Web Push subscription expired and was removed: subscription_id=%s status=%s",
                        subscription.pk,
                        status_code,
                    )
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


def notification_path(link) -> str:
    """Return a safe, RELATIVE in-app route for a notification deep link.

    Notifications are routes inside the SPA, never absolute URLs: the service
    worker resolves the path against its own registration origin, so the same
    payload opens the Vite dev server in development and the deployed origin in
    production (the browser attributes the notification to that origin).

    An absolute URL - for example an old ``http://localhost:5173/...`` row -
    is rejected here, so no device is ever navigated to a developer machine.
    """
    if (
        isinstance(link, str)
        and link.startswith("/")
        and not link.startswith("//")
        and "\\" not in link
    ):
        return link[:MAX_NOTIFICATION_PATH_LENGTH]
    return "/notifications"
