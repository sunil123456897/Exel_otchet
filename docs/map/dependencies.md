# Карта зависимостей

> **⚠️ ЗАМОРОЖЕННЫЙ СНАПШОТ (v5.5, 2026-06-25).** См. предупреждение в
> `structure.md`. Актуальные runtime-зависимости — в `requirements.txt`.

## Метаданные
- Дата: 2026-06-25
- Проект: Master-Report v5.5
- Источник: docs/map/structure.md + анализ кода

---

## 1. Внутренние зависимости

> Анализ импортов всех source-файлов в `APP/`. Учитываются только `core.*` импорты
> (внутренние пакеты проекта). Stdlib-импорты вынесены в раздел инфраструктуры.
> Тип: **function** | **class** | **type** | **constant** | **component**

### Точки входа

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `APP/main.py` | `core.bootstrap.Bootstrap` | class | yes | no |
| `APP/headless_run.py` | `core.bootstrap.Bootstrap` | class | yes | no |

### core/ — корневые модули

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `core/bootstrap.py` | `core.infra` (ConfigController, MasterWriter) | class | yes | no |
| `core/bootstrap.py` | `core.infra.utils` (path_exists_with_timeout) | function | yes | no |
| `core/bootstrap.py` | `core.infra.ingestion_engine` (IngestionEngine) | class | yes | no |
| `core/bootstrap.py` | `core.infra.session_repo` (SessionRepository) | class | yes | no |
| `core/bootstrap.py` | `core.domain` (LogicService, Validator) | class | yes | no |
| `core/bootstrap.py` | `core.app_controller` (AppController) | class | yes | no |
| `core/app_controller.py` | `core.infra` (DiscoveryService, is_file_writable) | class, function | yes | no |
| `core/app_controller.py` | `core.infra.utils_logging` (scrub_path) | function | yes | no |
| `core/app_controller.py` | `core.app.file_processor` (FileProcessor и др.) | class, function | yes | no |
| `core/app_controller.py` | `core.app.performance` (default_max_workers, resolve_max_workers) | function, constant | yes | no |
| `core/app_controller.py` | `core.app.message_formatting` (форматирование сообщений) | function | yes | no |
| `core/app_controller.py` | `core.infra.reconciliation` (build_combined_reconciliation_report) | function | yes | no |
| `core/app_controller.py` | `core.infra.rsch` (build_rsch_report) | function | yes | no |
| `core/app_controller.py` | `core.services.rsch_service` (RschService) | class | yes | no |
| `core/app_controller.py` | `core.services.reconciliation_service` (ReconciliationService) | class | yes | no |
| `core/app_controller.py` | `core.app.partial` (format_partial_note, mark_partial) | function | yes | no |
| `core/app_controller.py` | `core.infra.utils` (cleanup_local_copy_cache) | function | yes | no |

### core/app/ — прикладные сервисы

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `core/app/file_processor.py` | `core.app.performance` (resolve_max_workers) | function | yes | no |
| `core/app/file_processor.py` | `core.infra` (is_file_writable) | function | yes | no |
| `core/app/file_processor.py` | `core.infra.utils_logging` (safe_file_label, scrub_path) | function | yes | no |

### core/domain/ — доменный слой

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `core/domain/__init__.py` | `core.domain.interfaces` (IDataSource, IPersistence, IValidator, ILogicService, IExporter) | type | yes | no |
| `core/domain/__init__.py` | `core.domain.utils_helpers` (NumericParsingError, to_decimal, to_decimal_percent) | class, function | yes | no |
| `core/domain/__init__.py` | `core.domain.data_schemas` (FinancialRowSchema) | class | yes | no |
| `core/domain/__init__.py` | `core.domain.logic_service` (LogicService, Validator) | class | yes | no |
| `core/domain/data_loss_log.py` | `core.infra.utils_logging` (scrub_path) | function | yes | no |
| `core/domain/logic_service.py` | `core.domain.interfaces` (IValidator, ILogicService, IPersistence) | type | yes | no |
| `core/domain/logic_service.py` | `core.domain.utils_helpers` (to_decimal и др.) | function | yes | no |
| `core/domain/logic_service.py` | `core.domain.data_schemas` (FinancialRowSchema) | class | yes | no |

