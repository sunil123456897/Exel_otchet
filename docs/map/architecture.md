# Архитектурный анализ

## Метаданные
- Дата: 2026-06-25
- Проект: Master-Report v5.5
- Источник: docs/map/structure.md + анализ кода

---

## 1. Архитектурный паттерн

**[HYBRID] Layered Architecture + MVC + MVVM**

Проект не следует одному чистому паттерну — это гибрид трёх подходов, организованных в слоистую архитектуру.

### 1.1 Layered Architecture (доминирующий)
Директории `core/` чётко разделены на 4 слоя: `domain/` → `infra/` → `services/` + `app/` → `ui/` + `view_models/`. Каждый слой имеет пакетный `__init__.py` с публичным API (`core/domain/__init__.py:1-17`, `core/infra/__init__.py:1-13`), что характерно для Layered/Clean Architecture с портами и адаптерами.

### 1.2 MVC-элементы
- **Model**: `core/domain/` (бизнес-схемы, `FinancialRowSchema`, `LogicService`) + `core/infra/` (данные, БД)
- **Controller**: `core/app_controller.py:88` — `AppController` оркеструет операции, делегирует сервисам
- **View**: `core/ui/` — Tkinter-виджеты (`Sidebar`, `EmployeeTable`, `DashboardTabs`)

### 1.3 MVVM-элементы
- **View**: `core/ui/gui_master.py:62` — `GuiMaster` (Tkinter окно)
- **ViewModel**: `core/view_models/consolidation_viewmodel.py:12` — `ConsolidationViewModel`, `core/view_models/employee_list_viewmodel.py` — `EmployeeListViewModel`; принимают `app_controller` через конструктор, не импортируют infra
- **Model**: `AppController` + domain

### 1.4 Обоснование гибрида
MVVM-слой (`view_models/`) существует, но **не изолирован полностью**: `GuiMaster` (`gui_master.py:22`) импортирует `AppController` напрямую, минуя ViewModel, а ViewModel-и используются лишь для employee list и consolidation state. Большинство GUI-команд (`gui_commands/`) обращаются напрямую к `AppController` через `self.ctx.controller`, что соответствует MVC, а не MVVM. Поэтому паттерн — гибрид с доминирующим Layered + MVC.

---

## 2. Слои приложения

| Слой | Директории | Назначение | Примеры модулей |
|------|------------|------------|-----------------|
| **Presentation** | `core/ui/`, `core/view_models/` | Tkinter GUI, виджеты, тема, ViewModel-и | `gui_master.py`, `ui_dashboard.py`, `theme.py`, `consolidation_viewmodel.py` |
| **Application/Services** | `core/` (root), `core/services/`, `core/app/` | Оркестрация use-case-ов, threading, прикладные сервисы | `app_controller.py`, `rsch_service.py`, `file_processor.py`, `partial.py` |
| **Domain** | `core/domain/` | Бизнес-правила, схемы, интерфейсы (порты) | `logic_service.py`, `data_schemas.py`, `interfaces.py`, `utils_helpers.py` |
| **Infrastructure** | `core/infra/` | БД, Excel I/O, конфиг, ингестия, экспорт | `db_connection.py`, `export_writer.py`, `ingestion_engine.py`, `config_controller.py` |
| **Bootstrap** | `APP/main.py`, `APP/headless_run.py`, `core/bootstrap.py` | Composition root: сборка всех слоёв | `bootstrap.py:Bootstrap.setup()` |
| **Cross-cutting** | `core/infra/utils.py`, `core/infra/utils_logging.py`, `core/infra/event_bus.py` | Утилиты, логирование, event bus | `utils.py`, `utils_logging.py` |

### Правила общения между слоями

| Слой | Имеет право общаться с | НЕ должен общаться с |
|------|----------------------|---------------------|
| Presentation | Application/Services, Cross-cutting, same-layer | Domain напрямую, Infra напрямую |
| Application/Services | Domain, Infra, Cross-cutting, same-layer | Presentation |
| Domain | same-layer, Cross-cutting (через интерфейсы) | Infra (конкретные реализации), Presentation |
| Infra | Domain (реализация интерфейсов), same-layer, Cross-cutting | Presentation, Application/Services |
| Bootstrap | Все слои (composition root) | — |

