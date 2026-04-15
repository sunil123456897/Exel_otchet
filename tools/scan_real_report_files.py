import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(r"E:\Dlia Dashi\Version5")
APP = ROOT / "APP"
REPORTS = ROOT / "REPORTS"


CHILD_SCRIPT = r"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"E:\Dlia Dashi\Version5\APP")))

from core.bootstrap import Bootstrap


app_root = Path(r"E:\Dlia Dashi\Version5\APP")
cfg_ctl, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))
p = Path(sys.argv[1])

try:
    dates = app_ctl.ingestion.get_available_dates(p)
    rows = app_ctl.ingestion.read_file(p)
    print(json.dumps({"file": str(p), "dates": len(dates), "rows": len(rows)}, ensure_ascii=False))
finally:
    app_ctl.shutdown()
"""


def main() -> None:
    files = sorted(
        p
        for p in REPORTS.rglob("*")
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xls", ".xlsb"}
    )

    results = []
    for path in files:
        proc = subprocess.run(
            [sys.executable, "-c", CHILD_SCRIPT, str(path)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        results.append(
            {
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "returncode": proc.returncode,
                "stdout": proc.stdout[-1000:],
                "stderr": proc.stderr[-2000:],
            }
        )

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
