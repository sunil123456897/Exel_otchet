import os
import hashlib
import logging
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any
from python_calamine import CalamineWorkbook

from core.domain import IDataSource
from core.infra.utils import get_local_copy
from core.infra.ingestion_reader import CalamineReader, extract_date_from_sheet

logger = logging.getLogger(__name__)


class IngestionEngine(IDataSource):
    def __init__(
        self, config_markers: Dict[str, str], drive_letters: tuple = ("Q", "Z")
    ):
        self.markers = config_markers
        self.drive_letters = tuple(d.upper() for d in drive_letters)
        self.aliases = {
            "amount": ["сумма платежа", "бн рф руб", "бн", "приход", "расход"],
            "income": ["приход"],
            "expense": ["расход"],
            "customer": ["заказчик", "агент"],
            "contractor": ["исполнитель", "вторая сторона"],
            "total": ["итог", "итоги дня", "итог дня", "формула"],
            "commission": ["комиссия", "ставка/цена"],
            "percent_broker": ["% посредника", "%"],
            "broker1": [
                "посредник 1(кэш)",
                "посредник 1",
                "комиссия посредника 1",
                "приходный кассовый ордер",
            ],
            "broker2": ["посредник 2", "комиссия посредника 2", "%.1"],
            "filters": ["фильтры", "фильтр", "filter"],
        }
        self.reader = CalamineReader(self.markers, self.aliases, self.drive_letters)

    def get_available_dates(self, file_path: Path) -> List[str]:
        dates = set()
        f_path_abs = os.path.abspath(str(file_path))
        target_path, temp_file = get_local_copy(f_path_abs, self.drive_letters)

        try:
            wb = CalamineWorkbook.from_path(target_path)
            for s in wb.sheet_names:
                if s.startswith("_") or s in ("АНАЛИТИКА", "СВОД"):
                    continue
                d = extract_date_from_sheet(s)
                if d:
                    dates.add(d)
        except Exception as e:
            logger.error(f"Error getting dates from {file_path}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
        return sorted(list(dates))

    def scan_directory(self, root_path: Path) -> List[Dict[str, Any]]:
        res = []
        if not root_path.exists():
            logger.warning(f"[SCAN] Папка не найдена: {root_path}")
            return res
        logger.info(f"[SCAN] Сканирую папку: {root_path}...")
        for root, _, files in os.walk(root_path):
            for f in files:
                if f.startswith("~$") or not f.lower().endswith((".xlsx", ".xlsb")):
                    continue
                p = (Path(root) / f).resolve()
                try:
                    stat = os.stat(p)
                    # СКИПИРУЕМ хэширование при сканировании (это ОЧЕНЬ медленно по сети)
                    res.append(
                        {
                            "path": str(p),
                            "id": stat.st_ino,
                            "fp": None,  # Хэш будет вычислен только при необходимости
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    )
                except Exception as e:
                    logger.error(f"Error scanning file {p}: {e}")
        return res

    def read_file(self, file_path: Path) -> List[Dict[str, Any]]:
        if not file_path.exists():
            return []
        return self.reader.read(file_path)