---

## 3. Матрица зависимостей

| Модуль | Импортирует | Тип связи | Допустимо? |
|--------|-------------|-----------|------------|
| `main.py` | `core.bootstrap.Bootstrap` | bootstrap→all | ✅ Да |
| `headless_run.py` | `core.bootstrap.Bootstrap` | bootstrap→all | ✅ Да |
| `core/bootstrap.py` | `core.infra` (ConfigController, MasterWriter), `core.infra.utils`, `core.infra.ingestion_engine`, `core.infra.session_repo`, `core.domain` (LogicService, Validator), `core.app_controller.AppController`, `core.infra.customer_alias_repo` (lazy) | bootstrap→all | ✅ Да |
| `core/app_controller.py` | `core.infra` (DiscoveryService, is_file_writable), `core.infra.utils_logging`, `core.app.file_processor`, `core.app.performance`, `core.app.message_formatting`, `core.infra.reconciliation`, `core.infra.rsch`, `core.services.rsch_service`, `core.services.reconciliation_service`, `core.app.partial`, `core.infra.utils` | business→data, business→same-layer | ✅ Да |
| `core/app/file_processor.py` | `core.app.performance`, `core.infra` (is_file_writable), `core.infra.utils_logging` | business→data, business→cross-cutting | ✅ Да |
| `core/app/message_formatting.py` | (только stdlib) | same-layer | ✅ Да |
| `core/app/partial.py` | (только stdlib) | same-layer | ✅ Да |
| `core/app/performance.py` | (только stdlib) | same-layer | ✅ Да |
| `core/domain/__init__.py` | `core.domain.interfaces`, `core.domain.utils_helpers`, `core.domain.data_schemas`, `core.domain.logic_service` | same-layer | ✅ Да |
| `core/domain/data_loss_log.py` | `core.infra.utils_logging` | **domain→infra** | ❌ **Нарушение** (DIP) |
| `core/domain/data_schemas.py` | (только stdlib: pydantic) | same-layer | ✅ Да |
| `core/domain/interfaces.py` | (только stdlib: abc, typing) | same-layer | ✅ Да |
| `core/domain/logic_service.py` | `core.domain.interfaces`, `core.domain.utils_helpers`, `core.domain.data_schemas` | same-layer | ✅ Да |
| `core/domain/utils_helpers.py` | (только stdlib) | same-layer | ✅ Да |
| `core/infra/__init__.py` | `core.infra.utils`, `core.infra.utils_logging`, `core.infra.config_controller`, `core.infra.export_writer`, `core.infra.session_repo`, `core.infra.discovery_service`, `core.infra.path_resolver` | same-layer | ✅ Да (но см. circular dep) |
| `core/infra/config_controller.py` | `core.infra.utils_logging` | same-layer | ✅ Да |
| `core/infra/customer_alias_repo.py` | `core.infra.db_connection` | same-layer | ✅ Да |
| `core/infra/db_connection.py` | (только stdlib) | same-layer | ✅ Да |
| `core/infra/discovery_service.py` | `core.infra.config_controller`, `core.infra.ingestion_engine`, `core.infra.path_resolver`, `core.infra.utils_logging`, `core.infra.utils` | same-layer | ✅ Да |
| `core/infra/event_bus.py` | (только stdlib) | cross-cutting | ✅ Да (но dead code) |
| `core/infra/excel_backup.py` | (только stdlib) | same-layer | ✅ Да |
| `core/infra/excel_hyperlinks.py` | (только stdlib: openpyxl) | same-layer | ✅ Да |
| `core/infra/export_formatting.py` | (только stdlib: openpyxl) | same-layer | ✅ Да |
| `core/infra/export_writer.py` | `core.domain` (IExporter), `core.domain.utils_helpers`, `core.infra` (is_file_writable), `core.infra.excel_backup`, `core.infra.export_formatting`, `core.infra.excel_hyperlinks` | data→domain, **data→data (circular)** | ⚠️ Circular с `core.infra.__init__` |
| `core/infra/ingestion_engine.py` | `core.domain` (IDataSource), `core.infra.utils`, `core.infra.ingestion_reader` | data→domain, same-layer | ✅ Да |
| `core/infra/ingestion_reader.py` | `core.domain.utils_helpers`, `core.infra.utils` | data→domain, same-layer | ✅ Да |
| `core/infra/metrics.py` | (только stdlib) | cross-cutting | ✅ Да (но dead code) |
| `core/infra/path_resolver.py` | (только stdlib) | same-layer | ✅ Да |
| `core/infra/session_repo.py` | `core.domain` (IPersistence), `core.infra.db_connection`, `core.infra.source_file_repo`, `core.infra.staging_repo` | data→domain, same-layer | ✅ Да |
| `core/infra/settings_store.py` | `core.infra.config_controller` | same-layer | ✅ Да |
| `core/infra/source_file_repo.py` | `core.infra.db_connection` | same-layer | ✅ Да |
| `core/infra/staging_repo.py` | `core.infra.db_connection` | same-layer | ✅ Да |
| `core/infra/utils_logging.py` | (только stdlib) | cross-cutting | ✅ Да |
| `core/infra/utils.py` | (только stdlib) | cross-cutting | ✅ Да |
| `core/infra/reconciliation/__init__.py` | `._types`, `._utils`, `._build` | same-layer | ✅ Да |
| `core/infra/reconciliation/_build.py` | `core.infra.excel_hyperlinks`, `core.infra.excel_backup`, `core.infra.utils`, `._types`, `._utils`, `._resolve`, `._collect` | same-layer | ✅ Да |
| `core/infra/reconciliation/_collect.py` | `core.domain.data_loss_log`, `core.infra.excel_hyperlinks`, `._types`, `._utils`, `._resolve` | data→domain, same-layer | ✅ Да (но транзитивно domain→infra) |
| `core/infra/reconciliation/_resolve.py` | `core.infra.utils`, `._types`, `._utils` | same-layer | ✅ Да |
| `core/infra/reconciliation/_types.py` | (только stdlib) | same-layer | ✅ Да |
| `core/infra/reconciliation/_utils.py` | `._types` | same-layer | ✅ Да |
| `core/infra/rsch/__init__.py` | `._build` | same-layer | ✅ Да |
| `core/infra/rsch/_build.py` | `core.infra.excel_hyperlinks`, `core.infra.excel_backup`, `core.infra.utils`, `._format`, `._collect`, `._template` | same-layer | ✅ Да |
| `core/infra/rsch/_collect.py` | (только stdlib: openpyxl) | same-layer | ✅ Да |
| `core/infra/rsch/_format.py` | (только stdlib: openpyxl) | same-layer | ✅ Да |
| `core/infra/rsch/_template.py` | `._format`, `._collect` | same-layer | ✅ Да |
| `core/services/reconciliation_service.py` | `core.infra.reconciliation` | business→data | ✅ Да |
| `core/services/rsch_service.py` | `core.infra.rsch`, `core.app.message_formatting` | business→data, business→same-layer | ✅ Да |
| `core/ui/gui_master.py` | `core.ui.*` (7 модулей), `core.infra` (ConfigController, setup_gui_logging, open_path), `core.app_controller.AppController`, `core.view_models.*`, `core.ui.gui_commands`, `core.ui.gui_master_settings` | **presentation→infra**, presentation→business, same-layer | ❌ **Нарушение** (presentation→infra) |
| `core/ui/gui_master_settings.py` | `core.ui.theme`, `core.infra.settings_store` | **presentation→infra** | ❌ **Нарушение** |
| `core/ui/ui_dashboard.py` | `core.infra` (open_path), `core.ui.dashboard_state`, `core.ui.theme`, `core.ui.ui_aliases` (lazy) | **presentation→infra** | ❌ **Нарушение** |
| `core/ui/ui_settings.py` | `core.infra.config_controller`, `core.infra.settings_store`, `core.ui.theme` | **presentation→infra** | ❌ **Нарушение** |
| `core/ui/ui_sidebar.py` | `core.ui.theme`, `core.ui.debounce`, `core.ui.tooltip` (lazy) | same-layer | ✅ Да |
| `core/ui/ui_employee_table.py` | `core.ui.debounce`, `core.ui.theme` | same-layer | ✅ Да |
| `core/ui/ui_log_panel.py` | `core.ui.theme` | same-layer | ✅ Да |
| `core/ui/ui_stats_panel.py` | (только stdlib: tkinter) | same-layer | ✅ Да |
| `core/ui/ui_aliases.py` | (только stdlib: tkinter) | same-layer | ✅ Да |
| `core/ui/ui_dialogs.py` | (только stdlib: tkinter) | same-layer | ✅ Да |
| `core/ui/theme.py` | `core.ui.system_theme` (lazy) | same-layer | ✅ Да |
| `core/ui/system_theme.py` | (только stdlib) | same-layer | ✅ Да |
| `core/ui/toast.py` | (только stdlib) | same-layer | ✅ Да |
| `core/ui/tooltip.py` | (только stdlib) | same-layer | ✅ Да |
| `core/ui/debounce.py` | (только stdlib) | same-layer | ✅ Да |
| `core/ui/geometry.py` | (только stdlib) | same-layer | ✅ Да |
| `core/ui/operation_state.py` | (только stdlib) | same-layer | ✅ Да |
| `core/ui/operation_status_bar.py` | `core.ui.operation_state` | same-layer | ✅ Да |
| `core/ui/dashboard_state.py` | (только stdlib) | same-layer | ✅ Да |
| `core/ui/gui_commands/__init__.py` | `._base`, `._consolidation`, `._employee`, `._reconciliation` | same-layer | ✅ Да |
| `core/ui/gui_commands/_base.py` | `core.infra` (open_path), `core.ui.operation_state`, `core.ui.toast` | **presentation→infra** | ❌ **Нарушение** |
| `core/ui/gui_commands/_consolidation.py` | `core.ui.operation_state`, `._base` | same-layer | ✅ Да |
| `core/ui/gui_commands/_employee.py` | `core.infra` (open_path), `core.ui.operation_state`, `._base`, `core.ui.ui_dialogs` (lazy) | **presentation→infra** | ❌ **Нарушение** |
| `core/ui/gui_commands/_reconciliation.py` | `core.ui.operation_state`, `._base`, `._rsch` | same-layer | ✅ Да |
| `core/ui/gui_commands/_rsch.py` | `core.ui.operation_state`, `._base`, `core.ui.ui_dialogs` (lazy) | same-layer | ✅ Да |
| `core/view_models/consolidation_viewmodel.py` | (только stdlib) | same-layer | ✅ Да |
| `core/view_models/employee_list_viewmodel.py` | (только stdlib) | same-layer | ✅ Да |

