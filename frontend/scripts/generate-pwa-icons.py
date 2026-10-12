"""Generate the SAS RESERVE PWA icons.

The project ships a generic purple favicon (a Vite/template placeholder), so the
installable app icons are drawn here from the product's own brand tokens
(indigo #4f46e5 + a white calendar glyph matching the header brand mark).

Run from ``frontend/`` with Pillow available:

    python scripts/generate-pwa-icons.py

Outputs (public/, copied verbatim into the production build):

    pwa-192x192.png            any, 192x192
    pwa-512x512.png            any, 512x512
    pwa-maskable-512x512.png   maskable, 512x512 (glyph inside the safe zone)
    apple-touch-icon.png       iOS home screen, 180x180
"""

from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path(__file__).resolve().parent.parent / "public"

# Brand tokens from frontend/src/index.css (@theme).
BRAND = (79, 70, 229, 255)  # --color-brand  #4f46e5
BRAND_DARK = (67, 56, 202, 255)  # --color-brand-dark  #4338ca
WHITE = (255, 255, 255, 255)


def _draw_glyph(draw: ImageDraw.ImageDraw, size: int, scale: float) -> None:
    """Draw a white calendar glyph centred in a ``size`` square.

    ``scale`` is the fraction of the canvas the glyph occupies — smaller for
    maskable icons so the glyph stays inside the safe zone.
    """
    side = size * scale
    left = (size - side) / 2
    body_top = left + side * 0.16
    body_bottom = left + side
    right = left + side
    radius = side * 0.14

    # Two hanger rings above the calendar body.
    ring_w = side * 0.07
    ring_h = side * 0.16
    for cx in (left + side * 0.30, left + side * 0.70):
        draw.rounded_rectangle(
            [cx - ring_w / 2, left + side * 0.02, cx + ring_w / 2, left + side * 0.22],
            radius=ring_w / 2,
            fill=WHITE,
        )

    # Calendar body + darker header band.
    draw.rounded_rectangle(
        [left, body_top, right, body_bottom], radius=radius, fill=WHITE
    )
    header_bottom = body_top + side * 0.22
    draw.rounded_rectangle(
        [left, body_top, right, header_bottom], radius=radius, fill=BRAND_DARK
    )
    draw.rectangle([left, header_bottom - radius, right, header_bottom], fill=BRAND_DARK)

    # A 3x3 grid of brand dots below the header.
    dot = side * 0.085
    gap_x = (side - 3 * dot) / 4
    start_x = left + gap_x
    grid_top = header_bottom + side * 0.14
    row_gap = (body_bottom - grid_top - 3 * dot) / 2.4
    for row in range(3):
        for col in range(3):
            cx = start_x + col * (dot + gap_x)
            cy = grid_top + row * (dot + row_gap)
            draw.rounded_rectangle(
                [cx, cy, cx + dot, cy + dot], radius=dot * 0.3, fill=BRAND
            )


def _icon(size: int, *, maskable: bool) -> Image.Image:
    image = Image.new("RGBA", (size, size), BRAND)
    draw = ImageDraw.Draw(image)

    # Maskable icons must keep meaningful content within the inner 80% safe
    # zone; regular icons can use more of the canvas.
    _draw_glyph(draw, size, scale=0.60 if maskable else 0.68)
    return image


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    outputs = {
        "pwa-192x192.png": _icon(192, maskable=False),
        "pwa-512x512.png": _icon(512, maskable=False),
        "pwa-maskable-512x512.png": _icon(512, maskable=True),
        "apple-touch-icon.png": _icon(180, maskable=False),
    }
    for name, image in outputs.items():
        image.save(PUBLIC / name, format="PNG")
        print(f"wrote {PUBLIC / name} ({image.width}x{image.height})")


if __name__ == "__main__":
    main()
