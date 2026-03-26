# -*- coding: utf-8 -*-
"""
Скрипт для сравнения двух Excel-отчетов (старая vs новая версия)
Использование: python compare_reports.py <старый_файл.xlsx> <новый_файл.xlsx>
"""

import pandas as pd
import sys
import os


def compare_excel_files(old_file, new_file):
    """Сравнивает два отчета Excel"""
    try:
        xl_old = pd.ExcelFile(old_file)
        xl_new = pd.ExcelFile(new_file)
    except Exception as e:
        print(f"[ERR] Ошибка открытия файлов: {e}")
        return False
    
    print("="*70)
    print(f"СРАВНЕНИЕ ОТЧЕТОВ")
    print("="*70)
    print(f"Старый файл: {old_file}")
    print(f"Новый файл:  {new_file}")
    print()
    
    # Сравниваем листы (кроме ДАШБОРД и ВСЕ ОПЕРАЦИИ)
    sheets_old = set(xl_old.sheet_names) - {'ДАШБОРД', 'ВСЕ ОПЕРАЦИИ'}
    sheets_new = set(xl_new.sheet_names) - {'ДАШБОРД', 'ВСЕ ОПЕРАЦИИ'}
    
    print(f"Листов в старом файле: {len(sheets_old)}")
    print(f"Листов в новом файле:  {len(sheets_new)}")
    print()
    
    if sheets_old != sheets_new:
        print(f"⚠️ ВНИМАНИЕ: Разные наборы листов!")
        only_old = sheets_old - sheets_new
        only_new = sheets_new - sheets_old
        if only_old:
            print(f"   Только в старом: {only_old}")
        if only_new:
            print(f"   Только в новом:  {only_new}")
        print()
    
    all_match = True
    total_rows_old = 0
    total_rows_new = 0
    
    for sheet in sorted(sheets_old & sheets_new):  # Пересечение листов
        try:
            df_old = pd.read_excel(xl_old, sheet_name=sheet)
            df_new = pd.read_excel(xl_new, sheet_name=sheet)
            
            # Удаляем служебные колонки перед сравнением
            for col in ['_summary_flag']:
                if col in df_old.columns:
                    df_old = df_old.drop(columns=[col])
                if col in df_new.columns:
                    df_new = df_new.drop(columns=[col])
            
            rows_old = len(df_old)
            rows_new = len(df_new)
            total_rows_old += rows_old
            total_rows_new += rows_new
            
            # Сравниваем количество строк
            if rows_old != rows_new:
                print(f"[!] Лист '{sheet}': разное количество строк ({rows_old} vs {rows_new})")
                all_match = False
                continue
            
            # Сравниваем данные
            try:
                # Сравниваем только числовые колонки для гибкости
                numeric_cols = df_old.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    pd.testing.assert_frame_equal(
                        df_old[numeric_cols], 
                        df_new[numeric_cols],
                        check_exact=False,
                        rtol=1e-5
                    )
                # FIXED: 11
                str_cols = df_old.select_dtypes(include=['object']).columns
                if len(str_cols) > 0:
                    for col in str_cols:
                        if not df_old[col].fillna('').equals(df_new[col].fillna('')):
                            print(f"[!] Лист '{sheet}', колонка '{col}': текст отличается")
                            all_match = False
                print(f"[OK] Лист '{sheet}': ИДЕНТИЧЕН ({rows_old} строк)")
            except AssertionError as e:
                print(f"[!] Лист '{sheet}': ЕСТЬ РАЗЛИЧИЯ ({rows_old} строк)")
                # Показываем первое различие
                error_msg = str(e)
                if len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                print(f"   Пример: {error_msg}")
                all_match = False
                
        except Exception as e:
            print(f"[ERR] Лист '{sheet}': ОШИБКА - {e}")
            all_match = False
    
    print()
    print("="*70)
    print("ИТОГО:")
    print(f"  Общее количество строк:")
    print(f"    Старый файл: {total_rows_old}")
    print(f"    Новый файл:  {total_rows_new}")
    print()
    
    if all_match:
        print("[OK] РЕЗУЛЬТАТ: Файлы ИДЕНТИЧНЫ")
        print("="*70)
        return True
    else:
        print("[!] РЕЗУЛЬТАТ: ЕСТЬ РАЗЛИЧИЯ (требуется проверка)")
        print("="*70)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Сравнение двух Excel-отчетов")
        print()
        print("Использование:")
        print(f"  python {sys.argv[0]} <старый_файл.xlsx> <новый_файл.xlsx>")
        print()
        print("Пример:")
        print(f'  python {sys.argv[0]} "РЕЕСТР_2025-10_ТОЧНЫЙ.xlsx" "РЕЕСТР_2025-10_ТОЧНЫЙ_новый.xlsx"')
        sys.exit(1)
    
    old_file = sys.argv[1]
    new_file = sys.argv[2]
    
    # Проверяем существование файлов
    if not os.path.exists(old_file):
        print(f"[ERR] Файл не найден: {old_file}")
        sys.exit(1)
    
    if not os.path.exists(new_file):
        print(f"[ERR] Файл не найден: {new_file}")
        sys.exit(1)
    
    match = compare_excel_files(old_file, new_file)
    sys.exit(0 if match else 1)
