"""Equipment-specific routing letters for approved internal reservations.

A routing letter is an official request for permission to use equipment that is
managed by another responsible person or department. It is not a reservation
summary, an approval letter, or a workflow of its own: the reservation's
approval status remains the single source of truth and these documents never
carry a printed/claimed/released state, print counters, or a separate approval
step.

Two separate letters may be produced for one reservation:

* GSO requests permission from the configured sound-system custodian to use the
  sound system for an approved Gymnasium reservation.
* CAS requests permission from the College of Arts and Sciences to use the LED
  wall for an approved Gymnasium reservation. The requesting organization
  receives this letter by email as a PDF attachment.

The institutional letterhead and DOCX/PDF conversion are the ones already used
by the external approval-letter pipeline (``approval_documents``); only the
letter body differs, so no second document-generation system exists.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from facilities.models import Facility
from reservations.models import ApprovalLetterSettings, Reservation
from reservations.services import approval_documents as documents

logger = logging.getLogger(__name__)

GSO = "gso"
CAS = "cas"
LETTER_KINDS = (GSO, CAS)

#: The official catalog names (``equipment.admin`` keeps the catalog limited to
#: these items). Matching is by equipment name instead of a hardcoded id so a
#: re-seeded database, a renamed primary key, or a test fixture works the same.
_EQUIPMENT_NAMES = {
    GSO: "sound system",
    CAS: "led wall",
}
_EQUIPMENT_LABELS = {
    GSO: "Sound System",
    CAS: "LED Wall",
}
_DOCUMENT_LABELS = {
    GSO: "GSO routing letter",
    CAS: "CAS routing letter",
}
_PDF_FIELDS = {
    GSO: "generated_gso_routing_letter_pdf",
    CAS: "generated_cas_routing_letter_pdf",
}
_GENERATED_AT_FIELDS = {
    GSO: "generated_gso_routing_letter_at",
    CAS: "generated_cas_routing_letter_at",
}


class RoutingLetterUnavailable(ValueError):
    """Raised when a routing letter cannot be produced for a reservation."""


def _text(value) -> str:
    return str(value or "").strip()


def _requesting_organization(reservation):
    """The structured organization behind the reservation, when one is linked."""
    if reservation.organization_ref_id:
        return reservation.organization_ref
    requester = reservation.requester if reservation.requester_id else None
    if requester is not None and requester.organization_ref_id:
        return requester.organization_ref
    return None


def _requesting_unit(reservation) -> str:
    """The requesting department, college, or office, when the records have one.

    The reservation's own organization snapshot is preferred; a campus user's
    organization is used as a fallback. Nothing is invented when no unit is on
    file — the row is simply omitted.
    """
    organization = _requesting_organization(reservation)
    if organization is not None:
        return organization.organization_name
    if reservation.organization:
        return reservation.organization
    requester = reservation.requester if reservation.requester_id else None
    if requester is not None:
        if requester.organization_ref_id:
            return requester.organization_ref.organization_name
        if requester.organization:
            return requester.organization
    return ""


def _is_cas_requesting(reservation) -> bool:
    """Whether the requesting unit is the College of Arts and Sciences itself."""
    candidates = set()
    organization = _requesting_organization(reservation)
    if organization is not None:
        candidates.add(organization.acronym)
        candidates.add(organization.organization_name)
        candidates.add(organization.display_name)
    candidates.add(reservation.organization)
    requester = reservation.requester if reservation.requester_id else None
    if requester is not None:
        candidates.add(requester.organization)
        if requester.organization_ref_id:
            candidates.add(requester.organization_ref.acronym)
            candidates.add(requester.organization_ref.organization_name)
    normalized = {_text(value).casefold() for value in candidates if _text(value)}
    return bool(normalized & {"cas", "college of arts and sciences"})


def _facility_is_gymnasium(reservation) -> bool:
    facility = reservation.facility
    if facility is None:
        return False
    if facility.facility_type == Facility.FacilityType.GYMNASIUM:
        return True
    return _text(facility.name).casefold() == "gymnasium"


def _requested_items(reservation, kind):
    """The reservation items that contain this letter's equipment."""
    name = _EQUIPMENT_NAMES[kind]
    return [
        item
        for item in reservation.items.select_related("equipment").all()
        if _text(item.equipment.name).casefold() == name
    ]


