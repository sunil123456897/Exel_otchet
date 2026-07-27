"""Phase 2 — behavioural tests for ingestion_reader pure functions.

The reader's I/O path (CalamineWorkbook) is hard to unit-test without
real .xlsx fixtures, but its pure helpers decide correctness: which
sheet names yield dates, which rows are trash, which dates fall in the
requested scope. These are the gates that filter data before it ever
reaches LogicService. Pinning them prevents silent data loss regressions.
"""
from __future__ import annotations

import pytest
from core.infra.ingestion_reader import (
    CalamineReader,
    extract_date_from_sheet,
)

# --- extract_date_from_sheet --------------------------------------------


def test_date_in_dd_mm_yyyy_format():
    assert extract_date_from_sheet("01.05.2026") == "01.05.2026"


def test_date_with_two_digit_year_uses_2000_epoch():
    assert extract_date_from_sheet("15.03.26") == "15.03.2026"


def test_date_with_comma_separator():
    assert extract_date_from_sheet("07,11,2026") == "07.11.2026"


def test_date_without_year_returns_none_without_hint():
    """A sheet named just '05.06' has no year and no hint — must be
    None so it isn't silently assigned the current year."""
    assert extract_date_from_sheet("05.06") is None


def test_date_without_year_returns_none_even_with_hint():
    """A sheet named just '05.06' has no year — must return None even if year_hint is passed."""
    assert extract_date_from_sheet("05.06", year_hint=2026) is None


def test_date_with_surrounding_text():
    """Sheet names like 'Отчёт за 03.04.2026 (вторник)' must still parse."""
    assert extract_date_from_sheet("Отчёт за 03.04.2026 (вторник)") == "03.04.2026"


def test_invalid_month_returns_none():
    """Month 13 is invalid — the date must be rejected, not clamped.
    Format is DD.MM.YYYY, so 01.13.2026 has month=13."""
    assert extract_date_from_sheet("01.13.2026") is None


def test_invalid_day_returns_none():
    """Day 31 in April (30-day month) is invalid."""
    assert extract_date_from_sheet("31.04.2026") is None


def test_with_year_hint_flag_returns_meta_dict():
    res = extract_date_from_sheet("05.06.2026", with_year_hint=True)
    assert isinstance(res, dict)
    assert res["date"] == "05.06.2026"
    assert res["year_hint"] == 2026


def test_empty_sheet_name_returns_none():
    assert extract_date_from_sheet("") is None
    assert extract_date_from_sheet(None) is None  # type: ignore[arg-type]


# --- trash-row detection -------------------------------------------------


@pytest.fixture
def reader():
    """A CalamineReader with a minimal marker set; only used to reach the
    static _is_trash_row helper."""
    return CalamineReader(
        markers={"customer": ["заказчик"], "amount": ["сумма"], "contractor": ["исполнитель"]},
        aliases={},
    )


def test_is_trash_row_detects_itogo(reader):
    assert reader._is_trash_row(["ИТОГО", "", "1000", "200"]) is True


def test_is_trash_row_detects_vsego(reader):
    assert reader._is_trash_row(["Всего", "", "500"]) is True


def test_is_trash_row_detects_itog_dnya(reader):
    assert reader._is_trash_row(["Итог дня", "", "100"]) is True


def test_is_trash_row_passes_normal_data(reader):
    """A normal customer row must not be flagged as trash."""
    assert reader._is_trash_row(["ООО Ромашка", "Альфа", "1000"]) is False


def test_is_trash_row_word_boundary_prevents_false_positive(reader):
    """'итог' must not match inside a longer word (e.g. a customer name
    containing 'итог' as a substring)."""
    # 'Итого' standalone should match; a made-up name should not.
    assert reader._is_trash_row(["Итогооборот ООО", "Банк", "100"]) is False


def test_is_trash_row_empty_row_is_not_trash(reader):
    """An empty row is not trash — it's just empty (filtered elsewhere)."""
    assert reader._is_trash_row(["", "", ""]) is False


# --- header normalization edge cases ------------------------------------


def test_normalize_header_strips_invisible_chars(reader):
    from core.infra.ingestion_reader import _normalize_header_text

    # Non-breaking space and zero-width space must collapse to plain text.
    assert _normalize_header_text("ЗАКАЗЧИК\xa0") == "заказчик"
    assert _normalize_header_text("\ufeffПриход") == "приход"


def test_normalize_header_collapses_whitespace(reader):
    from core.infra.ingestion_reader import _normalize_header_text

    assert _normalize_header_text("сумма   платежа") == "сумма платежа"


def test_normalize_header_strips_trailing_colon(reader):
    from core.infra.ingestion_reader import _normalize_header_text

    assert _normalize_header_text("Комиссия:") == "комиссия"
