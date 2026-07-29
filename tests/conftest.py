"""Shared pytest configuration for the Master-Report test suite.

This is the single place for cross-test fixtures and hooks. Previously every
test managed its own ``tmp_path`` / ``monkeypatch.chdir`` and there was no
shared hook surface — adding an opt-in marker (e2e) needed a home, so it lives
here.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help=(
            "run end-to-end simulations on the operator's real data files "
            "(tests/test_e2e_simulations.py); skipped otherwise"
        ),
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip ``@pytest.mark.e2e`` tests unless ``--run-e2e`` is passed.

    e2e tests need the operator's real Excel data (рсч всех/, REPORTS/) which
    is never present on CI or a clean checkout. They must never block the
    normal suite; a maintainer opts in explicitly only when the data is local.
    """
    if config.getoption("--run-e2e", default=False):
        return
    skip_e2e = pytest.mark.skip(
        reason="e2e simulations need --run-e2e (and the operator's real data)"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)
