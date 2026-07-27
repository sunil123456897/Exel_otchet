#!/usr/bin/env python3
"""Merge all project source files into a single text file.

Includes:
- All .py files under APP/
- Root config files (requirements.txt, pyproject.toml)
- Batch launchers (.bat)
- tools/ scripts (.py, .ps1)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- File groups and ordering ---
APP_PY = sorted(p for p in Path(REPO_ROOT, "APP").rglob("*.py"))
ROOT_CONFIGS = [
    Path(REPO_ROOT, "requirements.txt"),
    Path(REPO_ROOT, "requirements-dev.txt"),
    Path(REPO_ROOT, "pyproject.toml"),
]
ROOT_BATS = sorted(Path(REPO_ROOT).glob("*.bat"))
TOOLS_SCRIPTS = sorted(
    p for p in Path(REPO_ROOT, "tools").glob("*")
    if p.suffix in (".py", ".ps1")
)

# Combine into final order
ALL_FILES = APP_PY + ROOT_CONFIGS + ROOT_BATS + TOOLS_SCRIPTS
ALL_FILES = [p for p in ALL_FILES if p.is_file()]

# Exclude itself and target output files to avoid self-inclusion or duplicate runs
EXCLUDED_NAMES = {"merge_to_txt.py", "project_source_code.txt", "project_code.txt"}
ALL_FILES = [p for p in ALL_FILES if p.name not in EXCLUDED_NAMES]

def main() -> None:
    output_path = REPO_ROOT / "project_source_code.txt"
    print(f"Merging {len(ALL_FILES)} files into {output_path.name} ...")
    
    try:
        with open(output_path, "w", encoding="utf-8") as f_out:
            for i, f in enumerate(ALL_FILES, 1):
                rel = f.relative_to(REPO_ROOT)
                print(f"  [{i:3d}/{len(ALL_FILES)}] {rel}")
                
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    f_out.write("=" * 80 + "\n")
                    f_out.write(f"FILE: {rel}\n")
                    f_out.write("=" * 80 + "\n\n")
                    f_out.write(content)
                    f_out.write("\n\n")
                except Exception as exc:
                    print(f"  WARNING: {rel}: {exc}", file=sys.stderr)
                    
        size_kb = output_path.stat().st_size / 1024
        print(f"\nDone: {output_path} ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"ERROR: Failed to write output file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
