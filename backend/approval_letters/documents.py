"""Approval-letter document generation (PDF + DOCX).

Both formats are rendered from ONE shared context (``build_letter_context``)
so the letter a requester sees in the email is the letter the signatory
previewed. The letterhead uses the institutional names the system already
uses; no official logo is invented.

PDF  — reportlab/Platypus, using the NORSU header/footer artwork and shared
       reservation/signature context.
DOCX — python-docx populates the supplied template, retaining its text boxes,
       images, headers, footers, and section layout.
"""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from django.conf import settings
from django.utils import timezone

from . import signature
from .constants import (
    DOCUMENT_DISCLAIMER,
    INSTITUTION,
    ISSUING_OFFICE,
    MISSION_STATEMENT,
    QUALITY_POLICY,
    SIGNATORY_POSITION,
    SYSTEM_NAME,
    TEST_SIGNATURE_DISCLAIMER,
    VISION_STATEMENT,
)

# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

def _format_time(value) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def build_letter_context(letter) -> dict:
    """Everything both renderers need, read live from the reservation.

    Detail fields are read from the reservation at render time (never
    snapshotted) so a preview always reflects the CURRENT approved data; the
    requester identity snapshots on the letter exist only for delivery
    bookkeeping.
    """
    from reservations.models import Reservation

    reservation = letter.reservation
    issued_at = timezone.localtime(letter.created_at)

    # Department/organization: the reservation's own snapshot first (covers
    # external organizations and staff-entered reservations), then the campus
    # requester's account organization.
    organization = (
        reservation.organization
        or (reservation.requester.organization if reservation.requester else "")
    )

    resources = [
        f"{item.quantity} × {item.equipment.name}" for item in reservation.items.all()
    ]

    # ``Facility.rules`` is a JSON list of strings (blank-safe); a stray
    # non-string entry is stringified rather than breaking the letter.
    facility_rules = [
        str(rule).strip()
        for rule in (reservation.facility.rules or [])
        if str(rule).strip()
    ]

    fees = list(reservation.fees.all()) if reservation.requester_type == Reservation.RequesterType.EXTERNAL else []
    # PDF core fonts cannot render the ₱ glyph, so amounts use the ISO code.
    estimated_total = (
        f"PHP {reservation.estimated_total:,.2f}" if fees else ""
    )

    return {
        "letter_id": letter.letter_id,
        "letter_status": letter.get_status_display(),
        "issued_date": issued_at.strftime("%B %d, %Y").replace(" 0", " "),
        "issued_at": issued_at,
        "reservation_reference": reservation.reservation_id,
        "reservation_pk": reservation.pk,
        "requester_name": letter.requester_name or reservation.requester_display_name,
        "requester_email": letter.requester_email,
        "organization": organization,
        "affiliation_label": reservation.affiliation_label,
        "event_name": reservation.event_name,
        "facility_name": reservation.facility.name,
        "facility_location": reservation.facility.location,
        "reservation_date": reservation.date.strftime("%B %d, %Y").replace(" 0", " "),
        "reservation_start": _format_time(reservation.start_time),
        "reservation_end": _format_time(reservation.end_time),
        "purpose": reservation.purpose or reservation.description or "—",
        "expected_participants": reservation.expected_participants,
        "resources": resources,
        "facility_rules": facility_rules,
        "estimated_total": estimated_total,
        "is_external": reservation.requester_type == Reservation.RequesterType.EXTERNAL,
        "signatory_name": (
            letter.signatory_name
            or (
                letter.signatory.get_full_name().strip() or letter.signatory.username
                if letter.signatory_id
                else ""
            )
        ),
        "signatory_position": SIGNATORY_POSITION,
        "signed_at": timezone.localtime(letter.signed_at) if letter.signed_at else None,
        "test_signature_disclaimer": TEST_SIGNATURE_DISCLAIMER,
        "issuing_office": ISSUING_OFFICE,
        "institution": INSTITUTION,
        "system_name": SYSTEM_NAME,
        "vision_statement": VISION_STATEMENT,
        "mission_statement": MISSION_STATEMENT,
        "quality_policy": QUALITY_POLICY,
        "document_disclaimer": DOCUMENT_DISCLAIMER,
    }


