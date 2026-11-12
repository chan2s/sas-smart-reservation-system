"""Official reservation quote and payment treatment.

This is the single source of truth for the official rental values. It is
deliberately *not* a standalone billing feature: the smart
recommendation engine calls into it to estimate cost, and reservation
creation calls into it to snapshot the final amount. It never trusts a
client-supplied total.

Official rates live in the staff-editable ``PricingRule`` table. Facility
rates use whole-day, half-day, and hourly periods. Equipment rates use the
approved equipment categories, and environmental/operator fees use the same
table. The booking date and time determine operator applicability.

External reservations pay the official total. Internal campus reservations
receive the same itemized reference quote with every line waived and a payable
total of zero. Their waived lines are never persisted as fee obligations.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time as time_cls, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from equipment.models import Equipment, FacilityResource

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


def _overtime_rule(facility):
    """Overtime rate for the facility's type, or ``None`` when unconfigured."""
    if facility is None:
        return None
    return (
        PricingRule.objects.filter(
            is_active=True,
            fee_type=PricingRule.FeeType.OVERTIME,
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


def _facility_resources(facility) -> dict:
    """equipment_id -> active ``FacilityResource`` for this facility.

    Empty when the facility has no configured assignment, in which case the
    legacy per-category ``PricingRule`` behavior applies unchanged.
    """
    if facility is None:
        return {}
    rows = FacilityResource.objects.filter(facility=facility, is_active=True)
    return {row.equipment_id: row for row in rows}


def _resolve_items(items) -> list[tuple[Equipment, int, bool | None]]:
    """Normalise input items to ``(equipment, quantity, operator)`` triples.

    Accepts dicts carrying either an ``equipment`` instance or an
    ``equipment_id``. Unknown/inactive equipment and non-positive quantities
    are ignored (they cannot be priced). ``operator`` is ``None`` when the
    caller did not express a preference (legacy auto behavior), otherwise the
    requester's explicit opt-in/opt-out.
    """
    resolved: list[tuple[Equipment, int, bool | None]] = []
    for item in items or []:
        equipment = item.get("equipment")
        if equipment is None and item.get("equipment_id"):
            equipment = (
                Equipment.objects.filter(pk=item["equipment_id"], is_active=True)
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
        operator = item.get("operator", None)
        if operator is not None:
            operator = bool(operator)
        resolved.append((equipment, quantity, operator))
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
    target_date=None,
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
            "total": Decimal("2000.00"),
        }

    The quote dict also carries ``included_hours``/``overtime_hours``;
    ``quote_to_dict`` adds an ``equipment_subtotal`` (sum of the EQUIPMENT
    lines) for the client breakdown.

    Internal requesters receive the same official reference fees, marked
    waived, with a zero payable total.
    """
    currency = CURRENCY
    external = is_external(requester_type)
    duration = reservation_duration_hours(start_time, end_time)
    base = {
        "requester_type": requester_type,
        "external": external,
        "currency": currency,
        "facility_id": getattr(facility, "id", None),
        "duration_hours": duration,
        "included_hours": Decimal("0.00"),
        "overtime_hours": Decimal("0.00"),
        "fees": [],
        "total": Decimal("0.00"),
    }
    fees: list[dict] = []

    # Facility flat fee ------------------------------------------------------
    # The flat fee is the fixed base price for the first ``included_hours``
    # hours of the standard day. It is deliberately NOT priced per hour.
    facility_rule = _facility_rule(facility)
    included_hours = Decimal("0.00")
    if facility_rule is not None:
        included_hours = money(facility_rule.included_hours)
        price = money(facility_rule.unit_price)
        # Official rental periods are selected from the scheduled duration.
        # The period rates themselves remain staff managed in PricingRule.
        if duration >= Decimal("8.00"):
            period = "WHOLE_DAY"
            period_label = "Whole day"
        elif duration >= Decimal("4.00"):
            period = "HALF_DAY"
            period_label = "Half day"
        else:
            period = "PER_HOUR"
            period_label = "Per hour"
        period_rule = PricingRule.objects.filter(
            is_active=True,
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=facility.facility_type,
            rental_period=period,
        ).order_by("id").first()
        if period_rule is not None:
            facility_rule = period_rule
            price = money(period_rule.unit_price)
        facility_quantity = duration if period == "PER_HOUR" else Decimal("1.00")
        facility_subtotal = money(price * facility_quantity)
        fees.append(
            {
                "fee_type": PricingRule.FeeType.FACILITY,
                "description": facility_rule.display_label,
                "quantity": Decimal("1.00"),
                "unit": PricingRule.Unit.HOUR if period == "PER_HOUR" else PricingRule.Unit.FLAT,
                "unit_price": price,
                "quantity": facility_quantity,
                "subtotal": facility_subtotal,
                "rental_period": period,
                "period_label": period_label,
            }
        )

    # Equipment + operator fees ---------------------------------------------
    # Unit prices resolve in priority order:
    #   1. a facility's own ``FacilityResource.additional_fee`` for that item
    #      (so the same item can cost differently from facility to facility —
    #      a non-zero fee overrides everything below; 0 means "no override"),
    #   2. the equipment item's own ``Equipment.price`` (configured per item
    #      by the SAS Office in the equipment manager),
    #   3. the legacy per-category ``PricingRule`` (kept so databases with
    #      category rates and items without a configured price keep working).
    equipment_rules = _rules_by_category(PricingRule.FeeType.EQUIPMENT)
    operator_rules = _rules_by_category(PricingRule.FeeType.OPERATOR)
    facility_resources = _facility_resources(facility)

    operator_triggers: dict[int, PricingRule] = {}
    for equipment, quantity, operator_requested in _resolve_items(items):
        category_id = equipment.category_id
        normalized_name = equipment.name.strip().casefold()
        if normalized_name in {"led wall", "sound system", "plastic chairs"}:
            if normalized_name == "led wall":
                equipment_period = "WHOLE_DAY" if duration >= Decimal("8") else "HALF_DAY"
                official_rule = PricingRule.objects.filter(
                    is_active=True,
                    fee_type=PricingRule.FeeType.EQUIPMENT,
                    equipment_category_id=equipment.category_id,
                    rental_period=equipment_period,
                ).order_by("id").first()
            else:
                official_rule = equipment_rules.get(category_id)
            official_equipment_price = money(official_rule.unit_price) if official_rule else Decimal("0.00")
            line_quantity = quantity if normalized_name == "plastic chairs" else 1
            fees.append({
                "fee_type": PricingRule.FeeType.EQUIPMENT,
                "description": equipment.name,
                "quantity": money(quantity),
                "unit": PricingRule.Unit.FLAT if normalized_name == "led wall" else PricingRule.Unit.UNIT,
                "unit_price": official_equipment_price,
                "subtotal": money(official_equipment_price * line_quantity),
                "equipment_id": equipment.id,
                "equipment_category_id": category_id,
                "equipment_unit": equipment.unit,
            })
            continue
        resource = facility_resources.get(equipment.id)
        rule = equipment_rules.get(category_id)
        # The equipment item's own price — the primary per-item rate.
        item_price = money(getattr(equipment, "price", None) or 0)

        if resource is not None:
            # Facility-configured resource. A non-zero ``additional_fee`` is a
            # facility-specific override; when it is zero no override is
            # configured, so the item price (then the per-category rate)
            # still applies. A resource is therefore free only when none of
            # the three sources is set.
            unit_price = money(resource.additional_fee)
            unit = PricingRule.Unit.UNIT
            description = equipment.name
            if unit_price <= 0 and item_price > 0:
                unit_price = item_price
            elif unit_price <= 0 and rule is not None:
                unit_price = money(rule.unit_price)
                unit = rule.unit or PricingRule.Unit.UNIT
            if unit_price > 0:
                fees.append(
                    {
                        "fee_type": PricingRule.FeeType.EQUIPMENT,
                        # Show the resource the requester actually selected
                        # rather than the generic category label.
                        "description": description,
                        "quantity": money(quantity),
                        "unit": unit,
                        "unit_price": unit_price,
                        "subtotal": money(unit_price * quantity),
                        "equipment_id": equipment.id,
                        "equipment_category_id": category_id,
                        # The item's configured counting unit ("piece", "set",
                        # …) so clients can say "112 pieces × ₱5.00".
                        "equipment_unit": equipment.unit,
                    }
                )
            # Operator service: only when explicitly requested (or forced by
            # the resource configuration), never just because it is present.
            # The facility resource stays authoritative here — a facility that
            # does not offer the operator is never charged for one.
            operator_fee = money(resource.operator_fee)
            if (
                (resource.operator_required or operator_requested is True)
                and operator_fee > 0
                and external
            ):
                fees.append(
                    {
                        "fee_type": PricingRule.FeeType.OPERATOR,
                        "description": f"{equipment.name} Operator",
                        "quantity": Decimal("1.00"),
                        "unit": PricingRule.Unit.FLAT,
                        "unit_price": operator_fee,
                        "subtotal": operator_fee,
                        "equipment_id": equipment.id,
                        "equipment_category_id": category_id,
                    }
                )
            continue

        if item_price > 0:
            unit_price = item_price
            unit = PricingRule.Unit.UNIT
            description = equipment.name
        elif rule is not None:
            unit_price = money(rule.unit_price)
            unit = rule.unit or PricingRule.Unit.UNIT
            description = rule.display_label
        else:
            unit_price = Decimal("0.00")
            description = equipment.name

        if unit_price > 0:
            fees.append(
                {
                    "fee_type": PricingRule.FeeType.EQUIPMENT,
                    "description": description,
                    "quantity": money(quantity),
                    "unit": unit,
                    "unit_price": unit_price,
                    "subtotal": money(unit_price * quantity),
                    "equipment_id": equipment.id,
                    "equipment_category_id": category_id,
                    # The item's configured counting unit ("piece", "set", …).
                    "equipment_unit": equipment.unit,
                }
            )

        # Legacy category operator: applies unless the requester explicitly
        # opted out (``operator_requested is False``). Pre-existing callers
        # that send no flag keep the historical automatic behavior.
        if category_id in operator_rules and operator_requested is not False:
            operator_triggers.setdefault(category_id, operator_rules[category_id])


    # Operator fee only applies when a triggering resource (e.g. a sound
    # system) is present. A ``flat`` operator rate is a single service charge
    # for the reservation; an ``hour`` rate scales with the event duration.
    operator_time_applies = bool(
        target_date
        and (target_date.weekday() >= 5 or (end_time and end_time > time_cls(17, 0)))
    )
    for category_id, rule in (operator_triggers.items() if external and operator_time_applies else []):
        unit_price = money(rule.unit_price)
        charge_per_hour = (rule.unit or PricingRule.Unit.UNIT) == PricingRule.Unit.HOUR
        if charge_per_hour:
            quantity = duration
            subtotal = money(unit_price * duration)
            unit = PricingRule.Unit.HOUR
        else:
            quantity = Decimal("1.00")
            subtotal = unit_price
            unit = PricingRule.Unit.FLAT
        fees.append(
            {
                "fee_type": PricingRule.FeeType.OPERATOR,
                "description": rule.display_label,
                "quantity": quantity,
                "unit": unit,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "equipment_category_id": category_id,
            }
        )

    environmental_rule = PricingRule.objects.filter(
        is_active=True, fee_type=PricingRule.FeeType.ENVIRONMENTAL
    ).order_by("id").first()
    environmental_price = money(environmental_rule.unit_price) if environmental_rule else Decimal("500.00")
    fees.append({
        "fee_type": PricingRule.FeeType.ENVIRONMENTAL,
        "description": "Environmental Fee",
        "quantity": Decimal("1.00"),
        "unit": PricingRule.Unit.FLAT,
        "unit_price": environmental_price,
        "subtotal": environmental_price,
    })
    if operator_time_applies:
        operator_rules_by_category = _rules_by_category(PricingRule.FeeType.OPERATOR)
        selected_equipment = _resolve_items(items)
        for equipment_name, label in (("led wall", "LED Wall Operator"), ("sound system", "Sound System Operator")):
            matching = next((equipment for equipment, _, _ in selected_equipment if equipment.name.strip().casefold() == equipment_name), None)
            operator_rule = operator_rules_by_category.get(matching.category_id) if matching else None
            if matching and operator_rule:
                operator_price = money(operator_rule.unit_price)
                fees.append({
                    "fee_type": PricingRule.FeeType.OPERATOR,
                    "description": label,
                    "quantity": Decimal("1.00"),
                    "unit": PricingRule.Unit.FLAT,
                    "unit_price": operator_price,
                    "subtotal": operator_price,
                })
    if not external:
        for line in fees:
            line["waived"] = True
            line["waiver_reason"] = "Internal Reservation — No Payment Required"

    reference_total = money(sum((line["subtotal"] for line in fees), Decimal("0.00")))
    total = reference_total if external else Decimal("0.00")
    base["reference_total"] = reference_total
    base["fees"] = fees
    base["total"] = total if external else Decimal("0.00")
    base["included_hours"] = included_hours
    base["overtime_hours"] = Decimal("0.00")
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
        # Counting unit of the selected equipment item (EQUIPMENT lines only).
        "equipment_unit": line.get("equipment_unit"),
        "waived": line.get("waived", False),
        "waiver_reason": line.get("waiver_reason", ""),
        "rental_period": line.get("rental_period", ""),
        "period_label": line.get("period_label", ""),
    }


def quote_to_dict(quote: dict) -> dict:
    """JSON-friendly form of a quote (money as fixed-point strings)."""
    equipment_subtotal = money(
        sum(
            (
                line["subtotal"]
                for line in quote["fees"]
                if line["fee_type"] == PricingRule.FeeType.EQUIPMENT
            ),
            Decimal("0.00"),
        )
    )
    return {
        "requester_type": quote["requester_type"],
        "requester_type_label": dict(Reservation.RequesterType.choices).get(
            quote["requester_type"], quote["requester_type"]
        ),
        "external": quote["external"],
        "currency": quote["currency"],
        "facility_id": quote.get("facility_id"),
        "duration_hours": _fmt_qty(quote.get("duration_hours") or Decimal("0")),
        "included_hours": _fmt_qty(quote.get("included_hours") or Decimal("0")),
        "overtime_hours": _fmt_qty(quote.get("overtime_hours") or Decimal("0")),
        "equipment_subtotal": f"{equipment_subtotal:.2f}",
        "fees": [fee_line_to_dict(line) for line in quote["fees"]],
        "total": f"{money(quote['total']):.2f}",
        "reference_total": f"{money(quote.get('reference_total', quote['total'])):.2f}",
        "note": (
            "Estimated external organization fee. The SAS Office confirms the "
            "final amount when the reservation is approved."
            if quote["external"]
            else "Internal Reservation — No Payment Required. Official charges are waived."
        ),
    }


def calculate_for_reservation(reservation) -> dict:
    """Quote the fees for an existing reservation from its trusted fields."""
    items = [
        {
            "equipment": item.equipment,
            "quantity": item.quantity,
            "operator": item.operator_requested,
        }
        for item in reservation.items.select_related("equipment__category")
    ]
    return quote_fees(
        reservation.requester_type,
        facility=reservation.facility,
        items=items,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
        target_date=reservation.date,
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
    ] if is_external(reservation.requester_type) else []
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
            "rental_period": rule.rental_period,
        }
        for rule in rules
    ]