def routing_letter_eligibility(reservation, kind=GSO):
    """Return ``(eligible, reason)`` for one routing letter.

    Both workflow conditions are checked against the current database values:
    the reservation must belong to an internal requester, and it must be
    approved with all required reservation information and its required
    document (the existing event approval letter) on file. The letter is then
    limited to the Gymnasium and to the equipment it actually requests.
    """
    if kind not in LETTER_KINDS:
        raise ValueError(f"Unknown routing letter kind: {kind!r}")
    if not reservation.is_internal:
        return False, "Routing letters are only generated for internal reservations."
    if reservation.status != Reservation.Status.APPROVED:
        return False, "Routing letters are only generated for approved reservations."
    missing = [
        label
        for label, present in (
            ("event name", bool(_text(reservation.event_name))),
            ("facility", bool(reservation.facility_id)),
            ("event date", bool(reservation.date)),
            ("start time", bool(reservation.start_time)),
            ("end time", bool(reservation.end_time)),
            ("requester", bool(_text(documents._name(reservation)))),
        )
        if not present
    ]
    if missing:
        return (
            False,
            "Missing required reservation information: " + ", ".join(missing) + ".",
        )
    if not reservation.has_approval_letter_document:
        return False, "The required event approval letter has not been submitted."
    if not _facility_is_gymnasium(reservation):
        return (
            False,
            "Routing letters are only generated for approved Gymnasium reservations.",
        )
    if not _requested_items(reservation, kind):
        return (
            False,
            f"The reservation does not request the {_EQUIPMENT_LABELS[kind]}.",
        )
    if kind == CAS and _is_cas_requesting(reservation):
        return (
            False,
            "CAS does not need a routing letter to request its own LED wall.",
        )
    return True, ""


def _stored_letter_name(reservation, kind) -> str:
    field = getattr(reservation, _PDF_FIELDS[kind])
    return field.name if field else ""


def _letter_generated_at(reservation, kind):
    return getattr(reservation, _GENERATED_AT_FIELDS[kind])


def _letter_file_exists(reservation, kind) -> bool:
    field = getattr(reservation, _PDF_FIELDS[kind])
    if not field:
        return False
    try:
        return field.storage.exists(field.name)
    except Exception:  # noqa: BLE001 - storage problems mean "not available"
        logger.warning(
            "Could not check the %s file for %s.",
            _DOCUMENT_LABELS[kind],
            reservation.reservation_id,
        )
        return False


def routing_letter_recipient_email(reservation) -> str:
    """The requesting organization's email, falling back to the requester.

    ``accounts.Organization.contact_email`` is the authoritative address for a
    linked internal organization. Older/seeded internal organizations may have
    no address yet, so the verified requester account is the next source; the
    reservation's contact email is the last resort. Only a valid address is
    ever returned.
    """
    candidates = []
    organization = _requesting_organization(reservation)
    if organization is not None:
        candidates.append(organization.contact_email)
    requester = reservation.requester if reservation.requester_id else None
    if requester is not None:
        candidates.append(requester.email)
    candidates.append(reservation.contact_email)
    for raw in candidates:
        email = _text(raw)
        if not email:
            continue
        try:
            validate_email(email)
        except ValidationError:
            continue
        return email
    return ""


def _recipient(kind):
    """Configured recipient block for one letter (never an invented signatory)."""
    if kind == GSO:
        name = getattr(
            settings, "GSO_ROUTING_LETTER_RECIPIENT_NAME", "Sir Clyde"
        )
        designation = getattr(
            settings, "GSO_ROUTING_LETTER_RECIPIENT_DESIGNATION", ""
        )
    else:
        name = getattr(
            settings,
            "CAS_ROUTING_LETTER_RECIPIENT_NAME",
            "College of Arts and Sciences",
        )
        designation = getattr(
            settings, "CAS_ROUTING_LETTER_RECIPIENT_DESIGNATION", ""
        )
    return {
        "name": _text(name) or (
            "Sir Clyde" if kind == GSO else "College of Arts and Sciences"
        ),
        "designation": _text(designation),
    }


