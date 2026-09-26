import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, models, transaction
from django.utils import timezone


class Organization(models.Model):
    """An external organization affiliated with SAS RESERVE.

    Google identifies the *person*; this entity identifies the *institution*
    that person represents. It is deliberately NOT an authentication
    mechanism: every member authenticates with their own Google account and
    is linked here by ``User.organization_ref``, so one organization can have
    many users (and one user belongs to at most one organization).

    Registration is self-service but inert until SAS staff verify it: new
    organizations start ``PENDING`` and their members cannot create
    reservations until the status is ``APPROVED``.
    """

    class OrganizationType(models.TextChoices):
        GOVERNMENT_AGENCY = "GOVERNMENT_AGENCY", "Government Agency"
        NGO = "NGO", "NGO"
        PRIVATE_ORGANIZATION = "PRIVATE_ORGANIZATION", "Private Organization"
        COMMUNITY_ORGANIZATION = "COMMUNITY_ORGANIZATION", "Community Organization"
        SCHOOL_UNIVERSITY = "SCHOOL_UNIVERSITY", "School/University"
        OTHER = "OTHER", "Other"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"

    # Unique, human-readable identifier (EXT-0001, EXT-0002, …) generated on
    # first save. Never derived from a Google account id.
    organization_code = models.CharField(
        max_length=16, unique=True, editable=False, db_index=True
    )
    organization_name = models.CharField(max_length=160)
    organization_type = models.CharField(
        max_length=32,
        choices=OrganizationType.choices,
        default=OrganizationType.OTHER,
    )
    contact_person = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_number = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=240, blank=True)
    purpose = models.TextField(
        blank=True,
        help_text="Why the organization needs to use NORSU facilities.",
    )
    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
    )
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # Who registered the organization (the first affiliated user).
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["verification_status", "organization_type"]),
        ]
        verbose_name = "external organization"
        verbose_name_plural = "external organizations"

    # ------------------------------------------------------------------

    CODE_PREFIX = "EXT-"

    @classmethod
    def _next_organization_code(cls) -> str:
        last = (
            cls.objects.filter(organization_code__startswith=cls.CODE_PREFIX)
            .order_by("-organization_code")
            .values_list("organization_code", flat=True)
            .first()
        )
        if last:
            try:
                sequence = int(last.rsplit("-", 1)[1]) + 1
            except (IndexError, ValueError):
                sequence = 1
        else:
            sequence = 1
        return f"{cls.CODE_PREFIX}{sequence:04d}"

    def save(self, *args, **kwargs):
        if self.organization_code:
            return super().save(*args, **kwargs)
        # Generate on first save. The unique constraint is the real guard, so
        # a concurrent insert simply retries with the next code instead of
        # silently colliding.
        for _ in range(10):
            self.organization_code = self._next_organization_code()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.organization_code = ""
        return super().save(*args, **kwargs)

    @property
    def is_verified(self) -> bool:
        return self.verification_status == self.VerificationStatus.APPROVED

    @property
    def member_count(self) -> int:
        return self.members.count()

    def __str__(self) -> str:
        return f"{self.organization_code} — {self.organization_name}"