---

## 4. Нарушения принципов

### 4.1 Circular Dependencies

**Цикл 1: `core.infra.__init__` ↔ `core.infra.export_writer`**

```
core.infra.__init__ (line 8)
  → from core.infra.export_writer import MasterWriter
    → core.infra.export_writer (line 12)
      → from core.infra import is_file_writable
        → core.infra.__init__ (уже в загрузке)
```

- **Файлы**: `core/infra/__init__.py:8` → `core/infra/export_writer.py:12` → `core/infra/__init__.py`
- **Runtime-влияние**: Работает благодаря порядку импортов в `__init__.py` — `is_file_writable` определён на line 2 до импорта `export_writer` на line 8. Но это хрупкая зависимость от порядка строк.
- **Рекомендация**: Заменить `from core.infra import is_file_writable` на `from core.infra.utils import is_file_writable` в `export_writer.py:12`.

**Цикл 2 (транзитивный, через domain): `core.infra.reconciliation._collect` → `core.domain.data_loss_log` → `core.infra.utils_logging`**

Это не классический цикл (нет обратного ребра), но создаёт **domain→infra зависимость**, которая в Clean Architecture недопустима. См. раздел 4.3.

### 4.2 God Objects

#### 4.2.1 `core/app_controller.py` — 1026 строк, 9 ответственностей