def _routing_rows(reservation, kind, items):
    """Only the reservation facts the permission request actually relies on."""
    rows = [("Reservation reference", reservation.reservation_id)]
    requesting_unit = _requesting_unit(reservation)
    if requesting_unit:
        rows.append(("Requesting department", requesting_unit))
    rows.append(("Requester", documents._name(reservation)))
    if reservation.event_name:
        rows.append(("Event", reservation.event_name))
    if reservation.facility_id and reservation.facility.name:
        rows.append(("Facility", reservation.facility.name))
    if reservation.date:
        rows.append(("Event date", documents._format_date(reservation.date)))
    if reservation.start_time and reservation.end_time:
        rows.append((
            "Time",
            f"{documents._format_time(reservation.start_time)} – "
            f"{documents._format_time(reservation.end_time)}",
        ))
    equipment = [
        f"{item.quantity:g} × {item.equipment.name}" for item in items
    ]
    if equipment:
        rows.append(("Equipment requested", "; ".join(equipment)))
    return rows


def _append_signature(document, label, name="", designation=""):
    """One consistent signature/approval area on the existing letter layout."""
    documents._paragraph(
        document, label, size=9, bold=True, color=documents.BLUE, before=16
    )
    if name:
        documents._paragraph(
            document,
            name,
            size=9.5,
            bold=True,
            color=documents.NAVY,
            before=12,
            after=0,
        )
    else:
        documents._paragraph(document, "", before=22, after=0)
    documents._paragraph(
        document, "________________________________", size=8, color=documents.MUTED,
        after=1,
    )
    if designation:
        documents._paragraph(
            document,
            designation,
            size=8,
            color=documents.MUTED,
            after=0,
        )


def _append_signature_areas(document, reservation, kind, letter_settings):
    """Two blocks only: who submits the request and who receives it.

    Neither block states or implies that the receiving department has already
    granted permission; the letter stays a request for permission.
    """
    recipient = _recipient(kind)
    if kind == GSO:
        _append_signature(
            document,
            "Respectfully submitted by:",
            letter_settings.sas_staff_display_name,
            letter_settings.sas_staff_designation,
        )
    else:
        _append_signature(
            document,
            "Respectfully submitted by:",
            documents._name(reservation),
            _requesting_unit(reservation),
        )
    _append_signature(document, "Received by:", recipient["name"])


def _build_docx(reservation, target, kind):
    """Build one routing letter on the existing institutional letterhead."""
    if kind not in LETTER_KINDS:
        raise ValueError(f"Unknown routing letter kind: {kind!r}")
    if not documents.TEMPLATE_PATH.is_file():
        raise FileNotFoundError("approval_template_missing")
    document = documents.Document(str(documents.TEMPLATE_PATH))
    documents._clear_body(document)

    letter_settings = (
        ApprovalLetterSettings.objects.filter(pk=1).first()
        or ApprovalLetterSettings()
    )
    equipment_label = _EQUIPMENT_LABELS[kind]
    recipient = _recipient(kind)
    document.core_properties.title = (
        f"{_DOCUMENT_LABELS[kind]} - {reservation.reservation_id}"
    )
    document.core_properties.subject = (
        f"Permission to use the {equipment_label} at the Gymnasium"
    )
    document.core_properties.author = (
        "Negros Oriental State University — GSO RESERVE"
    )

    section = document.sections[0]
    section.page_width = documents.Inches(8.5)
    section.page_height = documents.Inches(11)
    section.top_margin = documents.Inches(1.25)
    section.bottom_margin = documents.Inches(0.52)
    section.left_margin = documents.Inches(0.7)
    section.right_margin = documents.Inches(0.7)
    section.header_distance = documents.Inches(0.28)
    section.footer_distance = documents.Inches(0.35)

    documents._paragraph(
        document,
        "ROUTING LETTER",
        size=13,
        bold=True,
        color=documents.NAVY,
        align=documents.WD_ALIGN_PARAGRAPH.CENTER,
        after=3,
    )
    documents._paragraph(
        document,
        f"REQUEST FOR PERMISSION TO USE THE {equipment_label.upper()}",
        size=9.5,
        bold=True,
        color=documents.BLUE,
        align=documents.WD_ALIGN_PARAGRAPH.CENTER,
        after=6,
    )
    documents._add_metadata_table(document, reservation)

    documents._paragraph(document, recipient["name"], size=10, bold=True,
                         color=documents.NAVY, before=10, after=0)
    if recipient["designation"]:
        documents._paragraph(
            document, recipient["designation"], size=9, color=documents.MUTED,
            after=0,
        )
    documents._paragraph(document, "", after=4)
    if kind == GSO:
        documents._paragraph(
            document, f"Dear {recipient['name']},", size=9.5, color=documents.TEXT,
            after=6,
        )
    else:
        documents._paragraph(
            document,
            f"To the {recipient['name']}:",
            size=9.5,
            color=documents.TEXT,
            after=6,
        )

    # One direct request. The table below supplies the facts it refers to, so
    # no second request, no purpose/attendee filler, and no claims about the
    # equipment's use beyond this reservation are added.
    requesting_unit = _requesting_unit(reservation) or "The requesting department"
    if kind == GSO:
        introduction = (
            "The General Services Office (GSO) respectfully requests permission "
            f"from your office to use the {equipment_label} for the approved "
            "Gymnasium reservation detailed below."
        )
    else:
        introduction = (
            f"{requesting_unit} respectfully requests permission to use the "
            f"{equipment_label} for the approved Gymnasium reservation detailed "
            "below."
        )
    documents._paragraph(
        document, introduction, size=9.5, color=documents.TEXT, after=4
    )

    documents._section_heading(document, "Reservation details")
    documents._add_detail_table(
        document,
        _routing_rows(reservation, kind, _requested_items(reservation, kind)),
    )
    _append_signature_areas(document, reservation, kind, letter_settings)
    document.save(target)


