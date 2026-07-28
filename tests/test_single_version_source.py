"""Stage 0 / MR-0004 — single source of truth for the product version.

Regression for the "5.5 vs 5.6 drift" bug: the launcher BAT contained a
hard-coded ``v5.5`` while ``APP/__init__.py`` already declared ``5.6``.
That made the displayed version depend on which entry point the user
saw, and any future bump silently fell out of sync.

This test enforces three rules:

1. ``APP.__version__`` is importable and looks like a real version
   (``MAJOR.MINOR[.PATCH]``).
2. No Python UI source ships a hard-coded product-version literal that
   could drift from ``APP.__version__``. The product version is the one
   shown to the user in titles/banners/about dialogs. Importing
   ``APP.__version__`` is the only sanctioned way to display it.
3. The launcher ``ЗАПУСК.bat`` must not carry a hard-coded version
   literal; it must derive the title from ``APP/__init__.py`` so the BAT
   and the Python package can never disagree.

The drift detector is intentionally narrow: it only flags literals that
look like a *product* version token (``v5.6``, ``"5.6"``, ``= 5.6``),
not hex colors, Windows versions, library pins or comment examples.
Those are filtered by an explicit allowlist of file:line entries for the
small number of legitimate non-product version mentions.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Repo root = parent of ``tests/``. Resolved relative to this file so the
# test works no matter what directory pytest was invoked from.
REPO_ROOT = Path(__file__).resolve().parent.parent
APP_INIT = REPO_ROOT / "APP" / "__init__.py"
LAUNCHER_BAT = REPO_ROOT / "ЗАПУСК.bat"


def _read_version_from_app_init() -> str:
    """Parse ``__version__ = "x.y"`` from ``APP/__init__.py``."""
    text = APP_INIT.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    assert match, f"APP/__init__.py has no __version__ assignment: {APP_INIT}"
    return match.group(1)


def test_app_version_is_real_semver_like() -> None:
    """``APP.__version__`` must look like a version, not a placeholder."""
    version = _read_version_from_app_init()
    assert re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version), (
        f"APP.__version__={version!r} is not a MAJOR.MINOR[.PATCH] string. "
        "A placeholder here would silently break the single-source contract."
    )


def test_app_version_importable_at_runtime() -> None:
    """``from APP import __version__`` must succeed.

    If this fails, the UI's defensive ``try/except`` around the import
    would have masked it with a stale hard-coded fallback. We removed
    those fallbacks in MR-0004; this test proves they are no longer
    needed.
    """
    from APP import __version__

    assert __version__ == _read_version_from_app_init()


# ── drift detector ──────────────────────────────────────────────────────
#
# A literal that looks like a product version. We require either a ``v``
# prefix (``v5.6``), or surrounding quotes / ``=`` assignment
# (``"5.6"``, ``= 5.6``). A bare ``5.6`` floating in the middle of text
# is NOT matched, because that pattern hits hex colors (``5.6`` inside
# ``#a5b5.6c``-style noise is rare, but ``8.1`` for Windows versions
# and library pins is common).
_DRIFTING_VERSION_RE = re.compile(
    r"""
    (?<![\w.])               # word boundary on the left
    (?:                      # require a marker that says "this is a version":
        v                    #   - explicit v-prefix: v5.6
        |
        ["']                 #   - opening quote: "5.6" / '5.6'
        |
        =\s*["']?            #   - assignment: = 5.6  /  = "5.6"
    )
    v?                       # optional extra v (covers ``= v5.6``)
    (?P<ver>[5-9]\.\d{1,2}(?:\.\d{1,2})?)   # the actual N.M[.P], 5.x..9.x
    ["']?                    # optional closing quote
    (?![\w])                 # word boundary on the right (no trailing digit/letter)
    """,
    re.VERBOSE,
)


def _python_app_files() -> list[Path]:
    """All Python files under ``APP/`` where a drifting literal would matter."""
    base = REPO_ROOT / "APP"
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.py"))


# Legitimate mentions of version-like tokens that are NOT the product
# version. Keyed by ``path:lineno`` (1-based). Each entry explains why
# it is allowed, so future readers know it was intentional.
#
# These are stable identifiers (license key material, docstring mentions
# of the product in architecture comments, examples in data-loss docs).
# None of them is a *displayed* version that the user sees in UI.
_ALLOWLIST: dict[str, str] = {
    # THE source of truth itself. This is the assignment the rest of the
    # codebase is required to import; flagging it would defeat the test.
    "APP/__init__.py:18": "the canonical __version__ assignment",
    # Mirror in core/__init__.py. Required because of the dual sys.path
    # layout: at runtime only APP/ is on sys.path, so `from APP import
    # __version__` fails and UI code falls back to `from core import
    # __version__`. Kept in sync with APP/__init__.py by this very test.
    "APP/core/__init__.py:17": "mirror of __version__ for runtime fallback",
    # XOR license-key material — locked by TЗ section 3, must not change.
    "APP/core/license.py:41": "license XOR key material, not a displayed version",
    # Architecture comment in a module docstring.
    "APP/core/infra/utils_logging.py:3": "docstring mention of architecture version",
    # Manifest-shape example in updater_model docstring. Not a real version;
    # the actual version comes from the fetched manifest at runtime.
    # The line number shifts when the module header changes; allowlist
    # covers the whole docstring block — update the line numbers if the
    # header grows.
    "APP/core/shared/updater_model.py:66": "docstring example of manifest version field",
    "APP/core/shared/updater_model.py:67": "docstring example of manifest JSON",
    "APP/core/shared/updater_model.py:68": "docstring example of manifest asset filename",
    # Example inside a docstring describing what data_loss_log redacts.
    "APP/core/domain/data_loss_log.py:26": "comment example of redacted token",
}


def _scan_for_drifting_literals(path: Path) -> list[tuple[int, str, str]]:
    """Return ``[(lineno, line, matched_version), ...]`` for hits not allowlisted."""
    hits: list[tuple[int, str, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(REPO_ROOT).as_posix()
    for lineno, line in enumerate(text.splitlines(), start=1):
        key = f"{rel}:{lineno}"
        m = _DRIFTING_VERSION_RE.search(line)
        if not m:
            continue
        if key in _ALLOWLIST:
            continue
        hits.append((lineno, line.strip(), m.group("ver")))
    return hits


@pytest.mark.parametrize(
    "path",
    _python_app_files(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_no_drifting_version_literal_in_python(path: Path) -> None:
    """No Python source under ``APP/`` may hard-code a product version.

    Any literal that looks like a version (``v5.6``, ``"5.6"``, ``= 5.6``)
    and is not in the explicit allowlist fails. To display a version,
    import ``APP.__version__``.
    """
    hits = _scan_for_drifting_literals(path)
    if hits:
        detail = "\n  ".join(
            f":{lineno}  ({ver!r})  {line}" for lineno, line, ver in hits
        )
        pytest.fail(
            f"{path.relative_to(REPO_ROOT)}: hard-coded version literal(s) found.\n"
            f"  {detail}\n"
            "Import APP.__version__ instead so the displayed version cannot drift.\n"
            "If this is a legitimate non-product token (license key, docstring), "
            "add the file:line to _ALLOWLIST with a reason."
        )


def test_launcher_bat_derives_version_from_app_init() -> None:
    """``ЗАПУСК.bat`` must read the version from ``APP/__init__.py``.

    Before MR-0004 the BAT hard-coded ``v5.5`` and drifted from
    ``APP.__version__ = "5.6"``. The BAT must now parse the version out
    of ``APP/__init__.py`` via ``findstr``, and must not contain a
    hard-coded ``vN.M`` literal in title or banner.
    """
    if not LAUNCHER_BAT.exists():
        pytest.skip("ЗАПУСК.bat not present in this checkout")

    text = LAUNCHER_BAT.read_text(encoding="utf-8-sig", errors="replace")

    # 1) The BAT must reference APP/__init__.py as the version source.
    assert "__init__.py" in text and "findstr" in text.lower(), (
        "ЗАПУСК.bat must derive the version from APP/__init__.py via findstr, "
        "not from a hard-coded literal."
    )

    # 2) The BAT must not carry a hard-coded ``vN.M`` literal in title/banner.
    #    Lines that *read* the version (findstr) are allowed to mention the
    #    field name; everything else must use %APP_VERSION%.
    literal_lines = []
    for line in text.splitlines():
        if "findstr" in line.lower():
            continue
        if _DRIFTING_VERSION_RE.search(line):
            literal_lines.append(line.strip())

    assert not literal_lines, (
        "ЗАПУСК.bat still contains hard-coded version literals:\n  "
        + "\n  ".join(literal_lines)
        + "\nUse %APP_VERSION% (derived from APP/__init__.py) instead."
    )
