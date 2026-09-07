from django.contrib.auth import get_user_model

User = get_user_model()


def notify(user, notification_type, title, message="", link=""):
    """Create a notification for a single user (no-op for anonymous)."""
    if not user or not user.pk:
        return None
    return user.notifications.create(
        type=notification_type, title=title, message=message, link=link
    )


def notify_staff(notification_type, title, message="", link=""):
    """Notify every administrator and SAS staff member."""
    from notifications.models import Notification

    recipients = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.STAFF])
    created = []
    for recipient in recipients:
        created.append(
            Notification.objects.create(
                user=recipient,
                type=notification_type,
                title=title,
                message=message,
                link=link,
            )
        )
    return created