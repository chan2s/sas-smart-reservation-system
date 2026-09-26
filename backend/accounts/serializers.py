from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AuditLog, EmailOTPVerification, Organization
from . import twofa

User = get_user_model()


# ---------------------------------------------------------------------------
# External organizations
# ---------------------------------------------------------------------------


class OrganizationBriefSerializer(serializers.ModelSerializer):
    """Minimal organization identity — embedded in user profile payloads."""

    organization_type_label = serializers.CharField(
        source="get_organization_type_display", read_only=True
    )
    verification_status_label = serializers.CharField(
        source="get_verification_status_display", read_only=True
    )

    class Meta:
        model = Organization
        fields = (
            "id",
            "organization_code",
            "organization_name",
            "organization_type",
            "organization_type_label",
            "verification_status",
            "verification_status_label",
        )


class OrganizationMemberSerializer(serializers.ModelSerializer):
    """A user belonging to an organization (staff-facing only)."""

    display_name = serializers.CharField(read_only=True)
    affiliation_label = serializers.CharField(
        source="get_affiliation_display", read_only=True
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "display_name",
            "email",
            "role",
            "affiliation",
            "affiliation_label",
            "is_active",
            "date_joined",
        )


class OrganizationListSerializer(OrganizationBriefSerializer):
    """Row shape for the staff verification queue."""

    member_count = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.display_name", read_only=True, default=""
    )

    class Meta(OrganizationBriefSerializer.Meta):
        fields = OrganizationBriefSerializer.Meta.fields + (
            "contact_person",
            "contact_email",
            "contact_number",
            "member_count",
            "created_by_name",
            "created_at",
        )


class OrganizationSerializer(OrganizationListSerializer):
    """Full organization record, including its members (staff-facing)."""

    reviewed_by_name = serializers.CharField(
        source="reviewed_by.display_name", read_only=True, default=""
    )
    members = OrganizationMemberSerializer(many=True, read_only=True)

    class Meta(OrganizationListSerializer.Meta):
        fields = OrganizationListSerializer.Meta.fields + (
            "address",
            "purpose",
            "review_notes",
            "reviewed_by_name",
            "reviewed_at",
            "members",
            "updated_at",
        )


class OrganizationRegistrationSerializer(serializers.ModelSerializer):
    """Self-service registration payload from the affiliation form."""

    class Meta:
        model = Organization
        fields = (
            "organization_name",
            "organization_type",
            "contact_person",
            "contact_email",
            "contact_number",
            "address",
            "purpose",
        )


class AffiliationUpdateSerializer(serializers.Serializer):
    """Choose an affiliation, and register an organization when external.

    The organization is never chosen by id from the client — an external
    requester either reuses the organization their profile is already
    attached to, or creates a new one here (which is then bound to them).
    """

    affiliation = serializers.ChoiceField(choices=User.Affiliation.choices)
    organization = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        help_text="NORSU office/department, for internal affiliations.",
    )
    # External organization registration fields.
    organization_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    organization_type = serializers.ChoiceField(
        choices=Organization.OrganizationType.choices, required=False
    )
    contact_person = serializers.CharField(required=False, allow_blank=True, max_length=120)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_number = serializers.CharField(required=False, allow_blank=True, max_length=32)
    address = serializers.CharField(required=False, allow_blank=True, max_length=240)
    purpose = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["affiliation"] != User.Affiliation.EXTERNAL_ORGANIZATION:
            return attrs
        request = self.context.get("request")
        user = getattr(request, "user", None)
        # Already bound to an organization → registration details unnecessary.
        if user is not None and user.organization_ref_id:
            return attrs
        if not (attrs.get("organization_name") or "").strip():
            raise serializers.ValidationError(
                {"organization_name": "Organization name is required."}
            )
        if not (attrs.get("contact_person") or "").strip():
            raise serializers.ValidationError(
                {"contact_person": "Representative / contact person is required."}
            )
        if not (attrs.get("contact_email") or "").strip():
            raise serializers.ValidationError(
                {"contact_email": "Organization email is required."}
            )
        if not attrs.get("organization_type"):
            raise serializers.ValidationError(
                {"organization_type": "Organization type is required."}
            )
        return attrs