**Класс `AppController`** (`app_controller.py:88`) объединяет:

| # | Ответственность | Методы | Строки |
|---|----------------|--------|--------|
| 1 | Консолидация (day/all/month) | `run_consolidation`, `run_consolidation_all_dates`, `run_consolidation_month`, `_execute_consolidation`, `_run_consolidation_core`, `_run_consolidation_blocking` | 526-876 |
| 2 | РСЧ-отчёты | `run_rsch_report`, `run_rsch_report_period`, `run_rsch_report_period_batch`, `run_rsch_report_batch` | 1044-1097 |
| 3 | Сверка | `run_reconciliation_report`, `run_auto_reconciliation_day`, `_run_auto_master_report`, `_write_empty_auto_reconciliation_report` | 877-1042 |
| 4 | Управление сотрудниками | `refresh_status`, `_run_refresh_status`, `_check_employee_refresh_status`, `_resolve_employees_for_run`, `_filter_employees_for_curator`, `_get_enabled_curator_employee_keys` | 280-468 |
| 5 | CRUD алиасов заказчиков | `get_customer_aliases`, `add_customer_alias`, `update_customer_alias`, `delete_customer_alias` | 1118-1139 |
| 6 | Резолвинг путей | `_resolve_master_path`, `_resolve_report_path`, `_get_curator_config`, `_is_report_writable` | 140-194 |
| 7 | Threading | `_start_thread`, `_active_threads`, `_executor` | 113-116, 242-250 |
| 8 | Построение сообщений | `_build_session_meta`, `_build_empty_data_message`, `_build_no_files_message`, `_build_success_message`, `_format_file_error_note` | 436-514 |
| 9 | Shutdown | `shutdown` | 1098-1114 |

