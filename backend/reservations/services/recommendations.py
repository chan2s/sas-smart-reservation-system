"""Facility-configuration-driven resource recommendations.

Recommendations come from the selected facility's own equipment assignments
(``FacilityResource`` rows) — never from a built-in catalog of equipment
names, quantities, or participant thresholds.

For each considered event the engine reads the assignments of the selected
facility, keeps only rows that are

* active and marked available at that facility,
* backed by active, currently usable equipment,
* opted in with ``is_recommendable``,
* matching the configured event types and participant range,

then computes the quantity from the assignment's configured calculation and
reports separately what is actually available during the proposed window.

Extending the behaviour means changing configuration (Django admin), not
control flow: staff can change a threshold or quantity, deactivate an
assignment, or remove it from the facility and the booking form follows.

Every recommendation answers three questions:

* ``quantity`` — how many units the event *needs* (configured rule output).
* ``available`` — how many units exist at the facility during the window.
* ``reason`` / ``calculation`` — why that quantity was chosen and the exact
  arithmetic behind it.

Availability never overrides the recommendation: ``quantity`` is the rule
output, ``recommended`` is the availability-capped prefill, and
``can_fulfill``/``status`` flag shortages with a ``warning`` instead.
"""

from __future__ import annotations

import math
from datetime import date as date_cls
from datetime import time as time_cls

from equipment.models import Equipment, FacilityResource
from facilities.models import Facility

from . import pricing
from .availability import equipment_availability_map
from ..models import Reservation


# ---------------------------------------------------------------------------
# Assignment rule evaluation
# ---------------------------------------------------------------------------

Rec = FacilityResource.RecommendationCalculation


def _matches_event_types(resource: FacilityResource, event_type: str) -> bool:
    """True when the assignment is configured for this event type."""
    configured = resource.recommendation_event_types or []
    if not configured:
        return True  # empty = suitable for every event type
    return (event_type or Reservation.EventType.OTHER) in configured


def _matches_participants(resource: FacilityResource, participants: int) -> bool:
    minimum = resource.recommendation_min_participants
    maximum = resource.recommendation_max_participants
    if minimum is not None and participants < minimum:
        return False
    if maximum is not None and participants > maximum:
        return False
    return True


def _threshold_quantity(
    resource: FacilityResource, participants: int
) -> tuple[int, str]:
    """Tiered lookup: <= t1 -> q1; <= t2 -> q2; <= t3 -> q3; else configured."""
    fallback = resource.recommendation_quantity
    tiers = (
        (resource.recommendation_tier_1, resource.recommendation_tier_1_quantity),
        (resource.recommendation_tier_2, resource.recommendation_tier_2_quantity),
        (resource.recommendation_tier_3, resource.recommendation_tier_3_quantity),
    )
    higher_bound = 0
    for tier, quantity in tiers:
        if not tier or quantity is None:
            continue
        if participants <= tier:
            return quantity, f"{participants} participants → {quantity}"
        higher_bound = tier
    return fallback, f"participants > {higher_bound} → {fallback}"


def _calculate_quantity(
    resource: FacilityResource, participants: int
) -> tuple[int, str]:
    """Return ``(quantity, calculation_trace)`` from the configured rule."""
    calculation = resource.recommendation_calculation
    value = resource.recommendation_quantity

    if calculation == Rec.FIXED:
        quantity, trace = value, f"{value} × 1"
    elif calculation == Rec.PER_PARTICIPANT:
        quantity, trace = participants * value, f"{participants} × {value}"
    elif calculation == Rec.PER_GROUP:
        per_unit = max(resource.recommendation_participants_per_unit, 1)
        quantity = max(math.ceil(participants / per_unit), 1)
        trace = f"ceil({participants} / {per_unit}) = {quantity}"
    else:  # THRESHOLD
        quantity, trace = _threshold_quantity(resource, participants)

    minimum = resource.recommendation_min_quantity
    maximum = resource.recommendation_max_quantity
    if minimum is not None and quantity < minimum:
        quantity = minimum
        trace += f" → at least {minimum}"
    if maximum is not None and quantity > maximum:
        quantity = maximum
        trace += f" → at most {maximum}"
    return quantity, trace


def _reason(
    resource: FacilityResource, quantity: int, participants: int
) -> str:
    """Custom explanation if staff wrote one, otherwise derived from the rule."""
    if resource.recommendation_explanation:
        return resource.recommendation_explanation

    name = resource.equipment.name
    calculation = resource.recommendation_calculation

    if calculation == Rec.FIXED:
        return f"{quantity} × {name} for this event"
    if calculation == Rec.PER_PARTICIPANT:
        return f"{resource.recommendation_quantity} {name} per participant"
    if calculation == Rec.PER_GROUP:
        per_unit = max(resource.recommendation_participants_per_unit, 1)
        return f"1 {name} per {per_unit} participants, rounded up"

    # THRESHOLD: describe the tier that matched.
    tiers = (
        (resource.recommendation_tier_1, resource.recommendation_tier_1_quantity),
        (resource.recommendation_tier_2, resource.recommendation_tier_2_quantity),
        (resource.recommendation_tier_3, resource.recommendation_tier_3_quantity),
    )
    for tier, _tier_quantity in tiers:
        if tier and participants <= tier:
            return f"{quantity} {name} for events up to {tier} participants"
    highest = max((tier for tier, _ in tiers if tier), default=0)
    return f"{quantity} {name} for events over {highest} participants"


# ---------------------------------------------------------------------------
# Recommendation builder
# ---------------------------------------------------------------------------

