import secrets
import string

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .login_activity import record_password_login
from .models import AuditLog, LoginActivity, Organization

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
    # Account-approval summary (view-only policy). ``is_approved`` is the
    # authoritative server-side condition; ``is_view_only`` is its inverse and
    # drives the SPA's pending-approval notice. Both are read-only — a client
    # can never set its own approval state.
    is_approved = serializers.BooleanField(read_only=True)
    is_view_only = serializers.BooleanField(read_only=True)
    # Approval-letter signing designation. Read-only: an administrator grants
    # it server-side (Django admin / seed command); a client can never set it.
    is_approval_signatory = serializers.BooleanField(read_only=True)
    # True for a non-administrator designated signatory, whose access is
    # limited to the Approval Letters module. Drives the SPA's module-only
    # navigation; the backend enforces the same scope on every request.
    is_approval_letters_only = serializers.BooleanField(read_only=True)

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
            "is_approved",
            "is_view_only",
            "is_approval_signatory",
            "is_approval_letters_only",
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

    password = serializers.CharField(write_only=True)
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
        password = attrs.get("password")
        if password:
            candidate_user = User(
                username=attrs.get("username", ""),
                first_name=attrs.get("first_name", ""),
                last_name=attrs.get("last_name", ""),
                email=attrs.get("email", ""),
            )
            try:
                validate_password(password, candidate_user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc

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
        user.is_active = False
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

    A *not-approved* (inactive) account also signs in, but only ever gets the
    view-only experience: the login succeeds so the SPA can show the pending-
    approval banner, while every state-changing API call is refused with 403
    by ``accounts.permissions.IsAccountApprovedOrReadOnly``. Approval is a flag
    on the account, re-checked on every request — issuing a token never grants
    write access. Wrong usernames/passwords keep simplejwt's generic
    "no active account" 401, so the endpoint never confirms which usernames
    exist.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
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
    is_approved = serializers.BooleanField(read_only=True)

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
            "is_approved",
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


#: Alphabet for generated temporary passwords. Mixed case + digits + symbols
#: keeps them clear of Django's numeric/common-password validators.
_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def generate_temporary_password(length: int = 14) -> str:
    """Return a strong one-time password for administrator-created accounts."""
    while True:
        value = "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(char.islower() for char in value)
            and any(char.isupper() for char in value)
            and any(char.isdigit() for char in value)
        ):
            return value


class _AdminIdentityValidationMixin:
    """Shared uniqueness checks for administrator-managed accounts.

    Django's username uniqueness is exact-case; the management API additionally
    rejects case-only duplicates so two accounts cannot look identical in the
    table. Email is not unique at the database level, so it is checked here.
    """

    def validate_username(self, value):
        value = (value or "").strip()
        qs = User.objects.filter(username__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An account with this username already exists.")
        return value

    def validate_email(self, value):
        value = (value or "").strip()
        if not value:
            return value
        qs = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value


class AdminUserCreateSerializer(_AdminIdentityValidationMixin, serializers.ModelSerializer):
    """Administrator account creation.

    The account is always created in its intended role but never as a Django
    superuser. ``is_staff`` is derived from ``role == ADMIN`` (matching the
    project's existing authorization design), and ``is_superuser`` is always
    False: application administration is controlled by the custom role, not by
    a privilege flag supplied in the request body.

    A password may be supplied. When omitted (or blank), a strong temporary
    password is generated and returned exactly once by the view.
    """

    email = serializers.EmailField(required=True)
    role = serializers.ChoiceField(choices=User.Role.choices, default=User.Role.REQUESTER)
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "password",
        )

    def validate(self, attrs):
        raw_password = attrs.get("password") or ""
        generated = raw_password == ""
        password = generate_temporary_password() if generated else raw_password
        if not generated:
            candidate = User(
                username=attrs.get("username", ""),
                first_name=attrs.get("first_name", ""),
                last_name=attrs.get("last_name", ""),
                email=attrs.get("email", ""),
            )
            try:
                validate_password(password, candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        attrs["password"] = password
        attrs["_temporary_password"] = generated
        return attrs

    def create(self, validated_data):
        temporary = validated_data.pop("_temporary_password", False)
        password = validated_data.pop("password")
        role = validated_data.get("role", User.Role.REQUESTER)
        user = User.objects.create_user(
            password=password,
            is_active=True,
            is_staff=role == User.Role.ADMIN,
            is_superuser=False,
            **validated_data,
        )
        self.temporary_password = password if temporary else None
        return user


class AdminUserUpdateSerializer(_AdminIdentityValidationMixin, serializers.ModelSerializer):
    """Editable profile fields and application role for an existing account.

    ``is_staff`` is kept in sync with the role. ``is_superuser`` and the
    approval-letter designation are deliberately absent: a request body can
    never grant either through this endpoint.
    """

    role = serializers.ChoiceField(choices=User.Role.choices, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "role")

    def update(self, instance, validated_data):
        for field in ("username", "email", "first_name", "last_name", "role"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        if instance.role == User.Role.ADMIN:
            instance.is_staff = True
        elif not instance.is_superuser:
            instance.is_staff = False
        instance.save()
        return instance


class AdminUserPasswordSerializer(serializers.Serializer):
    """Set or generate a new password for an account.

    The plaintext value is never stored. A generated value is returned once by
    the view so the administrator can hand it to the account owner.
    """

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )

    def validate(self, attrs):
        target = self.context.get("user")
        if target is None:
            raise serializers.ValidationError("No account was selected.")
        raw_password = attrs.get("password") or ""
        generated = raw_password == ""
        password = generate_temporary_password() if generated else raw_password
        if not generated:
            try:
                validate_password(password, target)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        attrs["password"] = password
        attrs["_temporary_password"] = generated
        return attrs


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
