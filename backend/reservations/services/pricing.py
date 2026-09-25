"""External-organization pricing engine.

This is the single source of truth for what an EXTERNAL organization is
charged. It is deliberately *not* a standalone billing feature: the smart
recommendation engine calls into it to estimate cost, and reservation
creation calls into it to snapshot the final amount. It never trusts a
client-supplied total.

Rules live in the ``PricingRule`` table (staff-editable in Django admin), so
rates can change without touching source code:

* ``FACILITY``  — flat fee per reservation, matched on the facility *type*
  (e.g. Gymnasium ₱5,000, Cafeteria ₱5,000). A facility type with no rule is
  free (e.g. AVR = ₱0).
* ``EQUIPMENT`` — per-unit fee matched on the equipment *category*
  (e.g. chairs ₱5 each, sound system ₱1,000 each).
* ``OPERATOR``  — hourly fee triggered when a matching equipment category is
  part of the reservation (e.g. a sound system needs its operator at
  ₱5/hour). Operator hours always come from the reservation's own
  ``end_time - start_time`` — never from the current time.

Pricing only ever applies to ``Reservation.RequesterType.EXTERNAL``. Internal
campus requesters (students, faculty, employees, campus organizations)
remain free; ``quote_fees`` returns an empty breakdown for them regardless of
what the caller passes in.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time as time_cls, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from equipment.models import Equipment

from ..models import PricingRule, Reservation, ReservationFee

CURRENCY = "PHP"
TWO_PLACES = Decimal("0.01")
_SECONDS_PER_HOUR = Decimal("3600")


# ---------------------------------------------------------------------------
# Money / duration helpers
# ---------------------------------------------------------------------------

def money(value) -> Decimal:
    """Coerce any numeric input to a 2-decimal Decimal (half-up)."""
    return Decimal(str(value if value is not None else 0)).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


def reservation_duration_hours(start_time, end_time) -> Decimal:
    """Scheduled duration in hours, from the reservation window only.

    Returns ``0`` for missing/invalid windows. An ``end_time`` earlier than
    ``start_time`` is treated as crossing midnight (e.g. 22:00–01:00 = 3h) so
    a late-night booking still prices correctly.
    """
    if not start_time or not end_time:
        return Decimal("0.00")
    start = datetime.combine(date_cls(2000, 1, 1), start_time)
    end = datetime.combine(date_cls(2000, 1, 1), end_time)
    delta = end - start
    if delta <= timedelta(0):
        delta += timedelta(days=1)
    seconds = Decimal(str(delta.total_seconds()))
    return money(seconds / _SECONDS_PER_HOUR)


def is_external(requester_type) -> bool:
    return requester_type == Reservation.RequesterType.EXTERNAL


# ---------------------------------------------------------------------------
# Rule resolution
# ---------------------------------------------------------------------------

def _facility_rule(facility):
    if facility is None:
        return None
    return (
        PricingRule.objects.filter(
            is_active=True,
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=facility.facility_type,
        )
        .order_by("id")
        .first()
    )


def _rules_by_category(fee_type) -> dict:
    rows = (
        PricingRule.objects.filter(
            is_active=True, fee_type=fee_type, equipment_category__isnull=False
        )
        .select_related("equipment_category")
        .order_by("id")
    )
    # First rule per category wins, so staff can have a dormant duplicate.
    mapping: dict[int, PricingRule] = {}
    for rule in rows:
        mapping.setdefault(rule.equipment_category_id, rule)
    return mapping


def _resolve_items(items) -> list[tuple[Equipment, int]]:
    """Normalise input items to ``(equipment, quantity)`` pairs.

    Accepts dicts carrying either an ``equipment`` instance or an
    ``equipment_id``. Unknown/inactive equipment and non-positive quantities
    are ignored (they cannot be priced).
    """
    resolved: list[tuple[Equipment, int]] = []
    for item in items or []:
        equipment = item.get("equipment")
        if equipment is None and item.get("equipment_id"):
            equipment = (
                Equipment.objects.filter(pk=item["equipment_id"])
                .select_related("category")
                .first()
            )
        if equipment is None:
            continue
        try:
            quantity = int(item.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if quantity < 1:
            continue
        resolved.append((equipment, quantity))
    return resolved


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------

def quote_fees(
    requester_type,
    facility=None,
    items=None,
    start_time=None,
    end_time=None,
) -> dict:
    """Compute the applicable external-organization fees for a reservation.

    ``items`` is a list of ``{"equipment_id": int, "quantity": int}`` (or
    ``{"equipment": Equipment, ...}``). Returns::

        {
            "requester_type": "EXTERNAL",
            "external": True,
            "currency": "PHP",
            "facility_id": 1,
            "duration_hours": Decimal("4.00"),
            "fees": [ {fee_type, description, quantity, unit, unit_price,
                       subtotal, equipment_id?, equipment_category_id?}, ... ],
            "total": Decimal("1520.00"),
        }

    Internal requesters always get an empty, zero-total quote.
    """
    currency = CURRENCY
    external = is_external(requester_type)
    base = {
        "requester_type": requester_type,
        "external": external,
        "currency": currency,
        "facility_id": getattr(facility, "id", None),
        "duration_hours": Decimal("0.00"),
        "fees": [],
        "total": Decimal("0.00"),
    }
    if not external:
        return base

    fees: list[dict] = []

    # Facility flat fee ------------------------------------------------------
    facility_rule = _facility_rule(facility)
    if facility_rule is not None:
        price = money(facility_rule.unit_price)
        fees.append(
            {
                "fee_type": PricingRule.FeeType.FACILITY,
                "description": facility_rule.display_label,
                "quantity": Decimal("1.00"),
                "unit": PricingRule.Unit.FLAT,
                "unit_price": price,
                "subtotal": price,
            }
        )

    # Equipment + operator fees ---------------------------------------------
    equipment_rules = _rules_by_category(PricingRule.FeeType.EQUIPMENT)
    operator_rules = _rules_by_category(PricingRule.FeeType.OPERATOR)

    operator_triggers: dict[int, PricingRule] = {}
    for equipment, quantity in _resolve_items(items):
        category_id = equipment.category_id

        rule = equipment_rules.get(category_id)
        if rule is not None:
            unit_price = money(rule.unit_price)
            fees.append(
                {
                    "fee_type": PricingRule.FeeType.EQUIPMENT,
                    "description": rule.display_label,
                    "quantity": money(quantity),
                    "unit": rule.unit or PricingRule.Unit.UNIT,
                    "unit_price": unit_price,
                    "subtotal": money(unit_price * quantity),
                    "equipment_id": equipment.id,
                    "equipment_category_id": category_id,
                }
            )

        if category_id in operator_rules:
            operator_triggers.setdefault(category_id, operator_rules[category_id])

    # Operator fee is derived from the reservation's own duration and only
    # applies when a triggering resource (e.g. a sound system) is present.
    duration = reservation_duration_hours(start_time, end_time)
    for category_id, rule in operator_triggers.items():
        unit_price = money(rule.unit_price)
        fees.append(
            {
                "fee_type": PricingRule.FeeType.OPERATOR,
                "description": rule.display_label,
                "quantity": duration,
                "unit": PricingRule.Unit.HOUR,
                "unit_price": unit_price,
                "subtotal": money(unit_price * duration),
                "equipment_category_id": category_id,
            }
        )

    total = money(sum((line["subtotal"] for line in fees), Decimal("0.00")))
    base["fees"] = fees
    base["total"] = total
    base["duration_hours"] = duration
    return base


# ---------------------------------------------------------------------------
# Reporting / serialisation
# ---------------------------------------------------------------------------

def _fmt_qty(value: Decimal) -> str:
    """Trim insignificant zeros: 100.00 -> '100', 4.50 -> '4.5'."""
    value = money(value).normalize()
    if value == value.to_integral_value():
        return str(int(value))
    return str(value)


def fee_line_to_dict(line: dict) -> dict:
    return {
        "fee_type": line["fee_type"],
        "fee_type_label": dict(ReservationFee.FeeType.choices).get(
            line["fee_type"], line["fee_type"]
        ),
        "description": line["description"],
        "quantity": _fmt_qty(line["quantity"]),
        "unit": line["unit"],
        "unit_price": f"{money(line['unit_price']):.2f}",
        "subtotal": f"{money(line['subtotal']):.2f}",
        "equipment_id": line.get("equipment_id"),
        "equipment_category_id": line.get("equipment_category_id"),
    }


def quote_to_dict(quote: dict) -> dict:
    """JSON-friendly form of a quote (money as fixed-point strings)."""
    return {
        "requester_type": quote["requester_type"],
        "requester_type_label": dict(Reservation.RequesterType.choices).get(
            quote["requester_type"], quote["requester_type"]
        ),
        "external": quote["external"],
        "currency": quote["currency"],
        "facility_id": quote.get("facility_id"),
        "duration_hours": _fmt_qty(quote.get("duration_hours") or Decimal("0")),
        "fees": [fee_line_to_dict(line) for line in quote["fees"]],
        "total": f"{money(quote['total']):.2f}",
        "note": (
            "Estimated external organization fee. The SAS Office confirms the "
            "final amount when the reservation is approved."
            if quote["external"]
            else "No external organization fees apply to internal campus requesters."
        ),
    }


def calculate_for_reservation(reservation) -> dict:
    """Quote the fees for an existing reservation from its trusted fields."""
    items = [
        {"equipment": item.equipment, "quantity": item.quantity}
        for item in reservation.items.select_related("equipment__category")
    ]
    return quote_fees(
        reservation.requester_type,
        facility=reservation.facility,
        items=items,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
    )


# ---------------------------------------------------------------------------
# Snapshot (persisted at submission time)
# ---------------------------------------------------------------------------

def snapshot_reservation_fees(reservation) -> Decimal:
    """Persist the fee breakdown + total onto ``reservation`` and return it.

    The backend computes the amount from the facility, resource quantities,
    schedule, and configured rules — the client's own numbers are never
    consulted. Rates are stored on ``ReservationFee`` so a later change to
    ``PricingRule`` does not rewrite history.
    """
    quote = calculate_for_reservation(reservation)
    rows = [
        ReservationFee(
            reservation=reservation,
            fee_type=line["fee_type"],
            description=line["description"][:160],
            quantity=line["quantity"],
            unit=line["unit"],
            unit_price=line["unit_price"],
            subtotal=line["subtotal"],
        )
        for line in quote["fees"]
    ]
    with transaction.atomic():
        reservation.fees.all().delete()
        if rows:
            ReservationFee.objects.bulk_create(rows)
        reservation.estimated_total = quote["total"]
        reservation.save(update_fields=["estimated_total", "updated_at"])
    return quote["total"]


def rates_payload() -> list[dict]:
    """Active rates for the client, so the frontend never hardcodes prices."""
    rules = (
        PricingRule.objects.filter(is_active=True)
        .select_related("equipment_category")
        .order_by("fee_type", "id")
    )
    return [
        {
            "id": rule.id,
            "fee_type": rule.fee_type,
            "fee_type_label": rule.get_fee_type_display(),
            "facility_type": rule.facility_type,
            "facility_type_label": (
                rule.get_facility_type_display() if rule.facility_type else ""
            ),
            "equipment_category": (
                rule.equipment_category.name if rule.equipment_category_id else ""
            ),
            "equipment_category_id": rule.equipment_category_id,
            "label": rule.display_label,
            "unit": rule.unit,
            "unit_label": rule.get_unit_display(),
            "unit_price": f"{money(rule.unit_price):.2f}",
        }
        for rule in rules
    ]
