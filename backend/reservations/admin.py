from django.contrib import admin
from django.utils.html import format_html

from .models import (
    InspectionReport,
    PricingRule,
    Reservation,
    ReservationEvent,
    ReservationFee,
    ReservationItem,
    RescheduleRequest,
)


@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    """Staff-editable external-organization rates (no code changes needed)."""

    list_display = (
        "fee_type",
        "display_label_admin",
        "facility_type",
        "equipment_category",
        "rental_period",
        "unit",
        "unit_price",
        "is_active",
        "updated_at",
    )
    list_filter = ("fee_type", "is_active", "facility_type", "unit")
    search_fields = ("label", "equipment_category__name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "What is charged",
            {
                "fields": ("fee_type", "label", "rental_period", "unit_price", "unit", "included_hours"),
                "description": (
                    "One official rate table applies to every reservation. "
                    "External reservations pay these rates; internal reservations "
                    "use them as reference values and receive full waivers."
                ),
            },
        ),
        (
            "What it applies to",
            {
                "fields": ("facility_type", "equipment_category"),
                "description": (
                    "Facility rates match facility type and rental period. "
                    "Equipment and operator rates match the unified equipment category."
                ),
            },
        ),
        ("Status", {"fields": ("is_active", "created_at", "updated_at")}),
    )

    @admin.display(description="Applies to")
    def display_label_admin(self, rule: PricingRule) -> str:
        return rule.display_label


class ReservationItemInline(admin.TabularInline):
    model = ReservationItem
    extra = 0


