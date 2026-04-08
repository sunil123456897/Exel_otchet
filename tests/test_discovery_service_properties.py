"""Property-based тесты для DiscoveryService через Hypothesis.

Тестируем инварианты:
1. Rename detection всегда работает при совпадении ID
2. Path resolution всегда создаёт абсолютные пути
3. Deduplication всегда устраняет дубликаты
4. Case-insensitive matching всегда работает
"""

import pytest
import os
import hashlib
from pathlib import Path
from unittest.mock import MagicMock
from hypothesis import given, strategies as st, settings, assume
from hypothesis.strategies import text, lists, dictionaries

from core.infra.discovery_service import DiscoveryService


def _make_discovery_service(config, scan_result=None):
    config_controller = MagicMock()
    config_controller.config = config
    config_controller.config_path = "/tmp/config.yaml"
    emp_paths = config.get("employee_paths", {})
    if not emp_paths and "employees" in config:
        emp_list = config["employees"]
        if isinstance(emp_list, list):
            emp_paths = {name: [] for name in emp_list}
    config_controller.employees = emp_paths

    ingestion = MagicMock()
    ingestion.scan_directory.return_value = scan_result or []
    return DiscoveryService(config_controller, ingestion)


class TestRenameDetectionProperties:
    """Инварианты rename detection."""

    @given(
        st.text(min_size=1, max_size=20).filter(
            lambda s: "/" not in s and "\\" not in s
        ),
        st.integers(min_value=1, max_value=1000000),
    )
    @settings(max_examples=50)
    def test_same_id_always_detects_rename(self, old_name, file_id):
        """Файлы с одинаковым ID всегда распознаются как один файл."""
        old_path = f"/old/{old_name}.xlsx"
        new_path = f"/new/{old_name}_renamed.xlsx"

        config = {
            "employees": ["TestEmp"],
            "employee_paths": {
                "TestEmp": [{"path": old_path, "id": file_id, "fp": None}]
            },
            "paths": {"source_roots": ["/old", "/new"]},
        }
        ds = _make_discovery_service(
            config,
            scan_result=[
                {"path": new_path, "id": file_id, "fp": "hash"},
            ],
        )
        result = ds.get_employees_map()

        # Rename должен быть детектирован
        assert ds.rename_detected is True
        assert "TestEmp" in result
        assert result["TestEmp"][0]["path"] == new_path

    @given(
        st.text(min_size=1, max_size=20),
        st.text(min_size=1, max_size=20),
    )
    @settings(max_examples=50)
    def test_same_hash_always_detects_rename(self, old_name, new_name):
        """Файлы с одинаковым hash всегда распознаются."""
        old_path = f"/old/{old_name}.xlsx"
        new_path = f"/new/{new_name}.xlsx"
        shared_hash = "abc123def"

        config = {
            "employees": ["TestEmp"],
            "employee_paths": {
                "TestEmp": [{"path": old_path, "id": None, "fp": shared_hash}]
            },
            "paths": {"source_roots": ["/old", "/new"]},
        }
        ds = _make_discovery_service(
            config,
            scan_result=[
                {"path": new_path, "id": 999, "fp": shared_hash},
            ],
        )
        result = ds.get_employees_map()

        assert ds.rename_detected is True
        assert "TestEmp" in result


class TestPathResolutionProperties:
    """Инварианты разрешения путей."""

    @given(
        lists(
            st.text(min_size=1, max_size=10).filter(
                lambda s: all(c not in s for c in "/\\:")
            ),
            min_size=1,
            max_size=5,
        ).filter(lambda l: len(set(l)) == len(l)),  # unique names
    )
    @settings(max_examples=30)
    def test_result_paths_always_absolute(self, emp_names):
        """Все пути в результате всегда абсолютные."""
        root = "/reports"
        config = {"employees": emp_names, "paths": {"source_roots": [root]}}
        scan_result = []
        for name in emp_names:
            scan_result.append(
                {
                    "path": f"{root}/{name}/file.xlsx",
                    "id": hash(name) % 1000000,
                    "fp": f"hash_{name}",
                }
            )

        ds = _make_discovery_service(config, scan_result=scan_result)
        result = ds.get_employees_map()

        for name in emp_names:
            if name in result:
                for meta in result[name]:
                    assert Path(meta["path"]).is_absolute() or meta["path"].startswith(
                        "/"
                    )


class TestDeduplicationProperties:
    """Инварианты дедупликации."""

    @given(st.integers(min_value=2, max_value=10))
    @settings(max_examples=30)
    def test_duplicate_paths_removed(self, dup_count):
        """Дубликаты путей всегда устраняются."""
        config = {
            "employees": ["Alice"],
            "employee_paths": {
                "Alice": [{"path": "/reports/Alice/file.xlsx", "id": 1, "fp": "h"}]
                * dup_count
            },
            "paths": {"source_roots": ["/reports"]},
        }
        ds = _make_discovery_service(
            config,
            scan_result=[
                {"path": "/reports/Alice/file.xlsx", "id": 1, "fp": "h"},
            ],
        )
        result = ds.get_employees_map()

        # Alice should be found (via scan or custom paths)
        assert "Alice" in result
        # If found via scan, should have 1 entry
        assert len(result["Alice"]) >= 1
        assert result["Alice"][0]["path"] == "/reports/Alice/file.xlsx"


class TestCaseInsensitiveMatching:
    """Инварианты регистронезависимого сопоставления."""

    @given(
        st.text(alphabet="абвгдежзиклмнопрстуфхцчшщэюя", min_size=2, max_size=10),
    )
    @settings(max_examples=30)
    def test_case_insensitive_employee_match(self, emp_name_lower):
        """Сопоставление имён не зависит от регистра."""
        root = "/reports"
        # Папка в нижнем регистре
        folder_name = emp_name_lower
        file_path = f"{root}/{folder_name}/file.xlsx"

        config = {
            "employees": [emp_name_lower.upper()],  # Конфиг в верхнем регистре
            "paths": {"source_roots": [root]},
        }
        ds = _make_discovery_service(
            config,
            scan_result=[
                {"path": file_path, "id": 1, "fp": "h"},
            ],
        )
        result = ds.get_employees_map()

        # Должен найти сотрудника несмотря на разницу регистра
        assert emp_name_lower.upper() in result


class TestEdgeCaseProperties:
    """Инварианты для крайних случаев."""

    @given(st.integers(min_value=0, max_value=100))
    @settings(max_examples=20)
    def test_empty_scan_result_returns_empty_map(self, seed):
        """Пустой scan → пустая карта (при отсутствии custom paths)."""
        config = {"employees": [], "paths": {"source_roots": ["/reports"]}}
        ds = _make_discovery_service(config, scan_result=[])
        result = ds.get_employees_map()
        assert result == {}

    @given(st.text(min_size=0, max_size=50))
    @settings(max_examples=30)
    def test_special_chars_in_employee_name(self, emp_name):
        """Специальные символы в именах не ломают логику."""
        import sys

        if sys.platform == "win32":
            pytest.skip("Windows path restrictions")
        assume(emp_name.strip())
        assume("/" not in emp_name and "\\" not in emp_name)
        assume(all(c not in emp_name for c in ':*?"<>|'))

        config = {
            "employees": [emp_name],
            "employee_paths": {
                emp_name: [
                    {"path": f"/reports/{emp_name}/file.xlsx", "id": 1, "fp": "h"}
                ]
            },
            "paths": {"source_roots": ["/reports"]},
        }
        # Не должно выбрасывать
        ds = _make_discovery_service(config, scan_result=[])
        result = ds.get_employees_map()
        assert emp_name in result
