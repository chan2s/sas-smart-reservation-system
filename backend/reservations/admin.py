from django import forms
from django.contrib import admin

from facilities.models import Facility

from .models import (
    InspectionReport,
    RecommendationRule,
    Reservation,
    ReservationEvent,
    ReservationItem,
)


class RecommendationRuleForm(forms.ModelForm):
    """Scope + calculation validation for the rule editor."""

    class Meta:
        model = RecommendationRule
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The DB columns are plain CharFields (blank = "applies to all"), so
        # give the editor real dropdowns with an explicit "all" option.
        self.fields["event_type"].choices = [("", "All event types")] + list(
            Reservation.EventType.choices
        )
        self.fields["facility_type"].choices = [("", "All facility types")] + list(
            Facility.FacilityType.choices
        )

    def clean(self):
        cleaned = super().clean()
        event_type = cleaned.get("event_type") or ""
        facility_type = cleaned.get("facility_type") or ""
        min_participants = cleaned.get("min_participants") or 0
        max_participants = cleaned.get("max_participants")

        if max_participants is not None and max_participants < min_participants:
            self.add_error(
                "max_participants",
                "Maximum participants must be greater than or equal to minimum participants.",
            )

        calculation_type = cleaned.get("calculation_type")
        if calculation_type == RecommendationRule.CalculationType.PER_GROUP:
            participants_per_unit = cleaned.get("participants_per_unit") or 0
            if participants_per_unit < 1:
                self.add_error(
                    "participants_per_unit",
                    "Group size must be at least 1 participant.",
                )

        if calculation_type == RecommendationRule.CalculationType.THRESHOLD:
            t1 = cleaned.get("threshold_tier_1")
            q1 = cleaned.get("threshold_quantity_1")
            t2 = cleaned.get("threshold_tier_2")
            q2 = cleaned.get("threshold_quantity_2")
            q3 = cleaned.get("threshold_quantity_3")
            if not t1 and not t2:
                self.add_error(
                    "threshold_tier_1",
                    "Set at least one threshold tier (tier 1 or tier 2).",
                )
            if t1 and q1 is None:
                self.add_error(
                    "threshold_quantity_1",
                    "Provide a quantity for tier 1.",
                )
            if t2 and q2 is None:
                self.add_error(
                    "threshold_quantity_2",
                    "Provide a quantity for tier 2.",
                )
            if t2 and t1 and t2 <= t1:
                self.add_error(
                    "threshold_tier_2",
                    "Tier 2 must be greater than tier 1.",
                )
            if (not t1 or q1 is None) and (not t2 or q2 is None) and q3 is None:
                self.add_error(
                    "threshold_quantity_3",
                    "Provide the quantity for events above the highest tier.",
                )

        return cleaned


@admin.register(RecommendationRule)
class RecommendationRuleAdmin(admin.ModelAdmin):
    form = RecommendationRuleForm
    list_display = (
        "category",
        "scope_summary",
        "calculation_type",
        "quantity_summary",
        "priority",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "calculation_type", "category", "event_type", "facility_type")
    search_fields = ("category__name", "explanation")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "What is recommended",
            {
                "fields": ("category", "explanation"),
                "description": (
                    "The rule's quantity replaces the built-in default for this "
                    "category. Categories with no rule keep their built-in behavior."
                ),
            },
        ),
        (
            "When it applies",
            {
                "fields": ("event_type", "facility_type", "min_participants", "max_participants"),
                "description": (
                    "Leave event type / facility type blank to cover all. More specific "
                    "rules win: exact event type (4) + exact facility type (2) + "
                    "participant range (1), then priority (lower wins)."
                ),
            },
        ),
        (
            "How the quantity is calculated",
            {
                "fields": (
                    "calculation_type",
                    "quantity_value",
                    "participants_per_unit",
                    "threshold_tier_1",
                    "threshold_quantity_1",
                    "threshold_tier_2",
                    "threshold_quantity_2",
                    "threshold_quantity_3",
                    "priority",
                ),
                "description": (
                    "Fixed quantity: always N units. Units per participant: participants × N. "
                    "Units per group: ceil(participants ÷ group size), at least 1. "
                    "Threshold tiers: up to tier 1 → q1, up to tier 2 → q2, above → q3."
                ),
            },
        ),
        ("Status", {"fields": ("is_active", "created_at", "updated_at")}),
    )

    actions = ["enable_rules", "disable_rules"]

    @admin.display(description="Applies to")
    def scope_summary(self, rule: RecommendationRule) -> str:
        parts = []
        parts.append(rule.get_event_type_display() if rule.event_type else "All event types")
        parts.append(rule.get_facility_type_display() if rule.facility_type else "All facilities")
        if rule.min_participants and rule.max_participants:
            parts.append(f"{rule.min_participants}–{rule.max_participants} participants")
        elif rule.min_participants:
            parts.append(f"≥ {rule.min_participants} participants")
        elif rule.max_participants:
            parts.append(f"≤ {rule.max_participants} participants")
        return " · ".join(parts)

    @admin.display(description="Quantity")
    def quantity_summary(self, rule: RecommendationRule) -> str:
        ct = rule.calculation_type
        if ct == RecommendationRule.CalculationType.FIXED:
            return f"Always {rule.quantity_value}"
        if ct == RecommendationRule.CalculationType.PER_PARTICIPANT:
            return f"{rule.quantity_value} per participant"
        if ct == RecommendationRule.CalculationType.PER_GROUP:
            return f"1 per {rule.participants_per_unit} participants (rounded up)"
        tiers = []
        if rule.threshold_tier_1:
            tiers.append(f"≤{rule.threshold_tier_1}: {rule.threshold_quantity_1}")
        if rule.threshold_tier_2:
            tiers.append(f"≤{rule.threshold_tier_2}: {rule.threshold_quantity_2}")
        fallback = rule.threshold_quantity_3 if rule.threshold_quantity_3 is not None else rule.quantity_value
        tiers.append(f"above: {fallback}")
        return "Tiered: " + ", ".join(tiers)

    @admin.action(description="Enable selected rules")
    def enable_rules(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} rule(s) enabled.")

    @admin.action(description="Disable selected rules")
    def disable_rules(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} rule(s) disabled.")


class ReservationItemInline(admin.TabularInline):
    model = ReservationItem
    extra = 0


class ReservationEventInline(admin.TabularInline):
    model = ReservationEvent
    extra = 0
    readonly_fields = ("event_type", "actor", "message", "created_at")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "reservation_id",
        "event_name",
        "facility",
        "date",
        "start_time",
        "status",
        "requester",
    )
    list_filter = ("status", "event_type", "date")
    search_fields = ("reservation_id", "event_name", "organization")
    inlines = [ReservationItemInline, ReservationEventInline]


@admin.register(InspectionReport)
class InspectionReportAdmin(admin.ModelAdmin):
    list_display = ("reservation", "facility_condition", "equipment_returned", "created_at")
