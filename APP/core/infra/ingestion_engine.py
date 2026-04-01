import os
import hashlib
import logging
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any
from python_calamine import CalamineWorkbook

from core.domain.interfaces import IDataSource
from core.infra.ingestion_readers import CalamineReader
from core.infra.ingestion_utils import extract_date_from_sheet

logger = logging.getLogger(__name__)

class IngestionEngine(IDataSource):
    def __init__(self, config_markers: Dict[str, str]):
        self.markers = config_markers
        self.aliases = {
            'amount': ['сумма платежа', 'бн рф руб', 'бн', 'приход', 'расход'], 
            'income': ['приход'], 
            'expense': ['расход'], 
            'customer': ['заказчик', 'агент'], 
            'contractor': ['исполнитель', 'вторая сторона'], 
            'total': ['итог', 'итоги дня', 'итог дня', 'формула'], 
            'commission': ['комиссия', 'ставка/цена'], 
            'percent_broker': ['% посредника', '%'], 
            'broker1': ['посредник 1(кэш)', 'посредник 1', 'комиссия посредника 1', 'приходный кассовый ордер'], 
            'broker2': ['посредник 2', 'комиссия посредника 2', '%.1'], 
            'filters': ['фильтры', 'фильтр', 'filter']
        }
        self.reader = CalamineReader(self.markers, self.aliases)

    def get_available_dates(self, file_path: Path) -> List[str]:
        dates = set()
        f_path_abs = os.path.abspath(str(file_path))
        is_network = str(f_path_abs).startswith('\\\\') or f_path_abs[0].upper() in ('Q', 'Z')
        temp_file = None
        
        try:
            target_path = f_path_abs
            if is_network:
                fd, temp_file = tempfile.mkstemp(suffix=file_path.suffix)
                os.close(fd)
                shutil.copy2(f_path_abs, temp_file)
                target_path = temp_file
                
            wb = CalamineWorkbook.from_path(target_path)
            for s in wb.sheet_names:
                if s.startswith('_') or s in ("АНАЛИТИКА", "СВОД"): continue
                d = extract_date_from_sheet(s)
                if d: dates.add(d)
        except Exception as e:
            logger.error(f"Error getting dates from {file_path}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try: os.remove(temp_file)
                except: pass
        return sorted(list(dates))

    def scan_directory(self, root_path: Path) -> List[Dict[str, Any]]:
        res = []
        if not root_path.exists(): 
            logger.warning(f"⚠️ Папка не найдена: {root_path}")
            return res
        logger.info(f"📁 Сканирую папку: {root_path}...")
        for root, _, files in os.walk(root_path):
            for f in files:
                if f.startswith('~$') or not f.lower().endswith(('.xlsx', '.xlsb')): continue
                p = (Path(root) / f).resolve()
                try:
                    stat = os.stat(p)
                    # СКИПИРУЕМ хэширование при сканировании (это ОЧЕНЬ медленно по сети)
                    res.append({
                        "path": str(p), 
                        "id": stat.st_ino, 
                        "fp": None, # Хэш будет вычислен только при необходимости
                        "size": stat.st_size, 
                        "mtime": stat.st_mtime
                    })
                except Exception as e:
                    logger.error(f"Error scanning file {p}: {e}")
        return res

    def read_file(self, file_path: Path) -> List[Dict[str, Any]]:
        if not file_path.exists(): return []
        return self.reader.read(file_path)
