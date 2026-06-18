import pytest


def test_write_empty_preflight_error():
    from core.infra.export_writer import MasterWriter, ExportPreflightError
    from datetime import datetime
    from pathlib import Path
    from unittest.mock import patch
    writer = MasterWriter({'paths': {'master_file': 'e:\\test\\report.xlsx'}})
    with patch('os.access', return_value=False):
        with pytest.raises(ExportPreflightError):
            writer.write_empty_daily_report(Path('e:\\test\\report.xlsx'), datetime.now())
