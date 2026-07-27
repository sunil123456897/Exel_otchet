import json
import logging
import decimal
import threading
import queue
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
from core.infra.db_connection import SQLiteConnectionManager, sanitize_data


class DBWriterThread(threading.Thread):
    """Background thread that batches staging data writes to SQLite."""

    BATCH_SIZE = 500
    BATCH_TIMEOUT = 0.5

    def __init__(
        self,
        connection_manager: SQLiteConnectionManager,
        q: "queue.Queue[Any]",
        error_callback: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        super().__init__(name="DBWriterThread", daemon=True)
        self.connection_manager = connection_manager
        self.q = q
        self.running = True
        self.logger = logging.getLogger(__name__)
        self.error_callback = error_callback

    _WRITE_RETRIES = 1  # One retry on transient failure before giving up

    def run(self) -> None:
        while self.running or not self.q.empty():
            batch: List[Any] = []
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
                                self._process_batch_with_retry(batch)
                                for _ in batch:
                                    self.q.task_done()
                            return
                        batch.append(next_item)
                    except queue.Empty:
                        break
                self._process_batch_with_retry(batch)
                for _ in batch:
                    self.q.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error in DBWriterThread: {e}", exc_info=True)
                if self.error_callback is not None:
                    self.error_callback(e)
                # Mark batch items as done to avoid blocking join()
                for _ in batch:
                    try:
                        self.q.task_done()
                    except ValueError:
                        pass

    def _process_batch_with_retry(self, batch: List[Any]) -> None:
        """Try to process a batch, retrying once on transient errors.

        Previously a single _process_batch failure silently dropped the
        entire batch — rows were lost even though task_done() was called,
        making wait_for_writes() return as if everything succeeded.
        The retry gives transient SQLite lock errors a second chance before
        the data is declared lost.
        """
        try:
            self._process_batch(batch)
            return
        except Exception as first_err:
            self.logger.warning(
                "Batch write failed (attempt 1/%d): %s. Retrying...",
                self._WRITE_RETRIES + 1, first_err,
            )
        # Retry once
        try:
            self._process_batch(batch)
            self.logger.info("Batch write succeeded on retry.")
            return
        except Exception as retry_err:
            self.logger.critical(
                "Batch write failed on retry too. %d rows LOST: %s",
                sum(len(rows) for _, rows in batch), retry_err,
                exc_info=True,
            )
            if self.error_callback is not None:
                self.error_callback(retry_err)
            raise

    def _process_batch(self, batch: List[Any]) -> None:
        sql = "INSERT INTO staging_data (file_id, row_index, raw_content_json, date_val, amount, employee_name, source_type) VALUES (?, ?, ?, ?, ?, ?, ?)"
        all_data: List[Any] = []
        for file_id, rows in batch:
            for r in rows:
                amt_raw = r.get("amount", 0)
                try:
                    amt_val = decimal.Decimal(str(amt_raw))
                except (decimal.InvalidOperation, TypeError, ValueError):
                    amt_val = decimal.Decimal("0.00")
                    try:
                        from core.domain.data_loss_log import record_loss
                        record_loss(
                            source=f"staging_repo:file_id={file_id}",
                            kind="numeric_coercion",
                            reason=f"amount field could not be parsed: {amt_raw!r}",
                            row_index=r.get("_row_index"),
                            field="amount",
                            original_value=amt_raw,
                        )
                    except Exception:
                        pass

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

        def _save() -> None:
            conn = self.connection_manager.get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.executemany(sql, all_data)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self.connection_manager.execute_with_retry(_save)

    def stop(self) -> None:
        self.running = False
        self.q.put(None)


class StagingDataRepository:
    def __init__(self, connection_manager: SQLiteConnectionManager):
        self.connection_manager = connection_manager
        self.write_queue: queue.Queue[Any] = queue.Queue()
        self._write_error: Optional[Exception] = None
        self._write_error_lock = threading.Lock()
        self.writer_thread = DBWriterThread(
            self.connection_manager,
            self.write_queue,
            error_callback=self._record_write_error,
        )
        self.writer_thread.start()

    def _record_write_error(self, error: Exception) -> None:
        with self._write_error_lock:
            if self._write_error is None:
                self._write_error = error

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
        conn = self.connection_manager.get_connection()
        try:
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
        finally:
            conn.close()
        return results

    def close(self) -> None:
        self.writer_thread.stop()
        self.writer_thread.join()

    def wait_for_writes(self) -> None:
        self.write_queue.join()
        with self._write_error_lock:
            if self._write_error is not None:
                err = self._write_error
                self._write_error = None
                raise err
