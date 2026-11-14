import re
from decimal import Decimal


PLACEHOLDER_HELP = {
    "requester_name": "Requester's displayed name or external contact person.",
    "organization_name": "Reservation organization, when provided.",
    "requester_email": "Reservation contact email, then the requester's account email when available.",
    "contact_phone": "Reservation contact phone number, when provided.",
    "reservation_reference": "SAS RESERVE reservation ID.",
    "facility_name": "Reserved facility name.",
    "event_name": "Reservation event name.",
    "reservation_date": "Reservation date, formatted for the letter.",
    "start_time": "Reservation start time.",
    "end_time": "Reservation end time.",
    "purpose": "Reservation purpose, when provided.",
    "attendees": "Expected participant count, when provided.",
    "equipment_list": "Requested equipment and quantities, when provided.",
    "total_amount": "Applicable total from stored reservation fees, when available.",
    "signatory_name": "Configured authorized signatory name.",
    "signatory_credentials": "Configured signatory credentials, when provided.",
    "signatory_designation": "Configured official designation.",
}
ALLOWED_PLACEHOLDERS = frozenset(PLACEHOLDER_HELP)
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def placeholder_values(reservation, signatory_settings):
    requester = reservation.requester if reservation.requester_id else None
    requester_name = requester.display_name if requester else (
        reservation.contact_person or reservation.organization or "External Requester"
    )
    items = list(reservation.items.select_related("equipment").all())
    equipment = "; ".join(
        f"{item.quantity:g} units of {item.equipment.name}" for item in items
    )
    fees = list(reservation.fees.all())
    total = Decimal(reservation.estimated_total or 0)
    if total <= 0 and fees:
        total = sum((Decimal(fee.subtotal or 0) for fee in fees), Decimal("0.00"))
    return {
        "requester_name": requester_name,
        "organization_name": reservation.organization or "",
        "requester_email": reservation.contact_email or (requester.email if requester else ""),
        "contact_phone": reservation.contact_phone or "",
        "reservation_reference": reservation.reservation_id or "",
        "facility_name": reservation.facility.name if reservation.facility_id else "",
        "event_name": reservation.event_name or "",
        "reservation_date": reservation.date.strftime("%B %d, %Y").replace(" 0", " ") if reservation.date else "",
        "start_time": reservation.start_time.strftime("%I:%M %p").lstrip("0") if reservation.start_time else "",
        "end_time": reservation.end_time.strftime("%I:%M %p").lstrip("0") if reservation.end_time else "",
        "purpose": reservation.purpose or "",
        "attendees": f"{reservation.expected_participants:,}" if reservation.expected_participants else "",
        "equipment_list": equipment,
        "total_amount": f"PHP {total:,.2f}" if total > 0 else "",
        "signatory_name": signatory_settings.authorized_signatory_name or "",
        "signatory_credentials": signatory_settings.credentials or "",
        "signatory_designation": signatory_settings.designation or "",
    }


def render_template_text(value, reservation, signatory_settings):
    values = placeholder_values(reservation, signatory_settings)
    return resolve_template_text(value, values)


def resolve_template_text(value, values):
    return PLACEHOLDER_PATTERN.sub(
        lambda match: values.get(match.group(1), match.group(0)), value or ""
    )
