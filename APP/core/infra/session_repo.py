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


def _log_wal_size(db_path: Path, logger: logging.Logger) -> None:
    wal_path = Path(str(db_path) + "-wal")
    if wal_path.exists():
        size_mb = wal_path.stat().st_size / (1024 * 1024)
        if size_mb > 1:
            logger.info("WAL file size: %.1f MB", size_mb)
        if size_mb > 100:
            logger.warning(
                "WAL file is %.1f MB — exceeds 100 MB threshold. "
                "Consider increasing wal_autocheckpoint or running "
                "manual checkpoints more frequently.",
                size_mb,
            )


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
                conn.execute("BEGIN IMMEDIATE")
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
                conn.execute("BEGIN IMMEDIATE")
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

    def save_template_errors_batch(
        self, session_id: str, errors: List[Dict[str, Any]]
    ) -> None:
        if not errors:
            return

        def _save():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.executemany(
                    """INSERT INTO template_errors 
                       (session_id, file_path, sheet_name, row_index, error_type, details, raw_data) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [
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
                        )
                        for error_info in errors
                    ],
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self._execute_with_retry(_save)

    def get_template_errors(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM template_errors WHERE session_id = ? ORDER BY file_path, row_index",
                    (session_id,),
                )
            ]
        finally:
            conn.close()

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
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
        finally:
            conn.close()

    def list_recent_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent sessions for the history tab (UX-008).

        Each row includes session_id, created_at, status, and parsed
        metadata (session_type, target_date, etc.). Joined with
        source_files counts so the user can see how many files were
        processed per session.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT s.session_id, s.created_at, s.status, s.metadata, "
                "(SELECT COUNT(*) FROM source_files sf WHERE sf.session_id = s.session_id) AS file_count "
                "FROM sessions s "
                "ORDER BY s.created_at DESC "
                "LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                meta = {}
                try:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                except (json.JSONDecodeError, TypeError):
                    pass
                result.append({
                    "session_id": row["session_id"],
                    "created_at": row["created_at"],
                    "status": row["status"],
                    "session_type": meta.get("session_type", ""),
                    "target_date": meta.get("target_date", ""),
                    "start_date": meta.get("start_date", ""),
                    "end_date": meta.get("end_date", ""),
                    "file_count": row["file_count"],
                })
            return result
        finally:
            conn.close()

    def update_session_status(self, session_id: str, status: str) -> None:
        def _update():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
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
                conn.execute("BEGIN IMMEDIATE")
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
        # Log WAL file size before checkpoint
        _log_wal_size(self.db_path, self.logger)
        # Run a WAL checkpoint to flush the WAL file back into the main
        # database — keeps the WAL from growing unboundedly between runs.
        try:
            conn = self._get_connection()
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
        except Exception as e:
            self.logger.warning("WAL checkpoint failed (non-fatal): %s", e)
        self.source_file_repo.close()
        self.staging_repo.close()
        try:
            unclean_file = self.db_path.with_name(self.db_path.name + ".unclean")
            if unclean_file.exists():
                unclean_file.unlink()
        except Exception as e:
            self.logger.warning("Failed to remove unclean shutdown flag: %s", e)

    def get_file_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        return self.source_file_repo.get_file_cache(file_path)

    def save_file_cache(
        self,
        file_path: str,
        mtime: float,
        size: int,
        dates: List[str],
        fingerprint: str | None = None,
    ) -> None:
        self.source_file_repo.save_file_cache(
            file_path, mtime, size, dates, fingerprint=fingerprint
        )

    def get_row_cache(
        self, file_path: str, mtime: float, size: int, date_key: str
    ) -> Optional[List[Dict[str, Any]]]:
        return self.source_file_repo.get_row_cache(file_path, mtime, size, date_key)

    def save_row_cache(
        self,
        file_path: str,
        mtime: float,
        size: int,
        date_key: str,
        rows: List[Dict[str, Any]],
    ) -> None:
        self.source_file_repo.save_row_cache(file_path, mtime, size, date_key, rows)

    def get_discovery_cache(self, roots_key: str) -> Optional[List[Dict[str, Any]]]:
        return self.source_file_repo.get_discovery_cache(roots_key)

    def save_discovery_cache(self, roots_key: str, files: List[Dict[str, Any]]) -> None:
        self.source_file_repo.save_discovery_cache(roots_key, files)

    def purge_old_sessions(self, max_age_days: int = 30) -> int:
        """Delete sessions older than ``max_age_days`` and their dependent rows.

        Returns the number of sessions deleted. Called automatically on
        startup (see ``AppController.__init__``) so the cache.db does not
        grow unboundedly across months of daily use (TD-019).

        NB: db_schema.sql declares the foreign keys
        ``source_files.session_id → sessions``,
        ``staging_data.file_id → source_files`` and
        ``template_errors.session_id → sessions`` WITHOUT ``ON DELETE
        CASCADE``. Relying on a cascade therefore raised
        ``FOREIGN KEY constraint failed`` on the customer's PC where the
        schema predates that assumption. We delete the dependent rows in
        dependency order (children first) inside one transaction so the
        ``DELETE FROM sessions`` at the end never violates a constraint.
        """
        if max_age_days <= 0:
            return 0

        cutoff = f"-{int(max_age_days)} days"

        def _purge():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                # Собираем ID старых сессий (завершённых) до удаления.
                rows = conn.execute(
                    "SELECT session_id FROM sessions "
                    "WHERE created_at < datetime('now', ?) "
                    "AND status IN ('completed', 'failed', 'cancelled')",
                    (cutoff,),
                ).fetchall()
                old_ids = [r[0] for r in rows]
                if not old_ids:
                    conn.commit()
                    return 0
                placeholders = ",".join("?" for _ in old_ids)

                # 1. template_errors → по session_id напрямую.
                conn.execute(
                    f"DELETE FROM template_errors WHERE session_id IN ({placeholders})",
                    old_ids,
                )
                # 2. source_files (нужны их id) → staging_data по file_id.
                file_rows = conn.execute(
                    f"SELECT id FROM source_files WHERE session_id IN ({placeholders})",
                    old_ids,
                ).fetchall()
                file_ids = [r[0] for r in file_rows]
                if file_ids:
                    file_ph = ",".join("?" for _ in file_ids)
                    conn.execute(
                        f"DELETE FROM staging_data WHERE file_id IN ({file_ph})",
                        file_ids,
                    )
                # 3. source_files (теперь orphan-free).
                conn.execute(
                    f"DELETE FROM source_files WHERE session_id IN ({placeholders})",
                    old_ids,
                )
                # 4. consolidated_results → по session_id (если таблица есть).
                conn.execute(
                    f"DELETE FROM consolidated_results WHERE session_id IN ({placeholders})",
                    old_ids,
                )
                # 5. Наконец — сами сессии.
                cursor = conn.execute(
                    f"DELETE FROM sessions WHERE session_id IN ({placeholders})",
                    old_ids,
                )
                deleted = cursor.rowcount
                conn.commit()
                if deleted > 0:
                    self.logger.info(
                        "Purged %d old sessions (older than %d days)",
                        deleted,
                        max_age_days,
                    )
                return deleted
            except Exception:
                conn.rollback()
                self.logger.warning("purge_old_sessions failed", exc_info=True)
                return 0
            finally:
                conn.close()

        return self._execute_with_retry(_purge)


SQLiteManager = SessionRepository