**Рекомендация**: split — вынести алиасы в `AliasService`, резолвинг путей в `PathResolver`, построение сообщений в `message_formatting.py` (уже частично есть).

#### 4.2.2 `core/infra/ingestion_reader.py` — 1012 строк, 8 ответственностей

**Класс `CalamineReader`** (`ingestion_reader.py:202`) объединяет:

| # | Ответственность | Методы |
|---|----------------|--------|
| 1 | Классификация заголовков | `_classify_header_structure`, `_is_boris_second_percent_header`, `_is_soft_extra_header` |
| 2 | Маппинг колонок | `_map_columns`, `_find_header_index`, `_find_alias_index`, `_find_boris_second_percent_index` |
| 3 | Извлечение дат | `extract_date_from_sheet`, `_parse_scope_date`, `_sheet_date_matches_scope`, `_unpack_sheet_date_meta` |
| 4 | Обработка строк | `_process_workbook_sheet`, `_iter_sheet_rows_safe`, `_build_data_row_payload`, `_row_has_values`, `_is_trash_row` |
| 5 | Числовая конверсия | `_coerce_numeric_cell`, `_normalize_header_text` |
| 6 | Аудит потери данных | `_record_data_loss` |
| 7 | Поиск заголовков | `_find_best_header_candidate`, `_header_match_score`, `_is_valid_header_map`, `_activate_header_state` |
| 8 | I/O и cleanup | `_load_sheet_sample_rows`, `_cleanup_temp_file`, `read` |

**Рекомендация**: split — вынести классификацию заголовков в `HeaderClassifier`, маппинг колонок в `ColumnMapper`, обработку строк в `RowProcessor`.

#### 4.2.3 `core/ui/ui_dashboard.py` — 690 строк, 9 ответственностей

**Класс `DashboardTabs`** (`ui_dashboard.py:32`) объединяет:

| # | Ответственность | Методы |
|---|----------------|--------|
| 1 | Home tab | `_setup_home`, `_refresh_home` |
| 2 | Reports tab | `_setup_reports`, `_refresh_reports`, `_selected_report_path`, `_open_selected_report`, `_open_selected_report_folder` |
| 3 | Diagnostics tab | `_setup_diagnostics`, `run_diagnostics`, `copy_diagnostics` |
| 4 | Logs tab | `_setup_logs`, `_refresh_logs`, `_recent_log_errors` |
| 5 | Settings tab | `_setup_settings`, `_refresh_settings`, `_save_settings`, `_toggle_settings_mode`, `_browse_master_file`, `_browse_archive_dir`, `_add_source_root`, `_remove_source_root` |
| 6 | Aliases tab | `_setup_aliases` |
| 7 | Открытие файлов/папок | `_open_selected_result`, `_open_backup_folder`, `_open_report_by_label`, `_open_path`, `_show_missing` |
| 8 | Theme | `refresh_theme` |
| 9 | Background execution | `record_result`, `_run_in_background`, `refresh` |

