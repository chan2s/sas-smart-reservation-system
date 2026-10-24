from django.contrib import admin

from .models import ApprovalLetter


@admin.register(ApprovalLetter)
class ApprovalLetterAdmin(admin.ModelAdmin):
    """Operational view of approval letters (create stays workflow-driven).

    Letters are never created here by hand — approval does that automatically.
    The admin exists so staff can inspect state and regenerate a letter if its
    post-commit creation ever failed.
    """

    list_display = (
        "letter_id",
        "reservation",
        "status",
        "requester_name",
        "signed_at",
        "email_status",
        "emailed_at",
        "created_at",
    )
    list_filter = ("status", "email_status")
    search_fields = ("letter_id", "reservation__reservation_id", "requester_name")
    readonly_fields = (
        "letter_id",
        "reservation",
        "status",
        "requester",
        "requester_name",
        "requester_email",
        "signatory",
        "signed_at",
        "pdf_file",
        "docx_file",
        "email_status",
        "emailed_at",
        "email_error",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