class ReservationFeeInline(admin.TabularInline):
    """Read-only snapshot of the fees charged for this reservation."""

    model = ReservationFee
    extra = 0
    can_delete = False
    fields = ("fee_type", "description", "quantity", "unit", "unit_price", "subtotal")
    readonly_fields = fields


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
        "affiliation_admin",
        "organization_admin",
        "payment_status_admin",
        "approval_email",
    )
    list_filter = ("status", "event_type", "requester_type", "date", "payment_type")
    search_fields = (
        "reservation_id",
        "event_name",
        "organization",
        "organization_ref__organization_name",
        "organization_ref__organization_code",
        "requester__affiliation",
    )
    inlines = [ReservationItemInline, ReservationFeeInline, ReservationEventInline]
    readonly_fields = (
        "approval_email_status",
        "estimated_total",
        "total_price_admin",
        "payment_required_amount",
        "payment_status_admin",
        "remaining_balance_admin",
        "checkin_code",
        "reminder_sent_at",
        "reminder_email_sent_at",
        "reminder_email_claimed_at",
        "no_show_marked_at",
        "no_show_marked_by",
        "operator_assigned_at",
    )
    fieldsets = (
        (
            "Requester",
            {
                "fields": (
                    "requester_type",
                    "requester",
                    "organization_ref",
                    "organization",
                    "organization_type",
                    "contact_person",
                    "contact_email",
                    "created_by",
                ),
                "description": (
                    "Affiliation and organization are resolved from the "
                    "requester's profile; the text fields are display snapshots."
                ),
            },
        ),
        (
            "Event",
            {
                "fields": (
                    "event_name",
                    "event_type",
                    "purpose",
                    "description",
                    "expected_participants",
                    "special_requirements",
                )
            },
        ),
        ("Schedule", {"fields": ("facility", "date", "start_time", "end_time")}),
        (
            "Payment (external organizations only)",
            {
                "fields": (
                    "total_price_admin",
                    "payment_type",
                    "payment_required_amount",
                    "amount_paid",
                    "payment_status_admin",
                    "remaining_balance_admin",
                ),
                "description": (
                    "The required amount is calculated automatically from the "
                    "rental total: down payment is 50%, full payment is 100%. "
                    "Recording or recalculating a payment never changes the "
                    "amount already received."
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "notes",
                    "rejection_reason",
                    "approved_by",
                    "approved_at",
                    "approval_email_status",
                    "reminder_sent_at",
                    "reminder_email_sent_at",
                    "reminder_email_claimed_at",
                    "no_show_marked_at",
                    "no_show_marked_by",
                    "rebooked_from",
                    "estimated_total",
                ),
                "description": (
                    "NO_SHOW is recorded by an administrator through the "
                    "reservation page (or API) after the event has ended; "
                    "the timestamp and administrator below are audit facts."
                ),
            },
        ),
        (
            "Check-in",
            {
                "fields": (
                    "checkin_code",
                    "checked_in_at",
                    "checked_out_at",
                    "early_check_in_override",
                )
            },
        ),
        (
            "Sound System Package - Operator Assignment",
            {
                "fields": ("assigned_operator", "operator_assigned_at"),
                "description": (
                    "Assign a qualified Sound System Operator to this reservation. "
                    "This field is used when the reservation includes the Sound System Package."
                ),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ["retry_approval_email", "recalculate_fees"]

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None and obj.requester_type != Reservation.RequesterType.EXTERNAL:
            return tuple(
                (title, options)
                for title, options in fieldsets
                if not title.startswith("Payment")
            )
        return fieldsets

    @admin.display(description="Total reservation price")
    def total_price_admin(self, obj):
        if obj.requester_type != Reservation.RequesterType.EXTERNAL:
            return "—"
        return f"PHP {obj.estimated_total:,.2f}"

    @admin.display(description="Payment status")
    def payment_status_admin(self, obj):
        if obj.requester_type != Reservation.RequesterType.EXTERNAL:
            return "—"
        if not obj.payment_is_configured:
            return "Not configured"
        colors = {
            Reservation.PaymentStatus.UNPAID: "#b91c1c",
            Reservation.PaymentStatus.PARTIALLY_PAID: "#c2410c",
            Reservation.PaymentStatus.FULLY_PAID: "#15803d",
        }
        return format_html(
            '<strong style="color:{};">{}</strong>',
            colors[obj.payment_status],
            obj.payment_status_label,
        )

    @admin.display(description="Remaining balance")
    def remaining_balance_admin(self, obj):
        if (
            obj.requester_type != Reservation.RequesterType.EXTERNAL
            or not obj.payment_is_configured
        ):
            return "—"
        return f"PHP {obj.remaining_balance:,.2f}"

    @admin.display(description="Affiliation", ordering="requester__affiliation")
    def affiliation_admin(self, obj):
        return obj.affiliation_label

    @admin.display(description="Organization")
    def organization_admin(self, obj):
        if obj.organization_ref_id:
            return f"{obj.organization_ref.organization_name} ({obj.organization_ref.organization_code})"
        return obj.organization or "—"

    @admin.action(
        description="Recalculate external-organization fees from current rates"
    )
    def recalculate_fees(self, request, queryset):
        from .services.pricing import snapshot_reservation_fees

        updated = 0
        for reservation in queryset:
            snapshot_reservation_fees(reservation)
            updated += 1
        self.message_user(
            request, f"Recalculated estimated fees for {updated} reservation(s)."
        )

    @admin.display(description="Approval email")
    def approval_email(self, obj):
        if obj.status != "APPROVED":
            return "—"
        return obj.get_approval_email_status_display()

    @admin.action(description="Retry approval email for selected approved reservations")
    def retry_approval_email(self, request, queryset):
        from .services.workflow import resend_approval_email

        sent = failed = skipped = already = 0
        for reservation in queryset.select_related("requester", "created_by"):
            if reservation.status != Reservation.Status.APPROVED:
                continue
            if reservation.approval_email_status == Reservation.ApprovalEmailStatus.SENT:
                already += 1
                continue
            try:
                resend_approval_email(reservation, request.user)
            except Exception:
                failed += 1
                continue
            if reservation.approval_email_status == Reservation.ApprovalEmailStatus.SENT:
                sent += 1
            elif reservation.approval_email_status == Reservation.ApprovalEmailStatus.NO_EMAIL:
                skipped += 1
            else:
                failed += 1
        self.message_user(
            request,
            f"Approval email retry: {sent} sent, {failed} failed, "
            f"{skipped} skipped (no requester email), {already} already sent.",
        )


@admin.register(RescheduleRequest)
class RescheduleRequestAdmin(admin.ModelAdmin):
    """Read-only review queue; decisions run through the reservation API."""

    list_display = (
        "reservation",
        "current_schedule",
        "requested_schedule",
        "status",
        "submitted_at",
        "reviewed_by",
    )
    list_filter = ("status", "submitted_at")
    search_fields = (
        "reservation__reservation_id",
        "reservation__event_name",
        "reason",
    )
    readonly_fields = (
        "reservation",
        "requested_date",
        "requested_start_time",
        "requested_end_time",
        "reason",
        "status",
        "admin_message",
        "rejection_reason",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Current schedule")
    def current_schedule(self, obj):
        return (
            f"{obj.reservation.date} "
            f"{obj.reservation.start_time:%H:%M}–{obj.reservation.end_time:%H:%M}"
        )

    @admin.display(description="Requested schedule")
    def requested_schedule(self, obj):
        return (
            f"{obj.requested_date} "
            f"{obj.requested_start_time:%H:%M}–{obj.requested_end_time:%H:%M}"
        )

    def has_add_permission(self, request):
        return False


@admin.register(InspectionReport)
class InspectionReportAdmin(admin.ModelAdmin):
    list_display = ("reservation", "facility_condition", "equipment_returned", "created_at")
