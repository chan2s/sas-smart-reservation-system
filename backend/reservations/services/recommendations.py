"""Smart resource recommendations.

A deterministic, extensible rule engine that turns event requirements
(event type, purpose, expected participants, facility, schedule) into
sensible equipment quantities, then caps every suggestion against what is
actually available during the proposed reservation window.

Extending the engine means editing data tables, not control flow:

* ``_EVENT_PROFILES`` — one entry per event type; new event types are added
  here.
* ``_FACILITY_ADJUSTMENTS`` — per-facility-type tweaks (e.g. AVR always
  suggests a projector).
* ``_PURPOSE_PROJECTOR_KEYWORDS`` — purpose text that boosts a projector.
"""

from __future__ import annotations

import math
from datetime import date as date_cls
from datetime import time as time_cls

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility

from .availability import equipment_availability_map


# ---------------------------------------------------------------------------
# Quantity rules
# ---------------------------------------------------------------------------

def _chairs(participants: int) -> int:
    return max(participants, 0)


def _tables(participants: int) -> int:
    """One table per 10 participants; small events still get a table."""
    return max(math.ceil(participants / 10), 1)


def _sound(participants: int) -> int:
    if participants < 30:
        return 0
    if participants < 200:
        return 1
    return 2


def _microphones(participants: int) -> int:
    if participants <= 60:
        return 1
    if participants <= 200:
        return 2
    if participants <= 400:
        return 4
    return 6


# ---------------------------------------------------------------------------
# Rule tables (the extensible part)
# ---------------------------------------------------------------------------
#
# A profile maps a category key to either:
#   False   -> never suggested for this event type
#   True    -> use the base quantity rule for that category
#   int     -> fixed quantity
# A category key absent from a profile is never suggested.

_CATEGORY_KEYS = ("chairs", "tables", "sound", "microphones", "projector")
_BASE_RULES = {
    "chairs": _chairs,
    "tables": _tables,
    "sound": _sound,
    "microphones": _microphones,
    "projector": lambda _participants: 1,
}

_EVENT_PROFILES = {
    "SEMINAR": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "MEETING": {"projector": True, "sound": False, "microphones": 1, "chairs": True, "tables": 1},
    "WORKSHOP": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "TRAINING": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "CONFERENCE": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "RECOGNITION": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "ORIENTATION": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "CULTURAL": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "ACADEMIC": {"projector": True, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "SPORTS": {"projector": False, "sound": True, "microphones": True, "chairs": True, "tables": True},
    "OTHER": {"projector": False, "sound": True, "microphones": True, "chairs": True, "tables": True},
}

# Category key -> EquipmentCategory name keyword.
_CATEGORY_KEYWORDS = {
    "chairs": "chairs",
    "tables": "tables",
    "sound": "sound",
    "microphones": "microphones",
    "projector": "projector",
}

_REASONS = {
    "chairs": "One chair per expected participant.",
    "tables": "One table per 10 expected participants.",
    "sound": "A sound system is recommended for this event size.",
    "microphones": "Microphones are recommended for this event size.",
    "projector": "Projector recommended for this event type.",
}

_PURPOSE_PROJECTOR_KEYWORDS = (
    "presentation",
    "seminar",
    "conference",
    "workshop",
    "training",
    "recognition",
    "award",
    "ceremony",
    "graduation",
    "accreditation",
    "lecture",
)


def _purpose_suggests_projector(purpose: str) -> bool:
    lowered = (purpose or "").lower()
    return any(keyword in lowered for keyword in _PURPOSE_PROJECTOR_KEYWORDS)


def _adjust_profile(profile: dict, facility_type: str | None, purpose: str) -> dict:
    """Apply facility and purpose adjustments to a copy of an event profile."""
    adjusted = dict(profile)

    if facility_type == Facility.FacilityType.AVR:
        # Presentation rooms always warrant a projector.
        adjusted["projector"] = True
    elif facility_type == Facility.FacilityType.GYMNASIUM:
        # Open arenas rarely need a projector unless it is a program.
        if profile.get("projector") is False and not _purpose_suggests_projector(purpose):
            adjusted["projector"] = False
        else:
            adjusted["projector"] = True
    elif facility_type == Facility.FacilityType.CAFETERIA:
        adjusted["projector"] = False

    if _purpose_suggests_projector(purpose):
        adjusted["projector"] = True

    return adjusted


# ---------------------------------------------------------------------------
# Recommendation builder
# ---------------------------------------------------------------------------

def _evaluate_quantities(profile: dict, participants: int) -> dict:
    """category key -> rule quantity (pre-availability)."""
    quantities = {}
    for key in _CATEGORY_KEYS:
        spec = profile.get(key)
        if spec is False or spec is None:
            continue
        if spec is True:
            quantities[key] = _BASE_RULES[key](participants)
        else:
            quantities[key] = int(spec)
    return quantities


def recommend_resources(
    event_type: str,
    participants: int,
    facility_id=None,
    purpose: str = "",
    special_requirements: str = "",
    target_date: date_cls | None = None,
    start_time: time_cls | None = None,
    end_time: time_cls | None = None,
) -> list:
    """Recommend resources for an event profile.

    Returns a list of::

        {
            "equipment_id": int,
            "name": str,
            "category": str,
            "quantity": int,      # rule-based recommendation
            "available": int,     # units available during the window
            "recommended": int,   # min(quantity, available) — safe prefill
            "status": "AVAILABLE" | "PARTIAL" | "UNAVAILABLE",
            "reason": str,
        }

    When no schedule window is given, availability is computed against all
    current reservations (a conservative at-a-glance view).
    """
    profile = _EVENT_PROFILES.get(event_type or "OTHER", _EVENT_PROFILES["OTHER"])

    facility_type = None
    if facility_id is not None:
        facility_type = Facility.objects.filter(pk=facility_id).values_list(
            "facility_type", flat=True
        ).first()

    profile = _adjust_profile(profile, facility_type, purpose)
    quantities = _evaluate_quantities(profile, participants)

    availability = equipment_availability_map(target_date, start_time, end_time)

    recommendations = []
    for key in _CATEGORY_KEYS:
        quantity = quantities.get(key)
        if not quantity:
            continue
        category = EquipmentCategory.objects.filter(name__icontains=_CATEGORY_KEYWORDS[key]).first()
        if not category:
            continue
        # Only active, currently-usable inventory is considered. A line that
        # is archived, retired, or fully under maintenance is skipped entirely
        # (no point recommending an item that cannot be reserved at all);
        # schedule-level shortages are still surfaced as PARTIAL/UNAVAILABLE.
        equipment = (
            Equipment.objects.filter(
                category=category,
                is_active=True,
                status=Equipment.Status.AVAILABLE,
            )
            .order_by("name")
            .first()
        )
        if not equipment:
            continue

        info = availability.get(equipment.id, {})
        available = info.get("available", equipment.total_quantity)
        recommended = min(quantity, available)

        if available >= quantity:
            status = "AVAILABLE"
        elif available > 0:
            status = "PARTIAL"
        else:
            status = "UNAVAILABLE"

        recommendations.append(
            {
                "equipment_id": equipment.id,
                "name": equipment.name,
                "category": category.name,
                "quantity": quantity,
                "available": available,
                "recommended": recommended,
                "status": status,
                "reason": _REASONS[key],
            }
        )
    return recommendations