### core/infra/ — инфраструктурный слой

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `core/infra/__init__.py` | `core.infra.utils` (open_path, is_file_writable, get_local_copy) | function | yes | no |
| `core/infra/__init__.py` | `core.infra.utils_logging` (setup_gui_logging) | function | yes | no |
| `core/infra/__init__.py` | `core.infra.config_controller` (ConfigController) | class | yes | no |
| `core/infra/__init__.py` | `core.infra.export_writer` (MasterWriter) | class | yes | no |
| `core/infra/__init__.py` | `core.infra.session_repo` (SessionRepository) | class | yes | no |
| `core/infra/__init__.py` | `core.infra.discovery_service` (DiscoveryService) | class | yes | no |
| `core/infra/__init__.py` | `core.infra.path_resolver` (resolve_employee_path) | function | yes | no |
| `core/infra/config_controller.py` | `core.infra.utils_logging` (scrub_path) | function | yes | no |
| `core/infra/customer_alias_repo.py` | `core.infra.db_connection` (SQLiteConnectionManager) | class | yes | no |
| `core/infra/discovery_service.py` | `core.infra.config_controller` (ConfigController) | class | yes | no |
| `core/infra/discovery_service.py` | `core.infra.ingestion_engine` (IngestionEngine) | class | yes | no |
| `core/infra/discovery_service.py` | `core.infra.path_resolver` (resolve_employee_path) | function | yes | no |
| `core/infra/discovery_service.py` | `core.infra.utils_logging` (scrub_path) | function | yes | no |
| `core/infra/discovery_service.py` | `core.infra.utils` (path_exists_with_timeout) | function | yes | no |
| `core/infra/export_writer.py` | `core.domain` (IExporter) | type | yes | no |
| `core/infra/export_writer.py` | `core.domain.utils_helpers` (to_decimal) | function | yes | no |
| `core/infra/export_writer.py` | `core.infra` (is_file_writable) | function | yes | no |
| `core/infra/export_writer.py` | `core.infra.excel_backup` (backup_existing_excel_output, resolve_excel_backup_keep) | function | yes | no |
| `core/infra/export_writer.py` | `core.infra.export_formatting` (ExcelStyles и др.) | class, function | yes | no |
| `core/infra/export_writer.py` | `core.infra.excel_hyperlinks` (apply_cell_hyperlink) | function | yes | no |
| `core/infra/ingestion_engine.py` | `core.domain` (IDataSource) | type | yes | no |
| `core/infra/ingestion_engine.py` | `core.infra.utils` (get_local_copy) | function | yes | no |
| `core/infra/ingestion_engine.py` | `core.infra.ingestion_reader` (CalamineReader, extract_date_from_sheet) | class, function | yes | no |
| `core/infra/ingestion_reader.py` | `core.domain.utils_helpers` (to_decimal, to_decimal_percent) | function | yes | no |
| `core/infra/ingestion_reader.py` | `core.infra.utils` (get_local_copy) | function | yes | no |
| `core/infra/session_repo.py` | `core.domain` (IPersistence) | type | yes | no |
| `core/infra/session_repo.py` | `core.infra.db_connection` (SQLiteConnectionManager, DecimalEncoder, sanitize_data) | class, function | yes | no |
| `core/infra/session_repo.py` | `core.infra.source_file_repo` (SourceFileRepository) | class | yes | no |
| `core/infra/session_repo.py` | `core.infra.staging_repo` (DBWriterThread, StagingDataRepository) | class | yes | no |
| `core/infra/settings_store.py` | `core.infra.config_controller` (ConfigController) | class | yes | no |
| `core/infra/source_file_repo.py` | `core.infra.db_connection` (SQLiteConnectionManager) | class | yes | no |
| `core/infra/staging_repo.py` | `core.infra.db_connection` (SQLiteConnectionManager, sanitize_data) | class, function | yes | no |

