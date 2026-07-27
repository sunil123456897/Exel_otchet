#!/usr/bin/env python3
"""Generate the Master-Report app icon (app.ico + app.png).

Brand: "Тихая касса" — treasury/financial consolidator.
Design language: navy-blue (#1b4b8a) primary accent (see core/ui/theme.py),
clean geometric monogram, premium restraint. NOT a generic Tk feather.

The mark is a rounded-square tile with a vertical navy gradient, a thin
gold accent rule (treasury/coin connotation), and a stylised "ТК"
monogram (initials of "Тихая касса") set in a bold geometric typeface.
A subtle lighter inner panel adds depth without box-shadow.

Outputs:
  APP/assets/icons/app.png  — 256x256 master raster
  APP/assets/icons/app.ico  — multi-resolution (16/32/48/256)

Re-runnable: overwrites outputs idempotently. No external assets required.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Brand tokens (mirror core/ui/theme.py — single chromatic voice)
# ---------------------------------------------------------------------------
NAVY = (27, 75, 138)          # #1b4b8a primary
NAVY_DEEP = (22, 61, 112)     # #163d70 press/gradient bottom
NAVY_LIGHT = (54, 99, 162)    # gradient top highlight
INK = (26, 35, 50)            # #1a2332 ink
GOLD = (191, 149, 63)         # restrained treasury accent (not neon)
PAPER = (245, 246, 248)       # #f5f6f8 surface
WHITE = (255, 255, 255)

MASTER_SIZE = 256
SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]


def _find_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Pick a clean geometric sans for the monogram.

    Falls back to the default bitmap font if no TTF is found, but on
    Windows segsym/arial is effectively always present.
    """
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf",   # Segoe UI Bold
        "C:/Windows/Fonts/seguib.ttf",     # Segoe UI Black-ish
        "C:/Windows/Fonts/arialbd.ttf",    # Arial Bold
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _rounded_gradient_tile(size: int) -> Image.Image:
    """Rounded-square tile with a vertical navy gradient."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # Build a vertical gradient into a separate RGB, then composite via mask.
    grad = Image.new("RGB", (size, size), NAVY_DEEP)
    px = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(NAVY_LIGHT[0] * (1 - t) + NAVY_DEEP[0] * t)
        g = int(NAVY_LIGHT[1] * (1 - t) + NAVY_DEEP[1] * t)
        b = int(NAVY_LIGHT[2] * (1 - t) + NAVY_DEEP[2] * t)
        for x in range(size):
            px[x, y] = (r, g, b)

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    md.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def _draw_inner_panel(img: Image.Image, size: int) -> None:
    """Subtle recessed inner panel for depth (no box-shadow in ttk land)."""
    inset = int(size * 0.14)
    panel = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pr = int(size * 0.12)
    pd.rounded_rectangle(
        (inset, inset, size - 1 - inset, size - 1 - inset),
        radius=pr,
        fill=(255, 255, 255, 28),
        outline=(255, 255, 255, 60),
        width=max(1, int(size * 0.012)),
    )
    img.alpha_composite(panel)


def _draw_gold_rule(img: Image.Image, size: int) -> None:
    """Thin gold accent rule near the bottom — treasury/coin connotation."""
    y = int(size * 0.80)
    x0 = int(size * 0.30)
    x1 = int(size * 0.70)
    h = max(2, int(size * 0.020))
    od = ImageDraw.Draw(img)
    od.rounded_rectangle((x0, y, x1, y + h), radius=h // 2, fill=GOLD)


def _draw_monogram(img: Image.Image, size: int) -> None:
    """Stylised 'ТК' monogram centred above the gold rule."""
    # Latin glyphs render reliably across fonts; 'TK' stands for the
    # Cyrillic 'Тихая касса' initials while staying font-safe.
    text = "TK"
    font = _find_font(int(size * 0.42), bold=True)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # Soft shadow for legibility on the navy field.
    try:
        bbox = ld.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = ld.textsize(text, font=font)
    x = (size - tw) // 2 - int(size * 0.02)
    y = int(size * 0.20) - (th // 4)
    ld.text((x + max(1, size // 96), y + max(1, size // 96)), text, font=font, fill=(0, 0, 0, 90))
    ld.text((x, y), text, font=font, fill=WHITE)
    img.alpha_composite(layer)


def _draw_border(img: Image.Image, size: int) -> None:
    """Hairline border to crispen the tile edge at small sizes."""
    od = ImageDraw.Draw(img)
    radius = int(size * 0.22)
    od.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=radius,
        outline=(255, 255, 255, 40),
        width=max(1, int(size * 0.010)),
    )


def build_master() -> Image.Image:
    img = _rounded_gradient_tile(MASTER_SIZE)
    _draw_inner_panel(img, MASTER_SIZE)
    _draw_monogram(img, MASTER_SIZE)
    _draw_gold_rule(img, MASTER_SIZE)
    _draw_border(img, MASTER_SIZE)
    return img


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "APP" / "assets" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    master = build_master()

    png_path = out_dir / "app.png"
    master.save(png_path, format="PNG")

    ico_path = out_dir / "app.ico"
    # PIL writes a multi-resolution ICO when sizes= is provided.
    master.save(ico_path, format="ICO", sizes=SIZES)

    # Validate round-trip: every embedded size must decode.
    with Image.open(ico_path) as check:
        check.verify()
    sizes_in = sorted(Image.open(ico_path).ico.sizes())
    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path}")
    print(f"ICO embedded sizes: {sizes_in}")


if __name__ == "__main__":
    main()
