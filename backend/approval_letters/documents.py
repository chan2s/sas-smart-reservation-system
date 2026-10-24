"""Approval-letter document generation (PDF + DOCX).

Both formats are rendered from ONE shared context (``build_letter_context``)
so the letter a requester sees in the email is the letter the signatory
previewed. The letterhead uses the institutional names the system already
uses; no official logo is invented.

PDF  — reportlab/Platypus (layout flows, so long values paginate safely).
DOCX — python-docx, mirroring the same sections and embedding the test
       signature as a PNG (with an italic text fallback when Pillow is
       unavailable).
"""

from __future__ import annotations

import logging
from io import BytesIO

from django.utils import timezone

from . import signature
from .constants import (
    INSTITUTION,
    ISSUING_OFFICE,
    SIGNATORY_NAME,
    SIGNATORY_POSITION,
    SYSTEM_NAME,
    TEST_SIGNATURE_DISCLAIMER,
)

logger = logging.getLogger(__name__)


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
        "issued_date": issued_at.strftime("%B %d, %Y").replace(" 0", " "),
        "issued_at": issued_at,
        "reservation_reference": reservation.reservation_id,
        "reservation_pk": reservation.pk,
        "requester_name": letter.requester_name or reservation.requester_display_name,
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
        "signatory_name": SIGNATORY_NAME,
        "signatory_position": SIGNATORY_POSITION,
        "signed_at": timezone.localtime(letter.signed_at) if letter.signed_at else None,
        "test_signature_disclaimer": TEST_SIGNATURE_DISCLAIMER,
        "issuing_office": ISSUING_OFFICE,
        "institution": INSTITUTION,
        "system_name": SYSTEM_NAME,
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
    story: list = [
        Paragraph(context["institution"], styles["institution"]),
        Paragraph(context["issuing_office"], styles["office"]),
        Paragraph(f"{context['system_name']} — Facility & Resource Reservation System", styles["system"]),
        _rule(color=_BRAND, width=2.2),
        Paragraph("RESERVATION APPROVAL LETTER", styles["title"]),
        Paragraph(f"Letter No. {context['letter_id']}", styles["reference"]),
        Spacer(1, 12),
        Paragraph(f"Date of issuance: {context['issued_date']}", styles["meta"]),
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
                f"{context['system_name']} · Letter No. {context['letter_id']} · "
                "System-generated document"
            ),
        )
        canvas.restoreState()

    document.build(_story(context), onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def render_letter_docx(letter) -> bytes | None:
    """Render the SIGNED letter as DOCX bytes.

    DOCX generation is best-effort ("if supported"): when python-docx is not
    installed the function returns ``None`` and the API simply reports no DOCX
    available. Only a signed letter produces a DOCX — a pending letter has no
    finalized version.
    """
    if not letter.is_signed:
        return None
    try:
        import docx
    except ImportError:
        logger.info("python-docx unavailable; DOCX generation skipped.")
        return None

    context = build_letter_context(letter)
    document = docx.Document()

    for section in document.sections:
        section.top_margin = docx.shared.Mm(18)
        section.bottom_margin = docx.shared.Mm(18)
        section.left_margin = docx.shared.Mm(22)
        section.right_margin = docx.shared.Mm(22)

    def _center(text: str, size: int, bold=False, italic=False, color="212127"):
        paragraph = document.add_paragraph()
        paragraph.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(text)
        run.font.size = docx.shared.Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = docx.shared.RGBColor.from_string(color)
        return paragraph

    _center(context["institution"], 15, bold=True)
    _center(context["issuing_office"], 11, color="6B6B73")
    _center(
        f"{context['system_name']} — Facility & Resource Reservation System",
        8.5, italic=True, color="6B6B73",
    )
    _center("RESERVATION APPROVAL LETTER", 12.5, bold=True, color="3B5BDB")
    _center(f"Letter No. {context['letter_id']}", 9, color="6B6B73")

    def _body(text: str, style=None):
        paragraph = document.add_paragraph()
        if style == "justify":
            paragraph.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.JUSTIFY
        paragraph.paragraph_format.space_after = docx.shared.Pt(6)
        _add_runs_with_bold(paragraph, text)
        return paragraph

    def _add_runs_with_bold(paragraph, text: str):
        # Minimal **bold** marker support for the approval statement.
        parts = text.split("**")
        for index, part in enumerate(parts):
            if not part:
                continue
            run = paragraph.add_run(part)
            run.font.bold = index % 2 == 1
            run.font.size = docx.shared.Pt(10)

    document.add_paragraph(f"Date of issuance: {context['issued_date']}")
    document.add_paragraph(context["requester_name"])
    if context["organization"]:
        document.add_paragraph(context["organization"])
    document.add_paragraph(f"Dear {context['requester_name']},")
    _body("Greetings from the Student Affairs and Services Office!")
    _body(
        "This is to formally inform you that your reservation request detailed "
        "below has been **reviewed and APPROVED** by the Student Affairs and "
        "Services Office. The approved schedule is as follows:"
    )

    rows = _detail_rows(context)
    table = document.add_table(rows=len(rows), cols=2)
    table.style = "Light Grid Accent 1"
    for row_index, (label, value) in enumerate(rows):
        label_cell = table.cell(row_index, 0)
        value_cell = table.cell(row_index, 1)
        label_cell.text = label.upper()
        value_cell.text = value
        for run in label_cell.paragraphs[0].runs:
            run.font.size = docx.shared.Pt(9.5)
            run.font.bold = True
        for run in value_cell.paragraphs[0].runs:
            run.font.size = docx.shared.Pt(9.5)

    document.add_paragraph()
    if context["facility_rules"]:
        _body("Please be reminded of the following conditions governing the use of the facility:")
        for rule in context["facility_rules"]:
            bullet = document.add_paragraph(style="List Bullet")
            bullet.paragraph_format.space_after = docx.shared.Pt(2)
            run = bullet.add_run(rule)
            run.font.size = docx.shared.Pt(10)
    _body(
        "Kindly present your reservation reference number and a valid ID at the "
        "SAS Office during check-in, which opens three (3) hours before your "
        "event's start time. Should you need to make changes, contact the SAS "
        "Office as soon as possible."
    )
    _body("We wish you a successful and well-coordinated event.")
    document.add_paragraph("Very truly yours,")

    # Signature block: test signature image above the printed name/position.
    if png := signature.signature_png_bytes(context["signatory_name"]):
        image_paragraph = document.add_paragraph()
        image_paragraph.add_run().add_picture(
            BytesIO(png), width=docx.shared.Mm(58)
        )
    else:
        fallback = document.add_paragraph()
        run = fallback.add_run(context["signatory_name"])
        run.font.italic = True
        run.font.size = docx.shared.Pt(16)

    name_paragraph = document.add_paragraph()
    run = name_paragraph.add_run(context["signatory_name"])
    run.font.bold = True
    run.font.size = docx.shared.Pt(10.5)
    position_paragraph = document.add_paragraph()
    run = position_paragraph.add_run(context["signatory_position"])
    run.font.size = docx.shared.Pt(9.5)
    run.font.color.rgb = docx.shared.RGBColor.from_string("6B6B73")
    signed_line = (
        f"Signed on {context['signed_at']:%B %d, %Y at %I:%M %p} (system time)"
        if context["signed_at"]
        else "Awaiting signature"
    )
    signed_paragraph = document.add_paragraph()
    run = signed_paragraph.add_run(signed_line)
    run.font.italic = True
    run.font.size = docx.shared.Pt(8.5)
    run.font.color.rgb = docx.shared.RGBColor.from_string("6B6B73")
    disclaimer = document.add_paragraph()
    run = disclaimer.add_run(context["test_signature_disclaimer"])
    run.font.italic = True
    run.font.size = docx.shared.Pt(7.5)
    run.font.color.rgb = docx.shared.RGBColor.from_string("6B6B73")

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