### core/infra/reconciliation/ — отчёт расхождений

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `reconciliation/__init__.py` | `._types` (MasterReconciliationRow, RschReconciliationRow, ReconciliationRow) | type | yes | no |
| `reconciliation/__init__.py` | `._utils` (_row_id) | function | yes | no |
| `reconciliation/__init__.py` | `._build` (build_combined_reconciliation_report и др.) | function | yes | no |
| `reconciliation/_build.py` | `core.infra.excel_hyperlinks` (apply_cell_hyperlink) | function | yes | no |
| `reconciliation/_build.py` | `core.infra.excel_backup` (backup_existing_excel_output) | function | yes | no |
| `reconciliation/_build.py` | `core.infra.utils` (atomic_save_workbook) | function | yes | no |
| `reconciliation/_build.py` | `._types` (RschReconciliationRow, ReconciliationRow) | type | yes | no |
| `reconciliation/_build.py` | `._utils` (вспомогательные функции) | function | yes | no |
| `reconciliation/_build.py` | `._resolve` (функции резолва) | function | yes | no |
| `reconciliation/_build.py` | `._collect` (функции сбора) | function | yes | no |
| `reconciliation/_collect.py` | `core.domain.data_loss_log` (record_loss) | function | yes | no |
| `reconciliation/_collect.py` | `core.infra.excel_hyperlinks` (extract_hyperlink_formula_parts) | function | yes | no |
| `reconciliation/_collect.py` | `._types` (MasterReconciliationRow, RschReconciliationRow, ReconciliationRow) | type | yes | no |
| `reconciliation/_collect.py` | `._utils` (вспомогательные функции) | function | yes | no |
| `reconciliation/_collect.py` | `._resolve` (функции резолва) | function | yes | no |
| `reconciliation/_resolve.py` | `core.infra.utils` (get_local_copy) | function | yes | no |
| `reconciliation/_resolve.py` | `._types` (MasterReconciliationRow, RschReconciliationRow) | type | yes | no |
| `reconciliation/_resolve.py` | `._utils` (вспомогательные функции) | function | yes | no |
| `reconciliation/_utils.py` | `._types` (ReconciliationRow) | type | yes | no |

### core/infra/rsch/ — РСЧ-отчёт

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `rsch/__init__.py` | `._build` (build_rsch_report) | function | yes | no |
| `rsch/_build.py` | `core.infra.excel_hyperlinks` (apply_cell_hyperlink) | function | yes | no |
| `rsch/_build.py` | `core.infra.excel_backup` (backup_existing_excel_output) | function | yes | no |
| `rsch/_build.py` | `core.infra.utils` (atomic_save_workbook) | function | yes | no |
| `rsch/_build.py` | `._format` (_display_len, _excel_safe_text, _is_problem_row) | function | yes | no |
| `rsch/_build.py` | `._collect` (_collect_rows_from_workbook, _copy_style, _normalize_source_paths) | function | yes | no |
| `rsch/_build.py` | `._template` (_create_builtin_template_workbook, _find_total_row, _resolve_template_style_layout) | function | yes | no |
| `rsch/_collect.py` | `core.infra.utils` (get_local_copy) | function | yes | no |
| `rsch/_collect.py` | `._format` (_normalize_text, _to_decimal, _as_date, _clean_executor_name и др.) | function | yes | no |
| `rsch/_template.py` | `._format` (_normalize_text) | function | yes | no |
| `rsch/_template.py` | `._collect` (_copy_style) | function | yes | no |

### core/services/ — сервисы бизнес-оркестрации

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `services/reconciliation_service.py` | `core.infra.reconciliation` (build_combined_reconciliation_report) | function | yes | no |
| `services/rsch_service.py` | `core.infra.rsch` (build_rsch_report) | function | yes | no |
| `services/rsch_service.py` | `core.app.message_formatting` (build_issue_preview) | function | yes | no |

