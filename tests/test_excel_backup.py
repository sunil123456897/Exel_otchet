from pathlib import Path

from openpyxl import Workbook

from core.infra.excel_backup import backup_existing_excel_output, resolve_excel_backup_keep
from core.infra.export_writer import MasterWriter


def test_backup_existing_excel_output_keeps_limit(tmp_path: Path) -> None:
    output = tmp_path / "Master_Report.xlsx"
    backup_root = tmp_path / "backups"
    Workbook().save(output)

    for _ in range(3):
        backup_existing_excel_output(output, backup_root, keep=2)

    backups = sorted((backup_root / "excel_outputs" / "Master_Report").glob("*.xlsx"))
    assert len(backups) == 2
    assert all(path.name.endswith("_Master_Report.xlsx") for path in backups)


def test_master_writer_backs_up_existing_workbook_before_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "Master_Report.xlsx"
    backup_root = tmp_path / "backups"
    Workbook().save(output)

    writer = MasterWriter(
        {
            "paths": {
                "master_file": str(output),
                "archive_dir": str(backup_root),
            },
            "backup": {"excel_keep": 5},
        }
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "01.01.2026"
    ws.append(["Источник"])

    assert writer._save_workbook(wb, output) is True

    backups = list((backup_root / "excel_outputs" / "Master_Report").glob("*.xlsx"))
    assert len(backups) == 1


def test_resolve_excel_backup_keep_uses_safe_values() -> None:
    assert resolve_excel_backup_keep(None) == 10
    assert resolve_excel_backup_keep("") == 10
    assert resolve_excel_backup_keep("bad") == 10
    assert resolve_excel_backup_keep(-5) == 1
    assert resolve_excel_backup_keep("0") == 1
    assert resolve_excel_backup_keep("3") == 3


def test_master_writer_invalid_backup_keep_does_not_block_save(
    tmp_path: Path,
) -> None:
    output = tmp_path / "Master_Report.xlsx"
    backup_root = tmp_path / "backups"
    Workbook().save(output)

    writer = MasterWriter(
        {
            "paths": {
                "master_file": str(output),
                "archive_dir": str(backup_root),
            },
            "backup": {"excel_keep": "bad"},
        }
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "01.01.2026"
    ws.append(["Источник"])

    assert writer._save_workbook(wb, output) is True
    assert list((backup_root / "excel_outputs" / "Master_Report").glob("*.xlsx"))
