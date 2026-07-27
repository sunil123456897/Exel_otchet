"""Stage 5 / MR-0503 — architecture boundary tests.

These tests prevent regressions in the layering. They are deliberately
brittle: if someone adds ``import tkinter`` to a domain module, this
test fails immediately, before the leak spreads.

Current architecture:

::

    APP/core/ui         — Tkinter GUI. No Decimal arithmetic.
    APP/core/view_models — UI state. No Tkinter.
    APP/core/services   — orchestration. Calls domain + infra.
    APP/core/domain     — pure business rules. No Tkinter, no openpyxl,
                          no filesystem.
    APP/core/infra      — SQLite, Excel I/O, network.

Allowed relaxations (pinned here so future tightening is deliberate):

* ``core.domain.data_loss_log`` imports ``pathlib.Path`` because the
  logger needs to compute its own log-file path. We accept this as the
  lesser evil vs. passing a path through every call site. Tracked in
  the stage report for a future cleanup.
* ``core.domain.interfaces`` imports ``pathlib.Path`` purely for type
  hints in abstract method signatures. That is a type-system concern,
  not a runtime dependency.

The test list both as ``_ALLOWED_DOMAIN_PATH_IMPORTS`` so a future
addition must update the list (and thus surface in code review).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _python_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.py"))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ── 1) Domain must not depend on UI / Excel I/O ─────────────────────────

FORBIDDEN_DOMAIN_IMPORTS = [
    r"^\s*import\s+tkinter\b",
    r"^\s*from\s+tkinter\b",
    r"^\s*import\s+openpyxl\b",
    r"^\s*from\s+openpyxl\b",
    r"^\s*from\s+core\.ui\b",
    r"^\s*from\s+core\.infra\b",
    r"^\s*import\s+core\.infra\b",
]

# Domain modules that legitimately use pathlib (see module docstring).
_ALLOWED_DOMAIN_PATH_IMPORTS = {
    "APP/core/domain/data_loss_log.py",
    "APP/core/domain/interfaces.py",
}


@pytest.mark.parametrize(
    "path",
    _python_files(REPO_ROOT / "APP" / "core" / "domain"),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_domain_has_no_ui_or_excel_or_infra_imports(path: Path) -> None:
    """No domain module may import tkinter, openpyxl, core.ui, or core.infra.

    Domain must remain pure: no GUI, no Excel reading/writing, no SQLite.
    The persistence/Excel layers live in ``core.infra`` and implement
    interfaces declared in ``core.domain.interfaces``.
    """
    text = _read(path)
    for pattern in FORBIDDEN_DOMAIN_IMPORTS:
        assert not re.search(pattern, text, re.MULTILINE), (
            f"{path.relative_to(REPO_ROOT)} imports a forbidden module "
            f"(matched /{pattern}/). Domain must stay UI/IO-free."
        )


@pytest.mark.parametrize(
    "path",
    _python_files(REPO_ROOT / "APP" / "core" / "domain"),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_domain_path_imports_are_explicitly_allowlisted(path: Path) -> None:
    """Any ``pathlib`` use in domain must be on the explicit allowlist.

    A new domain module that reaches for the filesystem is a red flag
    — it likely belongs in infra. If it really is legitimate, add it to
    ``_ALLOWED_DOMAIN_PATH_IMPORTS`` with a comment explaining why.
    """
    text = _read(path)
    rel = path.relative_to(REPO_ROOT).as_posix()
    uses_pathlib = bool(re.search(r"^\s*(?:from\s+pathlib|import\s+pathlib)\b", text, re.MULTILINE))
    if not uses_pathlib:
        return
    assert rel in _ALLOWED_DOMAIN_PATH_IMPORTS, (
        f"{rel} imports pathlib but is not in the allowlist. Either move "
        f"the filesystem logic to core.infra, or add this file to "
        f"_ALLOWED_DOMAIN_PATH_IMPORTS with a reason."
    )


# ── 2) UI must not perform financial calculations ───────────────────────

FORBIDDEN_UI_PATTERNS = [
    # Decimal arithmetic in UI code is a leak — financial logic lives in
    # core.domain.LogicService.
    r"\bDecimal\s*\(",
    r"\bto_decimal\s*\(",
    r"\bROUND_HALF_UP\b",
    r"\bapply_financial_rules\s*\(",
]


@pytest.mark.parametrize(
    "path",
    _python_files(REPO_ROOT / "APP" / "core" / "ui"),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_ui_does_not_do_financial_math(path: Path) -> None:
    """No UI module may call Decimal arithmetic or financial-rule entry points.

    The UI is allowed to *display* numbers (including ``Decimal`` values
    that come from a view model), but it must not *compute* them. We
    catch the function-call shape ``Decimal(...)`` which only appears
    when constructing or converting, never when displaying.
    """
    text = _read(path)
    for pattern in FORBIDDEN_UI_PATTERNS:
        assert not re.search(pattern, text), (
            f"{path.relative_to(REPO_ROOT)} performs financial computation "
            f"(matched /{pattern}/). Move the calculation into "
            f"core.domain.LogicService."
        )


# ── 3) Domain module list stays stable ──────────────────────────────────

EXPECTED_DOMAIN_MODULES = {
    "data_loss_log.py",
    "data_schemas.py",
    "date_warnings.py",
    "interfaces.py",
    "logic_service.py",
    "operation_result.py",
    "utils_helpers.py",
    "__init__.py",
}


def test_domain_module_inventory() -> None:
    """Surface new domain modules in review.

    Adding a domain module is fine, but this test forces the author to
    update the expected list, which makes the change visible in the diff.
    Without this check a half-finished extraction can sneak into main.
    """
    domain = REPO_ROOT / "APP" / "core" / "domain"
    actual = {p.name for p in domain.glob("*.py")}
    new = actual - EXPECTED_DOMAIN_MODULES
    removed = EXPECTED_DOMAIN_MODULES - actual
    assert not new, (
        f"unexpected new domain module(s): {sorted(new)}. If intentional, "
        f"add them to EXPECTED_DOMAIN_MODULES."
    )
    assert not removed, (
        f"domain module(s) disappeared: {sorted(removed)}. If intentional, "
        f"remove them from EXPECTED_DOMAIN_MODULES."
    )


# ── 4) Non-UI layers must not depend on the GUI toolkit ─────────────────
#
# Only ``core.ui`` may touch tkinter / build widgets. Everything else
# (``app``, ``services``, ``view_models``, ``shared``, the top-level
# ``core/*.py`` orchestrators, and ``infra``) must stay GUI-free so the
# headless paths (updater, headless_run, services) never drag in tkinter.
# This is what previously let ``app_controller`` reach into ``core.ui`` for
# ``CancelledByUser`` unnoticed — that leak is now fixed and pinned here.

FORBIDDEN_GUI_IMPORTS = [
    r"^\s*import\s+tkinter\b",
    r"^\s*from\s+tkinter\b",
    r"^\s*import\s+core\.ui\b",
    r"^\s*from\s+core\.ui\b",
]

# infra modules that legitimately bridge to the GUI. ``utils_logging`` is a
# Tk ``TextHandler`` log bridge whose ``import tkinter`` is guarded by
# try/except so headless environments still work. Pinned so any future
# addition is a deliberate, reviewed decision.
_ALLOWED_INFRA_GUI_IMPORTS = {
    "APP/core/infra/utils_logging.py",
}

_NON_UI_LAYERS = ("app", "services", "view_models", "shared")


def _assert_no_gui_imports(path: Path) -> None:
    text = _read(path)
    for pattern in FORBIDDEN_GUI_IMPORTS:
        assert not re.search(pattern, text, re.MULTILINE), (
            f"{path.relative_to(REPO_ROOT)} imports tkinter / core.ui. "
            f"Only core.ui may depend on the GUI toolkit (matched /{pattern}/)."
        )


@pytest.mark.parametrize(
    "path",
    [
        p
        for layer in _NON_UI_LAYERS
        for p in _python_files(REPO_ROOT / "APP" / "core" / layer)
    ],
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_non_ui_layers_have_no_gui_imports(path: Path) -> None:
    """app/services/view_models/shared must never import tkinter or core.ui."""
    _assert_no_gui_imports(path)


@pytest.mark.parametrize(
    "path",
    _python_files(REPO_ROOT / "APP" / "core" / "infra"),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_infra_has_no_gui_imports_except_allowlist(path: Path) -> None:
    """infra must stay GUI-free except for the explicit bridge allowlist."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    if rel in _ALLOWED_INFRA_GUI_IMPORTS:
        return
    _assert_no_gui_imports(path)


