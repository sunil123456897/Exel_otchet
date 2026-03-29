import os
import shutil
import sys
import logging
import importlib
import time
import sqlite3
import openpyxl
import threading
from datetime import datetime
from pathlib import Path
from ruamel.yaml import YAML
from contextlib import contextmanager
from openpyxl import Workbook

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DestructiveTester")

class HarnessEnv:
    def __init__(self, env_name: str = "temp_destructive_env"):
        """
        Initializes the test harness environment manager.
        """
        self.root_dir = Path(__file__).parent.absolute()
        self.env_dir = self.root_dir / env_name
        self.app_root = self.root_dir / "APP"
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        
    def prepare(self):
        logger.info(f"Preparing environment in: {self.env_dir}")
        try:
            if self.env_dir.exists():
                self.cleanup()
            self.env_dir.mkdir(parents=True)
            
            # Copy APP/src/ to env/src/
            shutil.copytree(self.app_root / "src", self.env_dir / "src")
            # Copy APP/main.py to env/main.py
            shutil.copy2(self.app_root / "main.py", self.env_dir / "main.py")
            
            self._create_isolated_config()
            
            logger.info("Environment preparation completed.")
        except Exception as e:
            logger.error(f"Failed to prepare environment: {e}")
            raise

    def _create_isolated_config(self):
        source_config = self.app_root / "config.yaml"
        target_config = self.env_dir / "config.yaml"
        
        with open(source_config, 'r', encoding='utf-8') as f:
            config = self.yaml.load(f)
            
        # Clear existing mappings to force discovery in temp env
        config['employee_paths'] = {}
        config['employees'] = []
            
        if 'database' not in config: config['database'] = {}
        config['database']['path'] = (self.env_dir / "cache.db").absolute().as_posix()
        config['database']['schema_path'] = (self.env_dir / "src" / "db_schema.sql").absolute().as_posix()
        
        if 'paths' not in config: config['paths'] = {}
        config['paths']['archive_dir'] = (self.env_dir / "backups").absolute().as_posix()
        (self.env_dir / "backups").mkdir(exist_ok=True)
        config['paths']['master_file'] = (self.env_dir / "Final_Report.xlsx").absolute().as_posix()
        
        source_root = self.env_dir / "source"
        source_root.mkdir(exist_ok=True)
        config['paths']['source_root'] = source_root.absolute().as_posix()
        
        with open(target_config, 'w', encoding='utf-8') as f:
            self.yaml.dump(config, f)

    def cleanup(self):
        if self.env_dir.exists():
            def on_error(func, path, exc_info):
                import stat
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWUSR)
                    func(path)
            shutil.rmtree(self.env_dir, onerror=on_error)

    def import_class(self, module_path_str: str, class_name: str):
        env_path_str = str(self.env_dir.absolute())
        if env_path_str not in sys.path:
            sys.path.insert(0, env_path_str)
            
        try:
            module = importlib.import_module(module_path_str)
            return getattr(module, class_name)
        except Exception as e:
            logger.error(f"Failed to import {class_name} from {module_path_str}: {e}")
            raise

class EvilGenerator:
    def __init__(self):
        self.logger = logging.getLogger("EvilGenerator")

    def _ensure_dir(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)

    def generate_normal_file(self, path: str, employee_name: str, date_str: str = "29.03.2024"):
        target_path = Path(path)
        self._ensure_dir(target_path)
        wb = Workbook()
        ws = wb.active
        ws.title = date_str
        headers = ["Заказчик", "Исполнитель", "Приход", "Расход", "Комиссия", "Итог"]
        ws.append(headers)
        ws.append(["Standard Corp", employee_name, 1000.0, 0, 0, 1000.0])
        wb.save(target_path)

    def generate_double_header(self, path: str):
        target_path = Path(path)
        self._ensure_dir(target_path)
        wb = Workbook()
        ws = wb.active
        ws.title = "29.03.2024"
        for r in range(1, 5):
            ws.append([f"Junk_{r}_{c}" for c in range(6)])
        ws.append(["Заказчик", "Исполнитель", "Приход", "Расход", "Комиссия", "Итог"])
        ws.append(["Bad Head Corp", "Header Hunter", 1500.0, 0, 0, 1500.0])
        wb.save(target_path)

    def generate_extreme_math(self, path: str):
        target_path = Path(path)
        self._ensure_dir(target_path)
        wb = Workbook()
        ws = wb.active
        ws.title = "29.03.2024"
        ws.append(["Заказчик", "Исполнитель", "Приход", "Расход", "Комиссия", "Итог"])
        ws.append(["Mega Corp", "Global Bank", 9999999999.99, 0, 0, 9999999999.99])
        ws.append(["Greedy Corp", "Tax Man", 1000.0, 0, 1000.0, 0])
        ws.append(["Refund Corp", "Back Dept", 5000.0, 0, "возврат", 5000.0])
        wb.save(target_path)

    def generate_bad_sheets(self, path: str):
        target_path = Path(path)
        self._ensure_dir(target_path)
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "HiddenData"
        ws1.append(["Заказчик", "Исполнитель", "Сумма платежа ПРИХОД", "Дата"])
        ws1.append(["Invisible Inc", "Ghost Ops", 7777.77, "29.03.2024"])
        ws1.sheet_state = 'hidden'
        ws2 = wb.create_sheet("32.01.2024")
        ws2.append(["Заказчик", "Исполнитель", "Сумма платежа ПРИХОД", "Дата"])
        ws2.append(["Wrong Date", "Error", 10.0, "32.01.2024"])
        wb.save(target_path)

