"""Approval-letter lifecycle: creation, signing, and email delivery.

Rules the whole module enforces:

* A letter is created ONCE per approved reservation (``OneToOneField`` +
  ``get_or_create``) — repeated approvals, re-approvals after a change
  request, and concurrent approvals can never duplicate it.
* Only the designated signatory (an account granted the
  ``is_approval_signatory`` flag) may approve/sign, verified server-side.
  The designation scopes a non-administrator to this module only.
* A letter is signed at most once; every attempt revalidates under a row lock.
* Email delivery NEVER undoes a signature: it runs after the signing
  transaction commits and only ever updates the letter's email bookkeeping.
"""

from __future__ import annotations

import logging
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from accounts.models import AuditLog
from notifications.models import Notification
from notifications.services import notify

from .documents import render_letter_docx, render_letter_pdf
from .models import ApprovalLetter

logger = logging.getLogger(__name__)


class LetterSignError(ValueError):
    """A signing/email attempt violated a business rule (bad state, not auth)."""


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def _requester_snapshot(reservation) -> tuple[object | None, str, str]:
    """(requester account | None, display name, recipient email)."""
    requester = reservation.requester
    name = reservation.requester_display_name
    email = ""
    if requester and requester.email:
        email = requester.email.strip()
    elif reservation.contact_email:
        email = reservation.contact_email.strip()
    return requester, name, email


def create_letter_for_reservation(reservation) -> ApprovalLetter:
    """Return the reservation's letter, creating it if this is the first call.

    Idempotent and concurrency-safe: the ``OneToOneField`` is the real guard,
    so a double create attempt (two workers finishing the same approval) is
    resolved by ``get_or_create`` and never produces two letters. Called via
    ``transaction.on_commit`` by the approval workflow.
    """
    from .constants import SIGNATORY_NAME

    requester, requester_name, requester_email = _requester_snapshot(reservation)
    letter, created = ApprovalLetter.objects.get_or_create(
        reservation=reservation,
        defaults={
            "requester": requester,
            "requester_name": requester_name[:160],
            "requester_email": requester_email[:254],
        },
    )
    if created:
        AuditLog.record(
            None,
            AuditLog.Action.APPROVAL_LETTER_CREATED,
            object_type="approval_letter",
            object_id=letter.letter_id,
            object_repr=f"Reservation {reservation.reservation_id}",
            detail="NORSU reservation approval letter created; pending signature.",
        )
    # Generate the template-backed pending DOCX as part of issuance. It stays
    # private until signing; this same field is replaced with the final signed
    # DOCX when the signatory confirms.
    if not letter.docx_file:
        try:
            draft = render_letter_docx(letter)
            letter.docx_file.save(
                f"{letter.letter_id}-PENDING.docx", BytesIO(draft), save=True
            )
            AuditLog.record(
                None,
                AuditLog.Action.APPROVAL_LETTER_DOC_GENERATED,
                object_type="approval_letter",
                object_id=letter.letter_id,
                object_repr=f"Reservation {reservation.reservation_id}",
                detail="Template-backed pending DOCX generated.",
            )
        except Exception:  # issuance remains recorded and can be retried safely
            logger.exception(
                "Pending DOCX generation failed for approval letter %s.",
                letter.letter_id,
            )
    if created:
        logger.info(
            "Approval letter %s created for reservation %s (status=%s).",
            letter.letter_id,
            reservation.reservation_id,
            letter.status,
        )
        # Staff notice (the designated signatory is SAS staff, so this covers
        # them): a letter is waiting. In-app only — the letter itself is
        # emailed to the requester after signing.
        link = f"/approval-letters?letter={letter.pk}"
        user_model = get_user_model()
        signatories = user_model.objects.filter(
            is_active=True,
            is_approval_signatory=True,
            role__in=(user_model.Role.ADMIN, user_model.Role.STAFF),
        )
        message = (
            f"Letter {letter.letter_id} for {reservation.event_name} "
            f"({reservation.reservation_id}) is awaiting the designated "
            f"signatory ({SIGNATORY_NAME})."
        )
        for signatory in signatories:
            notify(
                signatory,
                Notification.Type.RESERVATION,
                "Approval letter awaiting signature",
                message,
                link,
            )
        if not signatories.exists():
            logger.warning(
                "Approval letter %s has no active designated signatory account; "
                "an administrator must configure one.",
                letter.letter_id,
            )
    return letter


