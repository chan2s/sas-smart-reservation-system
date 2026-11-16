"""Administrative payment tracking for external-organization reservations.

This is deliberately a financial *recording* feature, not a payment gateway:
staff enter the amount the organization must pay and the amount actually
received. Payment status and the remaining balance are always derived from
those two amounts (``Reservation.payment_status`` / ``remaining_balance``), so
they can never drift out of sync and are independent of the reservation's own
workflow status.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from ..models import Reservation, ReservationEvent
from .pricing import money
from .workflow import record_event

ZERO = Decimal("0.00")

#: Fixed wording for the approval warning. The frontend displays it, and the
#: approve endpoint returns it as the reason it requires an acknowledgement.
UNPAID_WARNING = (
    "Payment has not been received for this reservation. "
    "Are you sure you want to approve it without payment?"
)

OUTSTANDING_WARNING = (
    "The required payment has not been fully received for this reservation. "
    "Are you sure you want to approve it with an outstanding balance?"
)


class PaymentError(ValueError):
    """Payment information that must be refused (invalid reservation/amount)."""


def payment_summary(reservation) -> dict:
    """Derived payment position of one external reservation."""
    required = reservation.payment_required_amount
    paid = money(reservation.amount_paid)
    remaining = money(reservation.remaining_balance)
    status = reservation.payment_status
    return {
        "payment_type": reservation.payment_type,
        "payment_type_label": reservation.get_payment_type_display()
        if reservation.payment_type
        else "",
        "required_amount": money(required) if required is not None else None,
        "amount_paid": paid,
        "remaining_balance": remaining,
        "status": status,
        "status_label": reservation.payment_status_label,
        "is_configured": reservation.payment_is_configured,
        "is_outstanding": reservation.payment_outstanding,
    }


def approval_warning(reservation) -> str | None:
    """Warning the admin must acknowledge before approving, if any.

    Returns ``None`` when the reservation carries no configured payment
    obligation or it is fully settled. An unpaid configured reservation gets
    the explicit "no payment received" wording; a partial payment gets the
    outstanding-balance wording.
    """
    if not reservation.payment_is_configured or not reservation.payment_outstanding:
        return None
    if money(reservation.amount_paid) <= ZERO:
        return UNPAID_WARNING
    return OUTSTANDING_WARNING


def _coerce_amount(value, field_label: str, *, allow_zero: bool) -> Decimal:
    if value is None or value == "":
        raise PaymentError(f"Enter a valid {field_label.lower()}.")
    try:
        amount = money(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PaymentError(f"Enter a valid {field_label.lower()}.") from exc
    if amount < ZERO:
        raise PaymentError(f"The {field_label.lower()} cannot be negative.")
    if not allow_zero and amount <= ZERO:
        raise PaymentError(f"The {field_label.lower()} must be greater than zero.")
    return amount


def update_payment(reservation, actor, *, payment_type, payment_required_amount, amount_paid):
    """Validate and persist payment information for an external reservation.

    The reservation is re-read under a row lock so concurrent updates cannot
    interleave and leave an amount paid above the required amount.
    """
    if not payment_type or payment_type not in Reservation.PaymentType.values:
        raise PaymentError("Select a valid payment type.")
    required = _coerce_amount(
        payment_required_amount, "required payment amount", allow_zero=False
    )
    paid = _coerce_amount(amount_paid, "amount paid", allow_zero=True)
    if paid > required:
        raise PaymentError("The amount paid cannot exceed the required payment amount.")

    with transaction.atomic():
        locked = (
            Reservation.objects.select_for_update()
            .filter(pk=reservation.pk)
            .first()
        )
        if locked is None:
            raise PaymentError("This reservation no longer exists.")
        if locked.requester_type != Reservation.RequesterType.EXTERNAL:
            raise PaymentError(
                "Payment tracking applies only to external organization "
                "reservations."
            )

        previous = (
            locked.get_payment_type_display() if locked.payment_type else "Not set",
            locked.payment_required_amount,
            locked.amount_paid,
        )
        locked.payment_type = payment_type
        locked.payment_required_amount = required
        locked.amount_paid = paid
        locked.save(
            update_fields=[
                "payment_type",
                "payment_required_amount",
                "amount_paid",
                "updated_at",
            ]
        )

        if previous != (payment_type, required, paid):
            record_event(
                locked,
                ReservationEvent.EventType.PAYMENT_RECORDED,
                actor=actor,
                message=(
                    "Payment information updated: "
                    f"{locked.get_payment_type_display()}, required "
                    f"PHP {required:.2f}, paid PHP {paid:.2f}, remaining "
                    f"PHP {locked.remaining_balance:.2f}."
                ),
            )

    reservation.refresh_from_db()
    return reservation
