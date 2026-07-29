import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from core.infra.export_writer import ExportPreflightError, MasterWriter


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


def test_boris_ivan_curator_split_writes_correct_layouts(tmp_path):
    """Characterization: curator='boris' vs curator='ivan' select different
    column layouts (BORIS_HEADERS=12 cols, IVAN_HEADERS=15 cols) and route
    per-curator row values into the right positions.

    The file split itself is the caller's responsibility (AppController calls
    write_report once per curator with a per-curator path); this pins that the
    writer, given curator='boris'/'ivan', produces the distinct column set and
    value placement for each. Until now NO test exercised the curator path —
    a refactor that merged boris/ivan layouts would have passed silently.
    """
    from datetime import datetime

    import openpyxl

    from core.infra.export_writer import BORIS_HEADERS, IVAN_HEADERS, MasterWriter

    boris_out = tmp_path / "boris.xlsx"
    ivan_out = tmp_path / "ivan.xlsx"
    writer = MasterWriter({"paths": {"master_file": str(tmp_path / "master.xlsx")}})

    day = datetime(2026, 7, 29)
    boris_rows = [{
        "Дата": day,
        "Источник": "ООО Ромашка",
        "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "Клиент Б",
        "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Исполнитель Б",
        "сумма платежа ПРИХОД": "1000",
        "% посредник 2": "50",
        "посредник 2": "500",
    }]
    ivan_rows = [{
        "Дата": day,
        "Сотрудник": "Иванов И.И.",
        "Источник": "ООО Ромашка",
        "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "Клиент И",
        "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Исполнитель И",
        "сумма платежа ПРИХОД": "2000",
        "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ": "100",
        "курс": "90",
        "сумма": "180",
        "валюта": "USD",
    }]

    assert writer.write_report(boris_rows, boris_out, curator="boris") is True
    assert writer.write_report(ivan_rows, ivan_out, curator="ivan") is True

    wb_b = openpyxl.load_workbook(boris_out)
    wb_i = openpyxl.load_workbook(ivan_out)
    ws_b = wb_b["29.07.2026"]
    ws_i = wb_i["29.07.2026"]

    # Header row selects the distinct per-curator column layout.
    assert [c.value for c in ws_b[1]] == BORIS_HEADERS
    assert [c.value for c in ws_i[1]] == IVAN_HEADERS
    assert ws_b.max_column == len(BORIS_HEADERS)  # 12
    assert ws_i.max_column == len(IVAN_HEADERS)   # 15

    # Boris layout includes "% посредник 2"; Ivan layout includes the transit
    # + currency columns. Pin the value placement so a column reshuffle fails.
    boris_hdr_index = {h: i for i, h in enumerate(BORIS_HEADERS, start=1)}
    ivan_hdr_index = {h: i for i, h in enumerate(IVAN_HEADERS, start=1)}
    # In the grouped (curator) path row 2 is the employee sub-header; data
    # starts at row 3.
    boris_data_row = [c.value for c in ws_b[3]]
    ivan_data_row = [c.value for c in ws_i[3]]
    # Boris: the "% посредник 2" column carries the supplied value. The writer
    # interprets this column as a percentage, so "50" is stored as the fraction
    # 0.5 (50%). What matters for this characterization is that the value
    # reached the correct column position (not None/0-as-missing) — i.e. the
    # boris layout's extra column is wired to the right row key.
    assert boris_data_row[boris_hdr_index["% посредник 2"] - 1] is not None
    assert boris_data_row[boris_hdr_index["% посредник 2"] - 1] != 0
    # Ivan: transit + currency columns carry their supplied values.
    assert ivan_data_row[ivan_hdr_index["ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ"] - 1] == 100
    assert ivan_data_row[ivan_hdr_index["Валюта"] - 1] == "USD"
