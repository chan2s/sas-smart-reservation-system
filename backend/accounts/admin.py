from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Organization, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Staff verification workflow for external organizations."""

    list_display = (
        "organization_code",
        "organization_name",
        "organization_type",
        "verification_status",
        "member_count_admin",
        "contact_person",
        "contact_email",
        "created_at",
    )
    list_filter = ("verification_status", "organization_type")
    search_fields = (
        "organization_code",
        "organization_name",
        "contact_person",
        "contact_email",
    )
    readonly_fields = (
        "organization_code",
        "created_at",
        "updated_at",
        "reviewed_at",
        "member_count_admin",
    )
    actions = ["approve_organizations", "reject_organizations", "suspend_organizations"]
    fieldsets = (
        (
            "Organization",
            {
                "fields": (
                    "organization_code",
                    "organization_name",
                    "organization_type",
                    "purpose",
                )
            },
        ),
        (
            "Contact information",
            {"fields": ("contact_person", "contact_email", "contact_number", "address")},
        ),
        (
            "Verification",
            {
                "fields": (
                    "verification_status",
                    "review_notes",
                    "reviewed_by",
                    "reviewed_at",
                    "created_by",
                    "member_count_admin",
                ),
                "description": (
                    "Members of a Pending, Rejected, or Suspended organization "
                    "cannot submit facility reservations."
                ),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Members")
    def member_count_admin(self, obj):
        return obj.members.count() if obj.pk else 0

    def _set_status(self, request, queryset, status, description):
        from django.utils import timezone

        updated = queryset.update(
            verification_status=status,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} organization(s) {description}.")
        return updated

    @admin.action(description="Approve selected organizations")
    def approve_organizations(self, request, queryset):
        self._set_status(
            request, queryset, Organization.VerificationStatus.APPROVED, "approved"
        )

    @admin.action(description="Reject selected organizations")
    def reject_organizations(self, request, queryset):
        self._set_status(
            request, queryset, Organization.VerificationStatus.REJECTED, "rejected"
        )

    @admin.action(description="Suspend selected organizations")
    def suspend_organizations(self, request, queryset):
        self._set_status(
            request, queryset, Organization.VerificationStatus.SUSPENDED, "suspended"
        )


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "display_name",
        "role",
        "affiliation",
        "organization",
        "organization_ref",
        "is_active",
    )
    list_filter = ("role", "affiliation", "is_active")
    search_fields = UserAdmin.search_fields + ("organization", "organization_ref__organization_name")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Institution",
            {"fields": ("role", "affiliation", "organization", "organization_ref", "avatar")},
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Institution", {"fields": ("role", "affiliation", "organization")}),
    )
