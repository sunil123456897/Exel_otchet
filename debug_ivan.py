import sys
import logging
from pathlib import Path
sys.path.append(str(Path("APP").absolute()))
from core.infra.ingestion_readers import XlsxReader
import yaml

def debug_ivan():
    with open("APP/config.yaml", encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    markers = config.get('sh1', {}).get('markers', {})
    aliases = {
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
    
    reader = XlsxReader(markers, aliases)
    
    path = Path("E:/Для Даши/Версия 5/REPORTS/Отчет кураторов 1/Иван/Отчет новый Иван .xlsx")
    if not path.exists():
        print("Файл Ивана не найден!")
        return
        
    rows = reader.read(path)
    print(f"Прочитано {len(rows)} строк.")
    if rows:
        target_rows = [r for r in rows if r.get('date') == '23.03.2026']
        print(f"Найдено {len(target_rows)} строк для 23.03.2026.")
        if target_rows:
            print(f"Первая целевая строка: is_template_warning = {target_rows[0].get('is_template_warning')}")
            print(target_rows[0])
        
if __name__ == "__main__":
    debug_ivan()
