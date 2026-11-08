"""Signed bearer links for unauthenticated external reservation tracking."""

from urllib.parse import urlencode

from django.core.signing import BadSignature, Signer

from reservations.models import Reservation

_TRACKING_SALT = "sas-reserve.external-reservation-tracking"
_MAX_TOKEN_LENGTH = 256


def tracking_token_for(reservation: Reservation) -> str:
    """Create an unguessable, tamper-evident token for one guest reservation."""
    return Signer(salt=_TRACKING_SALT).sign(str(reservation.pk))


def reservation_for_tracking_token(token: str) -> Reservation | None:
    """Resolve a valid guest token without exposing internal reservations."""
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH:
        return None

    try:
        reservation_id = Signer(salt=_TRACKING_SALT).unsign(token)
        reservation_id = int(reservation_id)
    except (BadSignature, TypeError, ValueError):
        return None

    return (
        Reservation.objects.select_related("facility")
        .filter(
            pk=reservation_id,
            requester__isnull=True,
            requester_type=Reservation.RequesterType.EXTERNAL,
        )
        .first()
    )


def tracking_path_for(reservation: Reservation) -> str:
    """Relative frontend link suitable for email and the confirmation page."""
    query = urlencode({"token": tracking_token_for(reservation)})
    return f"/track-reservation?{query}"