@pytest.mark.parametrize(
    "path",
    sorted((REPO_ROOT / "APP" / "core").glob("*.py")),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_top_level_core_has_no_gui_imports(path: Path) -> None:
    """Top-level orchestrators (app_controller, bootstrap, license) stay GUI-free.

    This is the check that would have caught ``app_controller`` importing
    ``core.ui.gui_commands._base`` for ``CancelledByUser``.
    """
    _assert_no_gui_imports(path)


# ── 5) services must not import the app controller (cycle breaker) ──────


@pytest.mark.parametrize(
    "path",
    _python_files(REPO_ROOT / "APP" / "core" / "services"),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_services_do_not_import_app_controller(path: Path) -> None:
    """services -> app_controller is the import cycle this boundary prevents.

    The services used to do a lazy ``from core.app_controller import
    _cancel_message, _is_cancelled``; those helpers now live in the UI-free
    ``core.app.cancellation``, so there is no reason for a service to import
    the controller. Keep it that way.
    """
    text = _read(path)
    pattern = r"^\s*(?:from\s+core\.app_controller|import\s+core\.app_controller)\b"
    assert not re.search(pattern, text, re.MULTILINE), (
        f"{path.relative_to(REPO_ROOT)} imports core.app_controller — that "
        f"recreates the services->controller cycle. Import cancel helpers "
        f"from core.app.cancellation instead."
    )
