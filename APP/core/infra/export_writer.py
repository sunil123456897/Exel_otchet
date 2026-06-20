import os
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from pathlib import Path
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill
from core.domain import IExporter
from core.domain.utils_helpers import to_decimal
from core.infra import is_file_writable
from core.infra.excel_backup import backup_existing_excel_output, resolve_excel_backup_keep
from core.infra.export_formatting import ExcelStyles
from core.infra.export_formatting import (
    detect_header_columns,
    apply_cell_styling,
    build_total_row,
)
from core.infra.excel_hyperlinks import apply_cell_hyperlink

logger = logging.getLogger(__name__)


class ExportPreflightError(RuntimeError):
    pass


def _safe_text(value: Any) -> Any:
    """Mitigate Excel formula injection (CWE-1236).

    Prepends a single quote to any string that starts with ``=``, ``+``,
    ``-`` or ``@`` so Excel treats it as text instead of evaluating it as
    a formula. Non-string values (Decimal, int, float, None) pass through
    unchanged. Mirrors the existing ``_excel_safe_text`` helpers in
    ``reconciliation/_utils.py`` and ``rsch/_format.py``.
    """
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped and stripped[0] in ("=", "+", "-", "@"):
            return "'" + value
    return value


def preflight_output_path(path: Path) -> None:
    output_path = Path(path)
    if not output_path.parent.exists():
        raise ExportPreflightError(f"Output directory does not exist: {output_path.parent}")
    if not os.access(output_path.parent, os.W_OK):
        raise ExportPreflightError(f"Output directory is not writable: {output_path.parent}")

DEFAULT_HEADERS = [
    "Источник",
    "ЗАКАЗЧИК",
    "ИСПОЛНИТЕЛЬ",
    "Приход",
    "Расход",
    "Комиссия",
    "ИТОГ",
    "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ",
    "% посредника",
    "посредник 1(кэш)",
    "посредник 2",
    "Фильтры",
]


