import pytest

@pytest.mark.xfail(reason="Debug dump test — intentionally always fails to show data structure")
def test_dump():  
    from core.infra.export_writer import MasterWriter  
    from datetime import datetime  
    from openpyxl import Workbook  
    writer = MasterWriter({'paths': {'master_file': 'dummy.xlsx'}, 'logic': {}})  
    rows = [{'Источник': 'Иванов', 'сумма платежа ПРИХОД': 100, 'is_critical': False}, {'Источник': 'Петров', 'сумма платежа ПРИХОД': 200, 'is_critical': True}]  
    dt = datetime.now()  
    wb = Workbook()  
    writer.write_daily_data(dt, rows, wb=wb, curator='boris')  
    ws = wb[dt.strftime('%d.%m.%Y')]  
    dump = [str([c.value for c in r]) for r in ws.iter_rows()]  
    assert False, '\n'.join(dump)  
