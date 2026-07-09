"""Master-Report application package.

Single source of truth for the product version. Read this instead of
hard-coding version strings in the GUI title, the About dialog, or the
launcher scripts, so they can never drift out of sync.

Imported from inside the runtime (where ``APP`` is on ``sys.path``) as::

    from APP import __version__

Note: ``core`` is the top-level import package during runtime (``main.py``
puts the ``APP`` directory on ``sys.path``), but ``APP`` itself also resolves
because the parent of ``APP`` (the repo root) is the working directory.
When only ``APP`` is on the path, ``core`` imports succeed; when the repo
root is on the path, ``APP`` imports also succeed. Both patterns work.
"""

__version__ = "5.6"
