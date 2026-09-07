import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Application user with institutional roles."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        STAFF = "STAFF", "SAS Staff"
        REQUESTER = "REQUESTER", "Requester"

    role = models.CharField(
        max_length=16, choices=Role.choices, default=Role.REQUESTER
    )
    organization = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=32, blank=True)
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
        SETTINGS_CHANGED = "SETTINGS_CHANGED", "Settings changed"

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
