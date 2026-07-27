"""Верификационные тесты для репозиториев и контрактов build-API (QA-sweep Phase 2.3b).

Покрывает пункты B1 (config_controller), B3 (customer_alias_repo),
B6 (settings_store) и контрактные проверки A11-A13 (build-функции),
C1 (ReconciliationService) из docs/qa/qa-sweep-spec.md.

Логику НЕ меняем — фиксируем задокументированное поведение, чтобы поймать
регрессию и подтвердить корректность текущей реализации.
"""
from __future__ import annotations

import inspect
import sqlite3
import textwrap
from pathlib import Path

import pytest
from core.infra.customer_alias_repo import CustomerAliasRepository

# ---------------------------------------------------------------------------
# Helper: свежая in-memory / temp SQLite с применённой схемой проекта.
# ---------------------------------------------------------------------------


@pytest.fixture
def alias_repo(tmp_path):
    """Свежая БД со схемой customer_aliases и репозиторий над ней."""
    db_path = tmp_path / "test.db"
    schema = textwrap.dedent("""
        CREATE TABLE customer_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_customer TEXT NOT NULL,
            rsch_customer TEXT NOT NULL,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(master_customer, rsch_customer)
        );
    """).strip()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    conn.commit()
    conn.row_factory = sqlite3.Row
    conn.close()

    # Лёгкий stand-in для SQLiteConnectionManager — отдаёт соединения к
    # нашей временной БД. Реальный менеджер делает то же плюс retry/WAL,
    # что здесь не нужно (проверяем логику репозитория, не коннект-менеджер).
    class _FakeConnMgr:
        def __init__(self, path):
            self._path = str(path)

        def get_connection(self):
            c = sqlite3.connect(self._path)
            c.row_factory = sqlite3.Row
            return c

    repo = CustomerAliasRepository(_FakeConnMgr(db_path))
    yield repo


# ---------------------------------------------------------------------------
# B3: CustomerAliasRepository — CRUD + matching
# ---------------------------------------------------------------------------


class TestCustomerAliasRepository:
    def test_add_and_get_all(self, alias_repo):
        new_id = alias_repo.add_alias("ООО Ромашка", "Ромашка", "notes")
        assert isinstance(new_id, int) and new_id > 0
        all_aliases = alias_repo.get_all_aliases()
        assert len(all_aliases) == 1
        assert all_aliases[0].master_customer == "ООО Ромашка"
        assert all_aliases[0].rsch_customer == "Ромашка"

    def test_is_alias_case_insensitive(self, alias_repo):
        alias_repo.add_alias("ООО Ромашка", "Ромашка")
        # Разный регистр / пробелы → всё равно совпадает
        assert alias_repo.is_alias("ооо ромашка", "  ромашка ") is True
        # Обратное направление тоже работает (симметрично)
        assert alias_repo.is_alias("Ромашка", "ООО Ромашка") is True

    def test_is_alias_identical_names_returns_true(self, alias_repo):
        # Одинаковые имена — формально алиас не нужен, но метод возвращает True
        assert alias_repo.is_alias("Иван", "Иван") is True

    def test_is_alias_empty_returns_false(self, alias_repo):
        assert alias_repo.is_alias("", "x") is False
        assert alias_repo.is_alias("x", "") is False

    def test_is_alias_unrelated_returns_false(self, alias_repo):
        alias_repo.add_alias("А", "Б")
        assert alias_repo.is_alias("А", "В") is False

    def test_add_duplicate_raises(self, alias_repo):
        alias_repo.add_alias("А", "Б")
        with pytest.raises(ValueError):
            alias_repo.add_alias("А", "Б")

    def test_add_identical_pair_raises(self, alias_repo):
        # master == rsch → ValueError («Заказчики идентичны»)
        with pytest.raises(ValueError):
            alias_repo.add_alias("Одинаковые", "Одинаковые")

    def test_add_empty_raises(self, alias_repo):
        with pytest.raises(ValueError):
            alias_repo.add_alias("", "Б")
        with pytest.raises(ValueError):
            alias_repo.add_alias("А", "   ")

    def test_update_alias(self, alias_repo):
        aid = alias_repo.add_alias("А", "Б", "old")
        alias_repo.update_alias(aid, "А2", "Б2", "new")
        aliases = alias_repo.get_all_aliases()
        assert len(aliases) == 1
        assert aliases[0].master_customer == "А2"
        assert aliases[0].notes == "new"

    def test_delete_alias(self, alias_repo):
        aid = alias_repo.add_alias("А", "Б")
        alias_repo.delete_alias(aid)
        assert alias_repo.get_all_aliases() == []
        # После удаления is_alias должен вернуть False (после reload/invalidate)
        alias_repo.reload()
        assert alias_repo.is_alias("А", "Б") is False

    def test_reload_refreshes_cache(self, alias_repo):
        # Добавляем напрямую в БД (минуя репозиторий) — кэш не знает
        alias_repo.add_alias("А", "Б")
        # cache построен
        assert alias_repo.is_alias("А", "Б") is True
        # Прямая вставка второй пары через raw SQL
        conn = alias_repo._conn_mgr.get_connection()
        conn.execute(
            "INSERT INTO customer_aliases (master_customer, rsch_customer) VALUES (?, ?)",
            ("В", "Г"),
        )
        conn.commit()
        conn.close()
        # Без reload — кэш не видит новую пару
        assert alias_repo.is_alias("В", "Г") is False
        alias_repo.reload()
        assert alias_repo.is_alias("В", "Г") is True