def create_letter_after_commit(reservation_id: int) -> None:
    """on_commit callback: create the letter without ever breaking approval.

    The approval has already committed when this runs; a failure here is
    logged but never raised back into the requester's flow. The
    ``reconcile_approval_letters`` management command retries missing letters
    and pending template generation safely.
    """
    from reservations.models import Reservation

    try:
        reservation = Reservation.objects.select_related(
            "requester", "facility", "created_by"
        ).get(pk=reservation_id)
        create_letter_for_reservation(reservation)
    except Exception:  # noqa: BLE001 — letter creation must not undo approval
        logger.exception(
            "Approval-letter creation FAILED for reservation id %s. The "
            "approval itself is committed and unchanged.",
            reservation_id,
        )


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

#: Reservation statuses for which a letter may still be signed — the approval
#: the letter certifies must still stand. A reservation that was later
#: cancelled / rejected / expired must never produce a fresh signed letter.
_SIGNABLE_RESERVATION_STATUSES = frozenset({
    "APPROVED",
    "ACTIVE",
    "COMPLETED",
    "NO_SHOW",
})


def _assert_can_sign(actor) -> None:
    """Server-side authorization for approving. Never trusts the frontend.

    The designation is the sole authorization: administrator status without
    it is refused, and a staff role is not required (the designated signatory
    is intentionally scoped and no longer reports as SAS staff).
    """
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Authentication is required to approve letters.")
    if not getattr(actor, "is_approved", True):
        raise PermissionDenied(
            "Your account is pending administrator approval and cannot approve letters."
        )
    if not getattr(actor, "is_approval_signatory", False):
        raise PermissionDenied(
            "Only the designated approval-letter signatory can approve letters."
        )