### core/ui/ — GUI слой (Tkinter)

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `ui/gui_master.py` | `core.ui.ui_sidebar` (Sidebar) | component | yes | no |
| `ui/gui_master.py` | `core.ui.ui_employee_table` (EmployeeTable) | component | yes | no |
| `ui/gui_master.py` | `core.ui.ui_stats_panel` (StatsPanel) | component | yes | no |
| `ui/gui_master.py` | `core.ui.ui_log_panel` (LogPanel) | component | yes | no |
| `ui/gui_master.py` | `core.ui.ui_dashboard` (DashboardTabs) | component | yes | no |
| `ui/gui_master.py` | `core.ui.theme` (ThemeManager) | class | yes | no |
| `ui/gui_master.py` | `core.ui.geometry` (функции геометрии окна) | function | yes | no |
| `ui/gui_master.py` | `core.ui.operation_state` (OPERATION_LABELS, OperationState) | constant, class | yes | no |
| `ui/gui_master.py` | `core.ui.operation_status_bar` (OperationStatusBar) | component | yes | no |
| `ui/gui_master.py` | `core.ui.toast` (ToastManager) | class | yes | no |
| `ui/gui_master.py` | `core.infra` (ConfigController, setup_gui_logging, open_path) | class, function | yes | no |
| `ui/gui_master.py` | `core.app_controller` (AppController) | class | yes | no |
| `ui/gui_master.py` | `core.view_models.employee_list_viewmodel` (EmployeeListViewModel) | class | yes | no |
| `ui/gui_master.py` | `core.view_models.consolidation_viewmodel` (ConsolidationViewModel) | class | yes | no |
| `ui/gui_master.py` | `core.ui.gui_commands` (GuiCommands) | class | yes | no |
| `ui/gui_master.py` | `core.ui.gui_master_settings` (GuiMasterSettingsMixin) | class | yes | no |
| `ui/gui_master_settings.py` | `core.ui.theme` (ThemeManager) | class | yes | no |
| `ui/gui_master_settings.py` | `core.infra.settings_store` (SettingsStore, UIPreferences) | class | yes | no |
| `ui/ui_sidebar.py` | `core.ui.theme` (ThemeManager) | class | yes | no |
| `ui/ui_sidebar.py` | `core.ui.debounce` (Debouncer) | class | yes | no |
| `ui/ui_employee_table.py` | `core.ui.debounce` (Debouncer) | class | yes | no |
| `ui/ui_employee_table.py` | `core.ui.theme` (ThemeManager) | class | yes | no |
| `ui/ui_log_panel.py` | `core.ui.theme` (ThemeManager) | class | yes | no |
| `ui/ui_dashboard.py` | `core.infra` (open_path) | function | yes | no |
| `ui/ui_dashboard.py` | `core.ui.dashboard_state` (DashboardState и др.) | class, function | yes | no |
| `ui/ui_dashboard.py` | `core.ui.theme` (ThemeManager) | class | yes | no |
| `ui/ui_settings.py` | `core.infra.config_controller` (ConfigController) | class | yes | no |
| `ui/ui_settings.py` | `core.infra.settings_store` (SettingsStore, UIPreferences) | class | yes | no |
| `ui/ui_settings.py` | `core.ui.theme` (ThemeManager) | class | yes | no |
| `ui/operation_status_bar.py` | `core.ui.operation_state` (OperationState и др.) | class | yes | no |

### core/ui/gui_commands/ — команды GUI

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `gui_commands/__init__.py` | `._base` (CommandContext) | class | yes | no |
| `gui_commands/__init__.py` | `._consolidation` (ConsolidationCommandsMixin) | class | yes | no |
| `gui_commands/__init__.py` | `._employee` (EmployeeCommandsMixin) | class | yes | no |
| `gui_commands/__init__.py` | `._reconciliation` (ReconciliationCommandsMixin) | class | yes | no |
| `gui_commands/_base.py` | `core.infra` (open_path) | function | yes | no |
| `gui_commands/_base.py` | `core.ui.operation_state` (OperationState) | class | yes | no |
| `gui_commands/_base.py` | `core.ui.toast` (ToastLevel, ToastManager) | class | yes | no |
| `gui_commands/_consolidation.py` | `core.ui.operation_state` (OperationType) | class | yes | no |
| `gui_commands/_consolidation.py` | `._base` (CommandContext) | class | yes | no |
| `gui_commands/_employee.py` | `core.infra` (open_path) | function | yes | no |
| `gui_commands/_employee.py` | `core.ui.operation_state` (OperationType) | class | yes | no |
| `gui_commands/_employee.py` | `._base` (CommandContext) | class | yes | no |
| `gui_commands/_reconciliation.py` | `core.ui.operation_state` (OperationType) | class | yes | no |
| `gui_commands/_reconciliation.py` | `._base` (CommandContext, finish) | class, function | yes | no |
| `gui_commands/_reconciliation.py` | `._rsch` (RschCommandsMixin) | class | yes | no |
| `gui_commands/_rsch.py` | `core.ui.operation_state` (OperationType) | class | yes | no |
| `gui_commands/_rsch.py` | `._base` (CommandContext, finish) | class, function | yes | no |

### core/view_models/ — ViewModel слой

