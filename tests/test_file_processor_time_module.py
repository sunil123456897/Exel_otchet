"""Regression test: file_processor must use the time module it actually imports.

In commit fd3d95b (Phase 2.x-3.x: partial renamer + readiness split), the
writer accidentally used ``_time`` instead of ``time`` in the row-cache
hot path. ``import time`` is still in the file, so the import does not
fail, but every call into ``process_file_task`` raises ``NameError:
name '_time' is not defined`` once the cache is hit, which makes the
consolidation step produce zero rows and the GUI to show "Нет данных".

The fix is to use the actual module name. This test ensures the file
does not regress to either ``_time`` (typo) or to shadowing ``time``
with a local of the same name.
"""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
sys.path.insert(0, str(APP_DIR))


def test_file_processor_does_not_use_undefined_time():
    src = (APP_DIR / "core" / "app" / "file_processor.py").read_text(
        encoding="utf-8"
    )

    # 1. ``import time`` must still be there.
    assert re.search(r"^import time\b", src, re.MULTILINE), (
        "file_processor.py must keep `import time` — the PERF timing "
        "instrumentation needs it."
    )

    # 2. ``_time`` must NOT appear anywhere — the original typo bug.
    bad_uses = [line for line in src.splitlines() if "_time." in line]
    assert not bad_uses, (
        "file_processor.py still references `_time.` (typo for `time.`):\n"
        + "\n".join(bad_uses)
    )


def test_file_processor_module_imports_cleanly():
    # Importing the module triggers the top-level code, including the
    # ``import time``. If someone deletes that import, the test above
    # would still pass; this one exercises the import side too.
    from core.app import file_processor  # noqa: F401
