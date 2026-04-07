"""Employee List ViewModel — состояние и логика списка сотрудников."""
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from pathlib import Path
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EmployeeStatus:
    """Статус одного сотрудника."""
    name: str
    status_text: str  # "🟢 ГОТОВО", "🔴 НЕТ ФАЙЛА", etc
    path_text: str     # "file.xlsx" или "[3 файлов]"
    tag: str           # "ready", "missing", "partial"

    def to_tuple(self) -> tuple:
        return (self.name, self.status_text, self.path_text, self.tag)


class EmployeeListViewModel:
    """ViewModel для списка сотрудников.
    
    Отделяет логику:
    - Фильтрация по поисковому запросу
    - Сортировка
    - Подсчёт статистики
    - Определение должников
    """

    def __init__(self) -> None:
        self._all_employees: List[EmployeeStatus] = []
        self._employees_map: Dict[str, List[Dict[str, Any]]] = {}
        self._search_query: str = ""
        self._rename_detected: bool = False
        self._on_update: Optional[Callable] = None

    def set_update_callback(self, callback: Callable) -> None:
        """Установить callback при обновлении данных."""
        self._on_update = callback

    # === Commands (действия из UI) ===

    def refresh(self, app_controller, selected_date: datetime, on_progress: Callable[[float], None]) -> None:
        """Запустить обновление статуса сотрудников."""
        def on_complete(data: List[tuple], employees_map: Dict, rename_detected: bool) -> None:
            self._all_employees = [
                EmployeeStatus(name=n, status_text=s, path_text=p, tag=t)
                for n, s, p, t in data
            ]
            self._employees_map = employees_map
            self._rename_detected = rename_detected

            if rename_detected:
                app_controller.config_controller.save_config()

            if self._on_update:
                self._on_update()

        app_controller.refresh_status(selected_date, on_progress, on_complete)

    def add_employee(self, config_controller, name: str) -> None:
        """Добавить нового сотрудника."""
        config_controller.add_employee(name)

    def delete_employee(self, config_controller, name: str) -> None:
        """Удалить сотрудника."""
        config_controller.delete_employee(name)

    def attach_files(self, config_controller, name: str, paths: List[str]) -> None:
        """Прикрепить файлы к сотруднику."""
        config_controller.attach_files(name, paths)

    def get_master_path(self, config_controller) -> Optional[Path]:
        """Получить путь к мастер-файлу."""
        p = Path(config_controller.get_paths().get('master_file', 'Master_Report.xlsx'))
        if not p.is_absolute():
            p = Path(config_controller.config_path).parent / p
        return p

    # === Queries (состояние для UI) ===

    @property
    def search_query(self) -> str:
        return self._search_query

    @search_query.setter
    def search_query(self, value: str) -> None:
        self._search_query = value.lower()

    def get_filtered_employees(self) -> List[EmployeeStatus]:
        """Получить отфильтрованный список по поисковому запросу."""
        if not self._search_query:
            return self._all_employees

        return [
            emp for emp in self._all_employees
            if any(self._search_query in x.lower() for x in (emp.name, emp.status_text, emp.path_text))
        ]

    def get_ready_count(self) -> int:
        """Количество готовых сотрудников."""
        return sum(1 for e in self._all_employees if "🟢 ГОТОВО" in e.status_text)

    def get_total_count(self) -> int:
        """Общее количество."""
        return len(self._all_employees)

    def get_missing_names(self) -> List[str]:
        """Имена должников."""
        return [e.name for e in self._all_employees if "🟢 ГОТОВО" not in e.status_text]

    @property
    def rename_detected(self) -> bool:
        return self._rename_detected

    @property
    def employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        return self._employees_map

    def get_selected_employee_path(self, selected_name: Optional[str]) -> Optional[str]:
        """Получить путь выбранного сотрудника."""
        if not selected_name:
            return None
        metas = self._employees_map.get(selected_name, [])
        if not metas:
            return None
        meta = metas[0]
        return meta['path'] if isinstance(meta, dict) else meta

    def get_progress_percent(self) -> float:
        """Процент готовности (для прогресс-бара)."""
        if not self._all_employees:
            return 0.0
        return (self.get_ready_count() / self.get_total_count()) * 100
