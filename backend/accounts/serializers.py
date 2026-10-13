from django.contrib.auth import get_user_model
from rest_framework import exceptions, serializers, status
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .login_activity import record_password_login
from .models import AuditLog, LoginActivity, Organization

User = get_user_model()


#: Shown to a person whose credentials were *correct* but whose account an
#: administrator has deactivated. The exact copy is part of the API contract:
#: the SPA's deactivated-account modal (DeactivatedAccountModal) renders the
#: same sentence, so the two must stay in sync.
DEACTIVATED_LOGIN_MESSAGE = (
    "This account has been deactivated. Please contact the SAS Office to "
    "restore access."
)


class DeactivatedAccountAuthenticationFailed(exceptions.AuthenticationFailed):
    """403 refusal for a correct password on a deactivated account.

    The body is a dict on purpose: DRF renders a dict ``detail`` verbatim, so
    the response carries both the human message and a machine-readable
    ``code: "account_deactivated"`` the SPA can key the modal on. Bad
    credentials never raise this — they keep simplejwt's generic 401, so the
    endpoint still never reveals which usernames exist.
    """

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = {
        "detail": DEACTIVATED_LOGIN_MESSAGE,
        "code": "account_deactivated",
    }


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
    display_name = serializers.CharField(read_only=True)
    is_internal = serializers.BooleanField(read_only=True)
    status_label = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = (
            "id",
            "organization_code",
            "acronym",
            "organization_name",
            "display_name",
            "organization_type",
            "organization_type_label",
            "is_internal",
            "is_active",
            "verification_status",
            "verification_status_label",
            "status_label",
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


# Affiliations that represent an internal (campus) user. These may link to a
# managed INTERNAL organization; an EXTERNAL_ORGANIZATION affiliation never
# may, and vice versa. Internal organizations are represented by an authorized
# faculty/staff member, so NORSU_OFFICE is no longer a selectable affiliation.
INTERNAL_AFFILIATIONS = (User.Affiliation.NORSU_FACULTY_STAFF,)


def resolve_internal_organization(value):
    """Validate a client-supplied id and return an active INTERNAL org.

    A client can send *which* managed organization it belongs to, but never
    the organization type — that always comes from this database record.
    """
    if value in (None, ""):
        return None
    try:
        organization_id = int(value)
    except (TypeError, ValueError):
        raise serializers.ValidationError(
            {"organization_id": "Select a valid internal organization."}
        )
    organization = Organization.objects.filter(
        pk=organization_id,
        is_active=True,
        organization_type=Organization.OrganizationType.INTERNAL,
    ).first()
    if organization is None:
        raise serializers.ValidationError(
            {"organization_id": "Select a valid, active internal organization."}
        )
    return organization


class AffiliationUpdateSerializer(serializers.Serializer):
    """Choose an affiliation, and register an organization when external.

    An external requester either reuses the organization their profile is
    already attached to, or creates a new one here (which is then bound to
    them). An internal requester may additionally pick a managed internal
    organization by id; the backend validates its type and active state.
    """

    affiliation = serializers.ChoiceField(
        choices=User.selectable_affiliation_choices()
    )
    organization = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        help_text="NORSU office/department, for internal affiliations.",
    )
    organization_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Managed internal organization selected by an internal user.",
    )
    # External organization registration fields.
    organization_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    organization_type = serializers.ChoiceField(
        choices=Organization.external_type_choices(), required=False
    )
    contact_person = serializers.CharField(required=False, allow_blank=True, max_length=120)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_number = serializers.CharField(required=False, allow_blank=True, max_length=32)
    address = serializers.CharField(required=False, allow_blank=True, max_length=240)
    purpose = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["affiliation"] != User.Affiliation.EXTERNAL_ORGANIZATION:
            # Internal affiliation: resolve an optional managed organization.
            attrs["_internal_organization"] = resolve_internal_organization(
                attrs.get("organization_id")
            )
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
        choices=User.selectable_affiliation_choices(),
        required=False,
        allow_blank=True,
    )
    # Managed internal organization (id) selected from the seeded list. The
    # backend re-reads its type; the client never supplies a type here.
    organization_id = serializers.IntegerField(required=False, allow_null=True)
    # External organization registration fields.
    organization_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    organization_type = serializers.ChoiceField(
        choices=Organization.external_type_choices(),
        required=False,
        allow_blank=True,
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
            "organization_id",
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
            if attrs.get("affiliation") in INTERNAL_AFFILIATIONS:
                attrs["_internal_organization"] = resolve_internal_organization(
                    attrs.get("organization_id")
                )
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
        internal_organization = validated_data.pop("_internal_organization", None)
        # Not a model field — resolved into ``_internal_organization`` above.
        validated_data.pop("organization_id", None)
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
        elif internal_organization is not None:
            # Managed internal organization (CAS, CTED, …). Type/active state
            # were re-checked by the server in ``validate``.
            user.organization_ref = internal_organization
            user.save(update_fields=["organization_ref"])
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """JWT login that also returns the authenticated user profile.

    A valid username/password authenticates the account immediately — the
    token pair is issued in this single step, with no second verification
    factor and no ``mfa_required`` challenge.

    A *deactivated* account is refused distinctly: because the credential
    check itself succeeded, the response is a 403 whose body carries
    ``code: "account_deactivated"`` so the SPA can show the dedicated
    deactivated-account modal. Wrong usernames/passwords keep simplejwt's
    generic "no active account" 401 — the endpoint must never confirm which
    usernames exist.
    """

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except exceptions.AuthenticationFailed:
            # ModelBackend folds "inactive" into the same None it returns for
            # bad credentials, so simplejwt raised its generic error. Re-check
            # the credentials quietly: only a correct password for an existing
            # inactive account is upgraded to the explicit deactivation
            # refusal; everything else re-raises it untouched.
            self._raise_if_deactivated_account(attrs)
            raise
        request = self.context.get("request") if self.context else None
        # Successful credential sign-in — recorded server-side.
        record_password_login(self.user, request)
        AuditLog.record(
            self.user,
            AuditLog.Action.LOGIN,
            object_type="auth",
            object_repr="Password sign-in",
            request=request,
        )
        data["user"] = UserSerializer(self.user).data
        return data

    def _raise_if_deactivated_account(self, attrs):
        username = (attrs.get(self.username_field) or "").strip()
        password = attrs.get("password") or ""
        if not username or not password:
            return
        # Same case-insensitive natural-key lookup ModelBackend performs, so
        # the upgrade triggers exactly when its credential check passed.
        candidate = User.objects.filter(
            **{f"{self.username_field}__iexact": username}
        ).first()
        if (
            candidate is not None
            and not candidate.is_active
            and candidate.check_password(password)
        ):
            raise DeactivatedAccountAuthenticationFailed()


class AdminUserSerializer(serializers.ModelSerializer):
    """Row shape for the administrator user-management table.

    Exposes only what the management screen needs; never credentials or
    authentication secrets. ``is_protected`` marks accounts the API refuses to
    delete (superusers and the caller's own account) so the UI can disable the
    action instead of relying on a failed request.
    """

    display_name = serializers.CharField(read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    affiliation_label = serializers.CharField(
        source="get_affiliation_display", read_only=True
    )
    organization_ref = OrganizationBriefSerializer(read_only=True)
    is_protected = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "display_name",
            "email",
            "role",
            "role_label",
            "affiliation",
            "affiliation_label",
            "organization_ref",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
            "is_protected",
        )

    def get_is_protected(self, obj) -> bool:
        """True when deletion is blocked: a superuser, or the caller itself."""
        request = self.context.get("request") if self.context else None
        caller = getattr(request, "user", None)
        if caller is not None and caller.pk == obj.pk:
            return True
        return bool(obj.is_superuser)


class LoginActivitySerializer(serializers.ModelSerializer):
    """Administrator-facing login activity row.

    Denormalized identity fields are returned as stored (they survive account
    deletion). No token, password, or OTP data exists on the model, so none
    can leak here.
    """

    method_label = serializers.CharField(source="get_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = LoginActivity
        fields = (
            "id",
            "user",
            "user_name",
            "email",
            "role",
            "role_label",
            "method",
            "method_label",
            "status",
            "status_label",
            "ip_address",
            "created_at",
        )

    def get_role_label(self, obj) -> str:
        return dict(User.Role.choices).get(obj.role, obj.role)