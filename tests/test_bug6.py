def test_print_ws():  
    from core.infra.export_writer import MasterWriter  
    from datetime import datetime  
    from openpyxl import Workbook  
    writer = MasterWriter({'paths': {'master_file': 'dummy.xlsx'}})  
    rows = [  
        {'Источник': 'boris.xlsx', 'фильтры': 'возврат', 'сумма платежа ПРИХОД': 100, 'ЗАКАЗЧИК': 'A'},  
    ]  
    wb = Workbook()  
    dt = datetime.now()  
    writer.write_daily_data(dt, rows, wb=wb, curator='boris')  
    ws = wb[dt.strftime('%d.%m.%Y')]  
    for r in ws.iter_rows(values_only=True): print(r)  
