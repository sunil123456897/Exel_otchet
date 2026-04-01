import sys
import os
from pathlib import Path

# Add APP directory to sys.path
app_root = Path(__file__).parent.parent / "APP"
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))