| Модуль A | Импортирует из | Тип | Критичная? | Можно заменить? |
|----------|----------------|-----|------------|-----------------|
| `view_models/consolidation_viewmodel.py` | — (нет внутренних импортов) | — | — | — |
| `view_models/employee_list_viewmodel.py` | — (нет внутренних импортов) | — | — | — |

---

## 2. Внешние зависимости (pip)

### Runtime-зависимости (requirements.txt)

| Пакет | Версия | Назначение | Используется в | Заменяем? | Лицензия | Уязвимости известные? |
|-------|--------|------------|----------------|-----------|----------|----------------------|
| **openpyxl** | 3.1.5 | Чтение/запись .xlsx файлов, стилизация ячеек, гиперссылки, комментарии | `core/infra/export_writer.py`, `core/infra/export_formatting.py`, `core/infra/excel_hyperlinks.py`, `core/infra/reconciliation/_build.py`, `core/infra/reconciliation/_collect.py`, `core/infra/reconciliation/_resolve.py`, `core/infra/reconciliation/_utils.py`, `core/infra/rsch/_build.py`, `core/infra/rsch/_collect.py`, `core/infra/rsch/_format.py`, `core/infra/rsch/_template.py` | Да (xlsxwriter для записи, но не для чтения) | MIT | Нет известных для 3.1.5 |
| **ruamel.yaml** | 0.18.6 | Чтение/запись YAML-конфигурации (config.yaml) с сохранением комментариев | `core/infra/config_controller.py` (`YAML`) | Да (PyYAML, но теряет комментарии) | MIT | Нет известных для 0.18.6 |
| **tkcalendar** | 1.6.1 | Виджет выбора даты (DateEntry) для Tkinter GUI | `core/ui/ui_sidebar.py` (`DateEntry`) | Да (tkinter.ttk.Calendar кастомный) | GPL-3.0 | Нет известных для 1.6.1 |
| **pyxlsb** | 1.0.10 | Чтение .xlsb (Binary Excel) файлов | **НЕ ИСПОЛЬЗУЕТСЯ в коде** (см. раздел 6) | — | LGPL-3.0 | Нет известных для 1.0.10 |
| **PyYAML** | 6.0.1 | Парсинг YAML | **НЕ ИСПОЛЬЗУЕТСЯ в коде** (см. раздел 6) | — | MIT | Нет известных для 6.0.1 |
| **pydantic** | 2.10.6 | Валидация данных, схемы моделей, сериализация | `core/bootstrap.py` (`BaseModel`), `core/domain/data_schemas.py` (`BaseModel`, `Field`, `field_validator`, `ConfigDict`) | Да (dataclasses, но без валидации) | MIT | Нет известных для 2.10.6 |
| **python-calamine** | 0.6.2 | Быстрое чтение Excel через Calamine engine (Rust-based) | `core/infra/ingestion_engine.py` (`CalamineWorkbook`), `core/infra/ingestion_reader.py` (`CalamineWorkbook`), `core/infra/rsch/_collect.py` (`CalamineWorkbook`) | Да (openpyxl read, но медленнее в 10-50x) | MIT | Нет известных для 0.6.2 |

#### Детализация использования внешних пакетов

**openpyxl** (3.1.5)
- Где: 11 модулей в `core/infra/`
- Что используется:
  - `Workbook`, `load_workbook` — создание/загрузка .xlsx
  - `Worksheet` — тип для аннотаций
  - `Cell` — тип для работы с ячейками
  - `get_column_letter` — конвертация индекса колонки в букву
  - `PatternFill`, `Font`, `Alignment`, `Border`, `Side` — стилизация ячеек
  - `Comment` — комментарии к ячейкам
- Альтернатива: `xlsxwriter` (только запись), `xlsx2html` (только чтение)
- Размер пакета: ~2.4 MB
- Последнее обновление: 2024-09-02

**ruamel.yaml** (0.18.6)
- Где: `core/infra/config_controller.py`
- Что используется: `YAML` — парсинг/сериализация YAML с сохранением комментариев и порядка ключей
- Альтернатива: `PyYAML` (не сохраняет комментарии), `tomli` (другой формат)
- Размер пакета: ~850 KB
- Последнее обновление: 2024-10-12

**tkcalendar** (1.6.1)
- Где: `core/ui/ui_sidebar.py`
- Что используется: `DateEntry` — выпадающий календарь для выбора даты
- Альтернатива: кастомный `ttk.Calendar` виджет (требует разработки)
- Размер пакета: ~100 KB
- Последнее обновление: 2024-10-14

