import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any
import openpyxl
from pyxlsb import open_workbook as open_xlsb

from core.domain.interfaces import IDataSource
from core.infra.ingestion_readers import XlsxReader, XlsbReader
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
        self.xlsx_reader = XlsxReader(self.markers, self.aliases)
        self.xlsb_reader = XlsbReader(self.markers, self.aliases)

    def get_available_dates(self, file_path: Path) -> List[str]:
        dates = set()
        try:
            suffix = file_path.suffix.lower()
            if suffix == '.xlsx':
                wb = openpyxl.load_workbook(file_path, read_only=True, keep_links=False)
                for ws in wb.worksheets:
                    if ws.sheet_state == 'visible':
                        d = extract_date_from_sheet(ws.title)
                        if d: dates.add(d)
                wb.close()
            elif suffix == '.xlsb':
                with open_xlsb(str(file_path)) as wb:
                    for s in wb.sheets:
                        d = extract_date_from_sheet(s)
                        if d: dates.add(d)
        except Exception as e:
            logger.error(f"Error getting dates from {file_path}: {e}")
        return sorted(list(dates))

    def scan_directory(self, root_path: Path) -> List[Dict[str, Any]]:
        res = []
        if not root_path.exists(): return res
        for root, _, files in os.walk(root_path):
            for f in files:
                if f.startswith('~$') or not f.lower().endswith(('.xlsx', '.xlsb')): continue
                p = (Path(root) / f).resolve()
                try:
                    stat = os.stat(p)
                    with open(p, 'rb') as f_io: 
                        fp = hashlib.md5(f_io.read(8192)).hexdigest()
                    res.append({
                        "path": str(p), 
                        "id": stat.st_ino, 
                        "fp": fp, 
                        "size": stat.st_size, 
                        "mtime": stat.st_mtime
                    })
                except Exception as e:
                    logger.error(f"Error scanning file {p}: {e}")
        return res

    def read_file(self, file_path: Path) -> List[Dict[str, Any]]:
        if not file_path.exists(): return []
        s = file_path.suffix.lower()
        if s == '.xlsx': return self.xlsx_reader.read(file_path)
        if s == '.xlsb': return self.xlsb_reader.read(file_path)
        return []
