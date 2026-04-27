import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from core.domain import IPersistence
from core.infra.db_connection import SQLiteConnectionManager, DecimalEncoder
from core.infra.db_connection import sanitize_data as sanitize_data
from core.infra.source_file_repo import SourceFileRepository
from core.infra.staging_repo import DBWriterThread as DBWriterThread
from core.infra.staging_repo import StagingDataRepository


class SessionRepository(IPersistence):
    def __init__(self, db_path: str, schema_path: str, config: Dict[str, Any]):
        self.connection_manager = SQLiteConnectionManager(Path(db_path), config)
        self.connection_manager.init_db(Path(schema_path))

        self.source_file_repo = SourceFileRepository(self.connection_manager)
        self.staging_repo = StagingDataRepository(self.connection_manager)
        self.logger = logging.getLogger(__name__)

        self.db_path = Path(db_path)
        self.writer_thread = self.staging_repo.writer_thread
        self.write_queue = self.staging_repo.write_queue

    def init_db(self) -> None:
        pass

    def _get_connection(self):
        return self.connection_manager.get_connection()

    def _execute_with_retry(self, func, *args, **kwargs):
        return self.connection_manager.execute_with_retry(func, *args, **kwargs)

    def save_session(self, session_id: str, metadata: Dict[str, Any]) -> None:
        def _save():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute(
                    "INSERT INTO sessions (session_id, metadata) VALUES (?, ?)",
                    (
                        session_id,
                        json.dumps(metadata, ensure_ascii=False, cls=DecimalEncoder),
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self._execute_with_retry(_save)

    def save_template_error(self, session_id: str, error_info: Dict[str, Any]) -> None:
        def _save():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute(
                    """INSERT INTO template_errors 
                       (session_id, file_path, sheet_name, row_index, error_type, details, raw_data) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        error_info.get("file_path"),
                        error_info.get("sheet_name"),
                        error_info.get("row_index"),
                        error_info.get("error_type"),
                        error_info.get("details"),
                        json.dumps(
                            error_info.get("raw_data"),
                            ensure_ascii=False,
                            cls=DecimalEncoder,
                        ),
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self._execute_with_retry(_save)

    def get_template_errors(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM template_errors WHERE session_id = ? ORDER BY file_path, row_index",
                    (session_id,),
                )
            ]

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row:
                return {}
            stats = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM source_files WHERE session_id = ? GROUP BY status",
                (session_id,),
            ).fetchall()
            return {
                "session_id": row["session_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "file_stats": {s["status"]: s["cnt"] for s in stats},
            }

    def update_session_status(self, session_id: str, status: str) -> None:
        def _update():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute(
                    "UPDATE sessions SET status = ? WHERE session_id = ?",
                    (status, session_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self._execute_with_retry(_update)

    def update_file_status(
        self, file_id: int, status: str, error_message: Optional[str] = None
    ) -> None:
        def _update():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute(
                    "UPDATE source_files SET status = ?, error_message = ? WHERE id = ?",
                    (status, error_message, file_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self._execute_with_retry(_update)

    def save_file_metadata(
        self, session_id: str, files: List[Dict[str, Any]]
    ) -> List[int]:
        return self.source_file_repo.save_file_metadata(session_id, files)

    def save_staging_data(self, file_id: int, rows: List[Dict[str, Any]]) -> None:
        self.staging_repo.save_staging_data(file_id, rows)

    def get_consolidated_data(self, session_id: str) -> List[Dict[str, Any]]:
        return self.staging_repo.get_consolidated_data(session_id)

    def wait_for_writes(self) -> None:
        self.source_file_repo.wait_for_writes()
        self.staging_repo.wait_for_writes()

    def close(self) -> None:
        self.logger.info("Closing database manager.")
        self.source_file_repo.close()
        self.staging_repo.close()

    def get_file_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        return self.source_file_repo.get_file_cache(file_path)

    def save_file_cache(
        self, file_path: str, mtime: float, size: int, dates: List[str]
    ) -> None:
        self.source_file_repo.save_file_cache(file_path, mtime, size, dates)


SQLiteManager = SessionRepository
