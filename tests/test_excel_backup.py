"""Tests for core.infra.excel_backup — backup and pruning logic."""

from pathlib import Path

from core.infra.excel_backup import (
    backup_existing_excel_output,
    resolve_excel_backup_keep,
)


class TestResolveExcelBackupKeep:
    def test_valid_int(self):
        assert resolve_excel_backup_keep(5) == 5

    def test_string_int(self):
        assert resolve_excel_backup_keep("10") == 10

    def test_none(self):
        assert resolve_excel_backup_keep(None) == 10

    def test_invalid_string(self):
        assert resolve_excel_backup_keep("abc") == 10

    def test_zero_clamped_to_1(self):
        assert resolve_excel_backup_keep(0) == 1

    def test_negative_clamped_to_1(self):
        assert resolve_excel_backup_keep(-5) == 1

    def test_custom_default(self):
        assert resolve_excel_backup_keep(None, default=20) == 20


class TestBackupExistingExcelOutput:
    def test_nonexistent_file(self, tmp_path):
        result = backup_existing_excel_output(tmp_path / "no.xlsx")
        assert result is None

    def test_temp_file_skipped(self, tmp_path):
        f = tmp_path / "~$report.xlsx"
        f.write_text("temp")
        result = backup_existing_excel_output(f)
        assert result is None

    def test_backup_created(self, tmp_path):
        f = tmp_path / "report.xlsx"
        f.write_text("data")
        backup_root = tmp_path / "bak"
        result = backup_existing_excel_output(f, backup_root=backup_root, keep=5)
        assert result is not None
        assert result.exists()
        assert "report" in str(result)

    def test_backup_default_root(self, tmp_path):
        f = tmp_path / "report.xlsx"
        f.write_text("data")
        result = backup_existing_excel_output(f, keep=3)
        assert result is not None
        assert result.exists()
        backups_dir = tmp_path / "backups" / "excel_outputs" / "report"
        assert backups_dir.exists()

    def test_pruning_keeps_only_n(self, tmp_path):
        f = tmp_path / "report.xlsx"
        backup_root = tmp_path / "bak"
        for i in range(5):
            f.write_text(f"data-{i}")
            backup_existing_excel_output(f, backup_root=backup_root, keep=3)
        target_dir = backup_root / "excel_outputs" / "report"
        backups = list(target_dir.glob("*.xlsx"))
        assert len(backups) <= 3

    def test_directory_as_path(self, tmp_path):
        d = tmp_path / "somedir"
        d.mkdir()
        result = backup_existing_excel_output(d)
        assert result is None