class User(AbstractUser):
    """Application user with institutional roles.

    ``affiliation`` is how SAS RESERVE identifies *who the person represents*
    (NORSU student/faculty/office or an external organization), layered on top
    of the existing Google/OTP/2FA authentication — it is never used as a
    credential and never replaces it. Existing accounts keep their current
    behavior: a blank affiliation means "campus user as before".
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        STAFF = "STAFF", "SAS Staff"
        REQUESTER = "REQUESTER", "Requester"

    class Affiliation(models.TextChoices):
        NORSU_STUDENT = "NORSU_STUDENT", "NORSU Student"
        NORSU_FACULTY_STAFF = "NORSU_FACULTY_STAFF", "NORSU Faculty/Staff"
        NORSU_OFFICE = "NORSU_OFFICE", "NORSU Office/Department"
        EXTERNAL_ORGANIZATION = "EXTERNAL_ORGANIZATION", "External Organization"

    role = models.CharField(
        max_length=16, choices=Role.choices, default=Role.REQUESTER
    )
    # Free-text NORSU unit / department (legacy field, still used by the
    # profile form and shown in the UI). For external requesters the resolved
    # organization name comes from ``organization_ref`` instead.
    organization = models.CharField(max_length=120, blank=True)
    affiliation = models.CharField(
        max_length=32,
        choices=Affiliation.choices,
        blank=True,
        default="",
        db_index=True,
        help_text="Blank = not yet chosen (treated as an internal campus user).",
    )
    organization_ref = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        help_text=(
            "External organization this user belongs to. Set only through the "
            "backend from the authenticated user — never from a client-sent id."
        ),
    )
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    # Persistent first-time verification state (server-authoritative):
    # accounts created by first-time Google sign-in start as False and are
    # flipped to True ONLY by successful email-OTP verification. While
    # False the account cannot authenticate through ANY route (OAuth
    # callback, password login, token refresh, or an existing JWT).
    # Password-registered accounts are verified by default.
    first_login_verified = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        # Administrators get Django admin access automatically.
        if self.role == self.Role.ADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)

    @property
    def is_pending_verification(self) -> bool:
        return not self.first_login_verified

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_sas_staff(self) -> bool:
        return self.role in (self.Role.ADMIN, self.Role.STAFF)

    # -- Affiliation helpers -------------------------------------------

    @property
    def is_external_organization(self) -> bool:
        return self.affiliation == self.Affiliation.EXTERNAL_ORGANIZATION

    @property
    def has_affiliation(self) -> bool:
        """False only for accounts that have never completed the step.

        Legacy accounts (created before affiliations existed) also read as
        False — they keep working exactly as before and are only *prompted*.
        """
        return bool(self.affiliation)

    @property
    def organization_verification_status(self) -> str:
        """Verification status of this user's organization ('' when none)."""
        if self.organization_ref_id:
            return self.organization_ref.verification_status
        return ""

    @property
    def can_create_reservations(self) -> bool:
        """False only for external affiliations whose organization is not
        APPROVED. Internal/legacy users are always allowed."""
        return not self.reservation_block_reason

    @property
    def reservation_block_reason(self) -> str:
        """Why this user may not submit a reservation, or '' when allowed.

        Pending / Rejected / Suspended organizations cannot create normal
        reservations — the message is surfaced verbatim by the API so the
        frontend can show the matching status notice.
        """
        if not self.is_external_organization:
            return ""
        organization = self.organization_ref
        if organization is None:
            return (
                "Complete your external organization registration before "
                "submitting reservations."
            )
        if organization.verification_status == Organization.VerificationStatus.APPROVED:
            return ""
        return {
            Organization.VerificationStatus.PENDING: (
                "Your organization registration is pending administrator "
                "verification. You cannot submit reservations yet."
            ),
            Organization.VerificationStatus.REJECTED: (
                "Your organization registration was rejected, so reservations "
                "are not available. Contact the SAS Office for assistance."
            ),
            Organization.VerificationStatus.SUSPENDED: (
                "Your organization is currently suspended. Reservations are "
                "disabled until the SAS Office reactivates it."
            ),
        }.get(organization.verification_status, "")

    def __str__(self) -> str:
        return self.display_name


class AuditLog(models.Model):
    """Append-only trail of important actions (who / what / when / object).

    Used particularly for administrator actions: approval decisions, check-in
    overrides, equipment changes, and similar events that may need review.
    """

    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Logged in"
        LOGIN_2FA = "LOGIN_2FA", "Logged in with 2FA"
        LOGOUT = "LOGOUT", "Logged out"
        REGISTER = "REGISTER", "Registered"
        GOOGLE_FIRST_ACCOUNT = "GOOGLE_FIRST_ACCOUNT", "Google account created"
        OTP_SENT = "OTP_SENT", "Email verification code sent"
        OTP_RESENT = "OTP_RESENT", "Email verification code resent"
        OTP_VERIFIED = "OTP_VERIFIED", "Email verified"
        OTP_FAILED = "OTP_FAILED", "Email verification failed"
        OTP_EXPIRED = "OTP_EXPIRED", "Email verification code expired"
        RESERVATION_CREATED = "RESERVATION_CREATED", "Reservation created"
        RESERVATION_EDITED = "RESERVATION_EDITED", "Reservation edited"
        RESERVATION_APPROVED = "RESERVATION_APPROVED", "Reservation approved"
        RESERVATION_REJECTED = "RESERVATION_REJECTED", "Reservation rejected"
        RESERVATION_CANCELLED = "RESERVATION_CANCELLED", "Reservation cancelled"
        RESERVATION_STATUS = "RESERVATION_STATUS", "Reservation status changed"
        EARLY_CHECK_IN = "EARLY_CHECK_IN", "Early check-in performed"
        CHECK_IN = "CHECK_IN", "Checked in"
        CHECK_OUT = "CHECK_OUT", "Checked out"
        EQUIPMENT_CREATED = "EQUIPMENT_CREATED", "Equipment created"
        EQUIPMENT_EDITED = "EQUIPMENT_EDITED", "Equipment edited"
        EQUIPMENT_REMOVED = "EQUIPMENT_REMOVED", "Equipment removed"
        EQUIPMENT_IMAGE = "EQUIPMENT_IMAGE", "Equipment image changed"
        FACILITY_CREATED = "FACILITY_CREATED", "Facility created"
        FACILITY_EDITED = "FACILITY_EDITED", "Facility edited"
        FACILITY_REMOVED = "FACILITY_REMOVED", "Facility removed"
        FACILITY_IMAGE = "FACILITY_IMAGE", "Facility image changed"
        SETTINGS_CHANGED = "SETTINGS_CHANGED", "Settings changed"
        # External organization affiliations (Task: external organizations).
        AFFILIATION_CHANGED = "AFFILIATION_CHANGED", "Affiliation changed"
        ORGANIZATION_REGISTERED = "ORGANIZATION_REGISTERED", "Organization registered"
        ORGANIZATION_UPDATED = "ORGANIZATION_UPDATED", "Organization updated"
        ORGANIZATION_APPROVED = "ORGANIZATION_APPROVED", "Organization approved"
        ORGANIZATION_REJECTED = "ORGANIZATION_REJECTED", "Organization rejected"
        ORGANIZATION_SUSPENDED = "ORGANIZATION_SUSPENDED", "Organization suspended"
        ORGANIZATION_REACTIVATED = "ORGANIZATION_REACTIVATED", "Organization reactivated"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    # Denormalized name so entries survive actor deletion.
    actor_name = models.CharField(max_length=120, blank=True)
    action = models.CharField(max_length=32, choices=Action.choices)
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=60, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    # IP address is PII-adjacent but standard for audit trails; stored for
    # security review only. Never shown in bulk exports beyond staff pages.
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.actor_name or 'System'} — {self.get_action_display()} — {self.object_repr}"

    @staticmethod
    def record(actor, action, *, object_type="", object_id="", object_repr="", detail="", request=None):
        """Create an audit entry; never raises into the caller's flow."""
        try:
            return AuditLog.objects.create(
                actor=actor if getattr(actor, "pk", None) else None,
                actor_name=(actor.display_name if getattr(actor, "pk", None) else "") or "System",
                action=action,
                object_type=object_type,
                object_id=str(object_id or ""),
                object_repr=str(object_repr or "")[:200],
                detail=str(detail or "")[:2000],
                ip_address=(
                    request.META.get("REMOTE_ADDR")
                    if request is not None and hasattr(request, "META")
                    else None
                ),
            )
        except Exception:  # noqa: BLE001 — audit must never break the action
            return None


