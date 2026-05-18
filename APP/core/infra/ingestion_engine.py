import os
import logging
import time
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List, Dict, Any
import xml.etree.ElementTree as ET
from python_calamine import CalamineWorkbook

from core.domain import IDataSource
from core.infra.utils import get_local_copy
from core.infra.ingestion_reader import CalamineReader, extract_date_from_sheet

logger = logging.getLogger(__name__)

_FILE_READ_RETRIES = 3
_FILE_READ_BACKOFF = 1.0
_APP_ROOT = Path(__file__).resolve().parents[2]
_IGNORED_DATE_SHEETS = {"АНАЛИТИКА", "СВОД"}
_WORKBOOK_XML = "xl/workbook.xml"
_SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _extract_dates_from_sheet_names(sheet_names: List[str]) -> List[str]:
    dates = set()
    for sheet_name in sheet_names:
        if sheet_name.startswith("_") or sheet_name in _IGNORED_DATE_SHEETS:
            continue
        sheet_date = extract_date_from_sheet(sheet_name)
        if sheet_date:
            dates.add(sheet_date)
    return sorted(dates)


def _get_xlsx_sheet_dates_from_metadata(target_path: str | Path) -> List[str]:
    with zipfile.ZipFile(target_path) as archive:
        workbook_xml = archive.read(_WORKBOOK_XML)
    root = ET.fromstring(workbook_xml)
    sheet_names = [
        str(sheet.attrib.get("name", ""))
        for sheet in root.findall(f".//{_SPREADSHEET_NS}sheet")
    ]
    return _extract_dates_from_sheet_names(sheet_names)


def _try_get_xlsx_sheet_dates_from_metadata(target_path: str | Path) -> List[str] | None:
    if not str(target_path).lower().endswith(".xlsx"):
        return None
    try:
        return _get_xlsx_sheet_dates_from_metadata(target_path)
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        logger.debug(
            "Fast xlsx sheet metadata read failed for %s: %s",
            target_path,
            e,
        )
        return None


def _run_calamine_worker(
    mode: str,
    target_path: str,
    markers,
    aliases,
    strict_io: bool = False,
    target_date_str: str | None = None,
    start_date_str: str | None = None,
    end_date_str: str | None = None,
) -> Dict[str, Any]:
    script = r"""
import json
import importlib.util
import sys
import types
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app_root = Path(sys.argv[6])


def _load_module(name, file_path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core_pkg = types.ModuleType("core")
core_pkg.__path__ = [str(app_root / "core")]
sys.modules.setdefault("core", core_pkg)

domain_pkg = types.ModuleType("core.domain")
domain_pkg.__path__ = [str(app_root / "core" / "domain")]
sys.modules["core.domain"] = domain_pkg

infra_pkg = types.ModuleType("core.infra")
infra_pkg.__path__ = [str(app_root / "core" / "infra")]
sys.modules["core.infra"] = infra_pkg

_load_module("core.domain.utils_helpers", app_root / "core" / "domain" / "utils_helpers.py")
_load_module("core.infra.utils", app_root / "core" / "infra" / "utils.py")
reader_mod = _load_module("core.infra.ingestion_reader", app_root / "core" / "infra" / "ingestion_reader.py")

from python_calamine import CalamineWorkbook

CalamineReader = reader_mod.CalamineReader
extract_date_from_sheet = reader_mod.extract_date_from_sheet


mode = sys.argv[1]
target_path = sys.argv[2]
markers = json.loads(sys.argv[3])
aliases = json.loads(sys.argv[4])
strict_io = json.loads(sys.argv[5])
target_date_str = json.loads(sys.argv[7])
start_date_str = json.loads(sys.argv[8])
end_date_str = json.loads(sys.argv[9])

if mode == "dates":
    dates = set()
    wb = CalamineWorkbook.from_path(target_path)
    for sheet_name in wb.sheet_names:
        if sheet_name.startswith("_") or sheet_name in ("АНАЛИТИКА", "СВОД"):
            continue
        sheet_date = extract_date_from_sheet(sheet_name)
        if sheet_date:
            dates.add(sheet_date)
    print(json.dumps({"ok": True, "result": sorted(dates)}, ensure_ascii=False))
elif mode == "rows":
    reader = CalamineReader(markers, aliases)
    rows = reader.read(
        Path(target_path),
        strict_io=strict_io,
        target_date_str=target_date_str,
        start_date_str=start_date_str,
        end_date_str=end_date_str,
    )
    print(json.dumps({"ok": True, "result": rows}, ensure_ascii=False, default=str))
else:
    print(json.dumps({"ok": False, "error": f"Unknown mode: {mode}"}, ensure_ascii=False))
    raise SystemExit(2)
"""

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            mode,
            target_path,
            json.dumps(markers, ensure_ascii=False),
            json.dumps(aliases, ensure_ascii=False),
            json.dumps(strict_io),
            str(_APP_ROOT),
            json.dumps(target_date_str),
            json.dumps(start_date_str),
            json.dumps(end_date_str),
        ],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        cwd=str(Path(__file__).resolve().parents[3]),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": stderr or stdout or f"worker exited with code {proc.returncode}",
        }

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": stderr or stdout or "worker returned invalid json",
        }

    if stderr:
        payload["stderr"] = stderr
    return payload


