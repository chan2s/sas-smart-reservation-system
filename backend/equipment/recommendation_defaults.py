"""Seed defaults for per-assignment recommendation configuration.

The recommendation engine itself contains no built-in equipment list. These
defaults only give a freshly seeded database a useful starting point by
copying the profiles that used to live in code. Staff edit them per facility
afterwards, and only newly created assignments receive them.
"""

from .models import FacilityResource

ALL_EVENT_TYPES = [
    "SEMINAR",
    "MEETING",
    "WORKSHOP",
    "TRAINING",
    "SPORTS",
    "CONFERENCE",
    "RECOGNITION",
    "ORIENTATION",
    "CULTURAL",
    "ACADEMIC",
    "OTHER",
]

LEGACY_PROFILES = (
    (
        "chair",
        {
            "recommendation_calculation": FacilityResource.RecommendationCalculation.PER_PARTICIPANT,
            "recommendation_quantity": 1,
        },
    ),
    (
        "table",
        {
            "recommendation_calculation": FacilityResource.RecommendationCalculation.PER_GROUP,
            "recommendation_participants_per_unit": 10,
            "recommendation_quantity": 1,
            "recommendation_min_quantity": 1,
        },
    ),
    (
        "sound",
        {
            "recommendation_calculation": FacilityResource.RecommendationCalculation.THRESHOLD,
            "recommendation_tier_1": 29,
            "recommendation_tier_1_quantity": 0,
            "recommendation_tier_2": 199,
            "recommendation_tier_2_quantity": 1,
            "recommendation_quantity": 2,
            "recommendation_event_types": [
                event_type
                for event_type in ALL_EVENT_TYPES
                if event_type != "MEETING"
            ],
        },
    ),
    (
        "microphone",
        {
            "recommendation_calculation": FacilityResource.RecommendationCalculation.THRESHOLD,
            "recommendation_tier_1": 60,
            "recommendation_tier_1_quantity": 1,
            "recommendation_tier_2": 200,
            "recommendation_tier_2_quantity": 2,
            "recommendation_tier_3": 400,
            "recommendation_tier_3_quantity": 4,
            "recommendation_quantity": 6,
        },
    ),
    (
        "projector",
        {
            "recommendation_calculation": FacilityResource.RecommendationCalculation.FIXED,
            "recommendation_quantity": 1,
            "recommendation_event_types": [
                event_type
                for event_type in ALL_EVENT_TYPES
                if event_type not in {"SPORTS", "OTHER"}
            ],
        },
    ),
)


def default_config_for_category(category_name: str) -> dict | None:
    """Recommendation defaults for an equipment category, if one is known."""
    name = (category_name or "").lower()
    for keyword, profile in LEGACY_PROFILES:
        if keyword in name:
            return dict(profile)
    return None


def apply_default_recommendation_config(resource: FacilityResource) -> None:
    """Copy the legacy profile onto ``resource`` and save it (no-op if unknown)."""
    category = getattr(resource.equipment, "category", None)
    if category is None:
        return
    profile = default_config_for_category(category.name)
    if profile is None:
        return
    for field, value in profile.items():
        setattr(resource, field, value)
    resource.is_recommendable = True
    resource.save(update_fields=["is_recommendable", *profile.keys()])
