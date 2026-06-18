import pytest


@pytest.mark.skipif(
    not __import__("os").path.exists("Z:\\"),
    reason="Z: drive not mapped on this machine",
)
def test_write_empty_invalid_drive():
    from core.infra.export_writer import MasterWriter
    from datetime import datetime
    from pathlib import Path
    writer = MasterWriter({'paths': {'master_file': 'Z:\\invalid\\report.xlsx'}})
    writer.write_empty_daily_report(Path('Z:\\invalid\\report.xlsx'), datetime.now())
