import openpyxl
from pathlib import Path

def verify_report():
    file_path = Path("Master_Report.xlsx")
    if not file_path.exists():
        print("Файл Master_Report.xlsx не найден.")
        return

    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet_name = "23.03.2026"
    
    if sheet_name not in wb.sheetnames:
        print(f"Лист {sheet_name} не найден. Доступные листы: {wb.sheetnames}")
        return
        
    ws = wb[sheet_name]
    print(f"--- НАЧАЛО ПРОВЕРКИ ЛИСТА {sheet_name} ---")
    
    # Индексы колонок (1-based)
    cols = {'source': 2, 'income': 5, 'expense': 6, 'commission': 7, 'total': 8}
    
    # Ожидаемые цвета (из ExportStyles)
    COLOR_WARNING = "FFFF0000" # Красный
    COLOR_MATH_ERR = "00FFFF00" # Желтый
    COLOR_INCOME = "00C6EFCE" # Зеленоватый
    COLOR_EXPENSE = "00FFC7CE" # Красноватый

    error_count = 0
    warning_count = 0
    math_err_count = 0

    for r_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row - 1), start=2): # исключаем строку "ИТОГО"
        source = row[cols['source']-1].value
        if not source or source == "ИТОГО:": continue
        
        income = float(row[cols['income']-1].value or 0)
        expense = float(row[cols['expense']-1].value or 0)
        commission = float(row[cols['commission']-1].value or 0)
        total = float(row[cols['total']-1].value or 0)
        
        # Получаем цвета ячеек
        row_color = row[0].fill.start_color.rgb if row[0].fill and row[0].fill.start_color else "None"
        source_color = row[cols['source']-1].fill.start_color.rgb if row[cols['source']-1].fill and row[cols['source']-1].fill.start_color else "None"
        income_color = row[cols['income']-1].fill.start_color.rgb if row[cols['income']-1].fill and row[cols['income']-1].fill.start_color else "None"
        
        # Логика проверки
        amt = income if income != 0 else expense
        is_math_err = (commission == 0 and abs(amt) > 0.02 and (abs(total) < 0.02 or abs(amt - total) > 0.02))
        
        # Анализ цвета строки
        actual_row_status = "ОК (Обычный)"
        if source_color == COLOR_WARNING or row_color == COLOR_WARNING:
            actual_row_status = "🔴 ОШИБКА ШАБЛОНА (Розовый)"
            warning_count += 1
        elif row_color == COLOR_MATH_ERR:
            actual_row_status = "🟡 ОШИБКА МАТЕМАТИКИ (Желтый)"
            math_err_count += 1
            
        # Проверка несоответствий
        issues = []
        if is_math_err and row_color != COLOR_MATH_ERR and source_color != COLOR_WARNING:
            issues.append(f"ОЖИДАЛСЯ ЖЕЛТЫЙ (Комиссия: {commission}, Приход/Расход: {amt}, Итог: {total}), но цвет: {row_color}")
        
        if "Иван" in str(source) and source_color != COLOR_WARNING:
            issues.append(f"Подозрение на Ивана: строка не красная! Цвет: {source_color}")
            
        if income > 0.01 and income_color != COLOR_INCOME and source_color != COLOR_WARNING and row_color != COLOR_MATH_ERR:
             issues.append(f"Приход > 0, но цвет не зеленый! Цвет: {income_color}")

        if issues or actual_row_status != "ОК (Обычный)":
            print(f"Строка {r_idx} | Источник: {source[:15]}... | Статус: {actual_row_status}")
            if issues:
                for issue in issues:
                    print(f"  -> ❌ НАЙДЕНА ПРОБЛЕМА: {issue}")
                    error_count += 1

    print("--- ИТОГИ ПРОВЕРКИ ---")
    print(f"Найдено ошибок шаблона (Розовый): {warning_count}")
    print(f"Найдено математических ошибок (Желтый): {math_err_count}")
    if error_count == 0:
        print("✅ ВСЕ ЦВЕТА И ДАННЫЕ СОВПАДАЮТ С ЛОГИКОЙ!")
    else:
        print(f"❌ НАЙДЕНО {error_count} НЕСООТВЕТСТВИЙ ЦВЕТА/ЛОГИКИ!")

if __name__ == "__main__":
    verify_report()