**Рекомендация**: split — вынести каждую вкладку в отдельный модуль (`_home_tab.py`, `_reports_tab.py`, `_diagnostics_tab.py`, `_logs_tab.py`, `_settings_tab.py`).

### 4.3 Layer Violations

#### 4.3.1 Domain → Infrastructure (DIP нарушение)

| Файл | Строка | Импорт | Нарушение |
|------|--------|--------|-----------|
| `core/domain/data_loss_log.py` | 14 | `from core.infra.utils_logging import scrub_path` | Domain зависит от конкретного инфра-модуля вместо абстракции |

**Транзитивная цепочка**: `core.infra.reconciliation._collect:6` → `core.domain.data_loss_log:14` → `core.infra.utils_logging` — infra → domain → infra.

**Рекомендация**: Вынести `scrub_path` в domain utils или передавать через параметр (интерфейс).

#### 4.3.2 Presentation → Infrastructure (минуя business слой)

| Файл | Строка | Импорт | Нарушение |
|------|--------|--------|-----------|
| `core/ui/gui_master.py` | 21 | `from core.infra import ConfigController, setup_gui_logging, open_path` | Presentation → Infra напрямую |
| `core/ui/gui_master_settings.py` | 18 | `from core.infra.settings_store import SettingsStore, UIPreferences` | Presentation → Infra напрямую |
| `core/ui/ui_dashboard.py` | 9 | `from core.infra import open_path` | Presentation → Infra напрямую |
| `core/ui/ui_settings.py` | 22-23 | `from core.infra.config_controller import ConfigController` / `from core.infra.settings_store import SettingsStore` | Presentation → Infra напрямую |
| `core/ui/gui_commands/_base.py` | 19 | `from core.infra import open_path` | Presentation → Infra напрямую |
| `core/ui/gui_commands/_employee.py` | 13 | `from core.infra import open_path` | Presentation → Infra напрямую |

**Рекомендация**: Прокси-методы (`open_path`, `ConfigController`, `SettingsStore`) должны предоставляться через `AppController` или отдельный `UIService` фасад в application-слое.

### 4.4 SOLID Violations

#### 4.4.1 SRP (Single Responsibility)

| Файл | Класс/модуль | Нарушение | Детали |
|------|-------------|-----------|--------|
| `core/app_controller.py:88` | `AppController` | 9 ответственностей | См. раздел 4.2.1 |
| `core/infra/ingestion_reader.py:202` | `CalamineReader` | 8 ответственностей | См. раздел 4.2.2 |
| `core/ui/ui_dashboard.py:32` | `DashboardTabs` | 9 ответственностей | См. раздел 4.2.3 |

#### 4.4.2 OCP (Open/Closed)

| Файл | Строка | Нарушение |
|------|--------|-----------|
| `core/app_controller.py:1044-1097` | Методы `run_rsch_report`, `run_rsch_report_period`, `run_rsch_report_period_batch`, `run_rsch_report_batch` | Добавление нового типа отчёта требует модификации `AppController` (добавление нового `run_*` метода) вместо расширения через стратегию/команду |

**Позитивный пример OCP**: `core/domain/logic_service.py:151-185` — `CuratorStrategy` → `BorisCuratorStrategy` / `IvanCuratorStrategy` — добавление нового куратора не требует модификации `LogicService`.

#### 4.4.3 LSP (Liskov Substitution)

Нарушений не обнаружено. `BorisCuratorStrategy` и `IvanCuratorStrategy` (`logic_service.py:167,182`) корректно подставляются вместо `CuratorStrategy` (`logic_service.py:151`).

#### 4.4.4 ISP (Interface Segregation)

