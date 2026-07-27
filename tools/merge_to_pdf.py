#!/usr/bin/env python3
"""Merge all project source files into a single PDF document.

Includes:
- All .py files under APP/
- Root config files (requirements.txt, pyproject.toml)
- Batch launchers (.bat)
- tools/ scripts (.py, .ps1)

Usage:
    python tools/merge_to_pdf.py          # -> project_source_code.pdf
    python tools/merge_to_pdf.py -o out.pdf
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from fpdf import FPDF

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- File groups and ordering ---

APP_PY: list[Path] = sorted(
    p for p in Path(REPO_ROOT, "APP").rglob("*.py")
)

ROOT_CONFIGS: list[Path] = [
    Path(REPO_ROOT, "requirements.txt"),
    Path(REPO_ROOT, "requirements-dev.txt"),
    Path(REPO_ROOT, "pyproject.toml"),
]

ROOT_BATS: list[Path] = sorted(Path(REPO_ROOT).glob("*.bat"))

TOOLS_SCRIPTS: list[Path] = sorted(
    p for p in Path(REPO_ROOT, "tools").glob("*")
    if p.suffix in (".py", ".ps1")
)

# Combine into final order
ALL_FILES: list[Path] = APP_PY + ROOT_CONFIGS + ROOT_BATS + TOOLS_SCRIPTS
ALL_FILES = [p for p in ALL_FILES if p.is_file()]


class CodePDF(FPDF):
    """PDF builder with syntax-friendly monospace layout."""

    FONT_SIZE = 7
    LINE_HEIGHT = 3.2
    LEFT_MARGIN = 10
    RIGHT_MARGIN = 10

    def header(self) -> None:
        self.set_font(self._font_family, "B", 7)
        self.set_text_color(120, 120, 120)
        rel = self._current_rel_path()
        self.cell(0, 4, f"Master-Report — {rel}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self._font_family, "", 6)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"{self.page_no()}/{{nb}}", align="C")

    def _current_rel_path(self) -> str:
        return getattr(self, "_rel_path", "")

    def add_file(self, path: Path) -> None:
        rel = path.relative_to(REPO_ROOT)
        self._rel_path = str(rel)

        # --- Title page / separator ---
        self.add_page()
        self.ln(15)
        self.set_font(self._font_family, "B", 14)
        self.set_text_color(30, 30, 30)
        self.cell(0, 8, str(rel), new_x="LMARGIN", new_y="NEXT", align="C")

        self.set_font(self._font_family, "", 8)
        self.set_text_color(100, 100, 100)
        lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        self.cell(0, 5, f"{lines} lines  •  {path.stat().st_size:,} bytes", new_x="LMARGIN", new_y="NEXT", align="C")

        self.set_draw_color(180, 180, 180)
        self.line(self.l_margin + 30, self.get_y() + 2, self.w - self.r_margin - 30, self.get_y() + 2)

        # --- Code content ---
        self.add_page()
        self.set_font(self._font_family, "", self.FONT_SIZE)
        self.set_text_color(20, 20, 20)

        text = path.read_text(encoding="utf-8", errors="replace")
        for raw_line in text.splitlines():
            display = raw_line.replace("\t", "    ")
            if display.strip() == "":
                self.ln(self.LINE_HEIGHT)
            else:
                self.cell(0, self.LINE_HEIGHT, display, new_x="LMARGIN", new_y="NEXT")

    def _setup_fonts(self) -> None:
        """Register a Unicode-safe monospace font.

        Prefers Consola (Windows system font), falls back to Courier.
        """
        import os

        windir = os.environ.get("WINDIR", r"C:\Windows")
        fonts_dir = os.path.join(windir, "Fonts")
        regular = os.path.join(fonts_dir, "consola.ttf")
        bold = os.path.join(fonts_dir, "consolab.ttf")

        if os.path.isfile(regular):
            self.add_font("Code", "", regular)
            if os.path.isfile(bold):
                self.add_font("Code", "B", bold)
            self._font_family = "Code"
        else:
            self._font_family = "Courier"

    def finish(self, output: Path) -> None:
        self.alias_nb_pages()
        self.output(str(output))


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge project source into one PDF")
    parser.add_argument("-o", "--output", type=Path, default=Path(REPO_ROOT, "project_source_code.pdf"))
    args = parser.parse_args()

    pdf = CodePDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_left_margin(pdf.LEFT_MARGIN)
    pdf.set_right_margin(pdf.RIGHT_MARGIN)
    pdf._setup_fonts()

    print(f"Merging {len(ALL_FILES)} files into {args.output.name} ...")
    for i, f in enumerate(ALL_FILES, 1):
        rel = f.relative_to(REPO_ROOT)
        print(f"  [{i:3d}/{len(ALL_FILES)}] {rel}")
        try:
            pdf.add_file(f)
        except Exception as exc:
            print(f"  WARNING: {rel}: {exc}", file=sys.stderr)

    pdf.finish(args.output)
    size_mb = args.output.stat().st_size / (1024 * 1024)
    print(f"\nDone: {args.output} ({size_mb:.1f} MB, {pdf.page_no()} pages)")


if __name__ == "__main__":
    main()