def _remove_letter(reservation, kind):
    """Clear and delete a letter that the reservation no longer qualifies for."""
    pdf_field_name = _PDF_FIELDS[kind]
    at_field_name = _GENERATED_AT_FIELDS[kind]
    old_name = _stored_letter_name(reservation, kind)
    storage = getattr(reservation, pdf_field_name).storage
    update_fields = []
    if old_name:
        setattr(reservation, pdf_field_name, "")
        update_fields.append(pdf_field_name)
    if getattr(reservation, at_field_name) is not None:
        setattr(reservation, at_field_name, None)
        update_fields.append(at_field_name)
    if kind == CAS and reservation.generated_cas_routing_letter_email_sent_at:
        reservation.generated_cas_routing_letter_email_sent_at = None
        update_fields.append("generated_cas_routing_letter_email_sent_at")
    if not update_fields:
        return
    reservation.save(update_fields=update_fields)
    if old_name:
        try:
            storage.delete(old_name)
        except Exception:  # noqa: BLE001 - the cleared field is what matters
            # A file still being streamed by an earlier request (notably on
            # Windows) must never fail reconciliation; the field is already
            # cleared, so the stale file is harmless.
            logger.warning(
                "Could not remove the previous %s file for %s.",
                _DOCUMENT_LABELS[kind],
                reservation.reservation_id,
            )


def _generate_one(reservation, kind, *, regenerate=False):
    """Generate and persist one letter at most once per reservation version."""
    eligible, _reason = routing_letter_eligibility(reservation, kind)
    if not eligible:
        _remove_letter(reservation, kind)
        return False
    if (
        not regenerate
        and _letter_file_exists(reservation, kind)
        and _letter_generated_at(reservation, kind)
        and reservation.updated_at <= _letter_generated_at(reservation, kind)
    ):
        return True

    pdf_field_name = _PDF_FIELDS[kind]
    at_field_name = _GENERATED_AT_FIELDS[kind]
    old_name = _stored_letter_name(reservation, kind)
    try:
        with tempfile.TemporaryDirectory(prefix=f"gso-{kind}-routing-letter-") as temporary:
            tempdir = Path(temporary)
            docx_path = tempdir / f"{reservation.reservation_id}-{kind.upper()}.docx"
            _build_docx(reservation, docx_path, kind)
            pdf_path = documents._convert_pdf(docx_path, tempdir)
            with pdf_path.open("rb") as stream:
                getattr(reservation, pdf_field_name).save(
                    pdf_path.name, File(stream), save=False
                )
        # Do NOT touch ``updated_at`` here: it tracks business-data changes and
        # is shared by both letters. Bumping it for one document would make the
        # other look stale and the two would keep regenerating each other.
        reservation.save(update_fields=[pdf_field_name])
        # Record the marker AFTER the save so it is always newer than the last
        # business change the letter was built from.
        generated_at = timezone.now()
        setattr(reservation, at_field_name, generated_at)
        reservation.save(update_fields=[at_field_name])
    except Exception:
        logger.exception(
            "%s generation failed for %s.",
            _DOCUMENT_LABELS[kind],
            reservation.reservation_id,
        )
        raise

    if old_name and old_name != _stored_letter_name(reservation, kind):
        try:
            getattr(reservation, pdf_field_name).storage.delete(old_name)
        except Exception:  # noqa: BLE001 - the new file is already stored
            logger.warning(
                "Could not remove the previous %s file for %s.",
                _DOCUMENT_LABELS[kind],
                reservation.reservation_id,
            )
    return True