def sign_letter(letter: ApprovalLetter, actor) -> ApprovalLetter:
    """Apply the test signature, generate the finalized documents, queue email.

    Runs in one transaction under a row lock: the status re-check, PDF/DOCX
    generation, and the file writes commit together, so a PDF failure rolls
    the whole signature back (there is never a SIGNED letter without its
    document). Two concurrent sign requests produce exactly one signature —
    the loser re-reads the committed SIGNED state and fails clearly. The
    requester email is dispatched only AFTER the transaction commits.
    """
    _assert_can_sign(actor)
    now = timezone.now()

    with transaction.atomic():
        # Lock ONLY the letter row: PostgreSQL refuses ``FOR UPDATE`` on the
        # nullable side of the outer joins that ``select_related`` over the
        # nullable ``signatory``/``requester`` would create (same pattern as
        # workflow.resend_approval_email).
        locked = (
            ApprovalLetter.objects.select_for_update(of=("self",))
            .select_related("reservation", "reservation__facility", "reservation__requester")
            .get(pk=letter.pk)
        )

        if locked.status != ApprovalLetter.Status.PENDING_SIGNATURE:
            raise LetterSignError(
                "This letter has already been signed and cannot be signed again."
            )
        reservation = locked.reservation
        if reservation.status not in _SIGNABLE_RESERVATION_STATUSES:
            raise LetterSignError(
                "The linked reservation is no longer approved; this letter "
                "cannot be signed."
            )

        locked.signed_at = now
        locked.signatory = actor
        locked.status = ApprovalLetter.Status.SIGNED
        # Render both finalized files before writing either to storage. A
        # renderer error therefore leaves the pending letter untouched.
        pdf_bytes = render_letter_pdf(locked, signed=True)
        docx_bytes = render_letter_docx(locked)
        old_docx_name = locked.docx_file.name if locked.docx_file else ""
        stored_names: list[str] = []
        try:
            locked.pdf_file.save(
                f"{locked.letter_id}.pdf", BytesIO(pdf_bytes), save=False
            )
            stored_names.append(locked.pdf_file.name)
            locked.docx_file.save(
                f"{locked.letter_id}.docx", BytesIO(docx_bytes), save=False
            )
            stored_names.append(locked.docx_file.name)
            locked.save()
        except Exception:
            for stored_name in stored_names:
                default_storage.delete(stored_name)
            raise
        if old_docx_name and old_docx_name != locked.docx_file.name:
            transaction.on_commit(lambda name=old_docx_name: default_storage.delete(name))

        AuditLog.record(
            actor,
            AuditLog.Action.APPROVAL_LETTER_SIGNED,
            object_type="approval_letter",
            object_id=locked.letter_id,
            object_repr=f"Reservation {reservation.reservation_id}",
            detail=(
                f"Approval recorded by the designated signatory "
                f"(user id {getattr(actor, 'pk', None)}) at {now.isoformat()}; "
                "finalized PDF and DOCX generated from the institutional "
                "template. TEST SIGNATURE — not a verified digital signature."
            ),
        )
        AuditLog.record(
            actor,
            AuditLog.Action.APPROVAL_LETTER_DOC_GENERATED,
            object_type="approval_letter",
            object_id=locked.letter_id,
            object_repr=f"Reservation {reservation.reservation_id}",
            detail="Final signed PDF and DOCX generated from the issued letter.",
        )
        logger.info(
            "Approval letter %s signed by user id %s at %s.",
            locked.letter_id,
            getattr(actor, "pk", None),
            now,
        )

        # Email + requester notice only after the signature has committed.
        transaction.on_commit(
            lambda letter_id=locked.pk, reservation_pk=reservation.pk: (
                _after_signature_committed(letter_id, reservation_pk)
            )
        )

    letter.refresh_from_db()
    return letter


