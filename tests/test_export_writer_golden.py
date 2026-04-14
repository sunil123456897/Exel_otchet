import os
import pytest
import pandas as pd
import openpyxl
from datetime import datetime
from core.infra.export_writer import MasterWriter

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
GOLDEN_FILE = os.path.join(GOLDEN_DIR, "reference_output.xlsx")


def generate_test_data():
    return [
        {
            "Дата": "01.01.2026",
            "Источник": "Source A",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "Client 1",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Bank 1",
            "сумма платежа ПРИХОД": 1000.00,
            "сумма платежа РАСХОД": 0.00,
            "комиссия": 5.00,
            "ИТОГ": 950.00,
            "% посредника": 0.00,
            "посредник 1(кэш)": 0.00,
            "посредник 2": 0.00,
            "фильтры": "test filter",
            "is_template_warning": False,
        },
        {
            "Дата": "01.01.2026",
            "Источник": "Source B",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "Client 2",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Bank 2",
            "сумма платежа ПРИХОД": 0.00,
            "сумма платежа РАСХОД": 500.00,
            "комиссия": 0.00,
            "ИТОГ": 500.00,
            "% посредника": 0.00,
            "посредник 1(кэш)": 0.00,
            "посредник 2": 0.00,
            "фильтры": "test filter 2",
            "is_template_warning": True,
        },
        {
            "Дата": "02.01.2026",
            "Источник": "Source C",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "Client 3",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Bank 3",
            "сумма платежа ПРИХОД": 2000.00,
            "сумма платежа РАСХОД": 0.00,
            "комиссия": 0.00,
            "ИТОГ": 1000.00,  # Math error (2000 != 1000)
            "% посредника": 0.00,
            "посредник 1(кэш)": 0.00,
            "посредник 2": 0.00,
            "фильтры": "math error case",
            "is_template_warning": False,
        },
    ]


def compare_excel_files(file1, file2):
    wb1 = openpyxl.load_workbook(file1)
    wb2 = openpyxl.load_workbook(file2)

    assert wb1.sheetnames == wb2.sheetnames

    for sheet_name in wb1.sheetnames:
        df1 = pd.read_excel(file1, sheet_name=sheet_name)
        df2 = pd.read_excel(file2, sheet_name=sheet_name)

        # Compare dataframes (ignoring index)
        pd.testing.assert_frame_equal(df1, df2)

        # Compare some styles (e.g., yellow fill for math error)
        ws1 = wb1[sheet_name]
        ws2 = wb2[sheet_name]

        for row1, row2 in zip(ws1.iter_rows(), ws2.iter_rows()):
            for cell1, cell2 in zip(row1, row2):
                # Compare fill color if it's yellow (math error)
                if (
                    cell1.fill.fgColor.rgb == "00FFFF00"
                    or cell1.fill.fgColor.rgb == "FFFF00"
                ):
                    assert cell2.fill.fgColor.rgb in ["00FFFF00", "FFFF00"]
                elif (
                    cell2.fill.fgColor.rgb == "00FFFF00"
                    or cell2.fill.fgColor.rgb == "FFFF00"
                ):
                    assert cell1.fill.fgColor.rgb in ["00FFFF00", "FFFF00"]


def test_export_writer_golden(tmp_path):
    data = generate_test_data()
    output_file = tmp_path / "test_output.xlsx"

    config = {"paths": {"master_file": str(output_file)}}
    writer = MasterWriter(config)

    # write_report takes data and path
    success = writer.write_report(data, output_file)
    assert success
    assert output_file.exists()

    assert os.path.exists(GOLDEN_FILE), f"Missing golden file: {GOLDEN_FILE}"

    compare_excel_files(output_file, GOLDEN_FILE)
