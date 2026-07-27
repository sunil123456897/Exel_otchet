"""Phase 0 — stability: workbook handle is always released.

Regression for the "file is busy on Windows" class of bugs. Before the
fix, an exception raised between ``_get_workbook`` and ``_save_workbook``
left the openpyxl workbook unclosed, so the OS held the file handle and
the next attempt to write the same path failed. The try/finally wrappers
must guarantee ``wb.close()`` on every path, success or failure.

We assert close via a deterministic spy that wraps ``_get_workbook``:
the real workbook is still produced (so the call paths stay realistic),
but its ``close`` method records every invocation. This avoids relying
on Windows' non-deterministic handle-release timing.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from core.infra.export_writer import MasterWriter


def _make_writer(tmp_path) -> MasterWriter:
    return MasterWriter(config={}, config_path=str(tmp_path))


def _install_close_spy(monkeypatch):
    """Wrap MasterWriter._get_workbook so the returned workbook's
    ``close`` records each call. Returns the recorder list."""
    closed: list[bool] = []
    original_get = MasterWriter._get_workbook

    def spying_get(self, path=None):
        wb = original_get(self, path)
        if wb is not None:
            original_close = wb.close

            def spy_close(*args, **kwargs):  # noqa: ANN002, ANN003
                closed.append(True)
                return original_close(*args, **kwargs)

            wb.close = spy_close  # type: ignore[method-assign]
        return wb

    monkeypatch.setattr(MasterWriter, "_get_workbook", spying_get)
    return closed


def test_write_daily_data_closes_owned_workbook_on_exception(tmp_path, monkeypatch):
    """write_daily_data owns the wb when called without one — it must
    close it even if _append_data_rows raises mid-build."""
    writer = _make_writer(tmp_path)
    closed = _install_close_spy(monkeypatch)

    with patch(
        "core.infra.export_writer.MasterWriter._append_data_rows",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            writer.write_daily_data(datetime(2026, 5, 2), [{"Источник": "x"}])

    assert closed, "wb.close() was not called when _append_data_rows raised"


def test_write_report_closes_workbook_on_inner_exception(tmp_path, monkeypatch):
    """write_report opens wb then iterates dates; if a step that runs
    AFTER the date loop (here _write_template_errors_sheet) raises, the
    wb must still be closed by the outer try/finally."""
    writer = _make_writer(tmp_path)
    out = tmp_path / "report.xlsx"
    closed = _install_close_spy(monkeypatch)

    data = [
        {
            "Дата": datetime(2026, 5, 1),
            "Источник": "src",
            "сумма платежа ПРИХОД": "100",
            "сумма платежа РАСХОД": "0",
        }
    ]

    with patch.object(
        writer,
        "_write_template_errors_sheet",
        side_effect=RuntimeError("post-loop boom"),
    ):
        result = writer.write_report(data, out)

    assert result is False
    assert closed, "wb.close() was not called when _write_template_errors_sheet raised"


def test_write_empty_daily_report_closes_workbook_on_exception(tmp_path, monkeypatch):
    """write_empty_daily_report must close its wb if the inner
    write_daily_data raises (the finally must release the handle even
    when re-raising)."""
    writer = _make_writer(tmp_path)
    out = tmp_path / "empty.xlsx"
    closed = _install_close_spy(monkeypatch)

    with patch.object(
        writer,
        "write_daily_data",
        side_effect=RuntimeError("empty boom"),
    ):
        with pytest.raises(RuntimeError, match="empty boom"):
            writer.write_empty_daily_report(out, datetime(2026, 5, 1))

    assert closed, "wb.close() was not called when write_daily_data raised"


def test_write_report_success_path_still_works(tmp_path):
    """Sanity: the try/finally wrappers must not break the happy path."""
    writer = _make_writer(tmp_path)
    out = tmp_path / "ok.xlsx"

    data = [
        {
            "Дата": datetime(2026, 5, 1),
            "Источник": "src",
            "сумма платежа ПРИХОД": "100",
            "сумма платежа РАСХОД": "0",
            "ИТОГ": "100",
        }
    ]
    assert writer.write_report(data, out) is True
    assert out.exists()


def test_rsch_build_releases_workbooks_on_exception(tmp_path, monkeypatch):
    """rsch/_build.build_rsch_report must close both the template wb and
    the output wb even when _write_rsch_sheet raises mid-build."""
    import core.infra.rsch._build as rsch_build
    import openpyxl as _openpyxl
    from core.infra.rsch._build import build_rsch_report

    # Provide a real template file so build_rsch_report loads it via
    # openpyxl.load_workbook (the path we want to exercise).
    template = tmp_path / "tpl.xlsx"
    wb_tpl = _openpyxl.Workbook()
    wb_tpl.active.title = "РСЧ"
    wb_tpl.save(template)
    wb_tpl.close()

    # Source workbook (contents don't matter — collection is patched).
    src = tmp_path / "src.xlsx"
    wb_src = _openpyxl.Workbook()
    wb_src.save(src)
    wb_src.close()

    out = tmp_path / "rsch.xlsx"

    template_closed: list[bool] = []
    out_closed: list[bool] = []
    orig_load = rsch_build.openpyxl.load_workbook
    orig_workbook = rsch_build.Workbook

    def tracking_load(path, *args, **kwargs):  # noqa: ANN002, ANN003
        wb = orig_load(path, *args, **kwargs)
        if Path(path) == template:
            original_close = wb.close

            def spy():
                template_closed.append(True)
                return original_close()

            wb.close = spy  # type: ignore[method-assign]
        return wb

    def tracking_workbook():
        wb = orig_workbook()
        original_close = wb.close

        def spy():
            out_closed.append(True)
            return original_close()

        wb.close = spy  # type: ignore[method-assign]
        return wb

    # Patch the names the module bound at import time.
    monkeypatch.setattr(rsch_build.openpyxl, "load_workbook", tracking_load)
    monkeypatch.setattr(rsch_build, "Workbook", tracking_workbook)

    # Force collection to yield one row so the output workbook opens.
    with patch(
        "core.infra.rsch._build._collect_rows_from_workbook",
        return_value=[{
            "date": datetime(2026, 5, 1).date(),
            "executor": "Альфа",
            "customer": "ООО Тест",
            "contractor": "",
            "comment": "тест",
            "income": 100,
            "expense": 0,
            "account": "",
            "source": "src.xlsx",
            "source_path": str(src),
            "source_sheet": "РСЧ",
            "source_row": 2,
        }],
    ), patch(
        "core.infra.rsch._build._write_rsch_sheet",
        side_effect=RuntimeError("sheet boom"),
    ):
        with pytest.raises(RuntimeError, match="sheet boom"):
            build_rsch_report(
                [src],
                out,
                target_date=datetime(2026, 5, 1).date(),
                template_path=template,
            )

    # Both the template wb and the output wb must have been closed.
    assert template_closed, "template workbook was not closed when _write_rsch_sheet raised"
    assert out_closed, "output workbook was not closed when _write_rsch_sheet raised"