def recommend_resources(
    event_type: str,
    participants: int,
    facility_id=None,
    purpose: str = "",
    special_requirements: str = "",
    target_date: date_cls | None = None,
    start_time: time_cls | None = None,
    end_time: time_cls | None = None,
    event_name: str = "",
) -> list:
    """Recommend the selected facility's configured equipment.

    Returns a list of::

        {
            "equipment_id": int,
            "name": str,
            "category": str,
            "quantity": int,      # configured recommendation (uncapped)
            "available": int,     # units available during the window
            "recommended": int,   # min(quantity, available) — safe prefill
            "status": "AVAILABLE" | "PARTIAL" | "UNAVAILABLE",
            "can_fulfill": bool,  # recommendation fits the window's stock
            "reason": str,        # why this quantity
            "calculation": str,   # the exact arithmetic
            "warning": str,       # only when recommendation exceeds stock
        }

    ``quantity`` is always the configured rule output — never inventory —
    while ``recommended`` is the availability-capped value safe to prefill into
    the request form. When no schedule window is given, availability is
    computed against all current reservations (a conservative at-a-glance
    view).

    A facility is the source of truth: without one there is nothing to
    recommend, and an equipment item that is not assigned to the facility is
    never recommended. ``purpose``, ``special_requirements``, and
    ``event_name`` are accepted for API compatibility; they do not add
    equipment, because doing so would reintroduce hardcoded rules.
    """
    # No participant count → no participant-based quantities. This matches the
    # create-time validation (expected_participants >= 1) so the wizard never
    # shows recommendations that could not be requested.
    participants = int(participants or 0)
    if participants < 1 or facility_id is None:
        return []

    resources = (
        FacilityResource.objects.filter(
            facility_id=facility_id,
            is_active=True,
            status=FacilityResource.Status.AVAILABLE,
            is_recommendable=True,
            equipment__is_active=True,
            equipment__status=Equipment.Status.AVAILABLE,
        )
        .select_related("equipment__category")
        .order_by("display_order", "equipment__name")
    )

    configured = [
        resource
        for resource in resources
        if _matches_event_types(resource, event_type)
        and _matches_participants(resource, participants)
    ]
    if not configured:
        return []

    availability = equipment_availability_map(
        target_date, start_time, end_time, facility_id=facility_id
    )

    recommendations = []
    for resource in configured:
        quantity, calculation = _calculate_quantity(resource, participants)
        if quantity < 1:
            continue

        info = availability.get(resource.equipment_id) or {}
        available = info.get("available", resource.effective_quantity)
        recommended = min(quantity, available)

        if available >= quantity:
            status = "AVAILABLE"
        elif available > 0:
            status = "PARTIAL"
        else:
            status = "UNAVAILABLE"

        warning = None
        if available < quantity:
            warning = (
                f"Only {available} of the recommended {quantity} units are "
                f"currently available."
            )

        recommendations.append(
            {
                "equipment_id": resource.equipment_id,
                "name": resource.equipment.name,
                "category": resource.equipment.category.name,
                "quantity": quantity,
                "available": available,
                "recommended": recommended,
                "status": status,
                "can_fulfill": available >= quantity,
                "reason": _reason(resource, quantity, participants),
                "calculation": calculation,
                "warning": warning,
            }
        )
    return recommendations


# ---------------------------------------------------------------------------
# Recommendation + pricing bundle
# ---------------------------------------------------------------------------
def recommend_resources_with_pricing(
    event_type: str,
    participants: int,
    facility_id=None,
    purpose: str = "",
    special_requirements: str = "",
    target_date: date_cls | None = None,
    start_time: time_cls | None = None,
    end_time: time_cls | None = None,
    requester_type: str = Reservation.RequesterType.CAMPUS,
    event_name: str = "",
) -> dict:
    """Recommend resources, then price them for the requester type.

    Recommendation and pricing stay separate concerns: resources are chosen
    from the facility's configuration first (never from price), and only then
    is the applicable external-organization cost calculated from the
    recommended quantities and the schedule. Internal requesters get a
    visible zero-fee summary rather than external prices presented as if
    charged.

    Returns ``{"recommendations": [...], "pricing": {...}}``. Each
    recommendation gains ``unit_price``/``estimated_cost``/``fee_applies`` so
    the client can show per-line costs without hardcoding any rate.
    """
    recommendations = recommend_resources(
        event_type,
        participants,
        facility_id=facility_id,
        event_name=event_name,
        purpose=purpose,
        special_requirements=special_requirements,
        target_date=target_date,
        start_time=start_time,
        end_time=end_time,
    )

    facility = None
    if facility_id is not None:
        facility = Facility.objects.filter(pk=facility_id).first()

    quote = pricing.quote_fees(
        requester_type,
        facility=facility,
        items=[
            {"equipment_id": r["equipment_id"], "quantity": r["quantity"]}
            for r in recommendations
        ],
        start_time=start_time,
        end_time=end_time,
        target_date=target_date,
    )

    equipment_lines = {
        line["equipment_id"]: line
        for line in quote["fees"]
        if line["fee_type"] == pricing.PricingRule.FeeType.EQUIPMENT
        and line.get("equipment_id")
    }
    for item in recommendations:
        line = equipment_lines.get(item["equipment_id"])
        item["unit_price"] = (
            f"{pricing.money(line['unit_price']):.2f}" if line else None
        )
        item["estimated_cost"] = (
            f"{pricing.money(line['subtotal']):.2f}"
            if line and quote["external"] else "0.00"
        )
        item["reference_cost"] = (
            f"{pricing.money(line['subtotal']):.2f}" if line else "0.00"
        )
        item["fee_applies"] = line is not None and quote["external"]

    return {
        "recommendations": recommendations,
        "pricing": pricing.quote_to_dict(quote),
    }
