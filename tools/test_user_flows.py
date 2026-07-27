#!/usr/bin/env python3
"""Run end-to-end tests for key user flows: Consolidation, RSCH report, and Reconciliation."""
import sys
import os
import threading
from datetime import datetime
from pathlib import Path

# Add APP dir to PATH
app_root = Path(__file__).resolve().parents[1] / "APP"
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap

def test_flows():
    print("Initializing AppController via Bootstrap...")
    cfg_ctl, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))
    
    target_date_str = "01.04.2026"
    target_date = datetime.strptime(target_date_str, "%d.%m.%Y")
    
    # Resolve source paths from configuration
    rsch_cfg = cfg_ctl.config.get("rsch", {})
    recent_sources = [Path(p) for p in rsch_cfg.get("recent_sources", [])]
    output_dir = Path(rsch_cfg.get("last_output_dir", str(app_root.parent / "РСЧ")))
    output_dir.mkdir(parents=True, exist_ok=True)
    
    rsch_output_path = output_dir / f"РСЧ_отчет_{target_date_str}.xlsx"
    reconciliation_output_path = output_dir / f"Сверка_{target_date_str}.xlsx"
    
    # 1. Test Consolidation for Day
    print(f"\n--- Flow 1: Running Consolidation for {target_date_str} ---")
    done_event = threading.Event()
    results = {}
    
    def on_consolidation_comp(ok, msg, path):
        results["consolidation"] = (ok, msg, path)
        done_event.set()
        
    app_ctl.run_consolidation(
        target_date,
        on_progress=lambda p: None,
        on_complete=on_consolidation_comp
    )
    done_event.wait(timeout=120)
    print("Consolidation complete:", results["consolidation"])
    assert results["consolidation"][0], f"Consolidation failed: {results['consolidation'][1]}"
    
    # 2. Test RSCH Report Generation
    print(f"\n--- Flow 2: Generating RSCH Report for {target_date_str} ---")
    done_event.clear()
    
    def on_rsch_comp(ok, msg, path):
        results["rsch"] = (ok, msg, path)
        done_event.set()
        
    app_ctl.run_rsch_report(
        recent_sources,
        rsch_output_path,
        target_date,
        on_complete=on_rsch_comp
    )
    done_event.wait(timeout=120)
    print("RSCH report complete:", results["rsch"])
    assert results["rsch"][0], f"RSCH report failed: {results['rsch'][1]}"
    
    # 3. Test Auto-Reconciliation Day
    print(f"\n--- Flow 3: Running Auto-Reconciliation for {target_date_str} ---")
    done_event.clear()
    
    def on_reconciliation_comp(ok, msg, path):
        results["reconciliation"] = (ok, msg, path)
        done_event.set()
        
    app_ctl.run_auto_reconciliation_day(
        recent_sources,
        reconciliation_output_path,
        target_date,
        on_complete=on_reconciliation_comp
    )
    done_event.wait(timeout=120)
    print("Reconciliation complete:", results["reconciliation"])
    assert results["reconciliation"][0], f"Reconciliation failed: {results['reconciliation'][1]}"
    
    # Cleanup / Shutdown
    print("\nShutting down controllers...")
    app_ctl.shutdown()
    print("All tests passed successfully!")

if __name__ == "__main__":
    try:
        test_flows()
    except Exception as e:
        print(f"TEST FAILURE: {e}", file=sys.stderr)
        sys.exit(1)