class MonkeySaboteur:
    def __init__(self):
        self._original_methods = {}
        self.logger = logging.getLogger("MonkeySaboteur")

    @contextmanager
    def sabotage_context(self, patches: list):
        try:
            for patch_func in patches: patch_func()
            yield
        finally:
            self.revert_all()

    def patch_db_lock(self, sqlite_manager_class):
        original = sqlite_manager_class._execute_with_retry
        self._original_methods[(sqlite_manager_class, '_execute_with_retry')] = original
        def mocked(instance, func, *args, **kwargs):
            raise sqlite3.OperationalError("database is locked")
        setattr(sqlite_manager_class, '_execute_with_retry', mocked)

    def patch_excel_stall(self, ingestion_engine_class):
        original = ingestion_engine_class.read_file
        self._original_methods[(ingestion_engine_class, 'read_file')] = original
        def mocked(instance, file_path):
            time.sleep(0.1)
            return original(instance, file_path)
        setattr(ingestion_engine_class, 'read_file', mocked)

    def revert_all(self):
        for (target, name), original in self._original_methods.items():
            setattr(target, name, original)
        self._original_methods.clear()

class MissionRunner:
    def __init__(self, harness: HarnessEnv):
        self.harness = harness
        self.generator = EvilGenerator()
        self.saboteur = MonkeySaboteur()
        self.results = []
        self.logger = logging.getLogger("MissionRunner")

    def log_result(self, mission: str, status: str, reason: str):
        self.results.append({"Mission": mission, "Status": status, "Reason": reason})

    def run_all_missions(self):
        logger.info("Starting all missions...")
        try:
            self.harness.prepare()
            
            # Imports
            app_controller_cls = self.harness.import_class("src.controllers.app_controller", "AppController")
            sqlite_manager_cls = self.harness.import_class("src.sqlite_manager", "SQLiteManager")
            ingestion_engine_cls = self.harness.import_class("src.ingestion", "IngestionEngine")
            
            self._run_mission_1(app_controller_cls, sqlite_manager_cls, ingestion_engine_cls)
            self._run_mission_2(app_controller_cls)
            self._run_mission_3_4(app_controller_cls)
            
            self.print_summary()
        finally:
            self.harness.cleanup()

    def _check_zombies(self):
        # Allow some time for threads to wind down
        time.sleep(1)
        active = threading.enumerate()
        # Filter out MainThread and current thread
        others = [t for t in active if t != threading.main_thread() and t != threading.current_thread()]
        # Filter out logging/system threads if possible, or just report count
        app_threads = [t for t in others if "Thread-" in t.name or "task" in str(t)]
        return len(app_threads)

    def _run_mission_1(self, app_cls, db_cls, ing_cls):
        m = "Mission 1: Sabotage"
        try:
            source = Path(self.harness.env_dir / "source")
            for i in range(5):
                self.generator.generate_normal_file(source / f"Emp_{i}" / f"Rep.xlsx", f"Emp_{i}")
            
            app = self._init_app(app_cls)
            with self.saboteur.sabotage_context([lambda: self.saboteur.patch_db_lock(db_cls)]):
                success, msg = self._run_sync(app, "29.03.2024")
                zombies = self._check_zombies()
                if not success and "locked" in msg.lower():
                    self.log_result(m, "PASS", f"Caught DB Lock gracefully. Zombies: {zombies}")
                else:
                    self.log_result(m, "FAIL", f"Unexpected result: {msg}. Zombies: {zombies}")
        except Exception as e: self.log_result(m, "FAIL", str(e))

    def _run_mission_2(self, app_cls):
        m = "Mission 2: Parallel Chaos"
        try:
            app = self._init_app(app_cls)
            results = []
            threads = []
            for i in range(5):
                t = threading.Thread(target=lambda: results.append(self._run_sync(app, "29.03.2024")))
                threads.append(t)
                t.start()
            for t in threads: t.join(timeout=30)
            
            zombies = self._check_zombies()
            report = self.harness.env_dir / "Final_Report.xlsx"
            if report.exists():
                wb = openpyxl.load_workbook(report)
                wb.close()
                self.log_result(m, "PASS", f"Report exists and openable after race. Zombies: {zombies}")
            else:
                self.log_result(m, "FAIL", f"Report missing. Zombies: {zombies}")
        except Exception as e: self.log_result(m, "FAIL", str(e))

    def _run_mission_3_4(self, app_cls):
        m = "Mission 3 & 4: Toxic Data"
        try:
            source = Path(self.harness.env_dir / "source")
            self.generator.generate_double_header(source / "Toxic" / "dh.xlsx")
            self.generator.generate_extreme_math(source / "Toxic" / "em.xlsx")
            
            app = self._init_app(app_cls)
            success, msg = self._run_sync_all(app)
            
            zombies = self._check_zombies()
            report = self.harness.env_dir / "Final_Report.xlsx"
            if not report.exists():
                self.log_result(m, "FAIL", "Report missing after toxic data parsing")
                return

            wb = openpyxl.load_workbook(report, data_only=True)
            billion_ok = False
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    if any(isinstance(v, (int, float)) and abs(v - 9999999999.99) < 0.1 for v in row):
                        billion_ok = True; break
            wb.close()
            
            if billion_ok: self.log_result(m, "PASS", f"Billion accuracy OK. Zombies: {zombies}")
            else: self.log_result(m, "FAIL", f"Billion value not found. Zombies: {zombies}")
        except Exception as e: self.log_result(m, "FAIL", str(e))

    def _init_app(self, app_cls):
        H = self.harness
        cc_cls = H.import_class("src.controllers.config_controller", "ConfigController")
        cc = cc_cls(str(H.env_dir / "config.yaml"))
        cfg = cc.config
        ing = H.import_class("src.ingestion", "IngestionEngine")(cfg.get('sh1', {}).get('markers', {}))
        db = H.import_class("src.sqlite_manager", "SQLiteManager")(cfg['database']['path'], cfg['database']['schema_path'], cfg)
        val = H.import_class("src.logic_service", "Validator")(cfg)
        ls = H.import_class("src.logic_service", "LogicService")(db, cfg)
        wr = H.import_class("src.writer", "MasterWriter")(cfg)
        return app_cls(cc, ing, db, val, ls, wr)

    def _run_sync(self, app, date_str):
        evt = threading.Event()
        res = [False, ""]
        def cb(s, m, p): res[0], res[1] = s, m; evt.set()
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        # Need to refresh status first to cache employees
        evt_refresh = threading.Event()
        app.refresh_status(dt, lambda p: None, lambda d, m, r: evt_refresh.set())
        evt_refresh.wait(timeout=10)
        app.run_consolidation(dt, lambda p: None, cb)
        evt.wait(timeout=30)
        return res[0], res[1]

    def _run_sync_all(self, app):
        evt = threading.Event()
        res = [False, ""]
        def cb(s, m, p): res[0], res[1] = s, m; evt.set()
        app.run_consolidation_all_dates(lambda p: None, cb)
        evt.wait(timeout=30)
        return res[0], res[1]

    def print_summary(self):
        print("\n" + "="*80)
        print(f"{'Mission':<40} | {'Status':<10} | {'Reason'}")
        print("-" * 80)
        for r in self.results:
            print(f"{r['Mission']:<40} | {r['Status']:<10} | {r['Reason']}")
        print("="*80 + "\n")

def run_all_missions():
    harness = HarnessEnv()
    runner = MissionRunner(harness)
    runner.run_all_missions()

if __name__ == "__main__":
    run_all_missions()