| Файл | Строка | Нарушение |
|------|--------|-----------|
| `core/domain/interfaces.py` | (весь файл) | `IPersistence` объединяет session management, source file tracking, staging data — потенциально можно разделить на `ISessionRepository`, `ISourceFileRepository`, `IStagingRepository` |

**Позитивный пример ISP**: `interfaces.py` определяет 5 отдельных интерфейсов (`IDataSource`, `IPersistence`, `IValidator`, `ILogicService`, `IExporter`) вместо одного «бога-интерфейса».

#### 4.4.5 DIP (Dependency Inversion)

| Файл | Строка | Нарушение |
|------|--------|-----------|
| `core/domain/data_loss_log.py` | 14 | Domain зависит от конкретного `core.infra.utils_logging.scrub_path` вместо абстракции |
| `core/ui/gui_master.py` | 21 | Presentation зависит от конкретного `core.infra.ConfigController` вместо интерфейса |
| `core/ui/ui_settings.py` | 22-23 | Presentation зависит от конкретных infra-классов |

**Позитивный пример DIP**: `core/infra/export_writer.py:10` — `from core.domain import IExporter` — infra зависит от domain-интерфейса (порт). `core/infra/ingestion_engine.py:14` — `from core.domain import IDataSource`. `core/infra/session_repo.py:5` — `from core.domain import IPersistence`.

### 4.5 Dead Code

| Модуль | Строк | Импортируется в production? | Примечание |
|--------|-------|---------------------------|------------|
| `core/infra/event_bus.py` | 75 | ❌ Нет (только в `tests/test_phase3_reliability.py`) | Thread-safe pub/sub event bus. Декларирован для декаплинга FileProcessor/AppController от GuiMaster, но фактически не используется ни одним production-модулем |
| `core/infra/metrics.py` | 65 | ❌ Нет (ни в production, ни в tests) | In-process метрики. Полностью мёртвый код |
| `APP/config_missing.yaml` | 77 | ❌ Нет (не referenced ни в одном .py) | Копия `config.example.yaml`. Не загружается ни одним модулем |

**Проверка**: grep по всем `.py` файлам проекта подтверждает — `event_bus` импортируется только в тестах, `metrics` не импортируется нигде.

---

## 5. Оценка связности

