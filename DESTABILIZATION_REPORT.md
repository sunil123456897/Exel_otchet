# DESTABILIZATION_REPORT.md

## 1. Silent Data Loss on Malformed Numerics
- **Severity:** Critical
- **Reproduction Steps:** 
  1. Create an Excel file with 'NaN', 'NULL', or 'Zero' in the 'СУММА ПЛАТЕЖА' column.
  2. Run consolidation.
- **Observed Behavior:** The row is silently dropped. `to_decimal` converts the value to `0.00`, and `LogicService` filters out rows where both amount and total are zero. No error is reported to the user.
- **Architectural Weakness Root Cause:** Lack of strict type validation during ingestion. The system treats "failed to parse" and "actual zero" as the same state.

## 2. Configuration Schema Fragility
- **Severity:** Major
- **Reproduction Steps:** 
  1. Move the `markers` key from `sh1` to the root or `paths` in `config.yaml`.
  2. Start the application and refresh status.
- **Observed Behavior:** The app reports "НЕТ ДАННЫХ" or "НЕТ ФАЙЛА" (due to column mapping failure) without indicating that the configuration structure is invalid.
- **Architectural Weakness Root Cause:** `Bootstrap.setup` hardcodes the expected config path (`cfg.get('sh1', {})...`) instead of using a schema validator or providing defaults for missing keys.

## 3. Math Error Highlighting Bypass
- **Severity:** Minor
- **Reproduction Steps:** 
  1. Create a row where `Amount = 100`, `Total = 50`, and `Commission = 1`.
- **Observed Behavior:** No yellow highlight (`is_math_err`). The logic `(c_val == 0 and abs(amt) > 0.02 and ...)` specifically requires commission to be exactly zero to trigger a math warning.
- **Architectural Weakness Root Cause:** Overly restrictive conditional check for `is_math_err` in `MasterWriter`. It assumes that if a commission exists, any discrepancy is intended, which is an edge-case vulnerability.

## 4. Potential GUI Deadlock on Heavy Logging
- **Severity:** Major
- **Reproduction Steps:** 
  1. Process a directory with 100+ files where each file has dozens of "Template Warnings".
- **Observed Behavior:** GUI becomes unresponsive.
- **Architectural Weakness Root Cause:** `ui_log_panel.py` (via `setup_gui_logging`) and `refresh_status` push every log entry to the main thread via `root.after`. High-frequency logging saturates the Tkinter event loop.

## 5. File Lock Race Condition
- **Severity:** Major
- **Reproduction Steps:** 
  1. Start consolidation.
  2. While the "Saving..." progress is active, manually open the target `Master_Report.xlsx` and keep it open.
- **Observed Behavior:** `os.replace` fails. While a `messagebox` appears, the session state in the database is already marked as processed, potentially leading to desync if the user clicks "OK" without closing the file.
- **Architectural Weakness Root Cause:** The `_save_workbook` method in `MasterWriter` handles the error at the very end of the process rather than checking for file availability/lock at the start of the task.

## 6. Temporal Attack: Feb 29 / Invalid Date Black Hole
- **Severity:** Major
- **Reproduction Steps:** 
  1. Create an Excel sheet named "29.02".
  2. Run the application in a non-leap year (e.g., 2026).
- **Observed Behavior:** All rows in the sheet are silently dropped from the final report. The ingestion engine fails to parse the date and returns `None`, which `MasterWriter` then ignores without any warning or "Unknown Date" fallback.
- **Architectural Weakness Root Cause:** Lack of robust date parsing and a strict "valid date or skip" policy in `MasterWriter.write_report`.

## 7. Temporal Attack: Annual Sheet Overwrite (Data Collision)
- **Severity:** Critical
- **Reproduction Steps:** 
  1. Consolidate data for "01.12.2025".
  2. Consolidate data for "01.12.2026" into the same master file.
- **Observed Behavior:** The sheet "01.12" is deleted and recreated for 2026, permanently erasing the 2025 data from the report.
- **Architectural Weakness Root Cause:** The sheet naming schema (`%d.%m`) lacks a year component, making it impossible to store multi-year data in a single file.

## 8. Memory Exhaustion: XLSX Row Load Bomb
- **Severity:** Major
- **Reproduction Steps:** 
  1. Create an Excel file with 1,000,000 rows (even empty rows that have been touched/formatted).
- **Observed Behavior:** The application crashes with a `MemoryError` (OOM). 
- **Architectural Weakness Root Cause:** `XlsxReader.read` uses `list(ws.iter_rows(values_only=True))`, forcing the entire spreadsheet content into RAM instead of utilizing a memory-efficient generator/streaming approach.

## 9. Persistence: Transaction Integrity Failure
- **Severity:** Major
- **Reproduction Steps:** 
  1. Trigger a large consolidation.
  2. Kill the process (or simulate power loss) during the `save_staging_data` operation.
- **Observed Behavior:** Staging table may contain partial data sets from a single file, leading to incorrect consolidation totals on resume/next run.
- **Architectural Weakness Root Cause:** Inconsistent use of explicit transaction boundaries. While `sqlite3` uses implicit transactions with `with`, the retry logic in `SQLiteManager._execute_with_retry` does not explicitly manage rollbacks between attempts.

## 10. Path: MAX_PATH Buffer Overflow on Save
- **Severity:** Major (Windows-specific)
- **Reproduction Steps:** 
  1. Set the 'master_file' path to a location that is exactly 255-258 characters long.
- **Observed Behavior:** The final "Save" operation fails. `MasterWriter` attempts to save to `master_path + ".tmp"`, which exceeds the 260-character Windows MAX_PATH limit.
- **Architectural Weakness Root Cause:** Unsafe temporary filename construction (`+ ".tmp"`) without verifying final path length or using the `\\?\` long-path prefix.