def _after_signature_committed(letter_id: int, reservation_pk: int) -> None:
    """Post-commit work for a fresh signature: deliver email + notify requester.

    Both are best-effort; neither can undo the committed signature.
    """
    try:
        deliver_signed_letter(letter_id)
    except Exception:  # noqa: BLE001 — delivery bookkeeping must not raise here
        logger.exception(
            "Signed-letter delivery crashed for letter id %s. The signature "
            "remains committed.",
            letter_id,
        )
    try:
        letter = ApprovalLetter.objects.select_related("reservation").get(pk=letter_id)
        notify(
            letter.reservation.requester,
            Notification.Type.RESERVATION,
            "Approval letter signed",
            (
                f"Your reservation approval letter {letter.letter_id} for "
                f"{letter.reservation.event_name} has been signed and is ready "
                "to download."
            ),
            f"/reservations/{reservation_pk}",
        )
    except Exception:  # noqa: BLE001 — the notice is best-effort
        logger.exception(
            "Requester notice for signed letter id %s failed (best-effort).",
            letter_id,
        )


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def deliver_signed_letter(letter_id: int) -> ApprovalLetter:
    """Email the signed PDF to the requester, recording the delivery outcome.

    Never raises — a delivery failure is recorded on the letter (status
    EMAIL_FAILED, error category, no timestamp) while the signature stays
    intact. The row lock serialises concurrent deliveries/retries so an email
    can never be sent twice by racing requests. The atomic block is required:
    the function runs from ``transaction.on_commit`` (outside any surrounding
    transaction) and ``select_for_update`` needs one — the same structure as
    ``workflow.resend_approval_email``.
    """
    from notifications.email_service import (
        resolve_requester_email,
        send_approval_letter_signed,
    )

    with transaction.atomic():
        letter = (
            ApprovalLetter.objects.select_for_update(of=("self",))
            .select_related("reservation", "reservation__facility", "reservation__requester")
            .get(pk=letter_id)
        )

        if not letter.is_signed:
            logger.warning("Delivery skipped for letter %s: not signed yet.", letter.letter_id)
            return letter
        if letter.email_status == ApprovalLetter.EmailStatus.SENT:
            logger.info("Delivery skipped for letter %s: email already SENT.", letter.letter_id)
            return letter

        email = resolve_requester_email(letter.reservation)
        attempted_at = timezone.now()
        letter.email_attempted_at = attempted_at
        if not email:
            letter.email_status = ApprovalLetter.EmailStatus.NO_EMAIL
            letter.email_error = ""
            letter.save(update_fields=[
                "email_status", "email_error", "email_attempted_at", "updated_at",
            ])
            logger.warning(
                "Signed-letter email skipped for %s: requester has no valid email.",
                letter.letter_id,
            )
            return letter

        AuditLog.record(
            None,
            AuditLog.Action.APPROVAL_LETTER_EMAIL_TRY,
            object_type="approval_letter",
            object_id=letter.letter_id,
            object_repr=f"Reservation {letter.reservation.reservation_id}",
            detail="Signed PDF delivery attempted through the configured email service.",
        )

        try:
            ok, reason = send_approval_letter_signed(letter, email)
        except Exception as exc:  # noqa: BLE001 — never undo the signature
            ok, reason = False, type(exc).__name__
            logger.exception(
                "Signed-letter email raised for %s (%s).", letter.letter_id, reason
            )

        if ok:
            letter.email_status = ApprovalLetter.EmailStatus.SENT
            letter.email_error = ""
            letter.emailed_at = timezone.now()
            letter.status = ApprovalLetter.Status.SENT
            logger.info("Signed-letter email SENT for %s to the requester.", letter.letter_id)
            audit_action = AuditLog.Action.APPROVAL_LETTER_EMAIL_SENT
            audit_detail = "Signed PDF accepted by the configured email service."
        else:
            letter.email_status = ApprovalLetter.EmailStatus.FAILED
            letter.email_error = (reason or "unknown")[:100]
            letter.status = ApprovalLetter.Status.EMAIL_FAILED
            logger.error(
                "Signed-letter email FAILED for %s (reason: %s). The signature "
                "remains intact.",
                letter.letter_id,
                reason,
            )
            audit_action = AuditLog.Action.APPROVAL_LETTER_EMAIL_FAILED
            audit_detail = f"Signed PDF delivery failed ({letter.email_error})."
        letter.save(update_fields=[
            "email_status", "email_error", "email_attempted_at", "emailed_at",
            "status", "updated_at",
        ])
        AuditLog.record(
            None,
            audit_action,
            object_type="approval_letter",
            object_id=letter.letter_id,
            object_repr=f"Reservation {letter.reservation.reservation_id}",
            detail=audit_detail,
        )
        return letter


def retry_email(letter: ApprovalLetter, actor) -> ApprovalLetter:
    """Retry a failed/skipped delivery for an already-signed letter.

    Never creates another letter or signature: it only re-runs delivery for a
    signed letter whose email has not been accepted. Revalidation happens
    under the same row lock as the delivery itself.
    """
    with transaction.atomic():
        locked = ApprovalLetter.objects.select_for_update(of=("self",)).select_related(
            "reservation"
        ).get(pk=letter.pk)
        if not locked.is_signed:
            raise LetterSignError("Only a signed letter can be emailed.")
        if locked.email_status == ApprovalLetter.EmailStatus.SENT:
            raise LetterSignError("This letter's email was already delivered.")

        AuditLog.record(
            actor,
            AuditLog.Action.APPROVAL_LETTER_EMAIL_RETRIED,
            object_type="approval_letter",
            object_id=locked.letter_id,
            object_repr=f"Reservation {locked.reservation.reservation_id}",
            detail="Retry of the requester email delivery.",
        )

    result = deliver_signed_letter(locked.pk)
    letter.refresh_from_db()
    return result