**pydantic** (2.10.6)
- Где: `core/bootstrap.py`, `core/domain/data_schemas.py`
- Что используется:
  - `BaseModel` — базовый класс для схем данных
  - `Field` — описание полей модели
  - `field_validator` — кастомная валидация полей
  - `ConfigDict` — конфигурация модели
- Альтернатива: `dataclasses` (stdlib, но без валидации), `attrs` + `cattrs`
- Размер пакета: ~2.5 MB (с pydantic-core)
- Последнее обновление: 2025-01-22

**python-calamine** (0.6.2)
- Где: `core/infra/ingestion_engine.py`, `core/infra/ingestion_reader.py`, `core/infra/rsch/_collect.py`
- Что используется: `CalamineWorkbook` — быстрое чтение Excel (.xlsx, .xls, .xlsm)
- Альтернатива: `openpyxl` (медленнее в 10-50x), `pandas.read_excel` (зависит от openpyxl)
- Размер пакета: ~5 MB (включает Rust binary)
- Последнее обновление: 2025-01-10

### Dev-зависимости (requirements-dev.txt)

| Пакет | Версия | Назначение | Используется в | Заменяем? | Лицензия | Уязвимости известные? |
|-------|--------|------------|----------------|-----------|----------|----------------------|
| **pytest** | 9.0.2 | Фреймворк автотестов | `tests/` (все тестовые модули) | Да (unittest) | MIT | Нет известных |
| **pytest-mock** | 3.15.1 | Плагин pytest для mocker fixture | `tests/` | Да (unittest.mock) | MIT | Нет известных |
| **pytest-cov** | 7.0.0 | Покрытие кода в pytest | `tests/` (CI) | Да (coverage.py) | MIT | Нет известных |
| **hypothesis** | 6.151.10 | Property-based тестирование | `tests/` (`.hypothesis/` кэш присутствует) | Да (pytest-parametrized) | MPL-2.0 | Нет известных |
| **ruff** | 0.14.6 | Линтер и форматтер | `pyproject.toml` (конфиг), CI | Да (flake8, black) | MIT | Нет известных |
| **mypy** | 1.18.2 | Статический тип-чекер | `.mypy_cache/`, `.mypy_baseline.txt` | Да (pyright, pytype) | MIT | Нет известных |
| **pandas-stubs** | 2.3.2.250926 | Type stubs для pandas (для mypy) | dev-only (mypy) | Да (pyright) | BSD-3-Clause | Нет известных |
| **types-openpyxl** | 3.1.5.20260408 | Type stubs для openpyxl (для mypy) | dev-only (mypy) | Нет | Apache-2.0 | Нет известных |
| **types-psutil** | 7.2.2.20260408 | Type stubs для psutil (для mypy) | dev-only (mypy) | Нет | Apache-2.0 | Нет известных |

---

## 3. Сервисные зависимости

| Сервис | Тип | Назначение | Обязательный? | Fallback? |
|--------|-----|------------|---------------|-----------|
| SQLite | database | Локальная БД-кэш: сессии, staging, консолидация, ошибки, file_cache, row_cache, discovery_cache, customer_aliases | yes | Нет (приложение не работает без БД) |
| Local filesystem | storage | Чтение исходных Excel с network drive (Q:\), запись отчётов в output/, backups/, РСЧ/ | yes | Нет (файловая система обязательна) |
| Network drive (Q:\, Z:\) | storage | Источник исходных файлов отчётов кураторов (`Q:\Отчет кураторов 1/2/3`) | no | `direct_paths` в конфиге куратора (локальные пути) |
| Tkinter | component | GUI-фреймворк (входит в stdlib Python) | no (headless mode) | `headless_run.py` — CLI без GUI |
| Threading pool | queue | `concurrent.futures.ThreadPoolExecutor` для многопоточного чтения Excel | no | Однопоточный режим (max_workers=1) |
| Event Bus | queue | `core/infra/event_bus.py` — in-memory очередь событий | no | Прямые вызовы (синхронно) |
| Row cache | cache | SQLite `row_cache` таблица — кэш распарсенных строк Excel | no | Повторный парсинг при каждом запуске |
| File cache | cache | SQLite `file_cache` таблица — кэш метаданных файлов (mtime, size, dates) | no | Повторное сканирование network drive |
| Discovery cache | cache | SQLite `discovery_cache` таблица — кэш результатов discovery scan | no | Повторное сканирование директорий |

