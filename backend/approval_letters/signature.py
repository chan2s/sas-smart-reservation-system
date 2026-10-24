"""Test-signature rendering for approval letters.

The signature is a clearly-labelled DEMONSTRATION mark: the signatory's name
in a handwriting-style font with a flourish, captioned as a test signature.
It never claims to be a verified or legally authenticated digital signature.

The handwriting font (Dancing Script, SIL OFL 1.1 — see fonts/OFL.txt) is
bundled with the app so dev machines and containers render identically. If it
is ever missing, every renderer falls back to an italic system font and keeps
the mandatory "test signature" caption, so the signature is never presented
as anything more than the demonstration it is.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).resolve().parent / "fonts"
SCRIPT_FONT_PATH = FONT_DIR / "DancingScript.ttf"

_INK = (0.13, 0.13, 0.15)  # near-black ink used across PDF and PNG renderers

_registered_font_name: str | None = None


def register_script_font() -> str | None:
    """Register the bundled handwriting font with reportlab (idempotent).

    Returns the reportlab font name, or ``None`` when the font file is not
    available (renderers then fall back to Helvetica-Oblique).
    """
    global _registered_font_name
    if _registered_font_name:
        return _registered_font_name
    if not SCRIPT_FONT_PATH.exists():
        logger.warning(
            "Handwriting font %s is missing; the test signature falls back "
            "to an italic system font.",
            SCRIPT_FONT_PATH,
        )
        return None
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    name = "ApprovalLetterSignature"
    pdfmetrics.registerFont(TTFont(name, str(SCRIPT_FONT_PATH)))
    _registered_font_name = name
    return _registered_font_name


# ---------------------------------------------------------------------------
# PDF rendering (reportlab canvas primitives)
# ---------------------------------------------------------------------------

def draw_test_signature_pdf(canvas, x: float, y: float, name: str, width: float) -> None:
    """Draw the test signature into the PDF signature block.

    ``(x, y)`` is the top-left of the signature area; ``width`` is the usable
    width of the signature column. The drawn block is roughly 46pt tall.
    """
    from reportlab.lib.colors import Color
    from reportlab.pdfbase.pdfmetrics import stringWidth

    ink = Color(*_INK)
    canvas.saveState()
    font_name = register_script_font() or "Helvetica-Oblique"

    # Scale the name so long names stay inside the signature column.
    size = 30.0
    text = name
    text_width = stringWidth(text, font_name, size)
    if text_width > width * 0.92:
        size = max(16.0, size * (width * 0.92) / text_width)
        text_width = stringWidth(text, font_name, size)
    canvas.setFillColor(ink)
    canvas.setFont(font_name, size)
    baseline = y - size * 0.95
    canvas.drawString(x, baseline, text)

    # Handwritten-style flourish: one sweeping cubic bezier under the name.
    start_x = x - 1
    end_x = x + text_width + 6
    mid_x = (start_x + end_x) / 2
    base = baseline - 4
    canvas.setStrokeColor(ink)
    canvas.setLineWidth(1.15)
    canvas.setLineCap(1)
    p = canvas.beginPath()
    p.moveTo(start_x, base + 5)
    p.curveTo(start_x + (mid_x - start_x) * 0.3, base - 6, mid_x, base - 8, end_x * 0.98, base - 1)
    canvas.drawPath(p, stroke=1, fill=0)

    # Mandatory caption directly beneath the mark.
    canvas.setFont("Helvetica-Oblique", 6.6)
    canvas.setFillGray(0.42)
    canvas.drawString(x, base - 12, "Test signature — demonstration only")
    canvas.restoreState()


# ---------------------------------------------------------------------------
# PNG rendering (for the DOCX embedding; Pillow)
# ---------------------------------------------------------------------------

#: Rendered at 3x for crispness; displayed at 1/3 size in the document.
PNG_SCALE = 3


def signature_png_bytes(name: str) -> bytes | None:
    """Render the test signature as a transparent PNG (bytes).

    Returns ``None`` when Pillow or the handwriting font is unavailable; the
    DOCX generator then falls back to an italic text line. Never raises.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        font = ImageFont.truetype(str(SCRIPT_FONT_PATH), 64 * PNG_SCALE)
    except Exception:  # noqa: BLE001 — fallback is always acceptable
        logger.warning("Signature PNG skipped: Pillow/font unavailable.")
        return None

    ink = tuple(int(channel * 255) for channel in _INK)
    caption_fill = (108, 108, 112)

    padding = 14 * PNG_SCALE
    caption_size = 9 * PNG_SCALE
    width = 560 * PNG_SCALE
    height = 120 * PNG_SCALE
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Name.
    name_left, name_top = padding, padding // 2
    draw.text((name_left, name_top), name, font=font, fill=ink)
    try:
        text_box = draw.textbbox((name_left, name_top), name, font=font)
    except Exception:  # noqa: BLE001 — very old Pillow without textbbox
        text_box = (name_left, name_top, name_left + width // 2, name_top + 80)
    baseline_bottom = text_box[3]

    # Sweeping flourish under the name (polyline approximation of a bezier).
    start_x = text_box[0] - 3 * PNG_SCALE
    end_x = min(text_box[2] + 8 * PNG_SCALE, width - padding)
    mid_x = (start_x + end_x) / 2
    base = baseline_bottom + 6 * PNG_SCALE
    steps = 60
    points = []
    for i in range(steps + 1):
        t = i / steps
        # Quadratic bezier dipping below the baseline.
        x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * mid_x + t**2 * end_x
        y = (1 - t) ** 2 * (base - 5 * PNG_SCALE) + 2 * (1 - t) * t * (base + 4 * PNG_SCALE) + t**2 * base
        points.append((x, y))
    draw.line(points, fill=ink, width=PNG_SCALE, joint="curve")

    # Mandatory caption beneath the mark. A plain (non-script) font keeps the
    # disclaimer legible; the tiny default bitmap font is the last resort.
    caption = "Test signature — demonstration only"
    caption_font = None
    for candidate in (
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            caption_font = ImageFont.truetype(candidate, caption_size)
            break
        except Exception:  # noqa: BLE001 — try the next candidate
            caption_font = None
    if caption_font is None:
        try:
            caption_font = ImageFont.load_default(size=caption_size)
        except TypeError:  # Pillow < 10.1 cannot size the bitmap font
            caption_font = ImageFont.load_default()
    try:
        draw.text((start_x, base + 5 * PNG_SCALE), caption, font=caption_font, fill=caption_fill)
    except Exception:  # noqa: BLE001 — the mark itself is already drawn
        pass

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