def _send_cas_letter_email(reservation):
    """Email the CAS letter once to the requesting organization.

    The letter is already stored before this runs. A missing address or a
    delivery failure is logged and never deletes the document or affects the
    approved reservation. The row lock prevents two concurrent accesses from
    delivering the same letter twice.
    """
    from notifications.email_service import send_cas_routing_letter

    if reservation.generated_cas_routing_letter_email_sent_at:
        return "already_sent"
    if not _letter_file_exists(reservation, CAS):
        return "pdf_unavailable"
    if not routing_letter_recipient_email(reservation):
        logger.warning(
            "CAS routing letter for %s has no requesting-organization email; "
            "the document remains available to staff.",
            reservation.reservation_id,
        )
        return "no_email"
    try:
        with transaction.atomic():
            locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
            if locked.generated_cas_routing_letter_email_sent_at:
                return "already_sent"
            ok, reason = send_cas_routing_letter(locked)
            if not ok:
                logger.warning(
                    "CAS routing letter email for %s was not delivered (%s); "
                    "the document remains available to staff.",
                    locked.reservation_id,
                    reason or "delivery_failed",
                )
                return reason or "delivery_failed"
            locked.generated_cas_routing_letter_email_sent_at = timezone.now()
            locked.save(update_fields=["generated_cas_routing_letter_email_sent_at"])
            reservation.generated_cas_routing_letter_email_sent_at = (
                locked.generated_cas_routing_letter_email_sent_at
            )
            return "sent"
    except Exception:  # noqa: BLE001 - email must never destroy the document
        logger.exception(
            "CAS routing letter email failed for %s; the document remains "
            "available to staff.",
            reservation.reservation_id,
        )
        return "failed"


def generate_routing_letters(reservation, *, regenerate=False, send_cas_email=False):
    """Generate every routing letter the current reservation qualifies for.

    Both letters are attempted even if one fails, so a single broken document
    never blocks the other. Any generation error is re-raised after the attempt
    so the approval caller can log it while leaving the approval committed.
    Ineligible letters are removed, which is what keeps a CAS letter from
    staying attached after the LED wall is no longer requested.
    """
    first_error = None
    generated = {}
    for kind in LETTER_KINDS:
        try:
            generated[kind] = _generate_one(reservation, kind, regenerate=regenerate)
        except Exception as exc:  # noqa: BLE001 - attempt the other letter too
            generated[kind] = False
            first_error = first_error or exc
    if send_cas_email and generated.get(CAS):
        _send_cas_letter_email(reservation)
    if first_error is not None:
        raise first_error
    return reservation


def ensure_routing_letters(reservation):
    """Return current letters, regenerating or removing them as needed.

    Called when staff preview, download, or print a document. Previously
    generated PDFs are reused as-is until the reservation changes, so opening
    the page or printing repeatedly never creates duplicate documents.
    Email is never sent from this path: repeated staff access must not produce
    repeated messages.
    """
    eligible_kinds = []
    for kind in LETTER_KINDS:
        eligible, reason = routing_letter_eligibility(reservation, kind)
        if eligible:
            eligible_kinds.append(kind)
        else:
            logger.debug(
                "%s is not eligible for %s: %s",
                _DOCUMENT_LABELS[kind],
                reservation.reservation_id,
                reason,
            )
    if not eligible_kinds:
        reason = routing_letter_eligibility(reservation, GSO)[1]
        raise RoutingLetterUnavailable(reason)
    generate_routing_letters(reservation, send_cas_email=False)
    return reservation