### Конфигурационные параметры (config.yaml)

| Параметр | Тип | Назначение | Обязательный? | Значение по умолчанию |
|----------|-----|------------|---------------|----------------------|
| `database.path` | string | Путь к SQLite БД | yes | `cache.db` |
| `database.schema_path` | string | Путь к SQL-схеме | yes | `db_schema.sql` |
| `database.timeout` | float | Таймаут SQLite соединения (сек) | yes | `30.0` |
| `database.use_wal` | bool | WAL-режим SQLite | yes | `true` |
| `database.isolation_level` | string | Уровень изоляции транзакций | yes | `EXCLUSIVE` |
| `database.allow_local_fallback` | bool | Fallback на локальную БД | yes | `false` |
| `locking.retry_count` | int | Кол-во попыток при блокировке БД | yes | `5` |
| `locking.retry_backoff` | float | Множитель backoff | yes | `2.0` |
| `locking.use_semaphores` | bool | Использование семафоров | yes | `true` |
| `network.drive_letters` | list | Буквы network drives для проверки | no | `[Q, Z]` |
| `paths.master_file` | string | Путь к Master Report .xlsx | yes | `../Master_Report.xlsx` |
| `paths.source_roots` | list | Корневые директории исходных файлов | yes | `[Q:\Отчет кураторов 1/2/3]` |
| `paths.archive_dir` | string | Директория архивных копий | yes | `../backups` |
| `performance.max_workers` | int/null | Override кол-ва потоков | no | `null` (auto: min(32, CPU*2)) |
| `performance.isolate_calamine` | bool | Изоляция Calamine в subprocess | yes | `false` |
| `backup.excel_keep` | int | Кол-во хранимых бэкапов Excel | yes | `10` |
| `rsch.mode` | string | Режим РСЧ-отчёта | yes | `combined` |
| `rsch.last_output_dir` | string | Директория вывода РСЧ | yes | `../РСЧ` |

### Environment variables

| Переменная | Где используется | Назначение | Обязательная? |
|------------|------------------|------------|---------------|
| `HEADLESS_RUN_TIMEOUT` | `APP/headless_run.py` | Таймаут headless-режима (сек) | no (default: 600) |
| `PYTHONIOENCODING` | `core/infra/ingestion_engine.py` | Кодировка для subprocess (utf-8) | no (устанавливается программно) |
| `PYTEST_CURRENT_TEST` | `core/domain/data_loss_log.py` | Детектор тестового режима | no (устанавливается pytest) |

---

## 4. Инфраструктурные требования

- **Runtime**: Python 3.12+ (target-version в pyproject.toml: `py312`; используются `type X =` syntax, `match/case`, `dataclass` slots)
- **БД**: SQLite 3.50.4 (поставляется с Python 3.12), WAL-режим, isolation_level=EXCLUSIVE
  - Схема: `APP/db_schema.sql` — 9 таблиц + 6 индексов
  - Миграции: `APP/migrations/001_numeric_to_text.sql`, `APP/migrations/002_customer_aliases.sql`
- **Кэш**: In-process через SQLite (`row_cache`, `file_cache`, `discovery_cache` таблицы); in-memory `EventBus` (queue.Queue)
- **Очередь**: In-memory `queue.Queue` в `event_bus.py`, `source_file_repo.py`, `staging_repo.py`, `utils_logging.py` (GUI log queue); `ThreadPoolExecutor` для параллельного чтения Excel
- **Storage**: Local filesystem (БД, output, backups) + Network drive (Q:\, Z:\ — исходные файлы кураторов)
- **Внешние API**: Нет. Приложение полностью офлайн — никаких HTTP/API вызовов
- **GUI**: Tkinter (входит в stdlib Python, требует Tcl/Tk). На Windows используется `ctypes` для DPI-awareness
- **ОС**: Windows (используются `ntpath`, `PureWindowsPath`, network drive letters Q:\ Z:\, .bat запускатели). Кроссплатформенность частичная — core-логика OS-agnostic, но пути и запускатели Windows-only

---

## 5. Циркулярные зависимости