def _should_isolate_calamine(file_path: Path | str) -> bool:
    normalized = str(file_path).replace("\\", "/").lower()
    return "/reports/" in f"/{normalized.strip('/')}"


class IngestionEngine(IDataSource):
    def __init__(
        self, config_markers: Dict[str, str], drive_letters: tuple = ("Q", "Z")
    ):
        self.markers = config_markers
        self.drive_letters = tuple(d.upper() for d in drive_letters)
        self.config = {}
        self.aliases = {
            "amount": ["сумма платежа", "бн рф руб", "бн", "приход", "расход"],
            "income": ["приход"],
            "expense": ["расход"],
            "customer": ["заказчик", "агент"],
            "contractor": ["исполнитель", "вторая сторона"],
            "total": ["итог", "итоги дня", "итог дня", "формула"],
            "transit_obligation": ["отправка транзитных обязательств"],
            "commission": ["комиссия", "ставка/цена"],
            "percent_broker": ["% посредника", "%"],
            "broker1": [
                "посредник 1(кэш)",
                "посредник 1",
                "комиссия посредника 1",
                "приходный кассовый ордер",
            ],
            "broker2": ["посредник 2", "комиссия посредника 2", "%.1"],
            "exchange_rate": ["курс"],
            "currency_amount": ["сумма"],
            "currency": ["валюта"],
            "filters": ["фильтры", "фильтр", "filter"],
        }
        self.reader = CalamineReader(self.markers, self.aliases, self.drive_letters)

    def _should_isolate_calamine(self, file_path: Path | str) -> bool:
        if self.config.get("performance", {}).get("isolate_calamine") is False:
            return False
        return _should_isolate_calamine(file_path)

    def _get_available_dates_direct(self, target_path: str) -> List[str]:
        wb = CalamineWorkbook.from_path(target_path)
        return _extract_dates_from_sheet_names(list(wb.sheet_names))

    def get_available_dates(
        self,
        file_path: Path,
        remote_mtime: float | None = None,
        remote_size: int | None = None,
    ) -> List[str]:
        dates = set()
        f_path_abs = os.path.abspath(str(file_path))
        should_isolate = self._should_isolate_calamine(file_path)
        if should_isolate:
            metadata_dates = _try_get_xlsx_sheet_dates_from_metadata(f_path_abs)
            if metadata_dates is not None:
                return metadata_dates

        target_path, temp_file = get_local_copy(
            f_path_abs,
            self.drive_letters,
            remote_mtime=remote_mtime,
            remote_size=remote_size,
        )

        try:
            if should_isolate:
                metadata_dates = _try_get_xlsx_sheet_dates_from_metadata(target_path)
                if metadata_dates is not None:
                    return metadata_dates
            if should_isolate:
                payload = _run_calamine_worker(
                    "dates", target_path, self.markers, self.aliases
                )
                if not payload.get("ok"):
                    raise RuntimeError(
                        payload.get("error", "unknown calamine worker error")
                    )
                for d in payload.get("result", []):
                    if d:
                        dates.add(d)
                if payload.get("stderr"):
                    logger.warning(payload["stderr"])
            else:
                for d in self._get_available_dates_direct(target_path):
                    dates.add(d)
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise
            logger.error(f"Error getting dates from {file_path}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
        return sorted(list(dates))

    def scan_directory(self, root_path: Path) -> List[Dict[str, Any]]:
        res = []
        if not root_path.exists():
            logger.warning(f"[SCAN] Папка не найдена: {root_path}")
            return res
        logger.info(f"[SCAN] Сканирую папку: {root_path}...")
        scan_root = os.path.abspath(os.fspath(root_path))
        roots_to_visit = [scan_root]
        while roots_to_visit:
            current_root = roots_to_visit.pop()
            subdirs = []
            try:
                with os.scandir(current_root) as entries:
                    for entry in entries:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                subdirs.append(entry.path)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            f = entry.name
                            if f.startswith("~$") or not f.lower().endswith(
                                (".xlsx", ".xlsb")
                            ):
                                continue
                            stat = entry.stat(follow_symlinks=False)
                            # СКИПИРУЕМ хэширование при сканировании (это ОЧЕНЬ медленно по сети)
                            res.append(
                                {
                                    "path": str(entry.path),
                                    "id": stat.st_ino,
                                    "fp": None,  # Хэш будет вычислен только при необходимости
                                    "size": stat.st_size,
                                    "mtime": stat.st_mtime,
                                }
                            )
                        except Exception as e:
                            logger.error(f"Error scanning file {entry.path}: {e}")
                roots_to_visit.extend(reversed(subdirs))
            except Exception as e:
                logger.error(f"Error scanning directory {current_root}: {e}")
                continue
        return res

    def read_file(
        self,
        file_path: Path,
        strict_io: bool = False,
        target_date_str: str | None = None,
        start_date_str: str | None = None,
        end_date_str: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Read Excel file with retry logic for transient network errors."""
        if not file_path.exists():
            return []
        last_err = None
        for attempt in range(_FILE_READ_RETRIES):
            try:
                if self._should_isolate_calamine(file_path):
                    payload = _run_calamine_worker(
                        "rows",
                        str(file_path),
                        self.markers,
                        self.aliases,
                        strict_io=strict_io,
                        target_date_str=target_date_str,
                        start_date_str=start_date_str,
                        end_date_str=end_date_str,
                    )
                    if not payload.get("ok"):
                        raise RuntimeError(
                            payload.get("error", "unknown calamine worker error")
                        )
                    if payload.get("stderr"):
                        logger.warning(payload["stderr"])
                    return payload.get("result", [])
                if target_date_str or (start_date_str and end_date_str):
                    return self.reader.read(
                        file_path,
                        strict_io=strict_io,
                        target_date_str=target_date_str,
                        start_date_str=start_date_str,
                        end_date_str=end_date_str,
                    )
                return self.reader.read(file_path, strict_io=strict_io)
            except (OSError, IOError, PermissionError) as e:
                last_err = e
                logger.warning(
                    f"File read retry {attempt + 1}/{_FILE_READ_RETRIES} for "
                    f"{file_path}: {e}"
                )
                time.sleep(min(60, _FILE_READ_BACKOFF * (2**attempt)))
            except RuntimeError as e:
                last_err = e
                logger.error(f"Failed to read {file_path}: {e}")
                if strict_io:
                    raise
                return []
            except Exception:
                raise
        if strict_io and last_err is not None:
            raise last_err
        logger.error(
            f"Failed to read {file_path} after {_FILE_READ_RETRIES} retries: {last_err}"
        )
        return []