class TwoFactorBackupCode(models.Model):
    """Single-use TOTP recovery codes.

    Only the hash of each code is stored (same hashers as passwords), so a
    database leak does not expose usable codes. Codes are shown in plaintext
    exactly once — when generated. A used code is stamped and can never be
    reused.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_codes",
    )
    code_hash = models.CharField(max_length=200)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:  # pragma: no cover — debug convenience only
        return f"backup code for {self.user_id} ({'used' if self.used_at else 'unused'})"

    # ------------------------------------------------------------------

    CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous I/1/O/0

    @classmethod
    def generate(cls, user, count: int = 10) -> list[str]:
        """Replace all codes for the user and return the plaintext batch."""
        cls.objects.filter(user=user).delete()
        codes = []
        for _ in range(count):
            raw = "".join(secrets.choice(cls.CODE_CHARS) for _ in range(10))
            codes.append(f"{raw[:5]}-{raw[5:]}")
            cls.objects.create(user=user, code_hash=make_password(raw))
        return codes

    @classmethod
    def verify(cls, user, code: str) -> bool:
        """Check a backup code; consume it atomically when valid."""
        normalized = (code or "").strip().replace("-", "").upper()
        if not normalized:
            return False
        for entry in cls.objects.filter(user=user, used_at__isnull=True):
            if check_password(normalized, entry.code_hash):
                # Re-check used_at inside the update to avoid double-use races.
                updated = cls.objects.filter(
                    pk=entry.pk, used_at__isnull=True
                ).update(used_at=timezone.now())
                return bool(updated)
        return False

    @classmethod
    def remaining(cls, user) -> int:
        return cls.objects.filter(user=user, used_at__isnull=True).count()


# Verification limits (kept at module level so the service and tests share
# one source of truth).
OTP_LIFETIME_SECONDS = 600  # 10 minutes
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_RESENDS = 5
MAX_OTP_ATTEMPTS = OTP_MAX_ATTEMPTS
MAX_OTP_RESENDS = OTP_MAX_RESENDS


class EmailOTPVerification(models.Model):
    """Pending first-time Google sign-in email verification session.

    A new Google account is created but NOT authenticated until the user
    proves ownership of their Google-verified email via a 6-digit OTP.

    Security properties:
    * The OTP is stored hashed (password hashers) — a DB leak exposes no
      usable codes.
    * The session token given to the SPA is random and stored hashed; it is
      single-purpose (only OTP verify/resend) and short-lived. It is NOT a
      JWT and grants nothing else.
    * The OTP expires, is single-use, and is invalidated by a resend.
    * Verification attempts and resends are capped per session.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otp_verification",
    )
    email = models.EmailField()
    otp_hash = models.CharField(max_length=200)
    token_hash = models.CharField(max_length=200, db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    resend_count = models.PositiveIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "verified_at"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug convenience only
        return f"email OTP verification for {self.email} ({'verified' if self.verified_at else 'pending'})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_locked(self) -> bool:
        return self.attempts >= MAX_OTP_ATTEMPTS

    @property
    def is_exhausted(self) -> bool:
        return self.resend_count >= MAX_OTP_RESENDS
