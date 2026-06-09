def test_boris_curator_styling_offset():  
    from core.infra.export_writer import MasterWriter  
    from datetime import datetime  
    from openpyxl import Workbook  
    writer = MasterWriter({'paths': {'master_file': 'dummy.xlsx'}})  
    rows = [  
        {'Источник': 'boris.xlsx', 'фильтры': 'возврат', 'сумма платежа ПРИХОД': 100, 'ЗАКАЗЧИК': 'A'},  
        {'Источник': 'boris.xlsx', 'фильтры': '', 'сумма платежа ПРИХОД': 200, 'ЗАКАЗЧИК': 'B'},  
    ]  
    dt = datetime.now()
    wb = Workbook()  
    writer.write_daily_data(dt, rows, wb=wb, curator='boris')  
    ws = wb[dt.strftime('%d.%m.%Y')]  
    # Row 2 is group header 'boris.xlsx'  
    # Row 3 is first data row  
    # If mapping is wrong, Row 2 gets 'возврат' styling (math errors skipped) and Row 3 gets Row 2's logic  
    assert ws.cell(3, 4).value == 100  
    assert ws.cell(3, 4).fill.start_color.rgb == writer.st.fill_income.start_color.rgb  
