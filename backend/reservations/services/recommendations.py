"""Smart resource recommendations.

A deterministic, extensible rule engine that turns event requirements
(event type, purpose, expected participants, facility, schedule) into
sensible equipment **quantities**, then reports — separately — what is
actually available during the proposed reservation window.

Extending the engine means editing data tables, not control flow:

* ``_EVENT_PROFILES`` — one entry per event type; new event types are added
  here.
* ``_FACILITY_ADJUSTMENTS`` — per-facility-type tweaks (e.g. AVR always
  suggests a projector).
* ``_PURPOSE_PROJECTOR_KEYWORDS`` — purpose text that boosts a projector.
* ``RecommendationRule`` (DB, staff-editable via Django admin) — overrides
  any built-in category rule. Specificity decides which rule wins: exact
  event type > exact facility type > participant range > priority. Built-in
  rules remain the fallback whenever no active DB rule covers a category, so
  the engine behaves identically to the code-only version until staff add
  overrides.

Every recommendation in the payload answers three questions:

* ``quantity`` — how many units the event *needs* (rule-based).
* ``available`` — how many units exist during the window (inventory).
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

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility

from .availability import equipment_availability_map
from ..models import RecommendationRule


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

# Human-readable rule statements used in reasons and calculations. The noun
# pair is singular/plural so explanations read naturally ("1 table per 10
# participants", "2 microphones for large seminars").
_UNIT_NOUNS = {
    "chairs": ("chair", "chairs"),
    "tables": ("table", "tables"),
    "sound": ("sound system", "sound systems"),
    "microphones": ("microphone", "microphones"),
    "projector": ("projector", "projectors"),
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


# ---------------------------------------------------------------------------
# DB-configured rules (staff-editable via Django admin)
# ---------------------------------------------------------------------------

def _matching_rules(event_type: str, facility_type: str | None, participants: int) -> list:
    """Active DB rules matching the event, most specific first.

    Specificity: exact event type (4) + exact facility type (2) + participant
    range (1), then ``priority`` (lower wins), then most recently updated.
    """
    matched = []
    rules = (
        RecommendationRule.objects.filter(is_active=True)
        .select_related("category")
        .order_by("priority", "id")
    )
    for rule in rules:
        if rule.event_type and rule.event_type != event_type:
            continue
        if rule.facility_type and rule.facility_type != (facility_type or ""):
            continue
        if participants < rule.min_participants:
            continue
        if rule.max_participants is not None and participants > rule.max_participants:
            continue
        specificity = (
            (4 if rule.event_type else 0)
            + (2 if rule.facility_type else 0)
            + (1 if (rule.min_participants or rule.max_participants) else 0)
        )
        matched.append((-specificity, rule.priority, -rule.id, rule))
    matched.sort(key=lambda entry: entry[:3])
    return [entry[3] for entry in matched]


def _rule_quantity(rule: RecommendationRule, participants: int) -> tuple[int, str]:
    """Return ``(quantity, calculation_trace)`` for a DB rule."""
    ct = rule.calculation_type

    if ct == RecommendationRule.CalculationType.FIXED:
        quantity = rule.quantity_value
        return quantity, f"{quantity} × 1"

    if ct == RecommendationRule.CalculationType.PER_PARTICIPANT:
        quantity = participants * rule.quantity_value
        return quantity, f"{participants} × {rule.quantity_value}"

    if ct == RecommendationRule.CalculationType.PER_GROUP:
        per_unit = max(rule.participants_per_unit, 1)
        quantity = max(math.ceil(participants / per_unit), 1)
        return quantity, f"ceil({participants} / {per_unit}) = {quantity}"

    # THRESHOLD: participants <= tier 1 → q1; <= tier 2 → q2; else q3.
    tier_1 = rule.threshold_tier_1 or 0
    tier_2 = rule.threshold_tier_2 or 0
    q1 = rule.threshold_quantity_1
    q2 = rule.threshold_quantity_2
    q3 = (
        rule.threshold_quantity_3
        if rule.threshold_quantity_3 is not None
        else rule.quantity_value
    )
    if tier_1 and q1 is not None and participants <= tier_1:
        return q1, f"{participants} participants → {q1}"
    if tier_2 and q2 is not None and participants <= tier_2:
        return q2, f"{participants} participants → {q2}"
    return q3, f"participants > {tier_2 or tier_1} → {q3}"


def _rule_reason(rule: RecommendationRule, quantity: int, participants: int) -> str:
    """Custom explanation if staff wrote one, otherwise auto-generated."""
    if rule.explanation:
        return rule.explanation

    name = rule.category.name
    # "Chairs" -> "chair", "Sound Systems" -> "sound system".
    singular = name[:-1] if name.endswith("s") and not name.endswith("ss") else name
    singular = singular.lower()
    ct = rule.calculation_type

    if ct == RecommendationRule.CalculationType.FIXED:
        noun = singular if rule.quantity_value == 1 else name.lower()
        return f"{rule.quantity_value} {noun} for this event"
    if ct == RecommendationRule.CalculationType.PER_PARTICIPANT:
        return f"{rule.quantity_value} {singular} per participant"
    if ct == RecommendationRule.CalculationType.PER_GROUP:
        return f"1 {singular} per {rule.participants_per_unit} participants, rounded up"

    # THRESHOLD: describe the tier that matched.
    tier_1 = rule.threshold_tier_1 or 0
    tier_2 = rule.threshold_tier_2 or 0
    if tier_1 and participants <= tier_1:
        return f"{quantity} {singular if quantity == 1 else name.lower()} for events up to {tier_1} participants"
    if tier_2 and participants <= tier_2:
        return f"{quantity} {singular if quantity == 1 else name.lower()} for events up to {tier_2} participants"
    return f"{quantity} {singular if quantity == 1 else name.lower()} for events over {tier_2 or tier_1} participants"


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
# Explanation builders
# ---------------------------------------------------------------------------

def _explain(key: str, spec, quantity: int, participants: int) -> tuple[str, str]:
    """Return ``(reason, calculation)`` for one recommended category.

    ``reason`` is a human sentence explaining *why* the quantity was chosen;
    ``calculation`` traces the arithmetic used to get it.
    """
    singular, plural = _UNIT_NOUNS[key]

    # Fixed quantity (e.g. MEETING asks for exactly 1 microphone).
    if spec is not True:
        noun = singular if spec == 1 else plural
        return (
            f"Fixed allocation for this event type: {spec} {noun}.",
            f"{spec} × 1",
        )

    if key == "chairs":
        return (
            f"1 {singular} per participant",
            f"{participants} × 1",
        )
    if key == "tables":
        groups = math.ceil(participants / 10) if participants else 1
        return (
            f"1 {singular} per 10 participants, rounded up",
            f"ceil({participants} / 10) = {groups}",
        )
    if key == "sound":
        if quantity == 0:
            return ("Not needed for this event size", "")
        if quantity == 1:
            return ("1 sound system covers events up to 200 participants", "1 × 1")
        return (
            "2 sound systems for very large events",
            "participants > 200 → 2",
        )
    if key == "microphones":
        tiers = (
            (60, 1, "small events"),
            (200, 2, "medium events"),
            (400, 4, "large events"),
        )
        for limit, qty, label in tiers:
            if participants <= limit:
                return (
                    f"1 {singular} for {label} (up to {limit} participants)",
                    f"{participants} participants → {qty}",
                )
        return (
            f"6 {plural} for very large events",
            f"{participants} participants → 6",
        )
    # projector and any future fixed-1 rule
    return ("1 projector for this event type", "1 × 1")


# ---------------------------------------------------------------------------
# Recommendation builder
# ---------------------------------------------------------------------------

def _evaluate_quantities(profile: dict, participants: int) -> dict:
    """category key -> (rule spec, rule quantity) pre-availability."""
    quantities = {}
    for key in _CATEGORY_KEYS:
        spec = profile.get(key)
        if spec is False or spec is None:
            continue
        if spec is True:
            quantities[key] = (spec, _BASE_RULES[key](participants))
        else:
            quantities[key] = (spec, int(spec))
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
            "quantity": int,      # rule-based recommendation (uncapped)
            "available": int,     # units available during the window
            "recommended": int,   # min(quantity, available) — safe prefill
            "status": "AVAILABLE" | "PARTIAL" | "UNAVAILABLE",
            "can_fulfill": bool,  # recommendation fits the window's stock
            "reason": str,        # why this quantity
            "calculation": str,   # the exact arithmetic
            "warning": str,       # only when recommendation exceeds stock
        }

    ``quantity`` is always the rule output — never inventory — while
    ``recommended`` is the availability-capped value safe to prefill into the
    request form. When no schedule window is given, availability is computed
    against all current reservations (a conservative at-a-glance view).

    Staff-configured ``RecommendationRule`` rows (Django admin) take
    precedence over the built-in profile rules: a matching DB rule replaces
    the built-in quantity for its category, and categories not present in
    the built-in profile can be introduced purely through DB rules.

    Missing participants (0/None) skips participant-based calculation entirely
    and returns no recommendations rather than guessing quantities.
    """
    # No participant count → no participant-based quantities. This matches the
    # create-time validation (expected_participants >= 1) so the wizard never
    # shows recommendations that could not be requested.
    participants = int(participants or 0)
    if participants < 1:
        return []

    profile = _EVENT_PROFILES.get(event_type or "OTHER", _EVENT_PROFILES["OTHER"])

    facility_type = None
    if facility_id is not None:
        facility_type = Facility.objects.filter(pk=facility_id).values_list(
            "facility_type", flat=True
        ).first()

    profile = _adjust_profile(profile, facility_type, purpose)
    quantities = _evaluate_quantities(profile, participants)

    availability = equipment_availability_map(target_date, start_time, end_time)

    # ------------------------------------------------------------------
    # Build the recommendation set. DB rules (staff-configured) win over
    # built-ins for the categories they cover; built-in profile rules fill
    # in everything else. Entries are keyed by category id so a category is
    # recommended at most once.
    # ------------------------------------------------------------------
    selected: dict[int, dict] = {}

    covered = set()
    for rule in _matching_rules(event_type or "OTHER", facility_type, participants):
        if rule.category_id in covered:
            continue  # a more specific rule already covers this category
        covered.add(rule.category_id)
        quantity, calculation = _rule_quantity(rule, participants)
        selected[rule.category_id] = {
            "category": rule.category,
            "quantity": quantity,
            "reason": _rule_reason(rule, quantity, participants),
            "calculation": calculation,
        }

    for key in _CATEGORY_KEYS:
        spec, quantity = quantities.get(key, (None, 0))
        if not quantity:
            continue
        category = EquipmentCategory.objects.filter(
            name__icontains=_CATEGORY_KEYWORDS[key]
        ).first()
        if not category or category.id in covered:
            continue
        reason, calculation = _explain(key, spec, quantity, participants)
        selected[category.id] = {
            "category": category,
            "quantity": quantity,
            "reason": reason,
            "calculation": calculation,
        }

    recommendations = []
    for entry in sorted(selected.values(), key=lambda item: item["category"].name):
        category = entry["category"]
        quantity = entry["quantity"]
        if not quantity:
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

        warning = None
        if available < quantity:
            warning = (
                f"Only {available} of the recommended {quantity} units are "
                f"currently available."
            )

        recommendations.append(
            {
                "equipment_id": equipment.id,
                "name": equipment.name,
                "category": category.name,
                "quantity": quantity,
                "available": available,
                "recommended": recommended,
                "status": status,
                "can_fulfill": available >= quantity,
                "reason": entry["reason"],
                "calculation": entry["calculation"],
                "warning": warning,
            }
        )
    return recommendations
