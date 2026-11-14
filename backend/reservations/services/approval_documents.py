"""Generation and delivery support for private external approval letters."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.utils import timezone
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from reservations.models import ApprovalLetterSettings, Reservation

logger = logging.getLogger(__name__)
TEMPLATE_PATH = Path(settings.BASE_DIR) / "templates/documents/reservation_approval_template.docx"

NAVY = "123B68"
BLUE = "1F5A91"
GOLD = "C9A449"
PALE_BLUE = "EDF3F8"
TEXT = "202B36"
MUTED = "536273"


class LibreOfficeUnavailableError(RuntimeError):
    """Raised when no LibreOffice executable can be found on this host."""


class PdfConversionError(RuntimeError):
    """Raised when LibreOffice cannot produce a valid approval PDF."""


def _find_soffice_executable():
    """Discover the LibreOffice binary across Windows and Linux installations."""
    configured_paths = [
        os.environ.get("SOFFICE_PATH", "").strip().strip('"'),
        getattr(settings, "LIBREOFFICE_BIN", None),
    ]
    for configured in configured_paths:
        if not configured:
            continue
        if Path(configured).is_file():
            return str(Path(configured))
        resolved = shutil.which(configured)
        if resolved:
            return resolved

    for command in ("soffice", "libreoffice"):
        resolved = shutil.which(command)
        if resolved:
            return resolved

    if platform.system() == "Windows":
        candidates = (
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        )
    else:
        candidates = (
            "/usr/bin/soffice",
            "/usr/local/bin/soffice",
            "/usr/lib/libreoffice/program/soffice",
            "/opt/libreoffice/program/soffice",
        )
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file() and (platform.system() == "Windows" or os.access(path, os.X_OK)):
            return str(path)

    message = (
        "LibreOffice could not be found. Install LibreOffice and set SOFFICE_PATH "
        "to the full path of soffice (for example, C:\\Program Files\\LibreOffice\\program\\soffice.exe "
        "on Windows or /usr/bin/soffice on Linux)."
    )
    logger.error(message)
    raise LibreOfficeUnavailableError(message)


def _name(reservation):
    if reservation.requester_id:
        return reservation.requester.display_name
    return reservation.contact_person or reservation.organization or "External Requester"


def _php(value):
    return f"PHP {Decimal(value):,.2f}"


def _format_date(value):
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def _format_time(value):
    return value.strftime("%I:%M %p").lstrip("0")


def _clear_body(document):
    """Remove template body content while keeping the page section properties."""
    body = document._element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def _set_cell_shading(cell, fill):
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _set_table_borders(table, *, color="D6DEE7", size="4", edges=("bottom",)):
    properties = table._tbl.tblPr
    borders = properties.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        properties.append(borders)
    for edge in edges:
        tag = qn(f"w:{edge}")
        border = borders.find(tag)
        if border is None:
            border = OxmlElement(f"w:{edge}")
            borders.append(border)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), size)
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), color)


def _set_cell_margins(cell, *, top=65, start=95, bottom=65, end=95):
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for side, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _keep_row_together(row):
    properties = row._tr.get_or_add_trPr()
    if properties.find(qn("w:cantSplit")) is None:
        properties.append(OxmlElement("w:cantSplit"))


def _style_run(run, *, size=10, bold=False, color=TEXT, font="Arial", italic=False):
    run.bold = bold
    run.italic = italic
    run.font.name = font
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    return run


def _paragraph(document, text="", *, size=10, bold=False, color=TEXT, align=None,
               before=0, after=4, line_spacing=1.08, keep=False):
    paragraph = document.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = line_spacing
    paragraph.paragraph_format.keep_together = keep
    _style_run(paragraph.add_run(str(text)), size=size, bold=bold, color=color)
    return paragraph


def _append_templated_paragraphs(document, content, template_values, *, size=9.5, color=TEXT, after=4):
    from reservations.services.approval_letter_templates import resolve_template_text

    for text in (content or "").splitlines():
        if text.strip():
            _paragraph(
                document,
                resolve_template_text(text.strip(), template_values),
                size=size,
                color=color,
                after=after,
            )


def _text_align(value):
    return {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }.get(value)


def _append_rich_inline(paragraph, nodes, template_values, *, base_size=9.5, base_color=TEXT, base_bold=False):
    from reservations.services.approval_letter_templates import resolve_template_text

    for node in nodes or []:
        if node["type"] == "hardBreak":
            paragraph.add_run().add_break()
            continue
        marks = {mark["type"] for mark in node.get("marks", [])}
        value = resolve_template_text(node["text"], template_values)
        if not value:
            continue
        _style_run(
            paragraph.add_run(value),
            size=base_size,
            bold=base_bold or "bold" in marks,
            italic="italic" in marks,
            color=base_color,
        )


def _append_rich_paragraph(document, node, template_values, *, list_style=None):
    from reservations.services.approval_letter_templates import resolve_template_text

    attrs = node.get("attrs", {})
    content = node.get("content", [])
    if not any(
        child["type"] == "hardBreak"
        or (child["type"] == "text" and resolve_template_text(child["text"], template_values))
        for child in content
    ):
        return
    paragraph = document.add_paragraph(style=list_style) if list_style else document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(attrs.get("spaceAfter", 4))
    paragraph.paragraph_format.line_spacing = 1.08
    paragraph.paragraph_format.keep_together = True
    paragraph.alignment = _text_align(attrs.get("textAlign"))
    node_type = node["type"]
    if node_type == "heading":
        level = attrs.get("level", 2)
        font_size, color = {1: (17, NAVY), 2: (11, BLUE), 3: (10, BLUE)}[level]
        paragraph.paragraph_format.keep_with_next = True
        _append_rich_inline(
            paragraph, content, template_values,
            base_size=font_size, base_color=color, base_bold=True,
        )
    else:
        _append_rich_inline(paragraph, content, template_values)
    return paragraph


def _append_rich_list(document, node, template_values):
    style = "List Bullet" if node["type"] == "bulletList" else "List Number"
    for item in node.get("content", []):
        for paragraph in item.get("content", []):
            _append_rich_paragraph(document, paragraph, template_values, list_style=style)


def _reservation_detail_rows(reservation):
    rows = [("Reservation reference", reservation.reservation_id)]
    if reservation.facility and reservation.facility.name:
        rows.append(("Facility", reservation.facility.name))
    if reservation.event_name:
        rows.append(("Event", reservation.event_name))
    if reservation.date:
        rows.append(("Event date", _format_date(reservation.date)))
    if reservation.start_time and reservation.end_time:
        rows.append(("Time", f"{_format_time(reservation.start_time)} to {_format_time(reservation.end_time)}"))
    if reservation.purpose:
        rows.append(("Purpose", reservation.purpose))
    if reservation.description:
        rows.append(("Event description", reservation.description))
    if reservation.expected_participants:
        rows.append(("Expected attendees", f"{reservation.expected_participants:,}"))
    equipment = list(reservation.items.select_related("equipment").all())
    if equipment:
        rows.append((
            "Equipment requested",
            "; ".join(f"{item.quantity:g} units of {item.equipment.name}" for item in equipment),
        ))
    fees = list(reservation.fees.all())
    if fees:
        for fee in fees:
            rows.append((fee.description, _php(fee.subtotal)))
        if reservation.estimated_total is not None and Decimal(reservation.estimated_total) > 0:
            rows.append(("Total applicable fees", _php(reservation.estimated_total)))
    return rows


def _append_reservation_conditions(document, reservation):
    conditions = []
    facility_rules = reservation.facility.rules if reservation.facility_id else []
    if isinstance(facility_rules, (list, tuple)):
        conditions.extend(str(rule).strip() for rule in facility_rules if str(rule).strip())
    if reservation.special_requirements:
        conditions.append(f"Additional reservation requirement: {reservation.special_requirements.strip()}")
    for condition in conditions:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Inches(0.17)
        paragraph.paragraph_format.first_line_indent = Inches(-0.15)
        paragraph.paragraph_format.space_after = Pt(1.5)
        paragraph.paragraph_format.line_spacing = 1.0
        paragraph.paragraph_format.keep_together = True
        _style_run(paragraph.add_run("•  "), size=9, bold=True, color=GOLD)
        _style_run(paragraph.add_run(condition), size=8.8, color=TEXT)


def _append_body_content(document, reservation, template_values, body_content):
    for node in body_content.get("content", []):
        node_type = node["type"]
        if node_type == "documentMetadata":
            _add_metadata_table(document, reservation)
        elif node_type == "reservationDetails":
            _add_detail_table(document, _reservation_detail_rows(reservation))
        elif node_type == "reservationConditions":
            _append_reservation_conditions(document, reservation)
        elif node_type in {"paragraph", "heading"}:
            _append_rich_paragraph(document, node, template_values)
        elif node_type in {"bulletList", "orderedList"}:
            _append_rich_list(document, node, template_values)


def _section_heading(document, title):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(7)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.keep_with_next = True
    _style_run(paragraph.add_run(title.upper()), size=9, bold=True, color=BLUE)
    return paragraph


def _add_detail_table(document, rows):
    table = document.add_table(rows=0, cols=2)
    table.autofit = False
    table.allow_autofit = False
    table.columns[0].width = Inches(1.62)
    table.columns[1].width = Inches(5.48)
    _set_table_borders(table, color="D9E1E9", size="4", edges=("bottom",))
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].width = Inches(1.62)
        cells[1].width = Inches(5.48)
        for cell in cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_margins(cell)
        _set_cell_shading(cells[0], PALE_BLUE)
        label_p = cells[0].paragraphs[0]
        label_p.paragraph_format.space_after = Pt(0)
        label_p.paragraph_format.line_spacing = 1.0
        _style_run(label_p.add_run(label), size=8.8, bold=True, color=NAVY)
        value_p = cells[1].paragraphs[0]
        value_p.paragraph_format.space_after = Pt(0)
        value_p.paragraph_format.line_spacing = 1.0
        _style_run(value_p.add_run(str(value)), size=9.2,
                   bold=label == "Total applicable fees", color=TEXT)
        _keep_row_together(table.rows[-1])
    return table


def _add_metadata_table(document, reservation):
    table = document.add_table(rows=1, cols=2)
    table.autofit = False
    table.columns[0].width = Inches(4.28)
    table.columns[1].width = Inches(2.82)
    _set_table_borders(table, color=GOLD, size="10", edges=("bottom",))
    reference, issue_date = table.rows[0].cells
    for cell in (reference, issue_date):
        _set_cell_margins(cell, top=25, start=20, bottom=65, end=20)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = reference.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    _style_run(p.add_run("REFERENCE  "), size=8.5, bold=True, color=BLUE)
    _style_run(p.add_run(reservation.reservation_id), size=9, bold=True, color=NAVY)
    p = issue_date.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = Pt(0)
    _style_run(p.add_run("ISSUED  "), size=8.5, bold=True, color=BLUE)
    _style_run(p.add_run(_format_date(timezone.localdate())), size=9, color=TEXT)


def _build_docx(reservation, target, *, letter_settings=None):
    from reservations.services.approval_letter_templates import (
        placeholder_values,
        resolve_template_text,
    )

    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError("approval_template_missing")
    document = Document(str(TEMPLATE_PATH))
    _clear_body(document)
    letter_settings = letter_settings or ApprovalLetterSettings.objects.filter(pk=1).first()
    letter_settings = letter_settings or ApprovalLetterSettings()
    template_values = placeholder_values(reservation, letter_settings)
    document.core_properties.title = f"Reservation Approval - {reservation.reservation_id}"
    document.core_properties.subject = "External reservation approval"
    document.core_properties.author = "Negros Oriental State University — SAS RESERVE"

    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1.25)
    section.bottom_margin = Inches(0.52)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)
    section.header_distance = Inches(0.28)
    section.footer_distance = Inches(0.35)

    _append_body_content(
        document,
        reservation,
        template_values,
        letter_settings.body_content,
    )

    signatures = document.add_table(rows=5, cols=2)
    signatures.autofit = False
    signatures.columns[0].width = Inches(3.55)
    signatures.columns[1].width = Inches(3.55)
    signatures.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for row in signatures.rows:
        _keep_row_together(row)
        for cell in row.cells:
            cell.width = Inches(3.55)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
            _set_cell_margins(cell, top=0, start=90, bottom=0, end=90)
    # Chain the signature rows so Word keeps the entire group together when a
    # long reservation details section approaches a page boundary.
    for row in signatures.rows[:-1]:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.keep_with_next = True
                paragraph.paragraph_format.keep_together = True

    renter, staff = signatures.rows[0].cells
    renter.paragraphs[0].paragraph_format.space_after = Pt(1)
    _style_run(renter.paragraphs[0].add_run("Agreed by the Renter:"), size=8.5, bold=True, color=BLUE)
    for cell in signatures.rows[1].cells:
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        p.add_run(" ").font.size = Pt(35)
    for cell in signatures.rows[2].cells:
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(1)
        _style_run(p.add_run("________________________________"), size=8, color=MUTED)

    renter_p = signatures.rows[3].cells[0].paragraphs[0]
    renter_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    renter_p.paragraph_format.keep_together = True
    _style_run(renter_p.add_run(_name(reservation)), size=8.5, bold=True, color=NAVY)
    _style_run(renter_p.add_run("\nName & Signature of the Renter"), size=7.8, color=MUTED)

    staff_p = signatures.rows[3].cells[1].paragraphs[0]
    staff_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    staff_p.paragraph_format.keep_together = True
    if letter_settings.sas_staff_display_name:
        _style_run(staff_p.add_run(letter_settings.sas_staff_display_name), size=8.5, bold=True, color=NAVY)
        staff_p.add_run("\n")
    if letter_settings.sas_staff_designation:
        _style_run(staff_p.add_run(letter_settings.sas_staff_designation), size=7.8, color=MUTED)

    approver = signatures.rows[4].cells[0].merge(signatures.rows[4].cells[1])
    signatory_settings = letter_settings
    approver_p = approver.paragraphs[0]
    approver_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    approver_p.paragraph_format.space_before = Pt(8)
    approver_p.paragraph_format.space_after = Pt(0)
    approver_p.paragraph_format.keep_together = True
    approver_p.paragraph_format.keep_with_next = True
    _style_run(approver_p.add_run(resolve_template_text(
        signatory_settings.approval_label, template_values,
    )), size=8.5, bold=True, color=BLUE)

    signature_space = approver.add_paragraph()
    signature_space.alignment = WD_ALIGN_PARAGRAPH.CENTER
    signature_space.paragraph_format.space_before = Pt(18)
    signature_space.paragraph_format.space_after = Pt(10)
    signature_space.paragraph_format.keep_together = True
    signature_space.paragraph_format.keep_with_next = True
    _style_run(signature_space.add_run("________________________________"), size=8, color=MUTED)

    name_paragraph = approver.add_paragraph()
    name_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_paragraph.paragraph_format.space_before = Pt(0)
    name_paragraph.paragraph_format.space_after = Pt(0)
    name_paragraph.paragraph_format.keep_together = True
    _style_run(name_paragraph.add_run(resolve_template_text(
        "{{signatory_name}}", template_values,
    )), size=9, bold=True, color=NAVY)
    if signatory_settings and signatory_settings.credentials:
        name_paragraph.add_run("\n")
        _style_run(name_paragraph.add_run(resolve_template_text(
            "{{signatory_credentials}}", template_values,
        )), size=8.3, color=TEXT)
    if signatory_settings and signatory_settings.designation:
        name_paragraph.add_run("\n")
        _style_run(name_paragraph.add_run(resolve_template_text(
            "{{signatory_designation}}", template_values,
        )), size=8.3, color=MUTED)

    document.save(target)


def _convert_pdf(docx_path, output_dir):
    executable = _find_soffice_executable()
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    timeout_seconds = settings.LIBREOFFICE_TIMEOUT_SECONDS
    # A unique user profile prevents LibreOffice's profile lock from making
    # concurrent requests block or attach to another conversion process.
    # TemporaryDirectory removes the profile on success, timeout, and errors.
    with tempfile.TemporaryDirectory(prefix="sas-libreoffice-profile-") as profile_dir:
        profile_url = Path(profile_dir).resolve().as_uri()
        command = [
            executable,
            f"-env:UserInstallation={profile_url}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(docx_path),
        ]
        pdf_path.unlink(missing_ok=True)
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            message = (
                f"LibreOffice executable {executable!r} was discovered but could not be started. "
                "Check SOFFICE_PATH and the backend image installation."
            )
            logger.exception(message)
            raise LibreOfficeUnavailableError(message) from exc
        except subprocess.TimeoutExpired as exc:
            message = (
                f"LibreOffice PDF conversion exceeded the {timeout_seconds} second timeout "
                f"for {Path(docx_path).name}."
            )
            logger.error("%s stdout=%r stderr=%r", message, exc.stdout, exc.stderr)
            raise PdfConversionError(message) from exc

        if result.returncode:
            message = (
                f"LibreOffice PDF conversion failed with exit code {result.returncode}: "
                f"{(result.stderr or result.stdout or 'no converter output')[:500]}"
            )
            logger.error("%s", message)
            raise PdfConversionError(message)
        if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            message = f"LibreOffice reported success but did not create a non-empty approval PDF for {Path(docx_path).name}."
            logger.error("%s stdout=%r stderr=%r", message, result.stdout, result.stderr)
            raise PdfConversionError(message)
        with pdf_path.open("rb") as stream:
            pdf_bytes = stream.read()
            if (
                not pdf_bytes.startswith(b"%PDF-")
                or len(pdf_bytes) < 100
                or b"%%EOF" not in pdf_bytes[-1024:]
            ):
                message = f"LibreOffice created an invalid or incomplete PDF for {Path(docx_path).name}."
                logger.error("%s stdout=%r stderr=%r", message, result.stdout, result.stderr)
                raise PdfConversionError(message)
    return pdf_path


def generate_approval_documents(reservation, *, force=False):
    """Generate and persist the DOCX/PDF once, retaining the reservation on errors."""
    if reservation.requester_type != Reservation.RequesterType.EXTERNAL:
        return reservation
    if (
        reservation.generated_approval_status == Reservation.GeneratedApprovalStatus.GENERATED
        and reservation.generated_approval_pdf
        and reservation.generated_approval_docx
    ):
        return reservation
    try:
        old_docx_name = reservation.generated_approval_docx.name if reservation.generated_approval_docx else ""
        old_pdf_name = reservation.generated_approval_pdf.name if reservation.generated_approval_pdf else ""
        with tempfile.TemporaryDirectory(prefix="sas-approval-") as temporary:
            tempdir = Path(temporary)
            docx_path = tempdir / f"{reservation.reservation_id}.docx"
            _build_docx(reservation, docx_path)
            pdf_path = _convert_pdf(docx_path, tempdir)
            with docx_path.open("rb") as stream:
                reservation.generated_approval_docx.save(docx_path.name, File(stream), save=False)
            with pdf_path.open("rb") as stream:
                reservation.generated_approval_pdf.save(pdf_path.name, File(stream), save=False)
            reservation.generated_approval_status = Reservation.GeneratedApprovalStatus.GENERATED
            reservation.generated_approval_error = ""
            reservation.save(update_fields=[
                "generated_approval_docx", "generated_approval_pdf",
                "generated_approval_status", "generated_approval_error", "updated_at",
            ])
        if old_docx_name and old_docx_name != reservation.generated_approval_docx.name:
            reservation.generated_approval_docx.storage.delete(old_docx_name)
        if old_pdf_name and old_pdf_name != reservation.generated_approval_pdf.name:
            reservation.generated_approval_pdf.storage.delete(old_pdf_name)
        return reservation
    except Exception as exc:  # Generation failures must not undo approval.
        logger.exception("Approval document generation failed for %s.", reservation.reservation_id)
        Reservation.objects.filter(pk=reservation.pk).update(
            generated_approval_status=Reservation.GeneratedApprovalStatus.FAILED,
            generated_approval_error=(str(exc) or type(exc).__name__)[:80],
        )
        reservation.generated_approval_status = Reservation.GeneratedApprovalStatus.FAILED
        reservation.generated_approval_error = (str(exc) or type(exc).__name__)[:80]
        raise
