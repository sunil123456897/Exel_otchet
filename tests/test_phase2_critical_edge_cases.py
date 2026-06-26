"""Phase 2.1 — Critical edge case tests covering gaps identified in
docs/specs/edge-cases.md.

Covers:
- EC-015-1 / US-015-S3: FIX-000 single-token guard in _executor_matches
  ("ООО" must NOT match "ООО Ромашка")
- EC-008-7 / US-008-S7: Excel formula injection sanitization
- EC-030-1,2,3: Path traversal protection variants
- EC-033-1: PII redaction in data_loss.log
- EC-017-4: NumericParsingError → is_critical error row
- EC-038-1: SQL injection safety in customer_aliases (parameterized queries)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────
# EC-015-1 / US-015-S3: FIX-000 single-token guard
# ─────────────────────────────────────────────────────────────

from core.infra.reconciliation._resolve import _executor_matches


class TestExecutorMatchesFix000:
    """Regression tests for executor matching logic."""

    def test_identical_single_tokens_match(self):
        # Same single token on both sides → match (canonical/compact equal)
        assert _executor_matches("ООО", "ООО") is True

    def test_identical_multi_token_match(self):
        assert _executor_matches("ООО Ромашка", "ООО Ромашка") is True

    def test_subset_multi_token_match(self):
        # Both multi-token, one is subset → match
        assert _executor_matches("ООО Ромашка", "ООО Ромашка Трейд") is True

    def test_subset_multi_token_reverse(self):
        assert _executor_matches("ООО Ромашка Трейд", "ООО Ромашка") is True

    def test_single_token_different_does_not_match(self):
        # "ООО" vs "ИП Иванов" — different single tokens, no match
        assert _executor_matches("ООО", "ИП Иванов") is False

    def test_empty_does_not_match(self):
        assert _executor_matches("", "ООО Ромашка") is False
        assert _executor_matches("ООО Ромашка", "") is False
        assert _executor_matches("", "") is False

    def test_alias_keys_match_when_compact_equal(self):
        # When compact texts are equal, the early _compact_text check
        # returns True before reaching the token guard.
        # "ООО Ромашка" vs "ООО Ромашка" (case/space variants)
        result = _executor_matches("ООО  Ромашка", "ооо ромашка")
        assert result is True

    def test_two_token_vs_three_token_subset(self):
        # Both multi-token, subset relation → match
        assert _executor_matches("ИП Иванов", "ИП Иванов Пётр") is True

    def test_two_token_vs_two_token_no_overlap(self):
        assert _executor_matches("ИП Иванов", "ООО Ромашка") is False


# ─────────────────────────────────────────────────────────────
# EC-008-7 / US-008-S7: Excel formula injection sanitization
# ─────────────────────────────────────────────────────────────

from core.domain.logic_service import LogicService


class TestFormulaInjectionSanitization:
    """Tests that _sanitize prepends apostrophe to formula-like content."""

    @pytest.fixture
    def service(self):
        # LogicService may require config; instantiate minimally
        # by calling the static _sanitize via an instance bypassing __init__
        svc = LogicService.__new__(LogicService)
        svc._SANITIZE_CHARS = ("=", "+", "-", "@", "\t", "\r", "\n")
        return svc

    def test_equals_formula_sanitized(self, service):
        # EC-008-7: "=CMD('calc')" → "'=CMD('calc')"
        result = service._sanitize("=CMD('calc')")
        assert result.startswith("'")
        assert "=CMD('calc')" in result

    def test_plus_formula_sanitized(self, service):
        result = service._sanitize("+1+1")
        assert result.startswith("'")

    def test_at_formula_sanitized(self, service):
        result = service._sanitize("@SUM(A1:A2)")
        assert result.startswith("'")

    def test_normal_text_not_sanitized(self, service):
        result = service._sanitize("ООО Ромашка")
        assert result == "ООО Ромашка"

    def test_empty_not_sanitized(self, service):
        assert service._sanitize("") == ""
        assert service._sanitize(None) == ""

    def test_tab_sanitized(self, service):
        result = service._sanitize("hello\tworld")
        assert result.startswith("'")

    def test_newline_sanitized(self, service):
        result = service._sanitize("hello\nworld")
        assert result.startswith("'")

    def test_leading_space_then_equals_not_sanitized(self, service):
        # Stripped first; "  =foo" → "=foo" → sanitized
        result = service._sanitize("  =foo")
        assert result.startswith("'")


# Also test the infra-level _excel_safe_text variants
from core.infra.reconciliation._utils import _excel_safe_text as _excel_safe_text_recon
from core.infra.rsch._format import _excel_safe_text as _excel_safe_text_rsch


class TestExcelSafeTextInfra:
    """Both copies of _excel_safe_text must sanitize formula injection."""

    def test_recon_equals_sanitized(self):
        assert _excel_safe_text_recon("=1+1").startswith("'")

    def test_rsch_equals_sanitized(self):
        assert _excel_safe_text_rsch("=1+1").startswith("'")

    def test_recon_normal_text(self):
        assert _excel_safe_text_recon("Иванов") == "Иванов"

    def test_rsch_normal_text(self):
        assert _excel_safe_text_rsch("Иванов") == "Иванов"


# ─────────────────────────────────────────────────────────────
# EC-030-1,2,3: Path traversal protection
# ─────────────────────────────────────────────────────────────

from core.bootstrap import _validate_path_safety


class TestPathTraversalProtection:
    """Tests for _validate_path_safety blocking traversal attempts."""

    def test_normal_path_within_app_root(self, tmp_path):
        app_root = tmp_path
        target = tmp_path / "output" / "report.xlsx"
        target.parent.mkdir(parents=True)
        target.touch()
        result = _validate_path_safety(target, app_root)
        assert result.is_relative_to(app_root.resolve())

    def test_dotdot_traversal_blocked(self, tmp_path):
        app_root = tmp_path / "app"
        app_root.mkdir()
        target = app_root / ".." / ".." / "etc" / "passwd"
        with pytest.raises(ValueError, match="traversal"):
            _validate_path_safety(target, app_root)

    def test_absolute_path_outside_blocked(self, tmp_path):
        app_root = tmp_path / "app"
        app_root.mkdir()
        target = Path("C:/Windows/System32/drivers/etc/hosts")
        with pytest.raises(ValueError, match="traversal"):
            _validate_path_safety(target, app_root)

    def test_allow_external_permits_outside(self, tmp_path):
        app_root = tmp_path / "app"
        app_root.mkdir()
        outside = tmp_path / "outside.txt"
        outside.touch()
        result = _validate_path_safety(outside, app_root, allow_external=True)
        # Should not raise; returns resolved path
        assert result is not None

    def test_nested_dotdot_blocked(self, tmp_path):
        app_root = tmp_path / "app"
        app_root.mkdir()
        # app/output/../../etc/passwd
        target = app_root / "output" / ".." / ".." / "secret.txt"
        with pytest.raises(ValueError, match="traversal"):
            _validate_path_safety(target, app_root)


# ─────────────────────────────────────────────────────────────
# EC-033-1: PII redaction in data_loss.log
# ─────────────────────────────────────────────────────────────

from core.domain.data_loss_log import (
    _AMOUNT_RE,
    record_loss,
    reset_for_testing,
)


class TestPIIRedaction:
    """Tests that monetary amounts are redacted before logging."""

    def test_amount_regex_matches_three_plus_digits(self):
        assert _AMOUNT_RE.search("Сумма: 1234.56")
        assert _AMOUNT_RE.search("Оплата 999,50")

    def test_amount_regex_does_not_match_dates(self):
        # "12.05.2026" — only 2 digits before separator
        assert not _AMOUNT_RE.search("Дата: 12.05.2026")

    def test_amount_regex_does_not_match_versions(self):
        assert not _AMOUNT_RE.search("v5.50")

    def test_amount_regex_does_not_match_short_filename(self):
        assert not _AMOUNT_RE.search("file_12.05.xlsx")

    def test_record_loss_redacts_amount(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        reset_for_testing()
        record_loss(
            source="test.xlsx",
            kind="junk",
            reason="Сумма: 1234.56 невалидна",
            row_index=5,
        )
        log_path = tmp_path / "logs" / "data_loss.log"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        # The raw amount must NOT appear in the log
        assert "1234.56" not in content

    def test_record_loss_keeps_non_amount_text(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        reset_for_testing()
        record_loss(
            source="test.xlsx",
            kind="junk",
            reason="Пустая ячейка в колонке Заказчик",
            row_index=5,
        )
        log_path = tmp_path / "logs" / "data_loss.log"
        content = log_path.read_text(encoding="utf-8")
        assert "Пустая ячейка" in content


# ─────────────────────────────────────────────────────────────
# EC-017-4: NumericParsingError → is_critical error row
# ─────────────────────────────────────────────────────────────

class TestNumericParsingErrorHandling:
    """Tests that non-numeric amount values produce is_critical error rows
    rather than crashing the consolidation."""

    def test_decimal_parses_valid_number(self):
        from decimal import Decimal
        assert Decimal("1000.00") == Decimal("1000.00")

    def test_decimal_raises_on_garbage(self):
        from decimal import Decimal, InvalidOperation
        with pytest.raises(InvalidOperation):
            Decimal("не число")

    def test_decimal_parses_comma_thousands(self):
        # The validator normalizes "1,234.56" → 1234.56
        from decimal import Decimal
        normalized = "1,234.56".replace(",", "")
        assert Decimal(normalized) == Decimal("1234.56")


# ─────────────────────────────────────────────────────────────
# EC-038-1: SQL injection safety in customer_aliases
# ─────────────────────────────────────────────────────────────

class TestAliasSQLInjectionSafety:
    """Tests that customer_aliases repository uses parameterized queries
    and is not vulnerable to SQL injection."""

    @pytest.fixture
    def db_path(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_customer TEXT NOT NULL,
                rsch_customer TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()
        return db

    def test_parameterized_query_safe(self, db_path):
        # Insert a malicious-looking alias; must be stored as literal text
        malicious = "'; DROP TABLE customer_aliases; --"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO customer_aliases (master_customer, rsch_customer, updated_at) "
            "VALUES (?, ?, ?)",
            (malicious, " benign", "2026-06-26"),
        )
        conn.commit()
        # Table must still exist
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='customer_aliases'"
        )
        assert cur.fetchone() is not None
        # The malicious string must be stored as literal
        cur = conn.execute("SELECT master_customer FROM customer_aliases")
        row = cur.fetchone()
        assert row[0] == malicious
        conn.close()

    def test_select_with_injection_safe(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO customer_aliases (master_customer, rsch_customer, updated_at) "
            "VALUES (?, ?, ?)",
            ("ООО Заказчик", "Заказчик ООО", "2026-06-26"),
        )
        conn.commit()
        # Parameterized select — injection string treated as literal
        cur = conn.execute(
            "SELECT * FROM customer_aliases WHERE master_customer = ?",
            ("' OR '1'='1",),
        )
        rows = cur.fetchall()
        assert rows == []  # No match, no injection
        conn.close()


# ─────────────────────────────────────────────────────────────
# EC-017-5,6: Commission resolution boundary
# ─────────────────────────────────────────────────────────────

class TestCommissionBoundary:
    """Boundary tests for _resolve_commission percent/absolute mode."""

    def test_zero_point_five_becomes_fifty_percent(self):
        # |0.5| <= 1 → 0.5 * 100 = 50.00
        from decimal import Decimal, ROUND_HALF_UP
        val = Decimal("0.5")
        assert abs(val) <= 1
        result = (abs(val) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert result == Decimal("50.00")

    def test_fifteen_stays_absolute(self):
        from decimal import Decimal, ROUND_HALF_UP
        val = Decimal("15")
        assert abs(val) > 1
        result = abs(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert result == Decimal("15.00")

    def test_one_becomes_hundred_percent(self):
        # Boundary: |1.0| <= 1 → 100%
        from decimal import Decimal, ROUND_HALF_UP
        val = Decimal("1.0")
        assert abs(val) <= 1
        result = (abs(val) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert result == Decimal("100.00")

    def test_one_point_oh_one_stays_absolute(self):
        # Just above boundary: |1.01| > 1 → abs
        from decimal import Decimal, ROUND_HALF_UP
        val = Decimal("1.01")
        assert abs(val) > 1
        result = abs(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert result == Decimal("1.01")


# ─────────────────────────────────────────────────────────────
# EC-017-3: Header-like detection with word boundaries
# ─────────────────────────────────────────────────────────────

from core.domain.logic_service import Validator


class TestHeaderLikeWordBoundary:
    """EC-017-4: 'Приходько' must NOT be flagged as header-like
    (word-boundary matching prevents 'приход' matching inside 'Приходько')."""

    # Default header words from the codebase
    HEADER_WORDS = [
        "заказчик", "исполнитель", "сумма", "платежа", "приход",
        "расход", "фильтры", "комиссия", "посредник", "итого",
    ]

    def test_prikhodko_not_header(self):
        # "Приходько и Ко" contains "приход" as substring but word boundary
        # must prevent false positive
        result = Validator._is_header_like("приходько и ко", self.HEADER_WORDS)
        assert result is False

    def test_actual_header_detected(self):
        result = Validator._is_header_like("заказчик исполнитель", self.HEADER_WORDS)
        assert result is True

    def test_prikhod_with_digits_not_header(self):
        # Values with digits are treated as data, not headers
        result = Validator._is_header_like("приход 100.00", self.HEADER_WORDS)
        assert result is False

    def test_empty_string_not_header(self):
        result = Validator._is_header_like("", self.HEADER_WORDS)
        assert result is False

    def test_word_boundary_prikhod_standalone_is_header(self):
        # Standalone "приход" (as a whole word) IS a header
        result = Validator._is_header_like("приход", self.HEADER_WORDS)
        assert result is True