# ---------------------------------------------------------------------------
# B1: ConfigController — load/save/employees round-trip
# ---------------------------------------------------------------------------


class TestConfigController:
    def test_load_missing_returns_empty_and_creates_from_example(self, tmp_path):
        from core.infra.config_controller import ConfigController

        # Кладём config.example.yaml рядом, чтобы сработал fallback
        example = tmp_path / "config.example.yaml"
        example.write_text("paths:\n  master_file: x.xlsx\n", encoding="utf-8")
        cfg_path = tmp_path / "config.yaml"
        cc = ConfigController(str(cfg_path))
        assert isinstance(cc.config, dict)
        # config.yaml создан из example
        assert cfg_path.exists()

    def test_save_and_reload_roundtrip(self, tmp_path):
        from core.infra.config_controller import ConfigController

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("logic:\n  commission_is_percent: true\n", encoding="utf-8")
        cc = ConfigController(str(cfg_path))
        cc.config["logic"]["commission_is_percent"] = False
        cc.save_config()
        # Перезагружаем
        cc2 = ConfigController(str(cfg_path))
        assert cc2.config["logic"]["commission_is_percent"] is False

    def test_add_and_delete_employee(self, tmp_path):
        from core.infra.config_controller import ConfigController

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("paths:\n  master_file: x.xlsx\n", encoding="utf-8")
        cc = ConfigController(str(cfg_path))
        cc.add_employee("Иван")
        assert "Иван" in cc.get_employees()
        cc.delete_employee("Иван")
        assert "Иван" not in cc.get_employees()

    def test_resolve_path_absolute_under_allowed_root(self, tmp_path):
        """resolve_path имеет allowlist-защиту от path traversal.

        Абсолютный путь ВНУТРИ разрешённого корня (config_dir / project root /
        source_root) — проходит. Путь ВНЕ разрешённых корней — отбрасывается
        с ValueError. Это функция безопасности, работает корректно.
        """
        from core.infra.config_controller import ConfigController

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "paths:\n  master_file: x.xlsx\n  source_root: reports\n",
            encoding="utf-8",
        )
        cc = ConfigController(str(cfg_path))
        # Путь внутри config_dir — разрешён
        inside = tmp_path / "ok.xlsx"
        resolved = cc.resolve_path(str(inside))
        assert Path(resolved).resolve() == inside.resolve()

        # Путь вне разрешённых корней — отбрасывается
        with pytest.raises(ValueError, match="traversal|outside"):
            cc.resolve_path(r"E:\some\random\outside\path.xlsx")


# ---------------------------------------------------------------------------
# B6: SettingsStore — round-trip и приведение типов
# ---------------------------------------------------------------------------


