"""Master-Report core package.

Re-exports ``__version__`` from the top-level ``APP`` package so that
runtime code (which has ``APP/`` on ``sys.path`` and therefore imports
``core.*`` rather than ``APP.*``) can access the product version without
needing the parent of ``APP/`` to also be on the path.

This mirrors the assignment in ``APP/__init__.py`` — keep both in sync
when bumping the version. The single-version-source test
(``tests/test_single_version_source.py``) enforces that no other file
hard-codes a version literal.
"""

# Source of truth: APP/__init__.py. The literal is duplicated here only
# because of the dual sys.path layout (APP/ for runtime, parent of APP/
# for tests). test_single_version_source allows this file.
__version__ = "5.6"