class OrganizationVerificationSerializer(serializers.Serializer):
    """Staff verification decision for an organization."""

    class Action:
        APPROVE = "approve"
        REJECT = "reject"
        SUSPEND = "suspend"
        REACTIVATE = "reactivate"

    ACTIONS = (Action.APPROVE, Action.REJECT, Action.SUSPEND, Action.REACTIVATE)

    # Maps a staff action to the resulting verification status.
    STATUS_FOR_ACTION = {
        Action.APPROVE: Organization.VerificationStatus.APPROVED,
        Action.REJECT: Organization.VerificationStatus.REJECTED,
        Action.SUSPEND: Organization.VerificationStatus.SUSPENDED,
        Action.REACTIVATE: Organization.VerificationStatus.APPROVED,
    }

    AUDIT_ACTION_FOR_STATUS = {
        Organization.VerificationStatus.APPROVED: AuditLog.Action.ORGANIZATION_APPROVED,
        Organization.VerificationStatus.REJECTED: AuditLog.Action.ORGANIZATION_REJECTED,
        Organization.VerificationStatus.SUSPENDED: AuditLog.Action.ORGANIZATION_SUSPENDED,
    }

    action = serializers.ChoiceField(choices=ACTIONS)
    notes = serializers.CharField(required=False, allow_blank=True)


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    affiliation_label = serializers.CharField(
        source="get_affiliation_display", read_only=True
    )
    organization_ref = OrganizationBriefSerializer(read_only=True)
    organization_verification_status = serializers.CharField(read_only=True)
    has_affiliation = serializers.BooleanField(read_only=True)
    can_create_reservations = serializers.BooleanField(read_only=True)
    reservation_block_reason = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "organization",
            "display_name",
            "affiliation",
            "affiliation_label",
            "organization_ref",
            "organization_verification_status",
            "has_affiliation",
            "can_create_reservations",
            "reservation_block_reason",
        )
        read_only_fields = (
            "role",
            "affiliation",
            "organization_ref",
        )


class RegisterSerializer(serializers.ModelSerializer):
    """Self-service account creation, optionally with an affiliation.

    Internal NORSU affiliations simply record the free-text unit. An EXTERNAL
    ORGANIZATION registration additionally creates the organization in the
    ``PENDING`` state and binds it to the new account — the same rules as the
    affiliation endpoint, just folded into sign-up so the user never has to
    repeat the details after registering.

    This serializer never issues credentials: registration is deliberately
    separate from authentication, and the view returns a plain user payload
    (no tokens). The SPA must send external registrants to the login page.
    """

    password = serializers.CharField(write_only=True, min_length=8)
    affiliation = serializers.ChoiceField(
        choices=User.Affiliation.choices, required=False, allow_blank=True
    )
    # External organization registration fields.
    organization_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    organization_type = serializers.ChoiceField(
        choices=Organization.OrganizationType.choices, required=False, allow_blank=True
    )
    contact_person = serializers.CharField(required=False, allow_blank=True, max_length=120)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_number = serializers.CharField(required=False, allow_blank=True, max_length=32)
    address = serializers.CharField(required=False, allow_blank=True, max_length=240)
    purpose = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "username",
            "password",
            "first_name",
            "last_name",
            "email",
            "organization",
            "affiliation",
            "organization_name",
            "organization_type",
            "contact_person",
            "contact_email",
            "contact_number",
            "address",
            "purpose",
        )

    def validate(self, attrs):
        if attrs.get("affiliation") != User.Affiliation.EXTERNAL_ORGANIZATION:
            return attrs
        if not (attrs.get("organization_name") or "").strip():
            raise serializers.ValidationError(
                {"organization_name": "Organization name is required."}
            )
        if not (attrs.get("contact_person") or "").strip():
            raise serializers.ValidationError(
                {"contact_person": "Representative / contact person is required."}
            )
        if not (attrs.get("contact_email") or "").strip():
            raise serializers.ValidationError(
                {"contact_email": "Organization email is required."}
            )
        if not attrs.get("organization_type"):
            raise serializers.ValidationError(
                {"organization_type": "Organization type is required."}
            )
        return attrs

    _ORGANIZATION_FIELDS = (
        "organization_name",
        "organization_type",
        "contact_person",
        "contact_email",
        "contact_number",
        "address",
        "purpose",
    )

    def create(self, validated_data):
        password = validated_data.pop("password")
        affiliation = validated_data.pop("affiliation", "") or ""
        organization_fields = {
            field: validated_data.pop(field)
            for field in self._ORGANIZATION_FIELDS
            if validated_data.get(field)
        }
        user = User(**validated_data)
        user.set_password(password)
        if affiliation:
            user.affiliation = affiliation
        user.save()

        if affiliation == User.Affiliation.EXTERNAL_ORGANIZATION:
            organization = Organization.objects.create(
                created_by=user,
                verification_status=Organization.VerificationStatus.PENDING,
                **organization_fields,
            )
            user.organization_ref = organization
            user.save(update_fields=["organization_ref"])
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """JWT login that also returns the authenticated user profile.

    Two-factor handling: when the account has a confirmed TOTP device the
    response contains ``mfa_required`` + a short-lived ``mfa_token`` and NO
    tokens — the SPA must complete ``/api/auth/2fa/verify-login/`` before it
    is authenticated.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        # First-time Google accounts must finish email OTP verification
        # before ANY authentication — password login on such an account is
        # refused (it has no usable password anyway, but block defensively).
        if EmailOTPVerification.objects.filter(
            user=self.user, verified_at__isnull=True
        ).exists():
            raise serializers.ValidationError(
                "Finish verifying your email from the Google sign-in screen "
                "before signing in with a password."
            )
        if twofa.has_2fa(self.user):
            return {
                "mfa_required": True,
                "mfa_token": twofa.issue_challenge(self.user),
            }
        AuditLog.record(
            self.user,
            AuditLog.Action.LOGIN,
            object_type="auth",
            object_repr="Password sign-in",
        )
        data["user"] = UserSerializer(self.user).data
        return data