def _detail_rows(context: dict) -> list[tuple[str, str]]:
    rows = [
        ("Reference number", context["reservation_reference"]),
        ("Event", context["event_name"]),
        ("Facility", context["facility_name"]),
        ("Date", context["reservation_date"]),
        (
            "Time",
            f"{context['reservation_start']} – {context['reservation_end']}",
        ),
        ("Purpose", context["purpose"]),
    ]
    if context["organization"]:
        rows.insert(2, ("Organization", context["organization"]))
    if context.get("requester_email"):
        rows.insert(3, ("Requester email", context["requester_email"]))
    if context.get("facility_location"):
        rows.insert(5, ("Facility location", context["facility_location"]))
    if context["expected_participants"]:
        rows.append(("Expected participants", str(context["expected_participants"])))
    if context["resources"]:
        rows.append(("Requested resources", "; ".join(context["resources"])))
    if context["estimated_total"]:
        rows.append(("Estimated fees", context["estimated_total"]))
    return rows


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_BRAND = colors.HexColor("#3B5BDB")
_INK = colors.HexColor("#212127")
_MUTED = colors.HexColor("#6B6B73")
_LINE = colors.HexColor("#C9C9D1")
_SOFT = colors.HexColor("#F1F3F9")


class _SignatureFlowable(Flowable):
    """The test signature drawn with the shared signature renderer."""

    def __init__(self, width: float, name: str):
        super().__init__()
        self.width = width
        self.name = name
        self.height = 52

    def draw(self):
        signature.draw_test_signature_pdf(self.canv, 0, self.height, self.name, self.width)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "institution": ParagraphStyle(
            "institution", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=14.5, leading=18, textColor=_INK, alignment=TA_CENTER,
        ),
        "office": ParagraphStyle(
            "office", parent=base["Normal"], fontName="Helvetica",
            fontSize=10.5, leading=14, textColor=_MUTED, alignment=TA_CENTER,
        ),
        "system": ParagraphStyle(
            "system", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8.5, leading=11, textColor=_MUTED, alignment=TA_CENTER,
        ),
        "title": ParagraphStyle(
            "lettertitle", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12.5, leading=16, textColor=_BRAND, alignment=TA_CENTER,
            spaceBefore=10, spaceAfter=2,
        ),
        "reference": ParagraphStyle(
            "reference", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=12, textColor=_MUTED, alignment=TA_CENTER,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["Normal"], fontName="Helvetica", fontSize=10,
            leading=14, textColor=_INK,
        ),
        "body": ParagraphStyle(
            "letterbody", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=15, textColor=_INK, alignment=TA_JUSTIFY,
            spaceAfter=8,
        ),
        "cell_label": ParagraphStyle(
            "cell_label", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=13, textColor=_MUTED,
        ),
        "cell_value": ParagraphStyle(
            "cell_value", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=_INK,
        ),
        "signatory_name": ParagraphStyle(
            "signatory_name", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=10.5, leading=14, textColor=_INK,
        ),
        "signatory_role": ParagraphStyle(
            "signatory_role", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=_MUTED,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=7.5, leading=10, textColor=_MUTED,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, leading=11, textColor=_MUTED, alignment=TA_CENTER,
        ),
    }