| Модуль | Cohesion | Coupling | Рекомендация |
|--------|----------|----------|--------------|
| `core/app_controller.py` | **low** — 9 разных доменов в одном классе | **tight** — импортирует 11 внутренних модулей, передаётся в GUI/ViewModels/Services | **split** — разбить на `ConsolidationService`, `RschService` (уже есть), `AliasService`, `PathResolver`, `MessageBuilder` |
| `core/infra/ingestion_reader.py` | **low** — 8 разных ответственностей | **moderate** — импортирует 2 модуля (domain utils, infra utils) | **split** — `HeaderClassifier`, `ColumnMapper`, `RowProcessor` |
| `core/ui/ui_dashboard.py` | **low** — 9 вкладок/доменов | **moderate** — импортирует 3 модуля (infra, dashboard_state, theme) | **split** — по одному модулю на вкладку |
| `core/ui/gui_master.py` | **medium** — composition root + thin delegations | **tight** — импортирует 16 модулей | **refactor** — вынести infra-зависимости в AppController facade |
| `core/infra/export_writer.py` | **medium-high** — все методы связаны с Excel export | **moderate** — импортирует 6 модулей (domain + infra) | **keep** — следить за circular dep с `core.infra.__init__` |
| `core/domain/logic_service.py` | **medium-high** — финансовая логика, единый домен | **moderate** — импортирует 3 domain модуля | **keep** — хорошая стратегия-паттерн для кураторов |
| `core/domain/interfaces.py` | **high** — только абстрактные интерфейсы | **loose** — только stdlib | **keep** |
| `core/domain/data_schemas.py` | **high** — одна Pydantic-схема | **loose** — только stdlib | **keep** |
| `core/domain/utils_helpers.py` | **high** — утилиты парсинга чисел | **loose** — только stdlib | **keep** |
| `core/infra/db_connection.py` | **high** — SQLite connection management | **loose** — только stdlib | **keep** |
| `core/infra/config_controller.py` | **high** — конфигурация | **loose** — 1 импорт (utils_logging) | **keep** |
| `core/infra/discovery_service.py` | **medium-high** — file discovery + caching | **moderate** — 5 импортов | **keep** |
| `core/infra/ingestion_engine.py` | **medium-high** — Excel ingestion orchestration | **moderate** — 3 импорта | **keep** |
| `core/infra/session_repo.py` | **medium-high** — session/source/staging repos | **moderate** — 4 импорта | **keep** |
| `core/infra/reconciliation/_build.py` | **medium-high** — сборка Excel сверки | **moderate** — 7 импортов | **keep** |
| `core/infra/rsch/_build.py` | **medium-high** — сборка РСЧ Excel | **moderate** — 6 импортов | **keep** |
| `core/services/rsch_service.py` | **high** — оркестрация РСЧ | **moderate** — 2 импорта | **keep** |
| `core/services/reconciliation_service.py` | **high** — оркестрация сверки | **loose** — 1 импорт | **keep** |
| `core/view_models/consolidation_viewmodel.py` | **high** — состояние консолидации | **loose** — только stdlib, DI через конструктор | **keep** |
| `core/view_models/employee_list_viewmodel.py` | **high** — состояние списка сотрудников | **loose** — только stdlib, DI через конструктор | **keep** |
| `core/ui/theme.py` | **medium-high** — цветовые палитры + ttk styles | **loose** — 1 lazy импорт | **keep** |
| `core/ui/operation_state.py` | **high** — state machine операций | **loose** — только stdlib | **keep** |
| `core/ui/toast.py` | **high** — toast-уведомления | **loose** — только stdlib | **keep** |
| `core/ui/tooltip.py` | **high** — tooltip-виджет | **loose** — только stdlib | **keep** |
| `core/ui/debounce.py` | **high** — debounce-хелпер | **loose** — только stdlib | **keep** |
| `core/ui/geometry.py` | **high** — геометрия окна | **loose** — только stdlib | **keep** |
| `core/ui/ui_sidebar.py` | **medium-high** — sidebar с DateEntry | **moderate** — 3 импорта | **keep** |
| `core/ui/ui_employee_table.py` | **high** — таблица сотрудников | **moderate** — 2 импорта | **keep** |
| `core/ui/ui_settings.py` | **medium** — 8 вкладок настроек | **moderate** — 3 импорта (2 infra) | **refactor** — убрать infra-зависимость через фасад |
| `core/ui/gui_commands/_base.py` | **high** — CommandContext dataclass | **moderate** — 3 импорта (1 infra) | **refactor** — убрать `from core.infra import open_path` |
| `core/app/file_processor.py` | **medium-high** — многопоточное чтение Excel | **moderate** — 3 импорта | **keep** |
| `core/app/message_formatting.py` | **high** — форматирование сообщений | **loose** — только stdlib | **keep** |
| `core/app/partial.py` | **high** — .partial.xlsx переименование | **loose** — только stdlib | **keep** |
| `core/app/performance.py` | **high** — max_workers config | **loose** — только stdlib | **keep** |
| `core/bootstrap.py` | **medium** — composition root (по определению много импортов) | **tight** — 7 импортов (ожидаемо для bootstrap) | **keep** — это нормально для composition root |

---

## Краткое резюме

- **Паттерн**: [HYBRID] Layered Architecture + MVC + MVVM
- **Слоёв**: 6 (Presentation, Application/Services, Domain, Infrastructure, Bootstrap, Cross-cutting)
- **Circular dependencies**: 1 (package-level: `core.infra.__init__` ↔ `core.infra.export_writer`)
- **God objects**: 3 (`AppController`, `CalamineReader`, `DashboardTabs`)
- **Layer violations**: 7 (1 domain→infra, 6 presentation→infra)
- **SOLID violations**: 5 (3 SRP, 1 OCP, 1 DIP; ISP — частично)
- **Dead code**: 2 модуля (`event_bus.py`, `metrics.py`) + 1 конфиг (`config_missing.yaml`)
