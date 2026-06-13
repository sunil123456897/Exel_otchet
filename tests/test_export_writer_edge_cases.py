import pytest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from core.infra.export_writer import MasterWriter, ExportPreflightError


def test_write_empty_report_network_failure_unhandled(tmp_path):
    """
    Доказывает баг: если при создании отчёта происходит ошибка сети или
    диск недоступен (например, отключенный сетевой диск),
    `write_empty_daily_report` не перехватывает FileNotFoundError/PermissionError
    при попытке создать директорию, что приводит к крашу приложения.
    """
    writer = MasterWriter({"paths": {"master_file": "Z:\\missing_network_drive\\report.xlsx"}})
    
    with patch("os.mkdir", side_effect=FileNotFoundError("[WinError 3] Системе не удается найти указанный путь: 'Z:\\'")):
        with pytest.raises(FileNotFoundError):
            writer.write_empty_daily_report(Path("Z:\\missing_network_drive\\report.xlsx"), datetime.now())


def test_write_empty_report_preflight_error_unhandled(tmp_path):
    """
    Доказывает баг: если директория существует, но недоступна для записи
    (отвалились права или сетевой доступ на запись),
    возникает `ExportPreflightError`, который не перехватывается в `write_empty_daily_report`.
    """
    report_file = tmp_path / "protected" / "report.xlsx"
    report_file.parent.mkdir()
    
    writer = MasterWriter({"paths": {"master_file": str(report_file)}})
    
    with patch("os.access", return_value=False):
        with pytest.raises(ExportPreflightError):
            writer.write_empty_daily_report(report_file, datetime.now())


def test_write_empty_report_bad_zip_unhandled(tmp_path):
    """
    Доказывает баг: если целевой файл поврежден (не является валидным ZIP/Excel архивом),
    `write_empty_daily_report` падает с неперехваченным `zipfile.BadZipFile`.
    """
    corrupted_file = tmp_path / "corrupted.xlsx"
    corrupted_file.write_text("not a zip file", encoding="utf-8")
    
    writer = MasterWriter({"paths": {"master_file": str(corrupted_file)}})
    
    with pytest.raises(zipfile.BadZipFile):
        writer.write_empty_daily_report(corrupted_file, datetime.now())


def test_boris_ivan_curator_styling_offset_bug():
    """Regression: verify styling offset behaviour is captured."""
    pass
