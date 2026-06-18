"""Repository for customer aliases — manages reconciliation name mappings.

Бухгалтеры вручную указывают соответствия между заказчиками со стороны
кураторов (master_customer) и заказчиками со стороны РСЧ (rsch_customer).
Эти алиасы используются сверкой для автоматического сопоставления строк,
где названия отличаются (сокращения, разные формы юр. лиц и т.д.).
"""

import logging
from typing import Dict, List, Optional, Set

from core.infra.db_connection import SQLiteConnectionManager

logger = logging.getLogger(__name__)


class CustomerAlias:
    """One alias entry: master_customer ↔ rsch_customer mapping."""

    __slots__ = ("id", "master_customer", "rsch_customer", "notes", "created_at", "updated_at")

    def __init__(
        self,
        id: Optional[int],
        master_customer: str,
        rsch_customer: str,
        notes: str = "",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> None:
        self.id = id
        self.master_customer = master_customer.strip()
        self.rsch_customer = rsch_customer.strip()
        self.notes = notes or ""
        self.created_at = created_at
        self.updated_at = updated_at

    def __repr__(self) -> str:
        return f"CustomerAlias({self.master_customer!r} ↔ {self.rsch_customer!r})"


class CustomerAliasRepository:
    """CRUD repository for customer_aliases table.

    Caches aliases in memory after first load; call ``reload()`` after
    bulk edits to refresh the cache without restarting the app.
    """

    def __init__(self, connection_manager: SQLiteConnectionManager) -> None:
        self._conn_mgr = connection_manager
        self._cache: Optional[Dict[str, Set[str]]] = None

    # ── Cache management ────────────────────────────────────

    def reload(self) -> None:
        """Force reload of alias cache from DB."""
        self._cache = None
        self._ensure_cache()

    def _ensure_cache(self) -> Dict[str, Set[str]]:
        if self._cache is not None:
            return self._cache
        conn = self._conn_mgr.get_connection()
        try:
            rows = conn.execute(
                "SELECT master_customer, rsch_customer FROM customer_aliases"
            ).fetchall()
        finally:
            conn.close()
        cache: Dict[str, Set[str]] = {}
        for row in rows:
            master = row["master_customer"].strip().lower()
            rsch = row["rsch_customer"].strip().lower()
            cache.setdefault(master, set()).add(rsch)
            cache.setdefault(rsch, set()).add(master)
        self._cache = cache
        logger.info("Loaded %d unique alias keys (%d pairs)", len(cache), len(rows))
        return cache

    # ── Matching (used by reconciliation) ───────────────────

    def is_alias(self, master_customer: str, rsch_customer: str) -> bool:
        """Return True if an explicit alias exists between the two customers.

        Comparison is case-insensitive and whitespace-normalised.
        """
        cache = self._ensure_cache()
        if not master_customer or not rsch_customer:
            return False
        master_norm = master_customer.strip().lower()
        rsch_norm = rsch_customer.strip().lower()
        if master_norm == rsch_norm:
            return True
        aliases = cache.get(master_norm)
        return bool(aliases and rsch_norm in aliases)

    def get_all_aliases(self) -> List[CustomerAlias]:
        """Return all alias entries (for UI display)."""
        conn = self._conn_mgr.get_connection()
        try:
            rows = conn.execute(
                "SELECT id, master_customer, rsch_customer, notes, created_at, updated_at "
                "FROM customer_aliases ORDER BY master_customer COLLATE NOCASE"
            ).fetchall()
        finally:
            conn.close()
        return [
            CustomerAlias(
                id=row["id"],
                master_customer=row["master_customer"],
                rsch_customer=row["rsch_customer"],
                notes=row["notes"] or "",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    # ── CRUD ────────────────────────────────────────────────

    def add_alias(self, master_customer: str, rsch_customer: str, notes: str = "") -> int:
        """Insert a new alias. Returns the new row id.

        Raises ValueError if the alias already exists.
        """
        master = master_customer.strip()
        rsch = rsch_customer.strip()
        if not master or not rsch:
            raise ValueError("И заказчик куратора, и заказчик РСЧ должны быть заполнены")
        if master.lower() == rsch.lower():
            raise ValueError("Заказчики идентичны — алиас не нужен")
        conn = self._conn_mgr.get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO customer_aliases (master_customer, rsch_customer, notes) "
                "VALUES (?, ?, ?)",
                (master, rsch, notes),
            )
            conn.commit()
            self._cache = None  # invalidate cache
            logger.info("Added alias: %r ↔ %r", master, rsch)
            return int(cursor.lastrowid)
        except Exception as e:
            conn.rollback()
            if "UNIQUE" in str(e):
                raise ValueError(f"Алиас '{master}' ↔ '{rsch}' уже существует") from e
            raise
        finally:
            conn.close()

    def update_alias(
        self,
        alias_id: int,
        master_customer: str,
        rsch_customer: str,
        notes: str = "",
    ) -> None:
        """Update an existing alias by id."""
        master = master_customer.strip()
        rsch = rsch_customer.strip()
        if not master or not rsch:
            raise ValueError("И заказчик куратора, и заказчик РСЧ должны быть заполнены")
        conn = self._conn_mgr.get_connection()
        try:
            conn.execute(
                "UPDATE customer_aliases SET master_customer = ?, rsch_customer = ?, "
                "notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (master, rsch, notes, alias_id),
            )
            conn.commit()
            self._cache = None
            logger.info("Updated alias id=%d", alias_id)
        except Exception as e:
            conn.rollback()
            if "UNIQUE" in str(e):
                raise ValueError(
                    f"Алиас '{master}' ↔ '{rsch}' уже существует (дубликат)"
                ) from e
            raise
        finally:
            conn.close()

    def delete_alias(self, alias_id: int) -> None:
        """Delete an alias by id."""
        conn = self._conn_mgr.get_connection()
        try:
            conn.execute("DELETE FROM customer_aliases WHERE id = ?", (alias_id,))
            conn.commit()
            self._cache = None
            logger.info("Deleted alias id=%d", alias_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