class TestSettingsStore:
    def test_load_defaults_when_missing(self, tmp_path):
        from core.infra.config_controller import ConfigController
        from core.infra.settings_store import SettingsStore

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("paths:\n  master_file: x.xlsx\n", encoding="utf-8")
        cc = ConfigController(str(cfg_path))
        store = SettingsStore(cc)
        prefs = store.load_preferences()
        assert prefs.theme in ("light", "dark")
        assert prefs.user_scale == 1.0
        assert prefs.scale_mode == "auto"

    def test_save_and_reload_roundtrip(self, tmp_path):
        from core.infra.config_controller import ConfigController
        from core.infra.settings_store import SettingsStore, UIPreferences

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("paths:\n  master_file: x.xlsx\n", encoding="utf-8")
        cc = ConfigController(str(cfg_path))
        store = SettingsStore(cc)
        store.save_preferences(
            UIPreferences(theme="dark", user_scale=1.25, density="compact", sidebar_width=220)
        )
        cc2 = ConfigController(str(cfg_path))
        store2 = SettingsStore(cc2)
        prefs = store2.load_preferences()
        assert prefs.theme == "dark"
        assert prefs.user_scale == 1.25
        assert prefs.density == "compact"
        assert prefs.sidebar_width == 220

    def test_coercion_of_garbage(self, tmp_path):
        from core.infra.config_controller import ConfigController
        from core.infra.settings_store import SettingsStore

        cfg_path = tmp_path / "config.yaml"
        # Мусорные значения должны быть приведены к дефолтам
        cfg_path.write_text(
            "ui:\n  theme: purple\n  user_scale: notanumber\n  sidebar_width: -5\n",
            encoding="utf-8",
        )
        cc = ConfigController(str(cfg_path))
        store = SettingsStore(cc)
        prefs = store.load_preferences()
        # theme "purple" не валиден → дефолт
        assert prefs.theme in ("light", "dark")
        assert prefs.user_scale == 1.0
        # sidebar_width зажат снизу
        assert prefs.sidebar_width >= 0


# ---------------------------------------------------------------------------
# Контракты public build-API (A11-A13, C1) — сигнатуры и базовое поведение
# ---------------------------------------------------------------------------


class TestBuildApiContracts:
    """Проверяем, что public-функции экспортированы и принимают задокументированные параметры."""

    def test_build_rsch_report_signature(self):
        from core.infra.rsch._build import build_rsch_report

        params = inspect.signature(build_rsch_report).parameters
        expected = {
            "source_path",
            "output_path",
            "target_date",
            "start_date",
            "end_date",
            "template_path",
            "issues_sink",
            "drive_letters",
            "on_progress",
            "on_current_file",
        }
        assert expected.issubset(set(params.keys())), (
            f"build_rsch_report потерял параметры: {expected - set(params.keys())}"
        )

    def test_build_reconciliation_report_signature(self):
        from core.infra.reconciliation._build import (
            build_combined_reconciliation_report,
            build_reconciliation_report,
        )

        p1 = inspect.signature(build_reconciliation_report).parameters
        assert {"master_path", "rsch_path", "output_path", "target_date"}.issubset(set(p1))
        p2 = inspect.signature(build_combined_reconciliation_report).parameters
        assert {"master_paths", "rsch_path", "output_path", "target_date"}.issubset(set(p2))

    def test_reconciliation_service_signature(self):
        from core.services.reconciliation_service import ReconciliationService

        params = inspect.signature(ReconciliationService.run_reconciliation_report).parameters
        assert {
            "master_paths",
            "rsch_path",
            "output_path",
            "selected_date",
            "on_complete",
            "cancel_event",
        }.issubset(set(params))

    def test_build_rsch_report_rejects_no_date(self, tmp_path):
        """Без target_date и start_date — явная ValueError (BUG 5 guard)."""
        from core.infra.rsch._build import build_rsch_report

        with pytest.raises(ValueError, match="target_date|start_date"):
            build_rsch_report([tmp_path / "x.xlsx"], tmp_path / "out.xlsx")

    def test_build_rsch_report_rejects_missing_source(self, tmp_path):
        from datetime import date

        from core.infra.rsch._build import build_rsch_report

        with pytest.raises((FileNotFoundError, ValueError)):
            build_rsch_report(
                [tmp_path / "несуществует.xlsx"],
                tmp_path / "out.xlsx",
                target_date=date(2026, 6, 1),
            )

    def test_package_exports(self):
        """__init__ пакетов должен экспортировать public-функции."""
        from core.infra import reconciliation as recon_pkg
        from core.infra import rsch as rsch_pkg

        assert hasattr(rsch_pkg, "build_rsch_report")
        assert hasattr(recon_pkg, "build_combined_reconciliation_report")
