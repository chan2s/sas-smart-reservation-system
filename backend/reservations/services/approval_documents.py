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
from docx.shared import Inches, Pt

from reservations.models import Reservation

logger = logging.getLogger(__name__)
TEMPLATE_PATH = Path(settings.BASE_DIR) / "templates/documents/reservation_approval_template.docx"


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
        # Also allow a command name in SOFFICE_PATH for deployments that manage
        # PATH themselves, while preferring a valid explicit filesystem path.
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
    return f"PHP {Decimal(value or 0):,.2f}"


def _clear_body(document):
    """Remove template's intentionally blank body paragraphs, keeping section props."""
    body = document._element.body
    for child in list(body):
        if child.tag.endswith("}sectPr"):
            continue
        body.remove(child)


def _paragraph(document, text="", *, bold=False, size=11, align=None, after=4):
    paragraph = document.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(after)
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    return paragraph


def _hide_table_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        from docx.oxml import OxmlElement
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = qn(f"w:{edge}")
        element = borders.find(tag)
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "nil")


def _build_docx(reservation, target):
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError("approval_template_missing")
    document = Document(str(TEMPLATE_PATH))
    _clear_body(document)
    document.core_properties.title = f"Reservation Approval - {reservation.reservation_id}"

    _paragraph(document, timezone.localdate().strftime("%B %d, %Y"), align=WD_ALIGN_PARAGRAPH.RIGHT, after=10)
    _paragraph(document, _name(reservation), bold=True, after=0)
    if reservation.organization:
        _paragraph(document, reservation.organization, after=0)
    _paragraph(document, f"{reservation.contact_email or (reservation.requester.email if reservation.requester_id else '')}", after=10)
    _paragraph(document, "Dear Sir/Madam:", after=8)
    _paragraph(
        document,
        f"This is to inform you that your request to use {reservation.facility.name} "
        f"for {reservation.event_name} has been approved, subject to the details below.",
        after=8,
    )

    rows = [
        ("Reservation reference", reservation.reservation_id),
        ("Event", reservation.event_name),
        ("Description", reservation.description or "Not provided"),
        ("Purpose", reservation.purpose or "Not provided"),
        ("Facility", reservation.facility.name),
        ("Event date", reservation.date.strftime("%B %d, %Y")),
        ("Time", f"{reservation.start_time.strftime('%I:%M %p')} – {reservation.end_time.strftime('%I:%M %p')}"),
        ("Attendees", str(reservation.expected_participants)),
        ("Contact person", reservation.contact_person or _name(reservation)),
        ("Contact number", reservation.contact_phone or "Not provided"),
    ]
    equipment = list(reservation.items.select_related("equipment").all())
    rows.append(("Equipment", "; ".join(f"{i.quantity} × {i.equipment.name}" for i in equipment) or "None"))
    for fee in reservation.fees.all():
        rows.append((fee.description, _php(fee.subtotal)))
    rows.append(("Total amount payable", _php(reservation.estimated_total)))

    details = document.add_table(rows=0, cols=2)
    details.autofit = False
    details.columns[0].width = Inches(1.55)
    details.columns[1].width = Inches(4.85)
    for label, value in rows:
        cells = details.add_row().cells
        cells[0].width = Inches(1.55)
        cells[1].width = Inches(4.85)
        cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        cells[1].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        for cell, text in zip(cells, (label, value)):
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(text)
            run.font.size = Pt(9.5)
            run.bold = cell is cells[0] or label == "Total amount payable"

    _paragraph(document, "Please download and print this letter to obtain the signatures below. Thank you.", after=12)
    signatures = document.add_table(rows=3, cols=3)
    signatures.autofit = False
    _hide_table_borders(signatures)
    signatories = (
        ("SHELLA MEA A. ESPAÑOLA", "UED Staff / SAS Staff"),
        ("FRANCIS M. GALON", "Asst. Campus Director for Administration and Finance"),
        ("NAME AND SIGNATURE OF THE RENTER", "Renter"),
    )
    for index, (printed_name, title) in enumerate(signatories):
        for row in signatures.rows:
            row.cells[index].width = Inches(2.13)
            row.cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
            from docx.oxml import OxmlElement
            tr_pr = row._tr.get_or_add_trPr()
            tr_pr.append(OxmlElement("w:cantSplit"))
        signature_cell = signatures.cell(0, index)
        signature_cell.text = "\n\n"
        signature_cell.paragraphs[0].paragraph_format.space_after = Pt(0)
        line_cell = signatures.cell(1, index)
        line_cell.text = ""
        line = line_cell.paragraphs[0]
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        line.paragraph_format.space_after = Pt(1)
        line_run = line.add_run("________________________________")
        line_run.font.size = Pt(7)
        printed_cell = signatures.cell(2, index)
        printed_cell.text = ""
        p = printed_cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.keep_together = True
        run = p.add_run(printed_name)
        run.bold = True
        run.font.size = Pt(7.5)
        title_p = printed_cell.add_paragraph(title)
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_p.paragraph_format.space_after = Pt(0)
        for run in title_p.runs:
            run.font.size = Pt(7)
        if index == 2:
            printed_name = printed_cell.add_paragraph("Printed name: __________________________")
            printed_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
            printed_name.paragraph_format.space_after = Pt(0)
            for run in printed_name.runs:
                run.font.size = Pt(7)
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
        # A previous output must not make a no-op/failed invocation appear to
        # have produced this conversion's PDF.
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
            message = f"LibreOffice reported success but did not create a non-empty PDF for {Path(docx_path).name}."
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
        not force
        and reservation.generated_approval_status == Reservation.GeneratedApprovalStatus.GENERATED
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

