import json
import logging
import threading
import queue
from typing import List, Dict, Any, Optional
from core.infra.db_connection import SQLiteConnectionManager


class SourceFileRepository:
    def __init__(self, connection_manager: SQLiteConnectionManager):
        self.connection_manager = connection_manager
        self.write_queue = queue.Queue()
        self.writer_thread = threading.Thread(
            target=self._writer_loop, name="SourceFileWriter", daemon=True
        )
        self.writer_thread.start()
        self._logger = logging.getLogger(__name__)

    def _writer_loop(self):
        while True:
            try:
                item = self.write_queue.get(timeout=0.1)
                if item is None:
                    break
                fn, args = item
                self.connection_manager.execute_with_retry(fn, *args)
                self.write_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self._logger.error(f"SourceFileWriter error: {e}", exc_info=True)
                self.write_queue.task_done()

    def save_file_metadata(
        self, session_id: str, files: List[Dict[str, Any]]
    ) -> List[int]:
        def _save():
            ids = []
            conn = self.connection_manager.get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                for f in files:
                    file_hash = f.get("hash")
                    if file_hash is None:
                        file_hash = f.get("fp")

                    inode = f.get("inode")
                    if inode is None:
                        inode = f.get("id")

                    cur = conn.execute(
                        "INSERT INTO source_files (session_id, file_path, file_hash, inode, status) VALUES (?, ?, ?, ?, ?)",
                        (
                            session_id,
                            f["path"],
                            file_hash,
                            inode,
                            f.get("status", "pending"),
                        ),
                    )
                    ids.append(cur.lastrowid)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return ids

        return self.connection_manager.execute_with_retry(_save)

    def get_file_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        conn = self.connection_manager.get_connection()
        try:
            row = conn.execute(
                "SELECT mtime, size, dates_json FROM file_cache WHERE file_path = ?",
                (file_path,),
            ).fetchone()
            if row:
                raw_payload = json.loads(row["dates_json"])
                if isinstance(raw_payload, dict):
                    dates = raw_payload.get("dates", [])
                    cache_version = int(raw_payload.get("cache_version", 1) or 1)
                    fingerprint = raw_payload.get("fingerprint")
                else:
                    dates = raw_payload
                    cache_version = 1
                    fingerprint = None
                if not isinstance(dates, list):
                    dates = []
                return {
                    "mtime": row["mtime"],
                    "size": row["size"],
                    "dates": dates,
                    "cache_version": cache_version,
                    "fingerprint": fingerprint if isinstance(fingerprint, str) else None,
                }
            return None
        finally:
            conn.close()

    def save_file_cache(
        self,
        file_path: str,
        mtime: float,
        size: int,
        dates: List[str],
        fingerprint: str | None = None,
    ) -> None:
        def _save():
            conn = self.connection_manager.get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute(
                    "INSERT OR REPLACE INTO file_cache (file_path, mtime, size, dates_json, last_updated) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (
                        file_path,
                        mtime,
                        size,
                        json.dumps(
                            {
                                "cache_version": 4,
                                "dates": dates,
                                "fingerprint": fingerprint,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self.write_queue.put((_save, ()))

    def close(self):
        self.write_queue.put(None)
        self.writer_thread.join()

    def wait_for_writes(self):
        self.write_queue.join()