def _unsigned_notice(context: dict) -> list:
    styles = _styles()
    if context["signed_at"]:
        return []
    return [
        Spacer(1, 6),
        Table(
            [[Paragraph(
                "PENDING SIGNATURE — this preview is an UNSIGNED copy. It becomes "
                "the finalized document only after the designated signatory signs it.",
                ParagraphStyle(
                    "unsigned", fontName="Helvetica-Bold", fontSize=9, leading=13,
                    textColor=colors.HexColor("#92600A"),
                ),
            )]],
            colWidths=[160 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF6E7")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#EAD199")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
    ]


def _story(context: dict) -> list:
    styles = _styles()
    template_path = (
        settings.BASE_DIR / "templates" / "documents" /
        "reservation_approval_template.docx"
    )
    with ZipFile(template_path) as template_package:
        header_image = template_package.read("word/media/image2.png")
        footer_image = template_package.read("word/media/image3.png")
    header_width = 166 * mm
    header_height = header_width * 174 / 1050
    footer_width = 96 * mm
    footer_height = footer_width * 656 / 2640
    story: list = [
        Image(BytesIO(header_image), width=header_width, height=header_height, hAlign="CENTER"),
        Paragraph(context["issuing_office"], styles["office"]),
        Paragraph(f"{context['system_name']} — Facility & Resource Reservation System", styles["system"]),
        Paragraph(context["vision_statement"], styles["footer"]),
        Paragraph(context["mission_statement"], ParagraphStyle(
            "mission", parent=styles["footer"], fontSize=6.5, leading=8,
        )),
        Paragraph(context["quality_policy"], ParagraphStyle(
            "quality", parent=styles["footer"], fontSize=6.5, leading=8,
        )),
        _rule(color=_BRAND, width=2.2),
        Paragraph("RESERVATION APPROVAL LETTER", styles["title"]),
        Paragraph(f"Correspondence ID: {context['letter_id']}", styles["reference"]),
        Spacer(1, 12),
        Paragraph(
            f"Issue date: {context['issued_date']}  |  Status: {context['letter_status']}",
            styles["meta"],
        ),
        Spacer(1, 10),
        Paragraph(context["requester_name"], styles["meta"]),
    ]
    if context["organization"]:
        story.append(Paragraph(context["organization"], styles["meta"]))
    story.extend([
        Spacer(1, 10),
        Paragraph(f"Dear {context['requester_name']},", styles["body"]),
        Paragraph(
            "Greetings from the Student Affairs and Services Office!",
            styles["body"],
        ),
        Paragraph(
            "This is to formally inform you that your reservation request detailed "
            "below has been <b>reviewed and APPROVED</b> by the Student Affairs and "
            "Services Office. The approved schedule is as follows:",
            styles["body"],
        ),
        _details_table(context, styles),
        Spacer(1, 10),
    ])
    story.extend(_unsigned_notice(context))
    if context["facility_rules"]:
        story.extend([
            Paragraph("Please be reminded of the following conditions governing the use of the facility:", styles["body"]),
            _bullet_list(
                [Paragraph(rule, styles["body"]) for rule in context["facility_rules"]],
            ),
            Spacer(1, 2),
        ])
    story.extend([
        Paragraph(
            "Kindly present your reservation reference number and a valid ID at the "
            "SAS Office during check-in, which opens three (3) hours before your "
            "event's start time. Should you need to make changes, contact the SAS "
            "Office as soon as possible.",
            styles["body"],
        ),
        Paragraph(
            "We wish you a successful and well-coordinated event.",
            styles["body"],
        ),
        Spacer(1, 14),
        # The closing and the signature block stay on the same page — a
        # signature alone at the top of a page would look severed.
        KeepTogether(
            [Paragraph("Very truly yours,", styles["meta"])]
            + [Spacer(1, 4)]
            + _signature_block(context, styles)
        ),
        Spacer(1, 8),
        Paragraph(context["document_disclaimer"], styles["disclaimer"]),
        Spacer(1, 8),
        Image(BytesIO(footer_image), width=footer_width, height=footer_height, hAlign="CENTER"),
    ])
    return story


def _rule(color=_LINE, width=1) -> Flowable:
    class _Rule(Flowable):
        def __init__(self):
            super().__init__()
            self.height = width + 4

        def wrap(self, availWidth, availHeight):
            self.width = availWidth
            return (availWidth, self.height)

        def draw(self):
            self.canv.setStrokeColor(color)
            self.canv.setLineWidth(width)
            self.canv.line(0, self.height / 2, self.width, self.height / 2)

    return _Rule()


def _details_table(context: dict, styles) -> Table:
    rows = [
        [Paragraph(label.upper(), styles["cell_label"]), Paragraph(value, styles["cell_value"])]
        for label, value in _detail_rows(context)
    ]
    table = Table(rows, colWidths=[42 * mm, 118 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _SOFT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, _LINE),
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, _LINE),
    ]))
    return table


