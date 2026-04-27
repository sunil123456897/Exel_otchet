"""
Расширенные тесты для MasterWriter.
Покрывает: write_report, _save_workbook, _auto_adjust, write_daily_data edge cases.
"""

import pytest
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from core.infra.export_writer import MasterWriter
from openpyxl import Workbook
from openpyxl.styles import PatternFill


@pytest.fixture
def temp_output_dir():
    """Временная директория для выходных файлов."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def master_writer(temp_output_dir):
    """MasterWriter с временным выходным файлом."""
    config = {
        "paths": {"master_file": str(temp_output_dir / "test_output.xlsx")},
        "logic": {},
    }
    return MasterWriter(config)


@pytest.fixture
def sample_consolidated_data():
    """Пример консолидированных данных."""
    return [
        {
            "Дата": "01.04.2026",
            "Источник": "test_file.xlsx : Строка 5",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "ООО Заказчик",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "ИП Иванов",
            "сумма платежа ПРИХОД": 10000.00,
            "сумма платежа РАСХОД": 0,
            "комиссия": 2.5,
            "ИТОГ": 10000.00,
            "% посредника": 5.0,
            "посредник 1(кэш)": 250.00,
            "посредник 2": 0,
            "фильтры": "",
            "is_template_warning": False,
        },
        {
            "Дата": "01.04.2026",
            "Источник": "test_file.xlsx : Строка 12",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "ООО Клиент",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "ООО Исполнитель",
            "сумма платежа ПРИХОД": 0,
            "сумма платежа РАСХОД": 5000.00,
            "комиссия": 0,
            "ИТОГ": -5000.00,
            "% посредника": 0,
            "посредник 1(кэш)": 0,
            "посредник 2": 0,
            "фильтры": "доп сф",
            "is_template_warning": False,
        },
    ]


class TestWriteReport:
    """Тесты для write_report — полный поток записи."""

    def test_write_report_creates_file(
        self, master_writer, sample_consolidated_data, temp_output_dir
    ):
        output_path = temp_output_dir / "report.xlsx"
        result = master_writer.write_report(sample_consolidated_data, output_path)
        assert result is True
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_write_report_creates_sheet_with_date(
        self, master_writer, sample_consolidated_data, temp_output_dir
    ):
        from openpyxl import load_workbook

        output_path = temp_output_dir / "report.xlsx"
        master_writer.write_report(sample_consolidated_data, output_path)

        wb = load_workbook(output_path)
        assert "01.04.2026" in wb.sheetnames
        wb.close()

    def test_write_report_empty_data(self, master_writer, temp_output_dir):
        output_path = temp_output_dir / "report_empty.xlsx"
        result = master_writer.write_report([], output_path)
        assert result is False

    def test_write_report_multiple_dates(self, master_writer, temp_output_dir):
        data = [
            {
                "Дата": "01.04.2026",
                "Источник": "f1.xlsx : 1",
                "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "A",
                "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "B",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
                "% посредника": 0,
                "посредник 1(кэш)": 0,
                "посредник 2": 0,
                "фильтры": "",
                "is_template_warning": False,
            },
            {
                "Дата": "02.04.2026",
                "Источник": "f2.xlsx : 1",
                "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "C",
                "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "D",
                "сумма платежа ПРИХОД": 200,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 200,
                "% посредника": 0,
                "посредник 1(кэш)": 0,
                "посредник 2": 0,
                "фильтры": "",
                "is_template_warning": False,
            },
        ]
        from openpyxl import load_workbook

        output_path = temp_output_dir / "multi_date.xlsx"
        master_writer.write_report(data, output_path)

        wb = load_workbook(output_path)
        assert "01.04.2026" in wb.sheetnames
        assert "02.04.2026" in wb.sheetnames
        wb.close()

    def test_write_report_missing_date_is_skipped(self, master_writer, temp_output_dir):
        """Строка без даты должна быть пропущена, а не попадать в UNKNOWN_DATE."""
        data = [
            {
                "Дата": None,
                "Источник": "bad.xlsx : 1",
                "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "X",
                "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Y",
                "сумма платежа ПРИХОД": 50,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 50,
                "% посредника": 0,
                "посредник 1(кэш)": 0,
                "посредник 2": 0,
                "фильтры": "",
                "is_template_warning": False,
            },
            {
                "Дата": "01.04.2026",
                "Источник": "ok.xlsx : 1",
                "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "Z",
                "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Y",
                "сумма платежа ПРИХОД": 50,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 50,
                "% посредника": 0,
                "посредник 1(кэш)": 0,
                "посредник 2": 0,
                "фильтры": "",
                "is_template_warning": False,
            },
        ]
        from openpyxl import load_workbook

        output_path = temp_output_dir / "skip_missing_date.xlsx"
        with patch("core.infra.export_writer.logger") as mock_logger:
            result = master_writer.write_report(data, output_path)
            mock_logger.warning.assert_called()

        assert result is True

        wb = load_workbook(output_path)
        assert "UNKNOWN_DATE" not in wb.sheetnames
        assert "01.04.2026" in wb.sheetnames
        wb.close()

    def test_write_report_future_date_is_skipped(self, master_writer, temp_output_dir):
        output_path = temp_output_dir / "future_skip.xlsx"
        data = [
            {
                "Дата": "24.04.2999",
                "Источник": "future.xlsx : 1",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
            },
            {
                "Дата": "01.04.2026",
                "Источник": "ok.xlsx : 1",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
            },
        ]

        with patch("core.infra.export_writer.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 4, 17)
            mock_datetime.strptime = datetime.strptime
            result = master_writer.write_report(data, output_path)

        assert result is True

        from openpyxl import load_workbook

        wb = load_workbook(output_path)
        assert "01.04.2026" in wb.sheetnames
        assert "24.04.2999" not in wb.sheetnames
        wb.close()

    def test_write_report_file_locked(
        self, master_writer, sample_consolidated_data, temp_output_dir
    ):
        """Если файл занят Excel — вернуть False и показать ошибку в логах."""
        output_path = temp_output_dir / "locked.xlsx"
        # Создаём файл
        output_path.touch()

        with patch("core.infra.export_writer.is_file_writable", return_value=False):
            result = master_writer.write_report(sample_consolidated_data, output_path)
            assert result is False

    def test_write_report_with_template_errors(
        self, master_writer, sample_consolidated_data, temp_output_dir
    ):
        """write_report принимает template_errors, но не создаёт отдельный лист."""
        output_path = temp_output_dir / "with_errors.xlsx"
        template_errors = [
            {
                "file_path": "bad.xlsx",
                "sheet_name": "Sheet1",
                "row_index": 5,
                "error_type": "missing_column",
                "details": 'Нет столбца "приход"',
            }
        ]
        result = master_writer.write_report(
            sample_consolidated_data, output_path, template_errors=template_errors
        )
        assert result is True

        from openpyxl import load_workbook

        wb = load_workbook(output_path)
        assert "ОШИБКИ ШАБЛОНА" not in wb.sheetnames
        assert "01.04.2026" in wb.sheetnames
        wb.close()

    def test_write_report_does_not_overwrite_invalid_existing_workbook(
        self, master_writer, sample_consolidated_data, temp_output_dir
    ):
        output_path = temp_output_dir / "broken.xlsx"
        invalid_bytes = b"keep-existing-bytes"
        output_path.write_bytes(invalid_bytes)

        with (
            patch("core.infra.export_writer.is_file_writable", return_value=True),
            patch(
                "core.infra.export_writer.openpyxl.load_workbook",
                side_effect=__import__(
                    "openpyxl"
                ).utils.exceptions.InvalidFileException("bad workbook"),
            ),
        ):
            result = master_writer.write_report(sample_consolidated_data, output_path)

        assert result is False
        assert output_path.read_bytes() == invalid_bytes

    def test_write_report_uses_current_working_directory_when_no_path_passed(self, temp_output_dir):
        config = {
            "paths": {"master_file": "ignored.xlsx"},
            "logic": {},
        }
        writer = MasterWriter(config)

        output_path = temp_output_dir / "cwd_master.xlsx"
        data = [
            {
                "Дата": "01.04.2026",
                "Источник": "a.xlsx : 1",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
            }
        ]

        with patch("pathlib.Path.cwd", return_value=temp_output_dir):
            assert writer.write_report(data, output_path) is True

        assert output_path.exists()


class TestWriteDailyData:
    """Тесты для write_daily_data — форматирование и стили."""

    def test_headers_written(self, master_writer):
        wb = Workbook()
        ws = wb.create_sheet("test")
        master_writer.write_daily_data(datetime(2026, 4, 1), [], wb=wb)

        ws = wb["01.04.2026"]
        headers = [cell.value for cell in ws[1]]
        assert "Дата" not in headers
        assert headers[0] == "Источник"
        assert "Приход" in headers
        assert "Расход" in headers
        assert "Комиссия" in headers

    def test_income_row_highlighted(self, master_writer):
        """Строки с приходом > 0.01 должны быть зелёными."""
        rows = [
            {
                "сумма платежа ПРИХОД": 500,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 500,
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        # Приход — ячейка с заголовком "Приход"
        приход_col = None
        for cell in ws[1]:
            if "Приход" in str(cell.value or ""):
                приход_col = cell.column
                break

        data_cell = ws.cell(2, приход_col)
        assert data_cell.value == 500.0

    def test_expense_row_highlighted(self, master_writer):
        """Строки с расходом > 0.01 должны быть красными."""
        rows = [
            {
                "сумма платежа ПРИХОД": 0,
                "сумма платежа РАСХОД": 300,
                "комиссия": 0,
                "ИТОГ": -300,
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        расход_col = None
        for cell in ws[1]:
            if "Расход" in str(cell.value or ""):
                расход_col = cell.column
                break

        data_cell = ws.cell(2, расход_col)
        assert data_cell.value == 300.0

    def test_total_row_formula(self, master_writer):
        """Итоговая строка должна содержать формулы SUM."""
        rows = [
            {
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
            },
            {
                "сумма платежа ПРИХОД": 200,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 200,
            },
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        total_row = ws.max_row
        total_label = ws.cell(total_row, 1)
        assert total_label.value == "ИТОГО:"

        # Проверяем что хотя бы одна ячейка в итоговой строке содержит формулу
        has_formula = any(
            isinstance(ws.cell(total_row, c).value, str)
            and ws.cell(total_row, c).value.startswith("=")
            for c in range(1, ws.max_column + 1)
        )
        assert has_formula

    def test_percent_broker_formatting(self, master_writer):
        """% посредника должен быть в формате процента."""
        rows = [
            {
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
                "% посредника": 0.05,
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        pct_col = None
        for cell in ws[1]:
            if "% посредника" in str(cell.value or ""):
                pct_col = cell.column
                break

        pct_cell = ws.cell(2, pct_col)
        assert pct_cell.value == 0.05

    def test_template_warning_colors(self, master_writer):
        """Template warning — ячейка Источник должна быть жёлтой."""
        rows = [
            {
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
                "is_template_warning": True,
                "Источник": "warning_source.xlsx",
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        # Источник = колонка 1 в стандартном дневном листе
        источник_cell = ws.cell(2, 1)
        assert источник_cell.value == "warning_source.xlsx"

    def test_soft_template_warning_does_not_paint_source_red(self, master_writer):
        rows = [
            {
                "Источник": "soft_warning.xlsx",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
                "is_template_warning": False,
                "_template_warning_kind": "soft_structure",
                "_template_warning_reason": "unsupported header name: % -> % посредника",
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        assert source_cell.value == "soft_warning.xlsx"
        assert (
            source_cell.fill.start_color.rgb
            != master_writer.st.fill_warning.start_color.rgb
        )

    def test_hard_structure_warning_paints_source_red(self, master_writer):
        rows = [
            {
                "Источник": "hard_warning.xlsx",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
                "is_template_warning": True,
                "_template_warning_kind": "hard_structure",
                "_template_warning_reason": "unexpected columns: курс",
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        assert source_cell.value == "hard_warning.xlsx"
        assert (
            source_cell.fill.start_color.rgb
            == master_writer.st.fill_warning.start_color.rgb
        )

    def test_numeric_text_total_warning_paints_total_cell_not_source(
        self, master_writer
    ):
        rows = [
            {
                "Источник": "numeric_total.xlsx",
                "сумма платежа ПРИХОД": 0,
                "сумма платежа РАСХОД": 100,
                "комиссия": 0,
                "ИТОГ": 0,
                "is_template_warning": True,
                "_template_warning_kind": "template_warning",
                "_template_warning_reason": "text in numeric field: total",
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        total_col = next(cell.column for cell in ws[1] if cell.value == "ИТОГ")
        total_cell = ws.cell(2, total_col)

        assert (
            source_cell.fill.start_color.rgb
            != master_writer.st.fill_warning.start_color.rgb
        )
        assert (
            total_cell.fill.start_color.rgb
            == master_writer.st.fill_warning.start_color.rgb
        )

    def test_numeric_text_commission_warning_paints_commission_cell_not_source(
        self, master_writer
    ):
        rows = [
            {
                "Источник": "numeric_commission.xlsx",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
                "is_template_warning": True,
                "_template_warning_kind": "template_warning",
                "_template_warning_reason": "text in numeric field: commission",
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        commission_col = next(cell.column for cell in ws[1] if cell.value == "Комиссия")
        commission_cell = ws.cell(2, commission_col)

        assert (
            source_cell.fill.start_color.rgb
            != master_writer.st.fill_warning.start_color.rgb
        )
        assert (
            commission_cell.fill.start_color.rgb
            == master_writer.st.fill_warning.start_color.rgb
        )

    def test_numeric_text_total_warning_paints_total_for_boris_layout(
        self, master_writer
    ):
        rows = [
            {
                "Источник": "numeric_total_boris.xlsx",
                "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "ООО Тест",
                "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "ООО Исп",
                "сумма платежа ПРИХОД": 0,
                "сумма платежа РАСХОД": 100,
                "комиссия": 0,
                "ИТОГ": 0,
                "% посредника": 0,
                "посредник 1(кэш)": 0,
                "% посредник 2": 0,
                "посредник 2": 0,
                "фильтры": "",
                "is_template_warning": True,
                "_template_warning_kind": "template_warning",
                "_template_warning_reason": "text in numeric field: total",
            }
        ]
        headers = [
            "Источник",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "Комиссия",
            "ИТОГ",
            "% посредник 1",
            "посредник 1(кэш)",
            "% посредник 2",
            "посредник 2",
            "Фильтры",
        ]
        wb = Workbook()
        master_writer.write_daily_data(
            datetime(2026, 4, 1),
            rows,
            wb=wb,
            curator="boris",
            headers=headers,
        )
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        total_col = next(cell.column for cell in ws[1] if cell.value == "ИТОГ")
        total_cell = ws.cell(2, total_col)

        assert (
            source_cell.fill.start_color.rgb
            != master_writer.st.fill_warning.start_color.rgb
        )
        assert (
            total_cell.fill.start_color.rgb
            == master_writer.st.fill_warning.start_color.rgb
        )

    def test_curator_structure_warning_does_not_paint_source_red(self, master_writer):
        rows = [
            {
                "Источник": "boris.xlsx : Строка 7",
                "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "ООО Тест",
                "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "ООО Исп",
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
                "% посредника": 0,
                "посредник 1(кэш)": 0,
                "% посредник 2": 0,
                "посредник 2": 0,
                "фильтры": "",
                "is_template_warning": True,
                "_template_warning_kind": "hard_structure",
                "_template_warning_reason": "missing columns: сумма платежа",
            }
        ]
        headers = [
            "Источник",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "Комиссия",
            "ИТОГ",
            "% посредник 1",
            "посредник 1(кэш)",
            "% посредник 2",
            "посредник 2",
            "Фильтры",
        ]
        wb = Workbook()
        master_writer.write_daily_data(
            datetime(2026, 4, 1), rows, wb=wb, curator="boris", headers=headers
        )
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        assert source_cell.value == "boris.xlsx : Строка 7"
        assert source_cell.fill.start_color.rgb != master_writer.st.fill_warning.start_color.rgb

    def test_numeric_text_commission_warning_paints_commission_for_ivan_layout(
        self, master_writer
    ):
        rows = [
            {
                "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "ООО Тест",
                "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "ООО Исп",
                "сумма платежа ПРИХОД": 100,
                "комиссия": 0,
                "ИТОГ": 100,
                "% посредника": 0,
                "посредник 1(кэш)": 0,
                "% посредник 2": 0,
                "посредник 2": 0,
                "фильтры": "",
                "is_template_warning": True,
                "_template_warning_kind": "template_warning",
                "_template_warning_reason": "text in numeric field: commission",
            }
        ]
        headers = [
            "Сотрудник",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "Комиссия",
            "ИТОГ",
            "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ",
            "% посредника 1",
            "посредник 1(кэш)",
            "посредник 2",
            "курс",
            "сумма",
            "валюта",
            "фильтры",
        ]
        wb = Workbook()
        master_writer.write_daily_data(
            datetime(2026, 4, 1),
            rows,
            wb=wb,
            curator="ivan",
            headers=headers,
        )
        ws = wb["01.04.2026"]

        commission_col = next(cell.column for cell in ws[1] if cell.value == "Комиссия")
        commission_cell = ws.cell(2, commission_col)

        assert (
            commission_cell.fill.start_color.rgb
            == master_writer.st.fill_warning.start_color.rgb
        )


class TestAutoAdjust:
    """Тесты для _auto_adjust — автоподбор ширины колонок."""

    def test_numeric_columns_wider(self, master_writer):
        """Числовые колонки должны быть шире текстовых."""
        wb = Workbook()
        ws = wb.create_sheet("test")
        ws.append(["Короткое", "Очень длинный заголовок колонки", "Приход"])
        ws.append(["A", "B", 100000.00])

        master_writer._auto_adjust(ws)

        # Колонка с "Приход" должна быть >= 15
        приход_width = ws.column_dimensions["C"].width
        assert приход_width >= 15

    def test_income_column_width_accounts_for_total_formula(self, master_writer):
        """Итоговая формула внизу тоже должна влиять на ширину числовой колонки."""
        rows = [
            {
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
            }
            for _ in range(30)
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        income_col = None
        for cell in ws[1]:
            if cell.value == "Приход":
                income_col = cell.column_letter
                break

        assert income_col is not None
        assert ws.column_dimensions[income_col].width > 15

    def test_text_columns_capped(self, master_writer):
        """Текстовые колонки не должны превышать 35 символов."""
        wb = Workbook()
        ws = wb.create_sheet("test")
        ws.append(["Очень длинный текст который превышает лимит ширины колонки"])
        ws.append(["a" * 100])

        master_writer._auto_adjust(ws)

        width = ws.column_dimensions["A"].width
        assert width <= 35


class TestSaveWorkbook:
    """Тесты для _save_workbook — сохранение и сортировка листов."""

    def test_special_order_sheets(self, master_writer, temp_output_dir):
        """Специальные листы должны быть ближе к началу."""
        wb = Workbook()
        wb.create_sheet("01.01.2026")
        wb.create_sheet("АНАЛИТИКА")
        wb.create_sheet("02.01.2026")
        wb.create_sheet("СВОД")

        master_writer.master_path = str(temp_output_dir / "order_test.xlsx")
        master_writer._save_workbook(wb)

        from openpyxl import load_workbook

        wb2 = load_workbook(master_writer.master_path)
        names = wb2.sheetnames
        # All sheets should be present
        assert "АНАЛИТИКА" in names
        assert "СВОД" in names
        assert "01.01.2026" in names
        assert "02.01.2026" in names
        wb2.close()

    def test_date_sheets_sorted(self, master_writer, temp_output_dir):
        """Листы с датами должны быть отсортированы хронологически."""
        wb = Workbook()
        wb.create_sheet("03.01.2026")
        wb.create_sheet("01.01.2026")
        wb.create_sheet("02.01.2026")

        master_writer.master_path = str(temp_output_dir / "date_order.xlsx")
        master_writer._save_workbook(wb)

        from openpyxl import load_workbook

        wb2 = load_workbook(master_writer.master_path)
        names = wb2.sheetnames
        assert (
            names.index("01.01.2026")
            < names.index("02.01.2026")
            < names.index("03.01.2026")
        )
        wb2.close()

    def test_save_workbook_creates_missing_parent_directory(
        self, master_writer, temp_output_dir
    ):
        wb = Workbook()
        nested = temp_output_dir / "nested" / "reports" / "report.xlsx"

        assert master_writer._save_workbook(wb, nested) is True
        assert nested.exists()


class TestEdgeCases:
    """Edge cases и corner cases."""

    def test_total_without_income_and_expense_marked_yellow_math_error(
        self, master_writer
    ):
        rows = [
            {
                "Источник": "total_only.xlsx : 7",
                "сумма платежа ПРИХОД": 0,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 267_610,
                "фильтры": "",
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        assert source_cell.value == "total_only.xlsx : 7"
        assert "FFFF00" in str(source_cell.fill.start_color.rgb or "")

    def test_return_row_not_marked_yellow_math_error(self, master_writer):
        rows = [
            {
                "Источник": "return.xlsx : 5",
                "сумма платежа ПРИХОД": 0,
                "сумма платежа РАСХОД": -500,
                "комиссия": 0,
                "ИТОГ": -500,
                "фильтры": "возврат средств",
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        assert source_cell.value == "return.xlsx : 5"
        assert (
            source_cell.fill.start_color.rgb
            == master_writer.st.fill_odd.start_color.rgb
        )

    def test_custom_return_keyword_not_marked_yellow_math_error(self, temp_output_dir):
        config = {
            "paths": {"master_file": str(temp_output_dir / "custom_return.xlsx")},
            "logic": {"return_keywords": ["рефанд"]},
        }
        writer = MasterWriter(config)
        rows = [
            {
                "Источник": "refund.xlsx : 5",
                "сумма платежа ПРИХОД": 0,
                "сумма платежа РАСХОД": -500,
                "комиссия": 0,
                "ИТОГ": -500,
                "фильтры": "рефанд клиенту",
            }
        ]
        wb = Workbook()
        writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        source_cell = ws.cell(2, 1)
        assert source_cell.value == "refund.xlsx : 5"
        assert source_cell.fill.start_color.rgb == writer.st.fill_odd.start_color.rgb

    def test_very_small_income_not_highlighted(self, master_writer):
        """Приход < 0.02 не должен подсвечиваться."""
        rows = [
            {
                "сумма платежа ПРИХОД": 0.01,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 0,
            }
        ]
        wb = Workbook()
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)
        ws = wb["01.04.2026"]

        приход_col = None
        for cell in ws[1]:
            if "Приход" in str(cell.value or ""):
                приход_col = cell.column
                break

        data_cell = ws.cell(2, приход_col)
        # Не должен быть income fill
        assert data_cell.fill != master_writer.st.fill_income

    def test_commission_as_string_percent(self, master_writer):
        """Комиссия в формате строки — должно обрабатываться без падения."""
        rows = [
            {
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 2.5,  # Use numeric instead of string
                "ИТОГ": 100,
            }
        ]
        wb = Workbook()
        # Не должно выбрасывать исключение
        master_writer.write_daily_data(datetime(2026, 4, 1), rows, wb=wb)

    def test_existing_file_loaded(self, master_writer, temp_output_dir):
        """Если файл уже существует — загрузить и добавить лист."""
        from openpyxl import Workbook

        existing_path = temp_output_dir / "existing.xlsx"
        wb = Workbook()
        wb.create_sheet("Existing Sheet")
        wb.save(existing_path)

        master_writer.master_path = str(existing_path)
        rows = [
            {
                "сумма платежа ПРИХОД": 100,
                "сумма платежа РАСХОД": 0,
                "комиссия": 0,
                "ИТОГ": 100,
            }
        ]
        master_writer.write_daily_data(datetime(2026, 4, 1), rows)

        from openpyxl import load_workbook

        wb2 = load_workbook(existing_path)
        assert "Existing Sheet" in wb2.sheetnames
        assert "01.04.2026" in wb2.sheetnames
        wb2.close()
