from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import Organization, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Management for internal and external organizations.

    Internal organizations (CAS, CTED, …) are seeded, always APPROVED, and
    are managed through the active/inactive actions. External organizations
    keep the verification workflow. Deleting an organization that is still
    referenced by users or reservations is refused — deactivate it instead so
    historical records survive.
    """

    list_display = (
        "organization_code",
        "acronym",
        "organization_name",
        "organization_type",
        "verification_status",
        "is_active",
        "member_count_admin",
        "contact_person",
        "contact_email",
        "created_at",
    )
    list_filter = ("organization_type", "verification_status", "is_active")
    search_fields = (
        "organization_code",
        "acronym",
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
    actions = [
        "approve_organizations",
        "reject_organizations",
        "suspend_organizations",
        "deactivate_organizations",
        "reactivate_organizations",
    ]
    fieldsets = (
        (
            "Organization",
            {
                "fields": (
                    "organization_code",
                    "acronym",
                    "organization_name",
                    "organization_type",
                    "is_active",
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

    def _is_referenced(self, organization) -> bool:
        """True when users or reservations still point at this organization."""
        return (
            organization.members.exists()
            or organization.organization_reservations.exists()
        )

    def delete_model(self, request, obj):
        if self._is_referenced(obj):
            self.message_user(
                request,
                (
                    f"'{obj}' is referenced by existing users or reservations "
                    "and was not deleted. Deactivate it instead."
                ),
                level=messages.ERROR,
            )
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        protected = [obj.pk for obj in queryset if self._is_referenced(obj)]
        if protected:
            self.message_user(
                request,
                (
                    f"{len(protected)} organization(s) are referenced by existing "
                    "users or reservations and were not deleted. Deactivate them instead."
                ),
                level=messages.ERROR,
            )
            queryset = queryset.exclude(pk__in=protected)
        super().delete_queryset(request, queryset)

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

    @admin.action(description="Deactivate selected organizations")
    def deactivate_organizations(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} organization(s) deactivated.")

    @admin.action(description="Reactivate selected organizations")
    def reactivate_organizations(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} organization(s) reactivated.")


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
