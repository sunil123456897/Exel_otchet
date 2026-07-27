#!/usr/bin/env python3
"""Generate the UI icon set for Master-Report (light + dark variants).

Replaces astral-plane emoji (🟢🔴📊📁✅ etc.) with crisp, themeable vector
icons drawn via PIL. Emoji render through the OS emoji font with
unpredictable colour and metrics that can shift button heights; these
PNG icons are single-colour line-art tinted to the active palette's ink
or semantic colour, so they follow light↔dark switches cleanly.

Icon vocabulary (line-art, 24×24 grid, ~1.5px stroke at 1× scale):
  Status dots:    dot_ok, dot_err, dot_warn, dot_busy
  Actions:        play, globe, doc, check, plus, attach, refresh,
                   folder, trash, edit, copy
  Sections:       calendar, user, build, period, palette, gear,
                   keyboard, sun, moon, monitor, info, warning, error,
                   success, link

Outputs (per theme, rendered at 2× then downscaled for HiDPI crispness):
  APP/assets/icons/<theme>/<name>.png   e.g. light/dot_ok.png

Re-runnable: overwrites idempotently. No external assets required — all
icons are drawn from primitives (lines, arcs, ellipses, polygons).

Usage:
    python tools/generate_ui_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Palette mirrors (single source of truth is core/ui/theme.py:_LIGHT/_DARK)
# ---------------------------------------------------------------------------
LIGHT = {
    "ink": (26, 35, 50),        # #1a2332
    "ink_muted": (107, 117, 136),  # #6b7588
    "success": (26, 138, 78),    # #1a8a4e
    "warning": (180, 83, 9),     # #b45309
    "error": (192, 73, 47),      # #c0492f
    "info": (14, 110, 140),      # #0e6e8c
    "primary": (27, 75, 138),    # #1b4b8a
}
DARK = {
    "ink": (231, 235, 243),      # #e7ebf3
    "ink_muted": (139, 148, 165),  # #8b94a5
    "success": (95, 184, 122),   # #5fb87a
    "warning": (224, 163, 65),   # #e0a341
    "error": (236, 106, 95),     # #ec6a5f
    "info": (77, 176, 201),      # #4db0c9
    "primary": (91, 141, 239),   # #5b8def
}

# Render at 4× then downscale → crisp anti-aliasing on HiDPI.
SUPERSAMPLE = 4
GRID = 24
CANVAS = GRID * SUPERSAMPLE  # 96px working canvas
STROKE = int(1.75 * SUPERSAMPLE)

OUT_DIR = Path(__file__).resolve().parents[1] / "APP" / "assets" / "icons"

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _finish(img: Image.Image) -> Image.Image:
    """Downscale from supersample to target grid size."""
    return img.resize((GRID, GRID), Image.LANCZOS)


def _dot(palette: dict, name: str = "") -> Image.Image:
    """Filled status circle (for net-indicator, table badges).

    ``name`` selects the semantic colour via ICON_COLOR_KEY; the fn
    signature accepts the palette dict (like all icon fns) so it can be
    registered uniformly in ICONS.
    """
    color = _color_for(name, palette)
    img, d = _new_canvas()
    margin = int(6 * SUPERSAMPLE)
    d.ellipse([margin, margin, CANVAS - margin, CANVAS - margin], fill=color)
    return _finish(img)


def _circle(palette: dict, name: str = "") -> Image.Image:
    """Outline circle (busy/hollow status)."""
    color = _color_for(name, palette)
    img, d = _new_canvas()
    m = int(5 * SUPERSAMPLE)
    d.ellipse([m, m, CANVAS - m, CANVAS - m], outline=color, width=STROKE)
    return _finish(img)


def _polyline(color: tuple, points: list, closed: bool = False) -> Image.Image:
    img, d = _new_canvas()
    scaled = [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in points]
    d.line(scaled + ([scaled[0]] if closed else []), fill=color, width=STROKE,
           joint="curve")
    if closed:
        d.polygon(scaled, outline=color, width=STROKE)
    return _finish(img)


def _polygon(color: tuple, points: list, fill=None) -> Image.Image:
    img, d = _new_canvas()
    scaled = [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in points]
    d.polygon(scaled, fill=fill or color, outline=color, width=STROKE // 2)
    return _finish(img)


def _rect(color: tuple, box: list, fill=None) -> Image.Image:
    img, d = _new_canvas()
    scaled = [v * SUPERSAMPLE for v in box]
    d.rectangle(scaled, outline=color, width=STROKE, fill=fill)
    return _finish(img)


def _arc(color: tuple, box: list, start: float, end: float) -> Image.Image:
    img, d = _new_canvas()
    scaled = [v * SUPERSAMPLE for v in box]
    d.arc(scaled, start, end, fill=color, width=STROKE)
    return _finish(img)


# ---------------------------------------------------------------------------
# Icon definitions — each is a callable(canvas_color_dict) -> PIL.Image
# Coordinates are on a 24×24 grid (origin top-left).
# ---------------------------------------------------------------------------

def _ic_play(c):
    """Filled triangle — primary action (Собрать день)."""
    return _polygon(c["primary"], [(7, 6), (7, 18), (18, 12)])


def _ic_globe(c):
    """Circle + meridians — all-dates / world."""
    img, d = _new_canvas()
    m = int(4 * SUPERSAMPLE)
    color = c["ink"]
    d.ellipse([m, m, CANVAS - m, CANVAS - m], outline=color, width=STROKE)
    d.line([(2, 12 * SUPERSAMPLE), (22 * SUPERSAMPLE, 12 * SUPERSAMPLE)], fill=color, width=STROKE)
    d.arc([m, m, CANVAS - m, CANVAS - m], 300, 60, fill=color, width=STROKE)
    d.line([(12 * SUPERSAMPLE, m), (12 * SUPERSAMPLE, CANVAS - m)], fill=color, width=STROKE)
    return _finish(img)


def _ic_doc(c):
    """Document with fold — РСЧ / report."""
    color = c["ink"]
    img, d = _new_canvas()
    # page outline
    pts = [(6, 3), (15, 3), (19, 7), (19, 21), (6, 21)]
    scaled = [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in pts]
    d.line(scaled + [scaled[0]], fill=color, width=STROKE, joint="curve")
    # fold corner
    d.line([(15 * SUPERSAMPLE, 3 * SUPERSAMPLE), (15 * SUPERSAMPLE, 7 * SUPERSAMPLE),
            (19 * SUPERSAMPLE, 7 * SUPERSAMPLE)], fill=color, width=STROKE)
    # text lines
    for y in (11, 14, 17):
        d.line([(9 * SUPERSAMPLE, y * SUPERSAMPLE), (16 * SUPERSAMPLE, y * SUPERSAMPLE)],
               fill=color, width=STROKE)
    return _finish(img)


def _ic_check(c):
    """Checkmark in circle — verify / све��ка."""
    color = c["success"]
    img, d = _new_canvas()
    m = int(3 * SUPERSAMPLE)
    d.ellipse([m, m, CANVAS - m, CANVAS - m], outline=color, width=STROKE)
    d.line([(8 * SUPERSAMPLE, 12 * SUPERSAMPLE), (11 * SUPERSAMPLE, 15 * SUPERSAMPLE),
            (16 * SUPERSAMPLE, 8 * SUPERSAMPLE)], fill=color, width=STROKE + SUPERSAMPLE)
    return _finish(img)


def _ic_plus(c):
    color = c["ink"]
    img, d = _new_canvas()
    ctr = 12 * SUPERSAMPLE
    arm = int(6 * SUPERSAMPLE)
    d.line([(ctr - arm, ctr), (ctr + arm, ctr)], fill=color, width=STROKE + SUPERSAMPLE)
    d.line([(ctr, ctr - arm), (ctr, ctr + arm)], fill=color, width=STROKE + SUPERSAMPLE)
    return _finish(img)


def _ic_attach(c):
    """Paperclip — привязать файл."""
    return _polyline(c["ink"],
                     [(7, 4), (7, 18), (7, 20), (9, 22), (11, 22), (13, 20), (13, 8),
                      (13, 6), (12, 5), (11, 6), (11, 18)], closed=False)


def _ic_refresh(c):
    """Refresh / reload — single bold circular arrow (browser-style).

    A single ~300° arc with ONE large solid arrowhead at the open end.
    This reads far more clearly at 16px than the two-arc variant
    (arrowheads on a two-arc design vanish when downscaled). The
    arrowhead is drawn as a big filled triangle — the most legible
    reload glyph at small sizes.
    """
    import math
    color = c["ink"]
    img, d = _new_canvas()
    thick = STROKE + int(2 * SUPERSAMPLE)  # very bold
    m = int(3 * SUPERSAMPLE)
    box = [m, m, CANVAS - m, CANVAS - m]
    # Arc from 90° (top) clockwise 300° to 30° — leaves a gap at top-right
    # where the arrowhead sits. Start at 90, end at 90+300=390=30.
    d.arc(box, 90, 390, fill=color, width=thick)
    cx = cy = CANVAS // 2
    R = (CANVAS - 2 * m) // 2
    # End of arc at 30°: compute position.
    end_a = math.radians(30)
    ex = cx + R * math.cos(end_a)
    ey = cy + R * math.sin(end_a)
    # Arrowhead: large filled triangle whose tip extends beyond the arc
    # end, pointing in the arc's direction of travel (CW from 30° → down).
    # Tangent at 30° going CW points roughly at 120° (down-right→down).
    tang = math.radians(120)
    head = int(7 * SUPERSAMPLE)  # very large
    tip = (ex + head * math.cos(tang), ey + head * math.sin(tang))
    # Base behind the tip, perpendicular to tangent.
    perp = math.radians(120 + 90)
    half = int(4.5 * SUPERSAMPLE)
    b1 = (ex + half * math.cos(perp), ey + half * math.sin(perp))
    b2 = (ex - half * math.cos(perp), ey - half * math.sin(perp))
    d.polygon([tip, b1, b2], fill=color)
    return _finish(img)


def _ic_folder(c):
    color = c["ink"]
    img, d = _new_canvas()
    d.polygon([(3, 6), (3, 20), (21, 20), (21, 8), (11, 8), (9, 6)],
              outline=color, width=STROKE)
    return _finish(img)


def _ic_trash(c):
    color = c["error"]
    img, d = _new_canvas()
    # lid
    d.line([(5, 7) * 0 + (5 * SUPERSAMPLE, 7 * SUPERSAMPLE),
            (19 * SUPERSAMPLE, 7 * SUPERSAMPLE)], fill=color, width=STROKE)
    d.line([(9 * SUPERSAMPLE, 5 * SUPERSAMPLE),
            (15 * SUPERSAMPLE, 5 * SUPERSAMPLE)], fill=color, width=STROKE)
    d.line([(12 * SUPERSAMPLE, 5 * SUPERSAMPLE),
            (12 * SUPERSAMPLE, 4 * SUPERSAMPLE)], fill=color, width=STROKE)
    # body
    for x in (8, 12, 16):
        d.line([(x * SUPERSAMPLE, 9 * SUPERSAMPLE),
                (x * SUPERSAMPLE, 18 * SUPERSAMPLE)], fill=color, width=STROKE)
    d.line([(7 * SUPERSAMPLE, 9 * SUPERSAMPLE),
            (8 * SUPERSAMPLE, 19 * SUPERSAMPLE)], fill=color, width=STROKE)
    d.line([(17 * SUPERSAMPLE, 9 * SUPERSAMPLE),
            (16 * SUPERSAMPLE, 19 * SUPERSAMPLE)], fill=color, width=STROKE)
    d.line([(8 * SUPERSAMPLE, 19 * SUPERSAMPLE),
            (16 * SUPERSAMPLE, 19 * SUPERSAMPLE)], fill=color, width=STROKE)
    return _finish(img)


def _ic_edit(c):
    """Pencil — редактировать."""
    return _polyline(c["primary"],
                     [(3, 21), (4, 17), (17, 4), (20, 7), (7, 20), (3, 21)], closed=False)


def _ic_copy(c):
    """Two overlapping sheets — копировать."""
    color = c["ink"]
    img, d = _new_canvas()
    d.rectangle([6 * SUPERSAMPLE, 3 * SUPERSAMPLE, 16 * SUPERSAMPLE, 17 * SUPERSAMPLE],
                outline=color, width=STROKE)
    d.rectangle([8 * SUPERSAMPLE, 6 * SUPERSAMPLE, 21 * SUPERSAMPLE, 20 * SUPERSAMPLE],
                outline=color, width=STROKE)
    return _finish(img)


def _ic_calendar(c):
    color = c["ink_muted"]
    img, d = _new_canvas()
    d.rectangle([3 * SUPERSAMPLE, 5 * SUPERSAMPLE, 21 * SUPERSAMPLE, 20 * SUPERSAMPLE],
                outline=color, width=STROKE)
    d.line([(3 * SUPERSAMPLE, 9 * SUPERSAMPLE), (21 * SUPERSAMPLE, 9 * SUPERSAMPLE)],
           fill=color, width=STROKE)
    for x in (8, 16):
        d.line([(x * SUPERSAMPLE, 3 * SUPERSAMPLE), (x * SUPERSAMPLE, 7 * SUPERSAMPLE)],
               fill=color, width=STROKE)
    return _finish(img)


def _ic_user(c):
    """Head + shoulders — сотрудники."""
    color = c["ink_muted"]
    img, d = _new_canvas()
    d.ellipse([9 * SUPERSAMPLE, 3 * SUPERSAMPLE, 15 * SUPERSAMPLE, 9 * SUPERSAMPLE],
              outline=color, width=STROKE)
    d.arc([5 * SUPERSAMPLE, 10 * SUPERSAMPLE, 19 * SUPERSAMPLE, 21 * SUPERSAMPLE],
          0, 180, fill=color, width=STROKE)
    return _finish(img)


def _ic_build(c):
    """Lightning bolt — сборка."""
    return _polygon(c["primary"], [(13, 3), (7, 13), (11, 13), (9, 21), (17, 10), (13, 10)])


def _ic_period(c):
    """Two arrows opposing — период."""
    color = c["ink_muted"]
    img, d = _new_canvas()
    d.line([(4, 8), (18, 8)], fill=color, width=STROKE)
    d.polygon([(15, 5), (18, 8), (15, 11)], fill=color)
    d.line([(20, 16), (6, 16)], fill=color, width=STROKE)
    d.polygon([(9, 13), (6, 16), (9, 19)], fill=color)
    return _finish(img)


def _ic_palette(c):
    """Artist palette outline — тема."""
    color = c["ink_muted"]
    img, d = _new_canvas()
    m = int(3 * SUPERSAMPLE)
    d.ellipse([m, m, CANVAS - m, CANVAS - m], outline=color, width=STROKE)
    # thumb hole
    tm = int(7 * SUPERSAMPLE)
    d.ellipse([14 * SUPERSAMPLE, 13 * SUPERSAMPLE, 20 * SUPERSAMPLE, 19 * SUPERSAMPLE],
              outline=color, width=STROKE, fill=(0, 0, 0, 0))
    # paint dots
    for (x, y), col in [((8, 8), c["primary"]), ((14, 7), c["warning"]), ((7, 14), c["success"])]:
        d.ellipse([(x - 1) * SUPERSAMPLE, (y - 1) * SUPERSAMPLE,
                   (x + 1) * SUPERSAMPLE, (y + 1) * SUPERSAMPLE], fill=col)
    return _finish(img)


def _ic_gear(c):
    """Cog — настройки."""
    color = c["ink_muted"]
    img, d = _new_canvas()
    cx = cy = 12 * SUPERSAMPLE
    d.ellipse([7 * SUPERSAMPLE, 7 * SUPERSAMPLE, 17 * SUPERSAMPLE, 17 * SUPERSAMPLE],
              outline=color, width=STROKE)
    for ang in range(0, 360, 45):
        import math
        a = math.radians(ang)
        x1 = cx + 4 * SUPERSAMPLE * math.cos(a)
        y1 = cy + 4 * SUPERSAMPLE * math.sin(a)
        x2 = cx + 7 * SUPERSAMPLE * math.cos(a)
        y2 = cy + 7 * SUPERSAMPLE * math.sin(a)
        d.line([(x1, y1), (x2, y2)], fill=color, width=STROKE)
    d.ellipse([10 * SUPERSAMPLE, 10 * SUPERSAMPLE, 14 * SUPERSAMPLE, 14 * SUPERSAMPLE],
              outline=color, width=STROKE)
    return _finish(img)


def _ic_keyboard(c):
    """Keyboard outline + keys."""
    color = c["ink_muted"]
    img, d = _new_canvas()
    d.rounded_rectangle([3 * SUPERSAMPLE, 7 * SUPERSAMPLE, 21 * SUPERSAMPLE, 17 * SUPERSAMPLE],
                        radius=int(1.5 * SUPERSAMPLE), outline=color, width=STROKE)
    for x in (7, 11, 15):
        d.line([(x * SUPERSAMPLE, 10 * SUPERSAMPLE), (x * SUPERSAMPLE, 13 * SUPERSAMPLE)],
               fill=color, width=STROKE)
    d.line([(9 * SUPERSAMPLE, 15 * SUPERSAMPLE), (15 * SUPERSAMPLE, 15 * SUPERSAMPLE)],
           fill=color, width=STROKE)
    return _finish(img)


def _ic_sun(c):
    """Sun rays — light theme."""
    color = c["warning"]
    img, d = _new_canvas()
    cx = cy = 12 * SUPERSAMPLE
    d.ellipse([8 * SUPERSAMPLE, 8 * SUPERSAMPLE, 16 * SUPERSAMPLE, 16 * SUPERSAMPLE],
              fill=color)
    import math
    for ang in range(0, 360, 45):
        a = math.radians(ang)
        x1 = cx + 5 * SUPERSAMPLE * math.cos(a)
        y1 = cy + 5 * SUPERSAMPLE * math.sin(a)
        x2 = cx + 8 * SUPERSAMPLE * math.cos(a)
        y2 = cy + 8 * SUPERSAMPLE * math.sin(a)
        d.line([(x1, y1), (x2, y2)], fill=color, width=STROKE)
    return _finish(img)


def _ic_moon(c):
    """Crescent — dark theme."""
    color = c["primary"]
    img, d = _new_canvas()
    d.ellipse([4 * SUPERSAMPLE, 3 * SUPERSAMPLE, 20 * SUPERSAMPLE, 20 * SUPERSAMPLE],
              fill=color)
    d.ellipse([9 * SUPERSAMPLE, 1 * SUPERSAMPLE, 23 * SUPERSAMPLE, 18 * SUPERSAMPLE],
              fill=(0, 0, 0, 0))
    return _finish(img)


def _ic_monitor(c):
    """Desktop — system theme."""
    color = c["ink_muted"]
    img, d = _new_canvas()
    d.rectangle([3 * SUPERSAMPLE, 4 * SUPERSAMPLE, 21 * SUPERSAMPLE, 15 * SUPERSAMPLE],
                outline=color, width=STROKE)
    d.line([(9 * SUPERSAMPLE, 18 * SUPERSAMPLE), (15 * SUPERSAMPLE, 18 * SUPERSAMPLE)],
           fill=color, width=STROKE)
    d.line([(12 * SUPERSAMPLE, 15 * SUPERSAMPLE), (12 * SUPERSAMPLE, 18 * SUPERSAMPLE)],
           fill=color, width=STROKE)
    return _finish(img)


def _ic_info(c):
    """i in circle."""
    color = c["info"]
    img, d = _new_canvas()
    m = int(3 * SUPERSAMPLE)
    d.ellipse([m, m, CANVAS - m, CANVAS - m], outline=color, width=STROKE)
    d.ellipse([11 * SUPERSAMPLE, 6 * SUPERSAMPLE, 13 * SUPERSAMPLE, 8 * SUPERSAMPLE], fill=color)
    d.line([(12 * SUPERSAMPLE, 10 * SUPERSAMPLE), (12 * SUPERSAMPLE, 17 * SUPERSAMPLE)],
           fill=color, width=STROKE + SUPERSAMPLE)
    return _finish(img)


def _ic_warning(c):
    """Triangle with !."""
    color = c["warning"]
    img, d = _new_canvas()
    d.polygon([(12, 3), (21, 20), (3, 20)], outline=color, width=STROKE,
              fill=(0, 0, 0, 0))
    img2 = img.copy()
    d2 = ImageDraw.Draw(img2)
    d2.line([(12 * SUPERSAMPLE, 9 * SUPERSAMPLE), (12 * SUPERSAMPLE, 15 * SUPERSAMPLE)],
            fill=color, width=STROKE + SUPERSAMPLE)
    d2.ellipse([11 * SUPERSAMPLE, 17 * SUPERSAMPLE, 13 * SUPERSAMPLE, 19 * SUPERSAMPLE],
               fill=color)
    return _finish(img2)


def _ic_error(c):
    """Circle with X."""
    color = c["error"]
    img, d = _new_canvas()
    m = int(3 * SUPERSAMPLE)
    d.ellipse([m, m, CANVAS - m, CANVAS - m], outline=color, width=STROKE)
    d.line([(8 * SUPERSAMPLE, 8 * SUPERSAMPLE), (16 * SUPERSAMPLE, 16 * SUPERSAMPLE)],
           fill=color, width=STROKE + SUPERSAMPLE)
    d.line([(16 * SUPERSAMPLE, 8 * SUPERSAMPLE), (8 * SUPERSAMPLE, 16 * SUPERSAMPLE)],
           fill=color, width=STROKE + SUPERSAMPLE)
    return _finish(img)


def _ic_success(c):
    """Circle with check."""
    color = c["success"]
    img, d = _new_canvas()
    m = int(3 * SUPERSAMPLE)
    d.ellipse([m, m, CANVAS - m, CANVAS - m], outline=color, width=STROKE)
    d.line([(8 * SUPERSAMPLE, 12 * SUPERSAMPLE), (11 * SUPERSAMPLE, 15 * SUPERSAMPLE),
            (16 * SUPERSAMPLE, 8 * SUPERSAMPLE)], fill=color, width=STROKE + SUPERSAMPLE)
    return _finish(img)


def _ic_link(c):
    """Two chain links — алиасы."""
    color = c["primary"]
    img, d = _new_canvas()
    d.rounded_rectangle([3 * SUPERSAMPLE, 9 * SUPERSAMPLE, 12 * SUPERSAMPLE, 15 * SUPERSAMPLE],
                        radius=int(2 * SUPERSAMPLE), outline=color, width=STROKE)
    d.rounded_rectangle([12 * SUPERSAMPLE, 9 * SUPERSAMPLE, 21 * SUPERSAMPLE, 15 * SUPERSAMPLE],
                        radius=int(2 * SUPERSAMPLE), outline=color, width=STROKE)
    d.line([(10 * SUPERSAMPLE, 9 * SUPERSAMPLE), (14 * SUPERSAMPLE, 9 * SUPERSAMPLE)],
           fill=(0, 0, 0, 0))
    return _finish(img)


ICONS = {
    "dot_ok": _dot,
    "dot_err": _dot,
    "dot_warn": _dot,
    "dot_busy": _circle,
    "play": _ic_play,
    "globe": _ic_globe,
    "doc": _ic_doc,
    "check": _ic_check,
    "plus": _ic_plus,
    "attach": _ic_attach,
    "refresh": _ic_refresh,
    "folder": _ic_folder,
    "trash": _ic_trash,
    "edit": _ic_edit,
    "copy": _ic_copy,
    "calendar": _ic_calendar,
    "user": _ic_user,
    "build": _ic_build,
    "period": _ic_period,
    "palette": _ic_palette,
    "gear": _ic_gear,
    "keyboard": _ic_keyboard,
    "sun": _ic_sun,
    "moon": _ic_moon,
    "monitor": _ic_monitor,
    "info": _ic_info,
    "warning": _ic_warning,
    "error": _ic_error,
    "success": _ic_success,
    "link": _ic_link,
}

# Semantic colour override per icon-name (so dot_ok is green even though
# the base draw uses the palette's semantic colour directly).
ICON_COLOR_KEY = {
    "dot_ok": "success", "dot_err": "error", "dot_warn": "warning",
    "dot_busy": "ink_muted",
    "success": "success", "error": "error", "warning": "warning",
    "info": "info",
    "play": "primary", "check": "success", "edit": "primary",
    "link": "primary", "build": "primary",
    "trash": "error",
}


def _color_for(name: str, palette: dict) -> tuple:
    """Resolve the draw colour for an icon given the active palette.

    Most icons draw in ink/ink_muted; semantic ones override via
    ICON_COLOR_KEY. The draw functions already pick the right key from
    the palette dict they receive, so this only matters for the generic
    _dot/_circle primitives which need an explicit colour.
    """
    key = ICON_COLOR_KEY.get(name, "ink")
    return palette[key]


def generate() -> None:
    """Render all icons into APP/assets/icons/<theme>/<name>.png."""
    for theme_name, palette in (("light", LIGHT), ("dark", DARK)):
        out = OUT_DIR / theme_name
        out.mkdir(parents=True, exist_ok=True)
        for name, fn in ICONS.items():
            # dot_*/circle primitives need the icon name to resolve their
            # semantic colour; the rest read the palette dict directly.
            img = fn(palette, name) if fn.__name__ in ("_dot", "_circle") else fn(palette)
            img.save(out / f"{name}.png")
    print(f"Generated {len(ICONS)} icons × 2 themes = {len(ICONS) * 2} files")
    print(f"  → {OUT_DIR}/light/ and {OUT_DIR}/dark/")


if __name__ == "__main__":
    generate()
