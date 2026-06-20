"""Tests for core.infra.path_resolver — path resolution and discovery."""

from pathlib import Path
from types import SimpleNamespace

from core.infra.path_resolver import (
    _build_meta,
    _find_discovered_meta,
    _normalize_path_parts,
    _path_suffix_candidates,
    _resolve_reports_alias,
    _resolve_with_config_controller,
    resolve_employee_path,
)


class TestNormalizePathParts:
    def test_basic(self):
        assert _normalize_path_parts("a/b/c") == ["a", "b", "c"]

    def test_backslashes(self):
        assert _normalize_path_parts("a\\b\\c") == ["a", "b", "c"]

    def test_empty_and_dots(self):
        assert _normalize_path_parts("./a/../b") == ["a", "b"]

    def test_empty_string(self):
        assert _normalize_path_parts("") == []


class TestPathSuffixCandidates:
    def test_empty(self):
        assert _path_suffix_candidates("") == []
        assert _path_suffix_candidates("   ") == []

    def test_basic_path(self):
        candidates = _path_suffix_candidates("some/dir/file.xlsx")
        assert any("file.xlsx" in c for c in candidates)

    def test_with_reports_marker(self):
        candidates = _path_suffix_candidates("Q:\\Reports\\curator\\emp\\file.xlsx")
        assert len(candidates) > 1

    def test_deduplication(self):
        candidates = _path_suffix_candidates("file.xlsx")
        assert len(candidates) == len(set(candidates))


class TestResolveReportsAlias:
    def test_no_config_controller(self):
        assert _resolve_reports_alias("reports/cur/file.xlsx", None) is None

    def test_no_get_paths(self):
        cc = SimpleNamespace()
        assert _resolve_reports_alias("reports/cur/file.xlsx", cc) is None

    def test_non_reports_path(self):
        cc = SimpleNamespace(get_paths=lambda: {"source_roots": ["/root"]})
        assert _resolve_reports_alias("other/cur/file.xlsx", cc) is None

    def test_too_short_path(self):
        cc = SimpleNamespace(get_paths=lambda: {"source_roots": ["/root"]})
        assert _resolve_reports_alias("reports/x", cc) is None

    def test_get_paths_not_callable(self):
        cc = SimpleNamespace(get_paths="not_callable")
        assert _resolve_reports_alias("reports/cur/file.xlsx", cc) is None

    def test_get_paths_raises(self):
        def bad_get_paths():
            raise RuntimeError("fail")
        cc = SimpleNamespace(get_paths=bad_get_paths)
        assert _resolve_reports_alias("reports/cur/file.xlsx", cc) is None

    def test_candidate_found(self, tmp_path):
        root = tmp_path / "curator1"
        root.mkdir()
        (root / "file.xlsx").write_text("data")
        cc = SimpleNamespace(get_paths=lambda: {"source_roots": [str(root)]})
        result = _resolve_reports_alias("reports/curator1/file.xlsx", cc)
        assert result is not None
        assert result.exists()

    def test_source_root_string(self, tmp_path):
        root = tmp_path / "cur"
        root.mkdir()
        (root / "f.xlsx").write_text("x")
        cc = SimpleNamespace(get_paths=lambda: {"source_roots": str(root)})
        result = _resolve_reports_alias("reports/cur/f.xlsx", cc)
        assert result is not None


class TestResolveWithConfigController:
    def test_no_config_controller(self):
        result = _resolve_with_config_controller("/abs/path.xlsx", None)
        assert result == Path("/abs/path.xlsx")

    def test_no_resolve_path_attr(self):
        cc = SimpleNamespace()
        result = _resolve_with_config_controller("/abs/path.xlsx", cc)
        assert result == Path("/abs/path.xlsx")

    def test_resolve_path_not_callable(self):
        cc = SimpleNamespace(resolve_path="not_callable")
        result = _resolve_with_config_controller("/abs/path.xlsx", cc)
        assert result == Path("/abs/path.xlsx")

    def test_resolve_path_returns_string(self):
        cc = SimpleNamespace(resolve_path=lambda p: "/resolved.xlsx")
        result = _resolve_with_config_controller("file.xlsx", cc)
        assert result == Path("/resolved.xlsx")

    def test_resolve_path_raises_type_error(self):
        def bad_resolver(p):
            raise TypeError("bad")
        cc = SimpleNamespace(resolve_path=bad_resolver)
        result = _resolve_with_config_controller("file.xlsx", cc)
        assert result == Path("file.xlsx")


class TestFindDiscoveredMeta:
    def test_found_by_suffix(self):
        discovered = [{"path": "Q:\\reports\\curator\\file.xlsx"}]
        result = _find_discovered_meta("curator/file.xlsx", discovered)
        assert result is not None
        assert result["path"] == "Q:\\reports\\curator\\file.xlsx"

    def test_not_found(self):
        discovered = [{"path": "Q:\\other\\file.xlsx"}]
        result = _find_discovered_meta("missing/different.xlsx", discovered)
        assert result is None

    def test_found_by_id(self):
        discovered = [{"path": "Q:\\a.xlsx", "id": "abc123"}]
        result = _find_discovered_meta("nomatch", discovered, file_id="abc123")
        assert result is not None

    def test_found_by_hash(self):
        discovered = [{"path": "Q:\\a.xlsx", "fp": "hash123"}]
        result = _find_discovered_meta("nomatch", discovered, file_hash="hash123")
        assert result is not None

    def test_no_ids(self):
        discovered = [{"path": "Q:\\a.xlsx"}]
        result = _find_discovered_meta("nomatch", discovered)
        assert result is None


class TestBuildMeta:
    def test_basic(self):
        meta = _build_meta("/path/file.xlsx")
        assert meta == {"path": "/path/file.xlsx"}

    def test_with_id(self):
        meta = _build_meta("/path/file.xlsx", file_id="abc")
        assert meta["id"] == "abc"

    def test_with_hash(self):
        meta = _build_meta("/path/file.xlsx", file_hash="xyz")
        assert meta["fp"] == "xyz"


class TestResolveEmployeePath:
    def test_found_in_discovered(self):
        discovered = [{"path": "/real/file.xlsx"}]
        path, meta, renamed = resolve_employee_path(
            "file.xlsx", discovered_files=discovered
        )
        assert path == "/real/file.xlsx"
        assert renamed is True

    def test_existing_absolute_path(self, tmp_path):
        f = tmp_path / "report.xlsx"
        f.write_text("data")
        path, meta, renamed = resolve_employee_path(str(f))
        assert path == str(f)
        assert renamed is False

    def test_nonexistent_path(self):
        path, meta, renamed = resolve_employee_path("/nonexistent/file.xlsx")
        assert path == "/nonexistent/file.xlsx"
        assert meta is None
        assert renamed is False
