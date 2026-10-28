"""Approval-letter models.

One letter per approved reservation (``OneToOneField``), created automatically
after the existing approval workflow commits. Letter status is deliberately
INDEPENDENT of reservation status: signing/emailing a letter never changes the
reservation, and a reservation moving on (check-in, completion, …) never
changes its letter.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.db.models import F

from reservations.models import Reservation


def approval_letter_pdf_path(instance, filename: str) -> str:
    return f"approval_letters/{timezone.localdate():%Y}/{filename}"


def approval_letter_docx_path(instance, filename: str) -> str:
    return f"approval_letters/{timezone.localdate():%Y}/{filename}"


class ApprovalLetterSequence(models.Model):
    """Per-year allocator for correspondence IDs.

    The row lock serializes concurrent approvals on databases that support
    ``SELECT FOR UPDATE``. ``get_or_create`` handles the first allocation of a
    year safely; the unique year key is the final guard against duplicates.
    """

    year = models.PositiveSmallIntegerField(primary_key=True)
    next_number = models.PositiveIntegerField(default=1)


class ApprovalLetter(models.Model):
    """The formal approval letter issued for one approved reservation."""

    class Status(models.TextChoices):
        # Generated and awaiting approval from the position holder.
        PENDING_SIGNATURE = "PENDING_SIGNATURE", "Pending signature"
        # Approval is the terminal letter decision; delivery is tracked below.
        APPROVED = "APPROVED", "Approved"
        # Retained so old clients/data can be read during rolling deployment.
        SIGNED = "SIGNED", "Signed (legacy)"
        SENT = "SENT", "Signed and sent (legacy)"
        EMAIL_FAILED = "EMAIL_FAILED", "Signed — email failed (legacy)"

    class EmailStatus(models.TextChoices):
        NOT_SENT = "NOT_SENT", "Not sent"
        SENT = "SENT", "Accepted by email service"
        FAILED = "FAILED", "Failed"
        NO_EMAIL = "NO_EMAIL", "No requester email"

    letter_id = models.CharField(max_length=24, unique=True, editable=False)
    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.CASCADE,
        related_name="approval_letter",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_SIGNATURE,
        db_index=True,
    )

    # Recipient snapshots (survive requester-account changes/deletion).
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_letters",
        help_text="Requester account; null for external requesters.",
    )
    requester_name = models.CharField(max_length=160, blank=True)
    requester_email = models.CharField(max_length=254, blank=True)

    # Signatory record. ``signatory`` is the authenticated account that signed
    # (SET_NULL keeps the letter after account deletion); the printed name and
    # position always come from constants — never from a client.
    signatory = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_letters_signed",
    )
    # Snapshots preserve actual approver attribution if their account is later
    # deactivated, transferred, or deleted.
    signatory_name = models.CharField(max_length=160, blank=True)
    signatory_username = models.CharField(max_length=150, blank=True)
    signatory_email = models.EmailField(max_length=254, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    # DOCX is populated from the institutional template at issuance, then
    # replaced with its test-signed final version. PDF is produced when
    # signed. Pending documents are never exposed by download endpoints.
    pdf_file = models.FileField(
        upload_to=approval_letter_pdf_path, null=True, blank=True
    )
    docx_file = models.FileField(
        upload_to=approval_letter_docx_path, null=True, blank=True
    )

    # Requester email delivery bookkeeping.
    email_status = models.CharField(
        max_length=12,
        choices=EmailStatus.choices,
        default=EmailStatus.NOT_SENT,
        db_index=True,
    )
    email_attempted_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    email_error = models.CharField(
        max_length=100,
        blank=True,
        help_text="Short, safe error category of the last failed delivery attempt.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["email_status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.letter_id} — {self.get_status_display()}"

    # -- Identifier ------------------------------------------------------

    @classmethod
    def _next_letter_id(cls) -> str:
        year = timezone.localdate().year
        from django.db import transaction

        with transaction.atomic():
            ApprovalLetterSequence.objects.get_or_create(year=year)
            sequence = ApprovalLetterSequence.objects.select_for_update().get(year=year)
            current = sequence.next_number
            ApprovalLetterSequence.objects.filter(year=year).update(
                next_number=F("next_number") + 1
            )
        return f"NORSU-AL-{year}-{current:05d}"

    def save(self, *args, **kwargs):
        if not self.letter_id:
            self.letter_id = self._next_letter_id()
        super().save(*args, **kwargs)

    # -- State helpers ----------------------------------------------------

    @property
    def is_signed(self) -> bool:
        return self.status in (
            self.Status.APPROVED,
            self.Status.SIGNED,
            self.Status.SENT,
            self.Status.EMAIL_FAILED,
        )

    @property
    def has_signed_pdf(self) -> bool:
        return self.is_signed and bool(self.pdf_file)

    @property
    def has_signed_docx(self) -> bool:
        return self.is_signed and bool(self.docx_file)

    @property
    def can_retry_email(self) -> bool:
        """A signed letter whose email has not been accepted can be retried.

        Retrying never re-signs and never re-creates the letter; a NO_EMAIL
        result is retried too, in case the requester's email was added later.
        """
        return self.is_signed and self.email_status != self.EmailStatus.SENT