class MasterWriter(IExporter):
    def __init__(self, config: Dict[str, Any], config_path: str = ""):
        self.config = config
        self.config_dir = Path(config_path).parent if config_path else Path.cwd()
        logic_cfg = config.get("logic", {}) if isinstance(config, dict) else {}
        self.return_keywords = [
            str(v).lower() for v in logic_cfg.get("return_keywords", ["возврат"])
        ]
        p = (
            config.get("paths", {})
            if isinstance(config, dict)
            else getattr(config, "paths", {})
        )
        master = p.get("master_file", "Master_Report.xlsx")
        master_path = Path(master)
        if not master_path.is_absolute():
            master_path = self.config_dir / master_path
        self.master_path = str(master_path)
        self.st = ExcelStyles()

    def _apply_header_style(self, ws, row_idx=1):
        for cell in ws[row_idx]:
            cell.fill, cell.font, cell.alignment, cell.border = (
                self.st.fill_header,
                self.st.font_header,
                self.st.align_center,
                self.st.border_thin,
            )

    def _get_workbook(self, path=None):
        path_abs = os.path.abspath(path or self.master_path)
        if os.path.exists(path_abs):
            try:
                return openpyxl.load_workbook(path_abs)
            except (OSError, openpyxl.utils.exceptions.InvalidFileException) as e:
                logger.error("Failed to open workbook %s: %s", path_abs, e)
                return None
        wb = openpyxl.Workbook()
        if "Sheet" in wb.sheetnames:
            wb.remove(wb["Sheet"])
        return wb

    def _save_workbook(self, wb, path=None) -> bool:
        try:
            return self._save_workbook_inner(wb, path)
        finally:
            try:
                wb.close()
            except Exception:
                pass

    def _save_workbook_inner(self, wb, path=None) -> bool:
        SPECIAL_ORDER = ["ВСЕ ОПЕРАЦИИ", "ДАШБОРД", "АНАЛИТИКА", "СВОД"]

        def key(n):
            if "." in n:
                try:
                    p = n.split(".")
                    if len(p) == 3:
                        return (0, int(p[2]), int(p[1]), int(p[0]))
                    return (0, 9999, int(p[1]), int(p[0]))
                except (ValueError, IndexError):
                    return (0, 9999, 99, 99)
            return (1, 0, 0, SPECIAL_ORDER.index(n) if n in SPECIAL_ORDER else 99)

        if not wb.sheetnames:
            wb.create_sheet("СВОД")

        for i, n in enumerate(sorted(wb.sheetnames, key=key)):
            curr = wb.sheetnames.index(n)
            offset = i - curr
            if offset != 0:
                wb.move_sheet(n, offset=offset)

        path_abs = os.path.abspath(path or self.master_path)
        try:
            Path(path_abs).parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            logger.error(
                f"Не удалось создать папку для отчёта (нет доступа): {path_abs} | {e}"
            )
            return False
        preflight_output_path(Path(path_abs))
        if os.path.exists(path_abs):
            backup_cfg = self.config.get("backup", {}) if isinstance(self.config, dict) else {}
            paths_cfg = self.config.get("paths", {}) if isinstance(self.config, dict) else {}
            backup_root = paths_cfg.get("archive_dir")
            if backup_root:
                backup_root = Path(backup_root)
                if not backup_root.is_absolute():
                    backup_root = self.config_dir / backup_root
            backup_keep = resolve_excel_backup_keep(backup_cfg.get("excel_keep"))
            try:
                backup_existing_excel_output(path_abs, backup_root, keep=backup_keep)
            except Exception as e:
                logger.error("Could not create backup before overwriting %s: %s", path_abs, e)
                return False
        tmp = path_abs + ".tmp"

        if os.name == "nt" and len(tmp) > 250:
            tmp = "\\\\?\\" + tmp
            path_abs = "\\\\?\\" + path_abs

        try:
            wb.save(tmp)
            if os.path.exists(path_abs):
                try:
                    os.replace(tmp, path_abs)
                except PermissionError:
                    # Do NOT delete the tmp file — the user can rename it
                    # manually after closing Excel.  Previously the tmp was
                    # deleted here, destroying a successfully generated
                    # report and forcing a full re-run.
                    logger.error(
                        "Файл занят: Закройте '%s' в Excel! "
                        "Временный файл сохранён: %s",
                        path or self.master_path, tmp,
                    )
                    return False
            else:
                os.rename(tmp, path_abs)
            return True
        except Exception as e:
            logger.error(f"Save failed: {e}")
            # Preserve tmp on error too — do not remove it in the finally
            # block unless the rename succeeded.
            return False

    def _auto_adjust(self, ws):
        numeric_keywords = [
            "приход",
            "расход",
            "комиссия",
            "итог",
            "посредник",
            "транзит",
            "сумма",
        ]
        wide_text_keywords = ["заказчик", "исполнитель", "источник", "комментар"]
        compact_text_min_widths = {
            "статус": 14,
            "фильтры": 16,
        }
        for i in range(1, ws.max_column + 1):
            max_len = 0
            for row in ws.iter_rows(
                min_row=1, max_row=min(20, ws.max_row), values_only=True
            ):
                if row[i - 1]:
                    max_len = max(max_len, len(str(row[i - 1])))
            if ws.max_row > 20:
                tail_value = ws.cell(ws.max_row, i).value
                if tail_value:
                    max_len = max(max_len, len(str(tail_value)))
            let = get_column_letter(i)
            header = str(ws.cell(1, i).value or "").lower()
            if any(kw in header for kw in numeric_keywords):
                ws.column_dimensions[let].width = max((max_len * 1.1) + 6, 18)
            elif any(kw in header for kw in wide_text_keywords):
                ws.column_dimensions[let].width = min(max(max_len + 4, 18), 60)
            else:
                min_width = max(
                    [width for key, width in compact_text_min_widths.items() if key in header],
                    default=10,
                )
                ws.column_dimensions[let].width = min(max(max_len + 4, min_width), 60)

    def _append_data_rows(self, ws, date, rows, curator=None):
        from collections import OrderedDict

        warning_rows = {}
        row_to_data_idx = {}

        def _safe_decimal(v: Any, default: Decimal = Decimal("0")) -> Decimal:
            """Coerce a financial cell value to Decimal without float loss.

            The consolidated rows already carry Decimal values (built by
            LogicService._build_result_row); float() here only hid that
            fact and risked precision loss for >15-significant-digit
            sums. Decimal passthrough is the honest contract — openpyxl
            writes it straight into the cell's numeric value. Garbage
            cells fall back to the domain parser and then to the default.
            """
            if v is None or v == "":
                return Decimal(default)
            if isinstance(v, Decimal):
                return v
            if isinstance(v, bool):
                # bool is an int subclass — guard before the int/float branch.
                return Decimal("1") if v else Decimal("0")
            if isinstance(v, (int, float)):
                return Decimal(str(v))
            try:
                return to_decimal(v)
            except Exception:
                logger.warning(
                    "Could not convert %r to Decimal; defaulting to 0. Sheet=%s, row=%s",
                    v,
                    ws.title,
                    ws.max_row + 1,
                )
                return Decimal(default)

        def _get_employee(r):
            if curator == "ivan":
                return str(r.get("Сотрудник", r.get("Источник", ""))).strip()
            return str(r.get("Источник", "")).strip()

        def _get_row_values(r):
            if curator == "boris":
                return [_safe_text(v) for v in [
                    r.get("Источник", ""),
                    r.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", ""),
                    r.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", ""),
                    _safe_decimal(r.get("сумма платежа ПРИХОД", 0)),
                    _safe_decimal(r.get("сумма платежа РАСХОД", 0)),
                    _safe_decimal(r.get("комиссия", 0)),
                    _safe_decimal(r.get("ИТОГ", 0)),
                    _safe_decimal(r.get("% посредника", 0)),
                    _safe_decimal(r.get("посредник 1(кэш)", 0)),
                    _safe_decimal(r.get("% посредник 2", 0)),
                    _safe_decimal(r.get("посредник 2", 0)),
                    r.get("фильтры", ""),
                ]]
            elif curator == "ivan":
                return [_safe_text(v) for v in [
                    r.get("Сотрудник", r.get("Источник", "")),
                    r.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", ""),
                    r.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", ""),
                    _safe_decimal(r.get("сумма платежа ПРИХОД", 0)),
                    _safe_decimal(r.get("сумма платежа РАСХОД", 0)),
                    _safe_decimal(r.get("комиссия", 0)),
                    _safe_decimal(r.get("ИТОГ", 0)),
                    _safe_decimal(r.get("ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ", 0)),
                    _safe_decimal(r.get("% посредника", 0)),
                    _safe_decimal(r.get("посредник 1(кэш)", 0)),
                    _safe_decimal(r.get("посредник 2", 0)),
                    _safe_decimal(r.get("курс", 0)),
                    _safe_decimal(r.get("сумма", 0)),
                    r.get("валюта", ""),
                    r.get("фильтры", ""),
                ]]
            else:
                return [_safe_text(v) for v in [
                    r.get("Источник", ""),
                    r.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", ""),
                    r.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", ""),
                    _safe_decimal(r.get("сумма платежа ПРИХОД", 0)),
                    _safe_decimal(r.get("сумма платежа РАСХОД", 0)),
                    _safe_decimal(r.get("комиссия", 0)),
                    _safe_decimal(r.get("ИТОГ", 0)),
                    _safe_decimal(r.get("ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ", 0)),
                    _safe_decimal(r.get("% посредника", 0)),
                    _safe_decimal(r.get("посредник 1(кэш)", 0)),
                    _safe_decimal(r.get("посредник 2", 0)),
                    r.get("фильтры", ""),
                ]]

        if curator in ("boris", "ivan"):
            grouped = OrderedDict()
            for r in rows:
                emp = _get_employee(r)
                grouped.setdefault(emp, []).append(r)

            for emp_name, emp_rows in grouped.items():
                header_row_num = ws.max_row + 1
                ws.append([_safe_text(emp_name)] + [None] * (ws.max_column - 1))
                header_cell = ws.cell(header_row_num, 1)
                header_cell.font = self.st.font_bold
                header_cell.fill = PatternFill("solid", fgColor="D9E1F2")
                from openpyxl.styles import Border as _Border, Side as _Side
                med = _Side(style="medium", color="000000")
                header_cell.border = _Border(left=med, right=med, top=med, bottom=med)
                for c in range(2, ws.max_column + 1):
                    ws.cell(header_row_num, c).fill = PatternFill("solid", fgColor="D9E1F2")
                    ws.cell(header_row_num, c).border = _Border(left=med, right=med, top=med, bottom=med)

                for r in emp_rows:
                    warning_kind = r.get("_template_warning_kind")
                    suppress_structure_warning = curator in {"boris", "ivan"} and warning_kind in {
                        "hard_structure",
                        "soft_structure",
                    }
                    if r.get("is_template_warning") and not suppress_structure_warning:
                        warning_rows[ws.max_row + 1] = {
                            "kind": warning_kind,
                            "reason": r.get("_template_warning_reason"),
                        }
                    ws.append(_get_row_values(r))
                    data_row = ws.max_row
                    try:
                        data_idx = rows.index(r)
                    except ValueError:
                        data_idx = -1
                    if data_idx >= 0:
                        row_to_data_idx[data_row] = data_idx
                    apply_cell_hyperlink(
                        ws.cell(ws.max_row, 1),
                        r.get("_source_file_path"),
                        r.get("_source_sheet_name"),
                        r.get("_source_row_index"),
                    )

            return warning_rows, row_to_data_idx

        for i, r in enumerate(rows):
            warning_kind = r.get("_template_warning_kind")
            if r.get("is_template_warning") and not (curator in {"boris", "ivan"} and warning_kind in {
                "hard_structure",
                "soft_structure",
            }):
                warning_rows[ws.max_row + 1] = {
                    "kind": warning_kind,
                    "reason": r.get("_template_warning_reason"),
                }
            if curator == "boris":
                ws.append(
                    [_safe_text(v) for v in [
                        r.get("Источник", ""),
                        r.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", ""),
                        r.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", ""),
                        _safe_decimal(r.get("сумма платежа ПРИХОД", 0)),
                        _safe_decimal(r.get("сумма платежа РАСХОД", 0)),
                        _safe_decimal(r.get("комиссия", 0)),
                        _safe_decimal(r.get("ИТОГ", 0)),
                        _safe_decimal(r.get("% посредника", 0)),
                        _safe_decimal(r.get("посредник 1(кэш)", 0)),
                        _safe_decimal(r.get("% посредник 2", 0)),
                        _safe_decimal(r.get("посредник 2", 0)),
                        r.get("фильтры", ""),
                    ]]
                )
            elif curator == "ivan":
                ws.append(
                    [_safe_text(v) for v in [
                        r.get("Сотрудник", r.get("Источник", "")),
                        r.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", ""),
                        r.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", ""),
                        _safe_decimal(r.get("сумма платежа ПРИХОД", 0)),
                        _safe_decimal(r.get("сумма платежа РАСХОД", 0)),
                        _safe_decimal(r.get("комиссия", 0)),
                        _safe_decimal(r.get("ИТОГ", 0)),
                        _safe_decimal(r.get("ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ", 0)),
                        _safe_decimal(r.get("% посредника", 0)),
                        _safe_decimal(r.get("посредник 1(кэш)", 0)),
                        _safe_decimal(r.get("посредник 2", 0)),
                        _safe_decimal(r.get("курс", 0)),
                        _safe_decimal(r.get("сумма", 0)),
                        r.get("валюта", ""),
                        r.get("фильтры", ""),
                    ]]
                )
            else:
                ws.append(
                    [_safe_text(v) for v in [
                        r.get("Источник", ""),
                        r.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", ""),
                        r.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", ""),
                        _safe_decimal(r.get("сумма платежа ПРИХОД", 0)),
                        _safe_decimal(r.get("сумма платежа РАСХОД", 0)),
                        _safe_decimal(r.get("комиссия", 0)),
                        _safe_decimal(r.get("ИТОГ", 0)),
                        _safe_decimal(r.get("ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ", 0)),
                        _safe_decimal(r.get("% посредника", 0)),
                        _safe_decimal(r.get("посредник 1(кэш)", 0)),
                        _safe_decimal(r.get("посредник 2", 0)),
                        r.get("фильтры", ""),
                    ]]
                )
            data_row = ws.max_row
            row_to_data_idx[data_row] = i
            apply_cell_hyperlink(
                ws.cell(ws.max_row, 1),
                r.get("_source_file_path"),
                r.get("_source_sheet_name"),
                r.get("_source_row_index"),
            )
        return warning_rows, row_to_data_idx

    def _write_template_errors_sheet(self, wb, template_errors: List[Dict[str, Any]]):
        sheet_name = "ОШИБКИ ШАБЛОНА"
        if sheet_name in wb.sheetnames:
            del wb[sheet_name]
        # Template errors are stored in DB/session metadata only.
        # Do not render a separate workbook sheet.
        return

    def write_daily_data(
        self, date, rows, wb=None, sh_name_override=None, curator=None, headers=None
    ):
        should_save = False
        owns_wb = False
        if wb is None:
            wb = self._get_workbook()
            owns_wb = True
            should_save = True

        try:
            sh_name = sh_name_override or date.strftime("%d.%m.%Y")
            if sh_name in wb.sheetnames:
                del wb[sh_name]
            ws = wb.create_sheet(sh_name)
            # Make the newly created sheet active so wb.active access works as expected
            wb.active = wb.sheetnames.index(sh_name)

            ws.append(headers or DEFAULT_HEADERS)
            self._apply_header_style(ws)
            ws.freeze_panes = "A2"

            warning_rows, row_to_data_idx = self._append_data_rows(ws, date, rows, curator=curator)

            cols, num_indices, percent_broker_cols = detect_header_columns(ws)

            apply_cell_styling(
                ws,
                rows,
                warning_rows,
                cols,
                num_indices,
                percent_broker_cols,
                self.st,
                self.return_keywords,
                row_to_data_idx=row_to_data_idx,
            )

            build_total_row(ws, num_indices, self.st)

            self._auto_adjust(ws)
            if should_save:
                if not self._save_workbook(wb):
                    logger.error("Failed to save workbook in write_daily_data()")
        finally:
            # When we opened the workbook ourselves, guarantee it is
            # closed even if an exception aborted the build before the
            # save branch ran (otherwise the handle stays locked and a
            # retry hits "file is busy" on Windows).
            if owns_wb:
                try:
                    wb.close()
                except Exception:
                    pass

    def write_empty_daily_report(
        self,
        path: Path,
        date,
        curator=None,
        curator_config=None,
    ) -> bool:
        headers = None
        if curator_config and "headers" in curator_config:
            headers = curator_config["headers"]
        wb = self._get_workbook(path=str(path))
        if wb is None:
            return False
        try:
            self.write_daily_data(
                date,
                [],
                wb=wb,
                curator=curator,
                headers=headers,
            )
            return self._save_workbook(wb, path=str(path))
        finally:
            # _save_workbook closes wb on success; close explicitly on the
            # error path so a failed empty-report build doesn't leave the
            # file handle locked.
            try:
                wb.close()
            except Exception:
                pass

    def write_report(
        self,
        data: List[Dict[str, Any]],
        path: Path,
        template_errors: Optional[List[Dict[str, Any]]] = None,
        curator=None,
        curator_config=None,
    ) -> bool:
        if not is_file_writable(str(path)):
            logger.error(
                f"Файл занят: {os.path.abspath(str(path))}. Закройте его в Excel перед началом!"
            )
            return False

        headers = None
        if curator_config and "headers" in curator_config:
            headers = curator_config["headers"]

        try:
            today = datetime.now().date()
            dbd = {}
            for r in data:
                if r is None:
                    logger.warning(
                        "TEMPORAL FILTER: None row encountered and will be skipped."
                    )
                    continue
                d = r.get("Дата")
                if not d:
                    logger.warning(
                        "TEMPORAL FILTER: Row from %s has no date and will be skipped.",
                        r.get("Источник"),
                    )
                    continue

                if hasattr(d, "strftime") and hasattr(d, "date"):
                    d_str = d.strftime("%d.%m.%Y")
                    dt = d
                else:
                    try:
                        dt = datetime.strptime(str(d), "%d.%m.%Y")
                        d_str = dt.strftime("%d.%m.%Y")
                    except ValueError:
                        try:
                            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d")
                            d_str = dt.strftime("%d.%m.%Y")
                        except ValueError:
                            logger.warning(
                                "TEMPORAL FILTER: Row from %s has invalid date '%s' and will be skipped.",
                                r.get("Источник"),
                                d,
                            )
                            continue

                if dt.date() > today:
                    logger.warning(
                        "TEMPORAL FILTER: Future date %s from %s will be skipped.",
                        d,
                        r.get("Источник"),
                    )
                    try:
                        from core.domain.data_loss_log import record_loss
                        record_loss(
                            source=str(path),
                            kind="future_date",
                            reason=f"date {d} is in the future",
                            field="Дата",
                            original_value=d,
                        )
                    except Exception:
                        logger.debug("Failed to record data loss for future date %s", d, exc_info=True)
                    continue

                dbd.setdefault(d_str, []).append(r)

            if not dbd:
                logger.error("Write error: no valid dated rows after temporal filtering")
                return False

            wb = self._get_workbook(path=str(path))
            if wb is None:
                return False
            try:
                for d_str, rows in sorted(dbd.items()):
                    try:
                        dt = datetime.strptime(d_str, "%d.%m.%Y")
                        self.write_daily_data(
                            dt,
                            rows,
                            wb=wb,
                            curator=curator,
                            headers=headers,
                        )
                    except Exception as e:
                        logger.error(f"Date error {d_str}: {e}")
                self._write_template_errors_sheet(wb, template_errors or [])
                return self._save_workbook(wb, path=str(path))
            finally:
                # _save_workbook closes wb on success; this guarantees
                # close on the error paths too (exception raised between
                # open and save left the handle locked on disk).
                try:
                    wb.close()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Write error: {e}")
            return False
