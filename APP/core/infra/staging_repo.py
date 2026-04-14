import sqlite3
import json
import logging
import decimal
import datetime
import threading
import queue
from typing import List, Dict, Any
from pathlib import Path
from core.infra.db_connection import SQLiteConnectionManager, sanitize_data


class DBWriterThread(threading.Thread):
    """Background thread that batches staging data writes to SQLite."""

    BATCH_SIZE = 10
    BATCH_TIMEOUT = 0.5

    def __init__(self, connection_manager: SQLiteConnectionManager, q: queue.Queue):
        super().__init__(name="DBWriterThread", daemon=True)
        self.connection_manager = connection_manager
        self.q = q
        self.running = True
        self.logger = logging.getLogger(__name__)

    def run(self):
        while self.running or not self.q.empty():
            batch = []
            try:
                item = self.q.get(timeout=self.BATCH_TIMEOUT)
                if item is None:
                    self.q.task_done()
                    break
                batch.append(item)
                while len(batch) < self.BATCH_SIZE:
                    try:
                        next_item = self.q.get_nowait()
                        if next_item is None:
                            self.q.task_done()
                            # Process remaining batch before exiting
                            if batch:
                                self._process_batch(batch)
                                for _ in batch:
                                    self.q.task_done()
                            return
                        batch.append(next_item)
                    except queue.Empty:
                        break
                self._process_batch(batch)
                for _ in batch:
                    self.q.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error in DBWriterThread: {e}", exc_info=True)
                # Mark batch items as done to avoid blocking join()
                for _ in batch:
                    try:
                        self.q.task_done()
                    except ValueError:
                        pass

    def _process_batch(self, batch):
        sql = "INSERT INTO staging_data (file_id, row_index, raw_content_json, date_val, amount, employee_name, source_type) VALUES (?, ?, ?, ?, ?, ?, ?)"
        all_data = []
        for file_id, rows in batch:
            for r in rows:
                amt_raw = r.get("amount", 0)
                try:
                    amt_val = decimal.Decimal(str(amt_raw))
                except (decimal.InvalidOperation, TypeError, ValueError):
                    amt_val = decimal.Decimal("0.00")

                all_data.append(
                    (
                        file_id,
                        r.get("_row_index"),
                        json.dumps(sanitize_data(r), ensure_ascii=False),
                        r.get("date"),
                        amt_val,
                        r.get("employee_name"),
                        r.get("source_type"),
                    )
                )

        if not all_data:
            return

        def _save():
            conn = self.connection_manager.get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.executemany(sql, all_data)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self.connection_manager.execute_with_retry(_save)

    def stop(self):
        self.running = False
        self.q.put(None)


class StagingDataRepository:
    def __init__(self, connection_manager: SQLiteConnectionManager):
        self.connection_manager = connection_manager
        self.write_queue = queue.Queue()
        self.writer_thread = DBWriterThread(self.connection_manager, self.write_queue)
        self.writer_thread.start()

    def save_staging_data(self, file_id: int, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        self.write_queue.put((file_id, rows))

    def get_consolidated_data(self, session_id: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT staging_data.raw_content_json, staging_data.employee_name, 
                   staging_data.date_val, staging_data.row_index, source_files.file_path 
            FROM staging_data 
            JOIN source_files ON staging_data.file_id = source_files.id 
            WHERE source_files.session_id = ? 
            ORDER BY staging_data.employee_name, staging_data.date_val
        """
        results = []
        with self.connection_manager.get_connection() as conn:
            for row in conn.execute(sql, (session_id,)):
                data = json.loads(row["raw_content_json"])
                data.update(
                    {
                        "employee_name": row["employee_name"],
                        "date": row["date_val"],
                        "_source_info": f"{Path(row['file_path']).name} : Строка {row['row_index']}",
                    }
                )
                results.append(data)
        return results

    def close(self):
        self.writer_thread.stop()
        self.writer_thread.join()

    def wait_for_writes(self):
        self.write_queue.join()
