"""Move the previously hardcoded recommendation profiles into facility
equipment configuration.

Before this change the recommendation engine carried a built-in profile per
event type (chairs per participant, tables per ten participants, the 200+
sound-system rule, the microphone tiers, a projector). Those constants are
gone from the code; this one-off migration copies the equivalent rules onto
the existing ``FacilityResource`` assignments so current installations keep
their behaviour — now fully editable per facility and equipment item.

Assignments whose category does not match a known profile are left alone (not
recommendable), because inventing rules for them would be wrong.
"""

from django.db import migrations

#: Every reservation event type, spelled out because migrations must not
#: import live model enums.
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

#: category name keyword -> configuration migrated from the old built-in rule.
LEGACY_PROFILES = (
    (
        "chair",
        {
            "recommendation_calculation": "PER_PARTICIPANT",
            "recommendation_quantity": 1,
        },
    ),
    (
        "table",
        {
            "recommendation_calculation": "PER_GROUP",
            "recommendation_participants_per_unit": 10,
            "recommendation_quantity": 1,
            "recommendation_min_quantity": 1,
        },
    ),
    (
        "sound",
        {
            "recommendation_calculation": "THRESHOLD",
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
            "recommendation_calculation": "THRESHOLD",
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
            "recommendation_calculation": "FIXED",
            "recommendation_quantity": 1,
            "recommendation_event_types": [
                event_type
                for event_type in ALL_EVENT_TYPES
                if event_type not in {"SPORTS", "OTHER"}
            ],
        },
    ),
)


def _profile_for(category_name: str):
    name = (category_name or "").lower()
    for keyword, profile in LEGACY_PROFILES:
        if keyword in name:
            return profile
    return None


def seed_configuration(apps, schema_editor):
    FacilityResource = apps.get_model("equipment", "FacilityResource")
    rows = FacilityResource.objects.select_related("equipment__category")
    for resource in rows:
        category = getattr(resource.equipment, "category", None)
        if category is None:
            continue
        profile = _profile_for(category.name)
        if profile is None:
            continue
        FacilityResource.objects.filter(pk=resource.pk).update(
            is_recommendable=True, **profile
        )


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0018_facilityresource_is_recommendable_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_configuration, migrations.RunPython.noop),
    ]
