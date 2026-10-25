"""Serializers for the approval-letter API.

The list/detail serializer serves the signatory dashboard; the embedded
summary is attached to the reservation detail payload so requesters (and
staff) see the letter's state on the reservation they already have open.
"""

from rest_framework import serializers

from .models import ApprovalLetter
from .documents import build_letter_context


class ApprovalLetterSerializer(serializers.ModelSerializer):
    """Full letter payload for the signatory dashboard."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    email_status_label = serializers.CharField(
        source="get_email_status_display", read_only=True
    )
    email_attempted_at = serializers.DateTimeField(read_only=True)
    signatory_name = serializers.SerializerMethodField()
    signatory_position = serializers.SerializerMethodField()
    requester_email = serializers.CharField(read_only=True)
    # Reservation information block.
    reservation_reference = serializers.CharField(
        source="reservation.reservation_id", read_only=True
    )
    reservation_pk = serializers.IntegerField(source="reservation.pk", read_only=True)
    event_name = serializers.CharField(source="reservation.event_name", read_only=True)
    facility_name = serializers.CharField(source="reservation.facility.name", read_only=True)
    reservation_date = serializers.DateField(source="reservation.date", read_only=True)
    start_time = serializers.TimeField(source="reservation.start_time", read_only=True)
    end_time = serializers.TimeField(source="reservation.end_time", read_only=True)
    purpose = serializers.CharField(source="reservation.purpose", read_only=True)
    requester_name = serializers.CharField(source="reservation.requester_display_name", read_only=True)
    organization = serializers.CharField(source="reservation.organization", read_only=True)
    approved_at = serializers.DateTimeField(source="reservation.approved_at", read_only=True)

    has_signed_pdf = serializers.BooleanField(read_only=True)
    has_signed_docx = serializers.BooleanField(read_only=True)
    can_retry_email = serializers.BooleanField(read_only=True)
    can_sign = serializers.SerializerMethodField()

    preview_url = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()
    docx_url = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalLetter
        fields = (
            "id",
            "letter_id",
            "status",
            "status_label",
            # Reservation information.
            "reservation_pk",
            "reservation_reference",
            "event_name",
            "facility_name",
            "reservation_date",
            "start_time",
            "end_time",
            "purpose",
            "requester_name",
            "requester_email",
            "organization",
            "approved_at",
            # Signatory information.
            "signatory_name",
            "signatory_position",
            "signatory",
            "signed_at",
            # Documents.
            "has_signed_pdf",
            "has_signed_docx",
            "preview_url",
            "pdf_url",
            "docx_url",
            # Email delivery.
            "email_status",
            "email_status_label",
            "email_attempted_at",
            "emailed_at",
            "email_error",
            "can_retry_email",
            "can_sign",
            "created_at",
            "updated_at",
        )

    def get_signatory_name(self, obj) -> str:
        from .constants import SIGNATORY_NAME

        return SIGNATORY_NAME

    def get_signatory_position(self, obj) -> str:
        from .constants import SIGNATORY_POSITION

        return SIGNATORY_POSITION

    def get_can_sign(self, obj) -> bool:
        user = self.context.get("request").user if self.context.get("request") else None
        return bool(
            obj.status == ApprovalLetter.Status.PENDING_SIGNATURE
            and user is not None
            and getattr(user, "is_sas_staff", False)
            and getattr(user, "is_approval_signatory", False)
        )

    def get_preview_url(self, obj) -> str:
        return f"/api/approval-letters/{obj.pk}/preview/"

    def get_pdf_url(self, obj) -> str:
        return f"/api/approval-letters/{obj.pk}/download/pdf/"

    def get_docx_url(self, obj) -> str:
        return f"/api/approval-letters/{obj.pk}/download/docx/"


class ReservationApprovalLetterSummarySerializer(serializers.ModelSerializer):
    """Embedded in the reservation detail payload (requester-facing).

    Exposes exactly what a requester needs: that a letter exists, its status,
    and how to download the signed documents. Document URLs only resolve for
    the letter's own requester or SAS staff — the download endpoints enforce
    that server-side; the flags here merely avoid rendering dead buttons.
    """

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    email_status_label = serializers.CharField(
        source="get_email_status_display", read_only=True
    )
    email_attempted_at = serializers.DateTimeField(read_only=True)
    signatory_name = serializers.SerializerMethodField()
    signatory_position = serializers.SerializerMethodField()
    has_signed_pdf = serializers.BooleanField(read_only=True)
    has_signed_docx = serializers.BooleanField(read_only=True)
    can_retry_email = serializers.BooleanField(read_only=True)
    pdf_url = serializers.SerializerMethodField()
    docx_url = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalLetter
        fields = (
            "id",
            "letter_id",
            "status",
            "status_label",
            "signatory_name",
            "signatory_position",
            "signed_at",
            "has_signed_pdf",
            "has_signed_docx",
            "can_retry_email",
            "pdf_url",
            "docx_url",
            "email_status",
            "email_status_label",
            "email_attempted_at",
            "emailed_at",
            "email_error",
        )

    def get_signatory_name(self, obj) -> str:
        from .constants import SIGNATORY_NAME

        return SIGNATORY_NAME

    def get_signatory_position(self, obj) -> str:
        from .constants import SIGNATORY_POSITION

        return SIGNATORY_POSITION

    def get_pdf_url(self, obj) -> str:
        return f"/api/approval-letters/{obj.pk}/download/pdf/"

    def get_docx_url(self, obj) -> str:
        return f"/api/approval-letters/{obj.pk}/download/docx/"


class ApprovalLetterPreviewSerializer(serializers.Serializer):
    """Structured letter content for a readable HTML preview in the SPA.

    The signatory's dashboard renders this as a document-style preview; the
    PDF/DOCX renderers remain the authoritative document formats.
    """

    letter_id = serializers.CharField()
    status = serializers.CharField()
    issued_date = serializers.CharField()
    requester_name = serializers.CharField()
    organization = serializers.CharField()
    reservation_reference = serializers.CharField()
    event_name = serializers.CharField()
    facility_name = serializers.CharField()
    reservation_date = serializers.CharField()
    reservation_start = serializers.CharField()
    reservation_end = serializers.CharField()
    purpose = serializers.CharField()
    expected_participants = serializers.IntegerField()
    resources = serializers.ListField(child=serializers.CharField())
    facility_rules = serializers.ListField(child=serializers.CharField())
    estimated_total = serializers.CharField()
    is_external = serializers.BooleanField()
    signatory_name = serializers.CharField()
    signatory_position = serializers.CharField()
    signed_at = serializers.DateTimeField()
    is_signed = serializers.BooleanField()
    test_signature_disclaimer = serializers.CharField()
    institution = serializers.CharField()
    issuing_office = serializers.CharField()
    system_name = serializers.CharField()

    @classmethod
    def from_letter(cls, letter) -> dict:
        context = build_letter_context(letter)
        return {
            "letter_id": context["letter_id"],
            "status": letter.status,
            "issued_date": context["issued_date"],
            "requester_name": context["requester_name"],
            "organization": context["organization"],
            "reservation_reference": context["reservation_reference"],
            "event_name": context["event_name"],
            "facility_name": context["facility_name"],
            "reservation_date": context["reservation_date"],
            "reservation_start": context["reservation_start"],
            "reservation_end": context["reservation_end"],
            "purpose": context["purpose"],
            "expected_participants": context["expected_participants"],
            "resources": context["resources"],
            "facility_rules": context["facility_rules"],
            "estimated_total": context["estimated_total"],
            "is_external": context["is_external"],
            "signatory_name": context["signatory_name"],
            "signatory_position": context["signatory_position"],
            "signed_at": context["signed_at"],
            "is_signed": letter.is_signed,
            "test_signature_disclaimer": context["test_signature_disclaimer"],
            "institution": context["institution"],
            "issuing_office": context["issuing_office"],
            "system_name": context["system_name"],
        }
