from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path


class IDataSource(ABC):
    """Interface for scanning and reading source Excel reports."""

    @abstractmethod
    def scan_directory(self, root_path: Path) -> List[Dict[str, Any]]:
        """Scans directory and returns list of candidate file metadata."""
        pass

    @abstractmethod
    def read_file(
        self, file_path: Path, strict_io: bool = False
    ) -> List[Dict[str, Any]]:
        """Reads Excel file and returns raw rows.

        strict_io=True may raise I/O errors after retry exhaustion;
        strict_io=False should degrade to [] on transient read failures.
        """
        pass

    @abstractmethod
    def get_available_dates(
        self,
        file_path: Path,
        remote_mtime: float | None = None,
        remote_size: int | None = None,
    ) -> List[str]:
        """Returns detected sheet dates from a source workbook.

        Optional remote_mtime/remote_size allow callers to avoid duplicate
        network stat calls when metadata is already known.
        """
        pass


class IPersistence(ABC):
    """Interface for database operations (SQLite)."""

    @abstractmethod
    def init_db(self) -> None:
        """Initializes database tables and indexes."""
        pass

    @abstractmethod
    def save_session(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """Saves session start information."""
        pass

    @abstractmethod
    def save_file_metadata(
        self, session_id: str, files: List[Dict[str, Any]]
    ) -> List[int]:
        """Saves file metadata and returns generated IDs."""
        pass

    @abstractmethod
    def save_staging_data(self, file_id: int, rows: List[Dict[str, Any]]) -> None:
        """Saves raw rows into staging_data table."""
        pass

    @abstractmethod
    def save_template_error(self, session_id: str, error_info: Dict[str, Any]) -> None:
        """Saves a template violation or warning."""
        pass

    def save_template_errors_batch(
        self, session_id: str, errors: List[Dict[str, Any]]
    ) -> None:
        """Saves a batch of template violations or warnings."""
        for error_info in errors:
            self.save_template_error(session_id, error_info)



    @abstractmethod
    def get_template_errors(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves all template errors for a session."""
        pass

    @abstractmethod
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Retrieves session progress and stats."""
        pass

    @abstractmethod
    def update_session_status(self, session_id: str, status: str) -> None:
        """Updates session lifecycle status."""
        pass

    @abstractmethod
    def update_file_status(
        self, file_id: int, status: str, error_message: Optional[str] = None
    ) -> None:
        """Updates file processing status and optional error message."""
        pass

    @abstractmethod
    def get_consolidated_data(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves aggregated data grouped by employee and date."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes database connections."""
        pass


class IValidator(ABC):
    """Interface for row-level validation and junk detection."""

    @abstractmethod
    def validate_row(self, row: Dict[str, Any]) -> bool:
        """Returns True if row is valid, False otherwise."""
        pass

    @abstractmethod
    def get_errors(self) -> List[str]:
        """Returns list of validation errors for the last processed row."""
        pass


class ILogicService(ABC):
    """Interface for financial transformations and consolidation."""

    @abstractmethod
    def apply_financial_rules(
        self, raw_rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Applies commissions, returns, and other business rules."""
        pass

    @abstractmethod
    def consolidate(self, session_id: str) -> List[Dict[str, Any]]:
        """Performs SQL-based aggregation for the final report."""
        pass


class IExporter(ABC):
    """Interface for generating final Excel master reports."""

    @abstractmethod
    def write_report(self, data: List[Dict[str, Any]], output_path: Path) -> bool:
        """Writes consolidated data to the target Excel file with formatting."""
        pass