def _bullet_list(items: list) -> Table:
    body_style = _styles()["body"]
    rows = [[Paragraph("•", body_style), item] for item in items]
    table = Table(rows, colWidths=[6 * mm, 154 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _signature_block(context: dict, styles) -> list:
    signed_line = (
        f"Signed on {context['signed_at']:%B %d, %Y at %I:%M %p} (system time)"
        if context["signed_at"]
        else "Awaiting signature"
    )
    elements: list = []
    if context["signed_at"]:
        # The mark appears only on signed documents; a pending preview keeps
        # the block visibly unsigned.
        elements.append(_SignatureFlowable(width=70 * mm, name=context["signatory_name"]))
    else:
        elements.append(Spacer(1, 40))
    elements.extend([
        Paragraph(context["signatory_name"], styles["signatory_name"]),
        Paragraph(context["signatory_position"], styles["signatory_role"]),
        Spacer(1, 2),
        Paragraph(signed_line, ParagraphStyle(
            "signedat", fontName="Helvetica-Oblique", fontSize=8.5, leading=12,
            textColor=_MUTED,
        )),
        Spacer(1, 6),
        Paragraph(context["test_signature_disclaimer"], styles["disclaimer"]),
    ])
    return elements


def render_letter_pdf(letter, *, signed: bool | None = None) -> bytes:
    """Render the letter as PDF bytes.

    ``signed`` forces a mode; by default it follows the letter's state. A
    pending letter is ALWAYS rendered unsigned (with the pending notice) even
    if asked for signed — a pending letter must never become a finalized
    document.
    """
    if signed is None:
        signed = letter.is_signed
    context = build_letter_context(letter)
    context["signed_at"] = (
        timezone.localtime(letter.signed_at) if (signed and letter.signed_at) else None
    )

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Reservation Approval Letter {context['letter_id']}",
        author=context["issuing_office"],
        subject=f"Reservation approval — {context['reservation_reference']}",
    )

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawCentredString(
            A4[0] / 2,
            12 * mm,
            (
                f"{context['system_name']} · Correspondence ID {context['letter_id']} · "
                f"System-generated document · Page {doc.page}"
            ),
        )
        canvas.restoreState()

    document.build(_story(context), onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def render_letter_docx(letter) -> bytes | None:
    """Populate the supplied NORSU template and return a DOCX.

    The template's header images, vision/mission/quality statements, footer
    disclaimer, page-number fields, section geometry, and other package parts
    are retained by loading it as the starting document. Its main body is an
    intentionally blank letter canvas, so only blank body paragraphs are
    removed before inserting the reservation content.
    """
    import docx

    template_path = (
        settings.BASE_DIR / "templates" / "documents" /
        "reservation_approval_template.docx"
    )
    if not template_path.is_file():
        raise FileNotFoundError(f"NORSU approval letter template is missing: {template_path}")

    context = build_letter_context(letter)
    document = docx.Document(str(template_path))
    for paragraph in list(document.paragraphs):
        if not paragraph.text.strip() and not paragraph._p.xpath(".//w:drawing | .//w:br"):
            paragraph._element.getparent().remove(paragraph._element)

    def add_text(text="", *, bold=False, italic=False, size=10, color="212127", after=4):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = docx.shared.Pt(after)
        run = paragraph.add_run(str(text))
        run.font.size = docx.shared.Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = docx.shared.RGBColor.from_string(color)
        return paragraph

    add_text("RESERVATION APPROVAL LETTER", bold=True, size=13, color="1F4E79", after=2)
    add_text(f"{context['issuing_office']}  |  {context['institution']}", size=9, color="666666")
    add_text(f"Correspondence ID: {context['letter_id']}", bold=True, size=10)
    add_text(f"Issue date: {context['issued_date']}    Status: {letter.get_status_display()}", size=9)
    add_text()
    add_text(context["requester_name"], bold=True, size=11, after=1)
    if context["organization"]:
        add_text(context["organization"], size=10, after=1)
    if context.get("requester_email"):
        add_text(context["requester_email"], size=9, color="666666")
    add_text(f"Dear {context['requester_name']},", after=7)
    add_text(
        "This letter confirms that the reservation below has been approved "
        "through the NORSU facility reservation process.", after=7,
    )

    rows = _detail_rows(context)
    if context.get("facility_location"):
        rows.insert(3, ("Facility location", context["facility_location"]))
    if context.get("requester_email"):
        rows.insert(2, ("Requester email", context["requester_email"]))
    detail_table = document.add_table(rows=0, cols=2)
    detail_table.style = "Table Grid"
    for label, value in rows:
        cells = detail_table.add_row().cells
        cells[0].text = label
        cells[1].text = value or "—"
        for run in cells[0].paragraphs[0].runs:
            run.font.bold = True
            run.font.size = docx.shared.Pt(9)
        for run in cells[1].paragraphs[0].runs:
            run.font.size = docx.shared.Pt(9)

    if context["facility_rules"]:
        add_text("Approved facility conditions", bold=True, size=10, after=2)
        for rule in context["facility_rules"]:
            p = document.add_paragraph()
            p.paragraph_format.left_indent = docx.shared.Mm(5)
            p.paragraph_format.space_after = docx.shared.Pt(1)
            p.add_run(f"• {rule}").font.size = docx.shared.Pt(9)
    if context["resources"]:
        add_text("Approved resources: " + "; ".join(context["resources"]), size=9)
    if context["estimated_total"]:
        add_text(f"Estimated fees: {context['estimated_total']}", size=9)
    add_text("Please refer to the approved schedule and facility conditions above.", after=8)
    add_text("Very truly yours,", after=2)

    # The mark is only placed in the finalized version. Pending copies retain
    # the exact template and signature details but are visibly unsigned.
    if letter.is_signed and (png := signature.signature_png_bytes(context["signatory_name"])):
        image_paragraph = document.add_paragraph()
        image_paragraph.add_run().add_picture(BytesIO(png), width=docx.shared.Mm(48))
    else:
        add_text("Awaiting signature", italic=True, size=9, color="777777")
    add_text(context["signatory_name"], bold=True, size=10.5, after=1)
    add_text(context["signatory_position"], size=9, color="666666", after=1)
    if context["signed_at"]:
        add_text(
            f"Signed on {context['signed_at']:%B %d, %Y at %I:%M %p} (system time)",
            italic=True, size=8, color="666666",
        )
    add_text(context["test_signature_disclaimer"], italic=True, size=8, color="666666")

    # Populate the existing correspondence metadata cells in the template's
    # footer without changing its page-number fields or disclaimer text.
    for section in document.sections:
        for footer_table in section.footer.tables:
            for row in footer_table.rows:
                for index, cell in enumerate(row.cells[:-1]):
                    label = cell.text.strip().lower()
                    if label == "correspondence id":
                        row.cells[index + 1].text = context["letter_id"]
                    elif label == "issue date":
                        row.cells[index + 1].text = context["issued_date"]
                    elif label == "issue status":
                        row.cells[index + 1].text = letter.get_status_display()

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