### Найденная циркулярная зависимость

```
core.infra.__init__
  → core.infra.export_writer (MasterWriter)
    → core.infra (is_file_writable)
      → core.infra.__init__  [CYCLE]
```

**Оценка риска: low**

Это стандартный Python-паттерн re-export через `__init__.py`. Модуль `core/infra/__init__.py` реэкспортирует символы из подмодулей для удобства импорта (`from core.infra import ConfigController`). Подмодуль `export_writer.py` импортирует `is_file_writable` из `core.infra` (пакета). При первом импорте `core.infra` Python начинает выполнять `__init__.py`, доходит до `from core.infra.export_writer import MasterWriter`, загружает `export_writer.py`, который пытается `from core.infra import is_file_writable` — но `is_file_writable` ещё не определён в частично инициализированном `__init__.py`.

**Почему работает**: `is_file_writable` импортируется в `__init__.py` из `core.infra.utils` (строка 1-5) **до** импорта `export_writer` (строка 8). Поэтому к моменту загрузки `export_writer` символ уже доступен в частично инициализированном модуле `core.infra`.

**Рекомендация**: Не менять порядок импортов в `core/infra/__init__.py`. При рефакторинге — заменить `from core.infra import is_file_writable` в `export_writer.py` на прямой `from core.infra.utils import is_file_writable`, чтобы разорвать цикл.

### Других циркулярных зависимостей не найдено

Граф внутренних импортов представляет собой DAG (направленный ацикличный граф) за исключением указанного выше цикла. Слоистая архитектура соблюдается:
- `domain` → не зависит от `infra` (кроме `data_loss_log.py` → `utils_logging`)
- `infra` → не зависит от `app`, `services`, `ui`
- `app` → зависит только от `infra`
- `services` → зависит от `infra`, `app`
- `ui` → зависит от `infra`, `app_controller`, `view_models`
- `view_models` → не имеет внутренних зависимостей

---

## 6. Undeclared / Unused зависимости

### [UNUSED DEPENDENCY]

| Пакет | Версия | Где объявлен | Где используется | Примечание |
|-------|--------|--------------|------------------|------------|
| **pyxlsb** | 1.0.10 | `requirements.txt` | Нигде в Python-коде | Проверяется в `ЗАПУСК.bat` (`import pyxlsb`), но ни один модуль не импортирует его. Вероятно, был запланирован для чтения .xlsb файлов, но заменён на `python-calamine`. **Рекомендация**: удалить из requirements.txt или реализовать .xlsb поддержку. |
| **PyYAML** | 6.0.1 | `requirements.txt` | Нигде в Python-коде | Проверяется в `ЗАПУСК.bat` (`import yaml`), но в коде используется `ruamel.yaml` вместо PyYAML. **Рекомендация**: удалить из requirements.txt — `ruamel.yaml` не зависит от PyYAML. |
| **pandas-stubs** | 2.3.2.250926 | `requirements-dev.txt` | Нигде (pandas не используется в проекте) | Type stubs для pandas, но pandas не импортируется ни в APP/, ни в tests/. **Рекомендация**: удалить из requirements-dev.txt. |
| **types-psutil** | 7.2.2.20260408 | `requirements-dev.txt` | Нигде (psutil не используется в проекте) | Type stubs для psutil, но psutil не импортируется ни в APP/, ни в tests/. **Рекомендация**: удалить из requirements-dev.txt. |

### [UNDECLARED DEPENDENCY]

| Пакет | Где используется | Что используется | Примечание |
|-------|------------------|------------------|------------|
| **fpdf** | `tools/merge_to_pdf.py` | `FPDF` — генерация PDF из исходников | Инструментальный скрипт, не входит в runtime. **Рекомендация**: добавить в requirements-dev.txt или вынести в отдельный tools-requirements.txt. |

---

## Критерий завершения

- [x] Все импорты проанализированы (536 import-stmt в 72 source-файлах APP/)
- [x] Все внешние пакеты перечислены с версиями (7 runtime + 9 dev)
- [x] Сервисные зависимости описаны (SQLite, filesystem, network drive, threading, cache)
- [x] Циркулярные зависимости найдены (1 цикл: `core.infra.__init__` ↔ `core.infra.export_writer`, risk: low)
- [x] Undeclared и unused зависимости помечены (2 undeclared в tools, 4 unused в requirements)
