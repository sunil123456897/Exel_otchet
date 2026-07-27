# Структурная карта проекта

## Метаданные
- Дата создания: 2026-06-25
- Проект: Master-Report v5.5
- Объём анализа: APP/ + tests/ + tools/ + корневые файлы
- Всего файлов в реестре: 124 (122 текстовых + 2 бинарных .xlsx)
- Точек входа: 5

---

## 1. Дерево директорий

```
Version5/                          [корень проекта]
├── APP/                           — основное приложение
│   ├── (root)                     — точка входа + конфиги + схема БД
│   │   Файлов: 5                  Категория: source / config
│   ├── core/                      — ядро приложения (MVC+MVVM слои)
│   │   ├── (root)                 — app_controller, bootstrap, __init__
│   │   │   Файлов: 3              Категория: source
│   │   ├── app/                   — прикладные сервисы (file processing, formatting, performance)
│   │   │   Файлов: 5              Категория: source
│   │   ├── domain/                — доменный слой: схемы, интерфейсы, бизнес-логика
│   │   │   Файлов: 6              Категория: source
│   │   ├── infra/                 — инфраструктурный слой: БД, экспорт, ингестия, конфиг
│   │   │   ├── (root)             — 19 модулей инфраструктуры
│   │   │   │   Файлов: 19         Категория: source
│   │   │   ├── reconciliation/    — отчёт расхождений (декомпозиция reconciliation_report.py)
│   │   │   │   Файлов: 6          Категория: source
│   │   │   └── rsch/              — РСЧ-отчёт (декомпозиция rsch_report.py)
│   │   │       Файлов: 5          Категория: source
│   │   ├── services/              — сервисы бизнес-оркестрации (вынесены из AppController)
│   │   │   Файлов: 3              Категория: source
│   │   ├── ui/                    — GUI слой (Tkinter): виджеты, тема, команды
│   │   │   ├── (root)             — 19 UI модулей
│   │   │   │   Файлов: 19         Категория: source
│   │   │   └── gui_commands/      — команды GUI (декомпозиция gui_commands монолита)
│   │   │       Файлов: 6          Категория: source
│   │   └── view_models/           — ViewModel слой (MVVM)
│   │       Файлов: 3              Категория: source
│   └── migrations/                — SQL-миграции БД
│       Файлов: 2                  Категория: config
├── tests/                         — автотесты (pytest)
│   ├── (root)                     — 25 тестовых модулей
│   │   Файлов: 25                 Категория: test
│   ├── core/infra/                — тесты инфраструктурных отчётов
│   │   Файлов: 2                  Категория: test
│   └── golden/                    — golden-тесты (эталонные .xlsx)
│       └── backups/excel_outputs/reference_output/
│           Файлов: 2              Категория: asset
├── tools/                         — вспомогательные скрипты
│   Файлов: 9                      Категория: source
└── (корневые файлы)               — конфиги, документация, bat-запуск, eval-скрипты
    Файлов: 22                     Категория: config / doc / source / generated
```

---

## 2. Реестр файлов

### APP/ — корневые файлы приложения

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `APP/main.py` | python | source | GUI точка входа: настройка логирования, DPI-awareness, Bootstrap.setup, запуск Tk mainloop | 98 | 2026-06-19 | sys, tkinter, logging, logging.handlers, ctypes, pathlib.Path, tkinter.messagebox, core.bootstrap.Bootstrap |
| `APP/headless_run.py` | python | source | CLI/headless точка входа: консолидация без GUI, --date флаг, signal handling, timeout | 80 | 2026-06-18 | os, sys, signal, logging, threading, argparse, datetime, pathlib.Path, core.bootstrap.Bootstrap |
| `APP/config.example.yaml` | yaml | config | Переносимый пример конфигурации: БД, пути, логика, кураторы, РСЧ, маркеры | 77 | 2026-06-19 | — |
| `APP/config_missing.yaml` | yaml | config | Копия config.example.yaml — fallback при отсутствии config.yaml [UNVERIFIED: точное назначение неясно, содержимое идентично config.example.yaml] | 77 | 2026-06-25 | — |
| `APP/db_schema.sql` | sql | config | SQLite-схема: 9 таблиц (_migrations, sessions, source_files, staging_data, consolidated_results, template_errors, file_cache, row_cache, discovery_cache, customer_aliases) + индексы | 108 | 2026-06-18 | — |

### APP/core/ — ядро (корневые модули)

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `APP/core/__init__.py` | python | source | Пустой пакетный init | 0 | 2026-06-15 | — |
| `APP/core/app_controller.py` | python | source | Главный контроллер приложения: оркестрация консолидации, РСЧ, сверки; делегирование сервисам; threading | 1026 | 2026-06-18 | concurrent.futures, logging, os, threading, uuid, datetime, collections.abc, pathlib, typing, core.infra (DiscoveryService, is_file_writable), core.infra.utils_logging, core.app.file_processor, core.app.performance, core.app.message_formatting, core.infra.reconciliation, core.infra.rsch, core.services.rsch_service, core.services.reconciliation_service, core.app.partial, core.infra.utils |
| `APP/core/bootstrap.py` | python | source | Инициализация приложения: загрузка конфига, проверка зависимостей, создание БД, ingestion engine, session repo, LogicService, AppController; проверка целостности БД | 402 | 2026-06-18 | logging, importlib.util, re, sqlite3, pathlib, typing, pydantic.BaseModel, core.infra (ConfigController, MasterWriter), core.infra.utils, core.infra.ingestion_engine, core.infra.session_repo, core.domain (LogicService, Validator), core.app_controller.AppController |

### APP/core/app/ — прикладные сервисы

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `APP/core/app/__init__.py` | python | source | Пустой пакетный init | 0 | 2026-06-15 | — |
| `APP/core/app/file_processor.py` | python | source | Обработка файлов: многопоточное чтение Excel, row cache, прогресс-колбэки | 375 | 2026-06-18 | os, logging, time, concurrent.futures, threading, datetime, pathlib, typing, core.app.performance, core.infra (is_file_writable), core.infra.utils_logging |
| `APP/core/app/message_formatting.py` | python | source | Форматирование сообщений для UI: имена файлов, превью проблем, тексты статусов | 110 | 2026-06-18 | ntpath, os, datetime, typing |
| `APP/core/app/partial.py` | python | source | Переименование прерванных файлов в .partial.xlsx (как в браузерах для загрузок) | 60 | 2026-06-18 | logging, pathlib, typing |
| `APP/core/app/performance.py` | python | source | Настройка max_workers: default = min(32, CPU_COUNT*2), override из конфига | 18 | 2026-06-15 | os, typing |

### APP/core/domain/ — доменный слой

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `APP/core/domain/__init__.py` | python | source | Публичный API домена: IDataSource, IPersistence, IValidator, ILogicService, IExporter, NumericParsingError, to_decimal, to_decimal_percent, FinancialRowSchema, LogicService, Validator | 17 | 2026-06-18 | core.domain.interfaces, core.domain.utils_helpers, core.domain.data_schemas, core.domain.logic_service |
| `APP/core/domain/data_loss_log.py` | python | source | Аудит-логгер потери данных: запись каждого случая тихого отбрасывания/преобразования пользовательских данных | 111 | 2026-06-18 | json, logging, os, re, threading, datetime, pathlib, core.infra.utils_logging |
| `APP/core/domain/data_schemas.py` | python | source | Pydantic-схема FinancialRowSchema: валидация строк финансовых данных, Decimal precision | 85 | 2026-06-18 | decimal, typing, pydantic (BaseModel, Field, field_validator, ConfigDict), datetime |
| `APP/core/domain/interfaces.py` | python | source | Абстрактные интерфейсы: IDataSource, IPersistence, IValidator, ILogicService, IExporter | 116 | 2026-06-15 | abc, typing, pathlib |
| `APP/core/domain/logic_service.py` | python | source | Бизнес-логика: Validator (валидация строк), LogicService (применение финансовых правил: приход/расход/комиссия/фильтры) | 448 | 2026-06-18 | logging, re, decimal, typing, core.domain.interfaces, core.domain.utils_helpers, core.domain.data_schemas |
| `APP/core/domain/utils_helpers.py` | python | source | Утилиты парсинга: to_decimal, to_decimal_percent, NumericParsingError, regex-паттерны очистки чисел | 70 | 2026-06-18 | re, decimal, typing |

### APP/core/infra/ — инфраструктурный слой (корневые модули)

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `APP/core/infra/__init__.py` | python | source | Публичный API инфра: open_path, is_file_writable, get_local_copy, setup_gui_logging, ConfigController, MasterWriter, SessionRepository, DiscoveryService, resolve_employee_path | 13 | 2026-06-18 | core.infra.utils, core.infra.utils_logging, core.infra.config_controller, core.infra.export_writer, core.infra.session_repo, core.infra.discovery_service, core.infra.path_resolver |
| `APP/core/infra/config_controller.py` | python | source | Контроллер конфигурации: загрузка/валидация config.yaml (ruamel.yaml), thread-safe доступ, scrub_path | 233 | 2026-06-18 | os, logging, hashlib, re, threading, pathlib, typing, ruamel.yaml, core.infra.utils_logging |
| `APP/core/infra/customer_alias_repo.py` | python | source | Репозиторий алиасов заказчиков (customer_aliases): CRUD для маппинга master↔РСЧ | 170 | 2026-06-18 | logging, typing, core.infra.db_connection |
| `APP/core/infra/db_connection.py` | python | source | Менеджер SQLite-соединений: DecimalEncoder, sanitize_data, WAL, PRAGMA, thread-safe | 253 | 2026-06-18 | sqlite3, json, time, decimal, datetime, logging, threading, typing, pathlib |
| `APP/core/infra/discovery_service.py` | python | source | Сервис обнаружения файлов: сканирование сетевых папок, кэш discovery, хеширование путей | 375 | 2026-06-18 | hashlib, logging, time, concurrent.futures, pathlib, typing, core.infra.config_controller, core.infra.ingestion_engine, core.infra.path_resolver |
| `APP/core/infra/event_bus.py` | python | source | Thread-safe pub/sub event bus: декаплинг FileProcessor/AppController от GuiMaster | 75 | 2026-06-18 | queue, logging, threading, dataclasses, enum, typing |
| `APP/core/infra/excel_backup.py` | python | source | Бэкап Excel-выводов: resolve_excel_backup_keep, backup_existing_excel_output (ротация N файлов) | 52 | 2026-06-15 | logging, shutil, datetime, pathlib |
| `APP/core/infra/excel_hyperlinks.py` | python | source | Управление гиперссылками в openpyxl: apply_cell_hyperlink, extract_hyperlink_formula_parts | 59 | 2026-06-15 | pathlib, typing, openpyxl.cell.cell, openpyxl.styles |
| `APP/core/infra/export_formatting.py` | python | source | Excel-стили: ExcelStyles (цвета, шрифты, заливка, границы, выравнивание) | 336 | 2026-06-18 | logging, decimal, openpyxl.utils, openpyxl.styles |
| `APP/core/infra/export_writer.py` | python | source | Экспорт мастер-отчёта: MasterWriter, ExportPreflightError, запись в Excel через openpyxl | 597 | 2026-06-18 | os, logging, datetime, decimal, typing, pathlib, openpyxl, openpyxl.utils, openpyxl.styles, core.domain (IExporter), core.domain.utils_helpers, core.infra (is_file_writable), core.infra.excel_backup, core.infra.export_formatting, core.infra.excel_hyperlinks |
| `APP/core/infra/ingestion_engine.py` | python | source | Движок ингестии: IngestionEngine — чтение Excel через Calamine, извлечение XML, zip-парсинг | 423 | 2026-06-18 | os, logging, time, json, subprocess, sys, threading, zipfile, pathlib, typing, xml.etree.ElementTree, python_calamine, core.domain (IDataSource), core.infra.utils |
| `APP/core/infra/ingestion_reader.py` | python | source | CalamineReader — парсинг Excel через python-calamine, extract_date_from_sheet, извлечение строк | 1012 | 2026-06-21 | os, re, logging, pathlib, datetime, decimal, typing, python_calamine, core.domain.utils_helpers, core.infra.utils |
| `APP/core/infra/metrics.py` | python | source | In-process метрики: thread-safe счётчики для мониторинга консолидации | 65 | 2026-06-15 | logging, threading, time, typing |
| `APP/core/infra/path_resolver.py` | python | source | Резолвер путей: нормализация, resolve_employee_path, алиасы «Отчеты» | 137 | 2026-06-18 | logging, pathlib, typing |
| `APP/core/infra/session_repo.py` | python | source | Репозиторий сессий: SessionRepository (IPersistence), SourceFileRepository, StagingDataRepository, DBWriterThread | 255 | 2026-06-18 | json, logging, typing, pathlib, core.domain (IPersistence), core.infra.db_connection, core.infra.source_file_repo, core.infra.staging_repo |
| `APP/core/infra/settings_store.py` | python | source | Хранение UI-настроек: UIPreferences dataclass, SettingsStore (секция ui: в config.yaml) | 114 | 2026-06-25 | logging, dataclasses, typing, core.infra.config_controller |
| `APP/core/infra/source_file_repo.py` | python | source | Репозиторий source_files: SourceFileRepository, трекинг файлов сессии, хеши, inode | 241 | 2026-06-18 | json, logging, threading, queue, typing, core.infra.db_connection |
| `APP/core/infra/staging_repo.py` | python | source | Репозиторий staging_data: StagingDataRepository, DBWriterThread — буфер raw строк перед консолидацией | 198 | 2026-06-18 | json, logging, decimal, threading, queue, typing, pathlib, core.infra.db_connection |
| `APP/core/infra/utils_logging.py` | python | source | Утилиты логирования: scrub_path, safe_file_label, setup_gui_logging — безопасное логирование путей | 83 | 2026-06-18 | logging, queue, hashlib, re, pathlib |
| `APP/core/infra/utils.py` | python | source | Общие утилиты: open_path, is_file_writable, get_local_copy, atomic_save_workbook, cleanup_local_copy_cache | 225 | 2026-06-18 | os, subprocess, platform, hashlib, logging, shutil, tempfile, threading, time, types, pathlib |

### APP/core/infra/reconciliation/ — отчёт расхождений

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `__init__.py` | python | source | Публичный API пакета: MasterReconciliationRow, RschReconciliationRow, ReconciliationRow, _row_id, build_reconciliation_report, build_combined_reconciliation_report | 26 | 2026-06-18 | ._types, ._utils, ._build |
| `_build.py` | python | source | Сборка Excel-отчёта сверки: _build_workbook, build_reconciliation_report, build_combined_reconciliation_report | 432 | 2026-06-25 | datetime, pathlib, typing, openpyxl (Workbook, load_workbook, styles, comments, utils), core.infra.excel_hyperlinks, core.infra.excel_backup, core.infra.utils, ._types, ._utils, ._resolve, ._collect |
| `_collect.py` | python | source | Сбор строк сверки из Excel: _collect_master_rows, _collect_rsch_rows, чтение гиперссылок | 597 | 2026-06-25 | logging, decimal, typing, openpyxl, core.domain.data_loss_log, core.infra.excel_hyperlinks, ._types, ._utils, ._resolve |
| `_resolve.py` | python | source | Резолвер сверки: date/sheet resolution, executor/customer matching, _executor_matches | 186 | 2026-06-25 | contextlib, datetime, decimal, pathlib, openpyxl, core.infra.utils, ._types, ._utils |
| `_types.py` | python | source | Dataclass-типы сверки: MasterReconciliationRow, RschReconciliationRow, ReconciliationRow | 31 | 2026-06-25 | dataclasses, decimal, typing |
| `_utils.py` | python | source | Утилиты сверки: _to_decimal, _excel_safe_text, _row_id, константы стилей, lru_cache | 388 | 2026-06-25 | re, decimal, functools, typing, openpyxl.styles, ._types |

### APP/core/infra/rsch/ — РСЧ-отчёт

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `__init__.py` | python | source | Публичный API пакета: build_rsch_report | 9 | 2026-06-18 | ._build |
| `_build.py` | python | source | Сборка РСЧ-отчёта в Excel: build_rsch_report, копирование стилей, шаблоны | 479 | 2026-06-24 | logging, copy, datetime, decimal, pathlib, typing, openpyxl, core.infra.excel_hyperlinks, core.infra.excel_backup, core.infra.utils, ._format, ._collect, ._template |
| `_collect.py` | python | source | Сбор строк РСЧ из workbooks: _collect_rows_from_workbook, _copy_style, _normalize_source_paths | 386 | 2026-06-18 | logging, copy, datetime, decimal, pathlib, typing, openpyxl |
| `_format.py` | python | source | Форматирование РСЧ: _normalize_text, _to_decimal, _excel_safe_text, _display_len, _is_problem_row | 180 | 2026-06-24 | logging, datetime, decimal, pathlib, typing, openpyxl.styles |
| `_template.py` | python | source | Шаблоны РСЧ: _create_builtin_template_workbook, _find_total_row, _resolve_template_style_layout, стили | 318 | 2026-06-24 | logging, copy, pathlib, typing, openpyxl (Workbook, styles, utils), ._format, ._collect |

### APP/core/services/ — сервисы оркестрации

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `__init__.py` | python | source | Пакетный init: документация сервисного слоя | 4 | 2026-06-18 | — |
| `reconciliation_service.py` | python | source | ReconciliationService — оркестрация сверки, вынесена из AppController | 62 | 2026-06-18 | logging, threading, pathlib, typing, core.infra.reconciliation |
| `rsch_service.py` | python | source | RschService — 4 варианта run_rsch_* (день/месяц/combined/single), вынесен из AppController | 252 | 2026-06-18 | logging, threading, datetime, pathlib, typing, core.infra.rsch, core.app.message_formatting |

### APP/core/ui/ — GUI слой (корневые модули)

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `__init__.py` | python | source | Пустой пакетный init | 0 | 2026-06-15 | — |
| `dashboard_state.py` | python | source | Состояние дашборда: PathInfo, RuntimeResult, build_diagnostic_summary, read_recent_logs/errors | 430 | 2026-06-18 | os, json, sys, dataclasses, datetime, pathlib, typing |
| `debounce.py` | python | source | Debounce-хелпер для tkinter StringVar traces: отложенный вызов фильтра | 61 | 2026-06-18 | typing |
| `geometry.py` | python | source | Сохранение/восстановление геометрии окна: ~/.master_report_geometry, off-screen fallback | 93 | 2026-06-18 | typing |
| `gui_master.py` | python | source | Главный GUI-класс GuiMaster: сборка всех виджетов, sidebar, dashboard, employee table, commands | 348 | 2026-06-25 | logging, tkinter, pathlib, typing, core.ui.ui_sidebar, core.ui.ui_employee_table, core.ui.ui_stats_panel, core.ui.ui_log_panel, core.ui.ui_dashboard, core.ui.theme, core.ui.geometry, core.ui.operation_state, core.ui.operation_status_bar, core.ui.toast, core.infra, core.app_controller, core.view_models, core.ui.gui_commands, core.ui.gui_master_settings |
| `gui_master_settings.py` | python | source | Mixin для GuiMaster: загрузка/применение UIPreferences, открытие диалога настроек | 100 | 2026-06-25 | logging, typing, core.ui.theme, core.infra.settings_store |
| `operation_state.py` | python | source | Глобальная state machine операций: OperationState, OperationType, begin/end/request_cancel, listeners | 152 | 2026-06-18 | logging, threading, time, dataclasses, enum, typing |
| `operation_status_bar.py` | python | source | Status bar: имя операции, прогресс, elapsed time, ETA, Cancel button | 149 | 2026-06-18 | time, tkinter, typing, core.ui.operation_state |
| `system_theme.py` | python | source | Детектор тёмной темы ОС: Windows (registry), macOS (osascript), Linux (gsettings) | 137 | 2026-06-18 | logging, platform, shutil, subprocess, typing |
| `theme.py` | python | source | ThemeManager v2: цветовые палитры (light/dark), ttk styles, adaptive scaling, FONTS/SPACING/RADIUS/CONTROL | 715 | 2026-06-25 | math, tkinter, typing |
| `toast.py` | python | source | Non-modal toast-уведомления: до 3 одновременно, fade-out, ToastLevel, ToastManager | 348 | 2026-06-18 | logging, tkinter, dataclasses, enum, typing |
| `tooltip.py` | python | source | Лёгкий tooltip-виджет для ttk: hover, fade-in, без сторонних зависимостей | 195 | 2026-06-18 | logging, tkinter, typing |
| `ui_aliases.py` | python | source | UI-вкладка алиасов заказчиков: ручной маппинг master↔РСЧ для сверки | 216 | 2026-06-23 | tkinter, logging |
| `ui_dashboard.py` | python | source | DashboardTabs: вкладки диагностики, результаты операций, открытие файлов | 690 | 2026-06-19 | logging, threading, tkinter, datetime, pathlib, tkinter (filedialog, messagebox, ttk), typing, core.infra, core.ui.dashboard_state, core.ui.theme |
| `ui_dialogs.py` | python | source | Диалоги: show_multi_file_select_dialog, выбор нескольких файлов | 237 | 2026-06-18 | os, tkinter, pathlib, typing |
| `ui_employee_table.py` | python | source | EmployeeTable: таблица сотрудников, поиск/фильтр, debounce | 167 | 2026-06-25 | tkinter, core.ui.debounce, core.ui.theme |
| `ui_log_panel.py` | python | source | LogPanel: текстовая панель логов (scrolledtext) | 52 | 2026-06-19 | tkinter, core.ui.theme |
| `ui_settings.py` | python | source | Универсальный диалог настроек: 8 вкладок, deep copy конфига, Apply/OK/Cancel, live preview | 568 | 2026-06-25 | copy, logging, tkinter, typing, core.infra.config_controller, core.infra.settings_store, core.ui.theme |
| `ui_sidebar.py` | python | source | Sidebar: выбор даты (DateEntry), кнопки операций, debounce поиска | 442 | 2026-06-25 | sys, logging, tkinter, tkcalendar, datetime, core.ui.theme, core.ui.debounce |
| `ui_stats_panel.py` | python | source | StatsPanel: статистика сотрудников, прогресс-индикатор | 77 | 2026-06-19 | tkinter |

### APP/core/ui/gui_commands/ — команды GUI

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `__init__.py` | python | source | GuiCommands: композиция 4 feature-миксинов (Employee/Consolidation/Reconciliation + transitively Rsch), CommandContext | 73 | 2026-06-18 | core.ui.gui_commands._base, core.ui.gui_commands._consolidation, core.ui.gui_commands._employee, core.ui.gui_commands._reconciliation |
| `_base.py` | python | source | CommandContext dataclass + finish() helper: общий контекст для всех команд | 120 | 2026-06-18 | logging, dataclasses, pathlib |
| `_consolidation.py` | python | source | ConsolidationCommandsMixin: 3 команды (day / all dates / month) | 66 | 2026-06-18 | tkinter, core.ui.operation_state, core.ui.gui_commands._base |
| `_employee.py` | python | source | EmployeeCommandsMixin: refresh, add, delete, attach files, open folder | 159 | 2026-06-18 | tkinter, pathlib, typing, core.infra, core.ui.operation_state, core.ui.gui_commands._base |
| `_reconciliation.py` | python | source | ReconciliationCommandsMixin: ручная и автоматическая сверка, наследует RschCommandsMixin | 131 | 2026-06-18 | pathlib, tkinter, typing, core.ui.operation_state, core.ui.gui_commands._base, core.ui.gui_commands._rsch |
| `_rsch.py` | python | source | RschCommandsMixin: РСЧ команды (день/месяц), persistence helpers (saved sources, dirs) | 209 | 2026-06-18 | pathlib, tkinter, typing, core.ui.operation_state, core.ui.gui_commands._base |

### APP/core/view_models/ — ViewModel слой

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `__init__.py` | python | source | Пакетный init: документация MVVM-слоя | 1 | 2026-06-15 | — |
| `consolidation_viewmodel.py` | python | source | ConsolidationViewModel: состояние и логика консолидации | 103 | 2026-06-18 | threading, typing, datetime, pathlib, logging |
| `employee_list_viewmodel.py` | python | source | EmployeeListViewModel: EmployeeStatus dataclass, состояние списка сотрудников | 186 | 2026-06-18 | threading, typing, datetime, pathlib, logging, dataclasses |

### APP/migrations/ — SQL-миграции

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `001_numeric_to_text.sql` | sql | config | Миграция: NUMERIC→TEXT для financial columns (staging_data, consolidated_results), table-rebuild pattern | 45 | 2026-06-18 | — |
| `002_customer_aliases.sql` | sql | config | Миграция: создание таблицы customer_aliases + индексы для маппинга сверки | 20 | 2026-06-18 | — |

### tests/ — автотесты

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `tests/test_audit_refactoring.py` | python | test | Аудит рефакторинга: CalamineReader + FinancialRowSchema валидация | 35 | 2026-06-13 | pytest, decimal, core.infra.ingestion_reader, core.domain.data_schemas |
| `tests/test_dashboard_state_extended.py` | python | test | Расширенные тесты dashboard_state: read_recent_log_errors, read_recent_logs | 31 | 2026-06-18 | core.ui.dashboard_state |
| `tests/test_data_loss_log.py` | python | test | Тесты data_loss_log: record_loss, reset_for_testing | 49 | 2026-06-13 | json, os, pathlib, pytest, core.domain.data_loss_log |
| `tests/test_db_pragmas_and_migrations.py` | python | test | PRAGMA-проверки, BEGIN IMMEDIATE, система миграций | 185 | 2026-06-24 | sys, tempfile, pathlib |
| `tests/test_debounce.py` | python | test | Тесты Debouncer: отложенный вызов, tkinter after | 76 | 2026-06-09 | time, tkinter, unittest.mock, pytest, core.ui.debounce |
| `tests/test_export_writer_edge_cases.py` | python | test | Edge cases MasterWriter: ExportPreflightError, zipfile, mock patch | 47 | 2026-06-13 | pytest, zipfile, datetime, pathlib, unittest.mock, core.infra.export_writer |
| `tests/test_file_processor_time_module.py` | python | test | Регрессия: file_processor должен использовать `time` а не `_time` (NameError bug) | 37 | 2026-06-09 | re, sys, pathlib |
| `tests/test_finish_helper.py` | python | test | Тесты CommandContext и finish() helper (Phase 5.3 split) | 192 | 2026-06-13 | logging, pathlib, unittest.mock, core.ui.gui_commands._base, core.ui.operation_state, core.ui.toast |
| `tests/test_geometry.py` | python | test | Тесты geometry: сохранение/восстановление, off-screen fallback | 44 | 2026-06-13 | pathlib, core.ui.geometry |
| `tests/test_operation_state.py` | python | test | Тесты OperationState: begin/end/cancel, listeners, threading | 138 | 2026-06-13 | threading, time, pytest, core.ui.operation_state |
| `tests/test_operation_status_bar.py` | python | test | Тесты OperationStatusBar: прогресс, elapsed, ETA, _format_duration | 140 | 2026-06-18 | tkinter, time, unittest.mock, pytest, core.ui.operation_state, core.ui.operation_status_bar, core.ui.toast |
| `tests/test_partial_renamer.py` | python | test | Тесты partial.py: mark_partial, format_partial_note | 75 | 2026-06-09 | shutil, tempfile, unittest, pathlib, core.app.partial |
| `tests/test_percentage_matching_bugs.py` | python | test | Тесты LogicService: BorisCuratorStrategy, процентное сопоставление | 20 | 2026-06-13 | pytest, decimal, core.domain.logic_service |
| `tests/test_phase0_gui_marshaling.py` | python | test | Phase 0: GUI marshaling, threading, SimpleNamespace, GuiMaster import guard | 98 | 2026-06-14 | threading, types, unittest.mock, pytest, core.ui.gui_master |
| `tests/test_phase0_reconciliation_fail_soft.py` | python | test | Phase 0: fail-soft сверка, _collect, data_loss_log reset | 192 | 2026-06-14 | json, os, decimal, pathlib, typing, openpyxl, pytest, core.domain.data_loss_log, core.infra.reconciliation._collect |
| `tests/test_phase0_workbook_release.py` | python | test | Phase 0: освобождение workbook (MasterWriter), mock patch | 174 | 2026-06-14 | datetime, pathlib, unittest.mock, pytest, core.infra.export_writer |
| `tests/test_phase1_export_decimal.py` | python | test | Phase 1: Decimal precision в экспорте, MasterWriter | 131 | 2026-06-14 | tempfile, decimal, pathlib, openpyxl, pytest, core.infra.export_writer |
| `tests/test_phase1_schema_validator.py` | python | test | Phase 1: FinancialRowSchema валидация, Decimal | 89 | 2026-06-14 | decimal, pytest, core.domain.data_schemas |
| `tests/test_phase2_db_repositories.py` | python | test | Phase 2: DB-репозитории (SourceFile, Staging), JSON | 138 | 2026-06-14 | json, pathlib, pytest |
| `tests/test_phase2_ingestion_reader.py` | python | test | Phase 2: CalamineReader, ingestion_reader функции | 83 | 2026-06-24 | pytest, core.infra.ingestion_reader |
| `tests/test_phase2_logic_service.py` | python | test | Phase 2: LogicService.apply_financial_rules, Decimal | 194 | 2026-06-14 | decimal, typing, pytest, core.domain.logic_service |
| `tests/test_phase3_reliability.py` | python | test | Phase 3: EventBus singleton race, migration atomicity, SourceFileRepository error propagation | 170 | 2026-06-24 | sys, tempfile, threading, pathlib, pytest |
| `tests/test_system_theme.py` | python | test | Тесты system_theme: детектор тёмной темы (Windows/macOS/Linux) | 67 | 2026-06-13 | platform, core.ui.system_theme |
| `tests/test_theme_manager.py` | python | test | Тесты ThemeManager: палитры, ttk styles, set_theme | 54 | 2026-06-18 | tkinter, unittest.mock, pytest, core.ui.theme |
| `tests/test_tooltip.py` | python | test | Тесты Tooltip: hover, fade-in, видимость | 98 | 2026-06-09 | tkinter, unittest.mock, pytest, core.ui.tooltip |
| `tests/core/infra/test_reconciliation_report.py` | python | test | Тесты отчёта сверки: build_reconciliation_report, openpyxl Workbook | 187 | 2026-06-13 | tempfile, pathlib, datetime, decimal, pytest, openpyxl |
| `tests/core/infra/test_rsch_report.py` | python | test | Тесты РСЧ-отчёта: build_rsch_report, openpyxl | 126 | 2026-06-24 | tempfile, pathlib, datetime, decimal, openpyxl |
| `tests/golden/.../20260601_154442_284608_reference_output.xlsx` | xlsx | asset | Golden-тест эталон: эталонный Excel-вывод для сравнения (6856 байт) | — | 2026-05-23 | — |
| `tests/golden/.../20260601_162702_313519_reference_output.xlsx` | xlsx | asset | Golden-тест эталон: эталонный Excel-вывод для сравнения (6856 байт) | — | 2026-06-01 | — |

### tools/ — вспомогательные скрипты

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `tools/cleanup.ps1` | powershell | source | Очистка transient-файлов (startup_log, gui_error_log) и stale __pycache__ | 41 | 2026-06-25 | — |
| `tools/diff_workspaces.py` | python | source | Сравнение файлов между двумя рабочими пространствами (difflib) | 39 | 2026-06-18 | sys, os, difflib |
| `tools/find_large.ps1` | powershell | source | Поиск файлов >2MB в REPORTS, РСЧ, «рсч всех» | 5 | 2026-06-18 | — |
| `tools/merge_to_pdf.py` | python | source | Сборка всех .py/.bat/.ps1 в один PDF (fpdf) | 123 | 2026-06-23 | argparse, subprocess, sys, pathlib, fpdf |
| `tools/merge_to_txt.py` | python | source | Сборка всех исходников в один .txt файл | 57 | 2026-06-24 | sys, pathlib |
| `tools/precommit_check.py` | python | source | Pre-commit gate: ruff (F401 fix + lint) + mypy baseline mode | 81 | 2026-06-25 | subprocess, sys, pathlib |
| `tools/test_user_flows.py` | python | source | E2E тесты user flows: Consolidation, RSCH, Reconciliation через Bootstrap | 92 | 2026-06-24 | sys, os, threading, datetime, pathlib, core.bootstrap |
| `tools/trace_sbi.py` | python | source | Трассировка scoring для СБИ-строк: inline-копия функций из _utils.py, openpyxl | 266 | 2026-06-25 | sys, decimal, openpyxl, functools, re, collections |
| `tools/update_from_github.ps1` | powershell | source | Безопасный updater: pull из GitHub, pinned commit SHA, install deps, launch | 439 | 2026-06-24 | — |

### Корневые файлы

| Файл | Тип | Категория | Назначение | Размер (строк) | Последнее изменение | Зависимости (импорты) |
|------|-----|-----------|------------|----------------|---------------------|----------------------|
| `.gitignore` | txt | config | Игнорирование: auto-generated отчёты, __pycache__, .venv, IDE, OS | 22 | 2026-06-25 | — |
| `.mypy_baseline.txt` | txt | generated | Базовые ошибки mypy (682 строки) — pre-commit gate блокирует только новые ошибки | 682 | 2026-06-25 | — |
| `ЗАПУСК.bat` | bat | config | Главный launcher v5.5: поиск Python, venv, pip, установка deps, GUI preflight, запуск main.py | 212 | 2026-06-25 | — |
| `ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat` | bat | config | Обёртка для tools/update_from_github.ps1: запуск updater + launch | 22 | 2026-06-25 | — |
| `ARCHITECTURE.md` | markdown | doc | Архитектура v5.5: слои (UI→Commands→Controller→Services→Domain→Infra), диаграмма | 136 | 2026-06-21 | — |
| `CHANGELOG_WEEK.md` | markdown | doc | Отчёт улучшений за неделю 13–19 июня 2026: 47 коммитов, ~3000 строк удалено | 216 | 2026-06-19 | — |
| `FEATURE_TABLE.csv` | csv | doc | Таблица 34 фич: ID, имя, тип, user story, expected behaviour, edge cases, test cases, status | 35 | 2026-06-24 | — |
| `features.json` | json | doc | JSON-реестр 34 фич: meta, critical_flows, детальное описание каждой фичи | 1717 | 2026-06-25 | — |
| `INTEGRATION.md` | markdown | doc | Инструкция интеграции v5.6: 5 файлов (theme, ui_settings, ui_sidebar, gui_master_settings, settings_store) | 126 | 2026-06-25 | — |
| `oracle.py` | python | source | Тестовый oracle: 5 тестов Validator/LogicService (whitespace, markers, zero formats, filters, headers) | 39 | 2026-06-06 | os, sys, decimal, core.domain.logic_service |
| `PROJECT.md` | markdown | doc | Краткий обзор QA-тестинга: архитектура, milestones (Ingestion/Reconciliation/Export), code layout | 14 | 2026-06-06 | — |
| `PROMPT_AI_SVERKA.md` | markdown | doc | Промт для AI-сверки Excel-отчётов расхождений за май 2026 | 43 | 2026-06-25 | — |
| `pyproject.toml` | toml | config | Ruff config: target py312, line-length 100, lint select E/F, per-file-ignores | 19 | 2026-06-18 | — |
| `QA_PROGRESS.md` | markdown | doc | QA progress: 34 фичи, категории, статус тестирования | 59 | 2026-06-24 | — |
| `QA_REPORT.md` | markdown | doc | QA audit report: 34 фичи, 292/292 тестов проходят, исправлен критический баг сверки | 57 | 2026-06-25 | — |
| `README.md` | markdown | doc | Главный README: описание v5.5, состав ветки main, runtime-only политика | 167 | 2026-06-18 | — |
| `requirements.txt` | txt | config | Runtime-зависимости: openpyxl, ruamel.yaml, tkcalendar, pyxlsb, PyYAML, pydantic, python-calamine | 7 | 2026-06-18 | — |
| `requirements-dev.txt` | txt | config | Dev-зависимости: +pytest, pytest-mock, pytest-cov, hypothesis, ruff, mypy, types-* | 10 | 2026-06-18 | — |
| `rlm_eval.py` | python | source | RLM-оценка кода v1: запуск внешнего Python 3.12 для оценки модулей по группам | 206 | 2026-06-11 | sys, os, json, time, traceback |
| `rlm_eval_v2.py` | python | source | RLM-оценка v2: subprocess + fast_rlm, batch-обработка | 280 | 2026-06-11 | subprocess, sys, os, json, re |
| `rlm_eval_v3.py` | python | source | RLM-оценка v3: улучшенная batch-обработка, OpenRouter API | 267 | 2026-06-11 | os, sys, json, time, traceback, re |
| `rlm_eval_v4.py` | python | source | RLM-оценка v4: fixed config для OpenRouter free tier limits, smaller batches | 222 | 2026-06-11 | os, sys, json, time, traceback, re |

---

## 3. Точки входа

### 3.1 GUI точка входа — `APP/main.py`
- **Что запускается**: Tkinter GUI-приложение Master-Report v5.5
- **Запуск**: `python APP/main.py` или `ЗАПУСК.bat`
- **Модули загружаются первыми**:
  1. `core.bootstrap.Bootstrap` — инициализация всего стека
  2. `core.ui.gui_master.GuiMaster` (через `preflight_gui_imports()`) — preflight проверка GUI-зависимостей
- **Конфигурации читаются**:
  - `APP/config.yaml` (передаётся в `Bootstrap.setup(app_root, config_path)`)
  - `APP/startup_log.txt` (RotatingFileHandler для логов)
- **Поток выполнения**:
  1. Настройка logging (RotatingFileHandler + StreamHandler)
  2. `_enable_dpi_awareness()` — ctypes windll для HiDPI
  3. `preflight_gui_imports()` — проверка импорта GuiMaster
  4. `Bootstrap.setup()` — конфиг, БД, ingestion, LogicService, AppController
  5. `tk.Tk()` + `GuiMaster(root, cfg_ctl, app_ctl)` — создание главного окна
  6. `root.mainloop()` — запуск event loop

### 3.2 CLI/headless точка входа — `APP/headless_run.py`
- **Что запускается**: Консолидация без GUI (для CI/CD и power users)
- **Запуск**: `python APP/headless_run.py [--date DD.MM.YYYY]`
- **Модули загружаются первыми**:
  1. `core.bootstrap.Bootstrap` — инициализация стека (без GUI)
- **Конфигурации читаются**:
  - `APP/config.yaml` (передаётся в `Bootstrap.setup()`)
  - Env var `HEADLESS_RUN_TIMEOUT` (default: 600 сек)
- **Поток выполнения**:
  1. argparse: `--date` (опционально, формат DD.MM.YYYY)
  2. signal handlers: SIGTERM/SIGINT → cancel_event
  3. `Bootstrap.setup()` — конфиг, БД, AppController
  4. Если `--date`: `app_ctl.run_consolidation(target_date, ...)`
  5. Иначе: `app_ctl.run_consolidation_all_dates(...)`
  6. `done.wait(timeout)` — ожидание завершения

### 3.3 Launcher точка входа — `ЗАПУСК.bat`
- **Что запускается**: Batch-скрипт для запуска GUI на рабочих ПК
- **Поток выполнения**:
  1. Поиск Python (venv → py -3.12 → py → python in PATH)
  2. Проверка/восстановление pip
  3. Проверка библиотек (tkinter, openpyxl, yaml, ruamel.yaml, tkcalendar, pyxlsb, pydantic, python_calamine)
  4. Установка из requirements.txt при необходимости
  5. GUI preflight: `python -c "import main; main.preflight_gui_imports()"`
  6. Запуск: `pythonw main.py` (без консоли) или `python main.py`

### 3.4 Updater точка входа — `ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat`
- **Что запускается**: Обёртка для `tools/update_from_github.ps1 -Launch`
- **Поток выполнения**:
  1. Поиск pwsh/powershell
  2. Запуск `tools/update_from_github.ps1 -Launch` (pull из GitHub, pinned commit, install deps, launch)

### 3.5 E2E тест точка входа — `tools/test_user_flows.py`
- **Что запускается**: End-to-end тесты ключевых user flows
- **Модули загружаются первыми**:
  1. `core.bootstrap.Bootstrap` — полная инициализация
- **Конфигурации читаются**: `APP/config.yaml`
- **Покрывает**: Consolidation, RSCH report, Reconciliation

---

## 4. Конфигурация сборки

### 4.1 `pyproject.toml`
- **Назначение**: Минимальная dev-конфигурация для runtime-only main ветки
- **Содержимое**:
  - `[tool.ruff]`: target-version = "py312", line-length = 100
  - exclude: .git, .pytest_cache, .ruff_cache, tmp_*, output, APP/output
  - `[tool.ruff.lint]`: select = ["E", "F"], ignore = ["E402", "E501", "E701"]
  - `[tool.ruff.lint.per-file-ignores]`: F401 для `APP/core/domain/__init__.py` и `APP/core/infra/__init__.py`
- **Зависимости**: не указаны (управляются через requirements.txt)
- **Скрипты**: не определены (entry points через main.py / headless_run.py)

### 4.2 `requirements.txt`
- **Назначение**: Runtime-зависимости для рабочих ПК
- **Пакеты**:
  - openpyxl==3.1.5 — Excel read/write
  - ruamel.yaml==0.18.6 — YAML config (с сохранением комментариев)
  - tkcalendar==1.6.1 — DateEntry виджет
  - pyxlsb==1.0.10 — чтение .xlsb файлов
  - PyYAML==6.0.1 — YAML (для employees.yaml)
  - pydantic==2.10.6 — FinancialRowSchema валидация
  - python-calamine==0.6.2 — быстрый Excel-парсер (CalamineReader)

### 4.3 `requirements-dev.txt`
- **Назначение**: Dev-зависимости (включает requirements.txt)
- **Дополнительно**:
  - pytest==9.0.2, pytest-mock==3.15.1, pytest-cov==7.0.0
  - hypothesis==6.151.10 — property-based testing
  - ruff==0.14.6 — linter
  - mypy==1.18.2 — type checker
  - pandas-stubs, types-openpyxl, types-psutil — stubs для mypy

### 4.4 `.gitignore`
- **Игнорирует**:
  - Auto-generated отчёты: Сверка_Master_РСЧ_*.xlsx, *.docx, Master-Report_*_TechnicalDoc.docx
  - PROMPT_AI_SVERKA.md, ИТОГИ_СЕССИИ_*.txt
  - Python: __pycache__/, *.pyc, .venv/, .venv_backup/, .pytest_cache/
  - IDE: .vscode/, .idea/
  - OS: Thumbs.db, .DS_Store
- **Не игнорирует**: tools/*.py (явно указано — bat и tools являются файлами проекта)

### 4.5 `.mypy_baseline.txt`
- **Назначение**: Базовый список известных ошибок mypy (682 строки)
- **Использование**: `tools/precommit_check.py` блокирует коммит только при появлении **новых** ошибок (не в baseline)
- **Содержит**: ошибки типа arg-type, no-untyped-def, union-attr, attr-defined и др. по всем модулям APP/core/

### 4.6 `ЗАПУСК.bat`
- **Назначение**: Главный launcher для рабочих ПК (Windows)
- **Логика**:
  1. Поиск Python: локальный .venv → py -3.12 → py → python in PATH → pyw
  2. Если .venv сломан (скопирован с другого ПК) — пересоздание
  3. Проверка pip (ensurepip при необходимости)
  4. Проверка 8 библиот: tkinter, openpyxl, yaml, ruamel.yaml, tkcalendar, pyxlsb, pydantic, python_calamine
  5. Установка из requirements.txt (в venv или --user)
  6. GUI preflight: `import main; main.preflight_gui_imports()`
  7. Запуск через pythonw (без консоли) или python (с консолью)
- **Логи**: startup_log.txt, gui_error_log.txt

### 4.7 `ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat`
- **Назначение**: Обёртка для tools/update_from_github.ps1
- **Логика**: Поиск pwsh → powershell, запуск `-NoProfile -ExecutionPolicy Bypass -File update_from_github.ps1 -Launch`

### 4.8 `APP/config.example.yaml`
- **Назначение**: Переносимый пример конфигурации (копируется в config.yaml)
- **Секции**:
  - `database`: path (cache.db), schema_path, timeout, isolation_level, use_wal
  - `locking`: retry_count, retry_backoff, use_semaphores
  - `network`: drive_letters (Q, Z)
  - `logic`: commission_is_percent, income_overrides, return_keywords
  - `paths`: master_file, source_roots (Q:\Отчет кураторов 1-3), archive_dir
  - `curators`: boris/ivan (enabled, output_path, employees_key, direct_paths)
  - `rsch`: recent_sources, last_output_dir, mode (combined)
  - `sh1`: markers (16 маркеров колонок: source, amount, broker1, broker2, commission, ...)
  - `sh2`: {} (пусто)
  - `validation`: {} (пусто)
  - `performance`: isolate_calamine, max_workers
  - `backup`: excel_keep (10)

### 4.9 `APP/config_missing.yaml`
- **Назначение**: [UNVERIFIED] Копия config.example.yaml — возможно fallback при отсутствии config.yaml. Содержимое идентично config.example.yaml.

### 4.10 `APP/db_schema.sql`
- **Назначение**: SQLite-схема гибридного кэша
- **Таблицы** (10):
  - `_migrations` — трекинг миграций
  - `sessions` — сессии консолидации
  - `source_files` — метаданные файлов (hash, inode, status)
  - `staging_data` — raw строки перед консолидацией (amount как TEXT для Decimal)
  - `consolidated_results` — итоговые результаты
  - `template_errors` — нарушения шаблонов
  - `file_cache` — кэш найденных дат (оптимизация сетевых дисков)
  - `row_cache` — кэш распарсенных строк
  - `discovery_cache` — кэш результатов сканирования
  - `customer_aliases` — алиасы заказчиков для сверки
- **Индексы**: 7 индексов для производительности

### 4.11 `APP/migrations/001_numeric_to_text.sql`
- **Назначение**: Миграция NUMERIC→TEXT для financial columns
- **Метод**: table-rebuild pattern (create new, copy, drop old, rename)
- **Затронутые таблицы**: staging_data (amount), consolidated_results (total_amount, commission, net_amount)

### 4.12 `APP/migrations/002_customer_aliases.sql`
- **Назначение**: Создание таблицы customer_aliases для маппинга сверки
- **Метод**: CREATE TABLE IF NOT EXISTS + 2 индекса

---

## 5. Классификация файлов

### source (исходный код приложения) — 87 файлов

**APP/ (5):**
- `APP/main.py`, `APP/headless_run.py`

**APP/core/ (3):**
- `APP/core/__init__.py`, `APP/core/app_controller.py`, `APP/core/bootstrap.py`

**APP/core/app/ (5):**
- `APP/core/app/__init__.py`, `APP/core/app/file_processor.py`, `APP/core/app/message_formatting.py`, `APP/core/app/partial.py`, `APP/core/app/performance.py`

**APP/core/domain/ (6):**
- `APP/core/domain/__init__.py`, `APP/core/domain/data_loss_log.py`, `APP/core/domain/data_schemas.py`, `APP/core/domain/interfaces.py`, `APP/core/domain/logic_service.py`, `APP/core/domain/utils_helpers.py`

**APP/core/infra/ (19):**
- `APP/core/infra/__init__.py`, `APP/core/infra/config_controller.py`, `APP/core/infra/customer_alias_repo.py`, `APP/core/infra/db_connection.py`, `APP/core/infra/discovery_service.py`, `APP/core/infra/event_bus.py`, `APP/core/infra/excel_backup.py`, `APP/core/infra/excel_hyperlinks.py`, `APP/core/infra/export_formatting.py`, `APP/core/infra/export_writer.py`, `APP/core/infra/ingestion_engine.py`, `APP/core/infra/ingestion_reader.py`, `APP/core/infra/metrics.py`, `APP/core/infra/path_resolver.py`, `APP/core/infra/session_repo.py`, `APP/core/infra/settings_store.py`, `APP/core/infra/source_file_repo.py`, `APP/core/infra/staging_repo.py`, `APP/core/infra/utils_logging.py`, `APP/core/infra/utils.py`

**APP/core/infra/reconciliation/ (6):**
- `__init__.py`, `_build.py`, `_collect.py`, `_resolve.py`, `_types.py`, `_utils.py`

**APP/core/infra/rsch/ (5):**
- `__init__.py`, `_build.py`, `_collect.py`, `_format.py`, `_template.py`

**APP/core/services/ (3):**
- `__init__.py`, `reconciliation_service.py`, `rsch_service.py`

**APP/core/ui/ (19):**
- `__init__.py`, `dashboard_state.py`, `debounce.py`, `geometry.py`, `gui_master_settings.py`, `gui_master.py`, `operation_state.py`, `operation_status_bar.py`, `system_theme.py`, `theme.py`, `toast.py`, `tooltip.py`, `ui_aliases.py`, `ui_dashboard.py`, `ui_dialogs.py`, `ui_employee_table.py`, `ui_log_panel.py`, `ui_settings.py`, `ui_sidebar.py`, `ui_stats_panel.py`

**APP/core/ui/gui_commands/ (6):**
- `__init__.py`, `_base.py`, `_consolidation.py`, `_employee.py`, `_reconciliation.py`, `_rsch.py`

**APP/core/view_models/ (3):**
- `__init__.py`, `consolidation_viewmodel.py`, `employee_list_viewmodel.py`

**tools/ (9):**
- `tools/cleanup.ps1`, `tools/diff_workspaces.py`, `tools/find_large.ps1`, `tools/merge_to_pdf.py`, `tools/merge_to_txt.py`, `tools/precommit_check.py`, `tools/test_user_flows.py`, `tools/trace_sbi.py`, `tools/update_from_github.ps1`

**Корневые (5):**
- `oracle.py`, `rlm_eval.py`, `rlm_eval_v2.py`, `rlm_eval_v3.py`, `rlm_eval_v4.py`

### config (конфигурационные файлы) — 10 файлов
- `APP/config.example.yaml`, `APP/config_missing.yaml`, `APP/db_schema.sql`
- `APP/migrations/001_numeric_to_text.sql`, `APP/migrations/002_customer_aliases.sql`
- `.gitignore`, `ЗАПУСК.bat`, `ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat`
- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`

### test (тесты) — 27 файлов
- `tests/test_audit_refactoring.py`, `tests/test_dashboard_state_extended.py`, `tests/test_data_loss_log.py`, `tests/test_db_pragmas_and_migrations.py`, `tests/test_debounce.py`, `tests/test_export_writer_edge_cases.py`, `tests/test_file_processor_time_module.py`, `tests/test_finish_helper.py`, `tests/test_geometry.py`, `tests/test_operation_state.py`, `tests/test_operation_status_bar.py`, `tests/test_partial_renamer.py`, `tests/test_percentage_matching_bugs.py`, `tests/test_phase0_gui_marshaling.py`, `tests/test_phase0_reconciliation_fail_soft.py`, `tests/test_phase0_workbook_release.py`, `tests/test_phase1_export_decimal.py`, `tests/test_phase1_schema_validator.py`, `tests/test_phase2_db_repositories.py`, `tests/test_phase2_ingestion_reader.py`, `tests/test_phase2_logic_service.py`, `tests/test_phase3_reliability.py`, `tests/test_system_theme.py`, `tests/test_theme_manager.py`, `tests/test_tooltip.py`
- `tests/core/infra/test_reconciliation_report.py`, `tests/core/infra/test_rsch_report.py`

### asset (статические ресурсы) — 2 файла
- `tests/golden/backups/excel_outputs/reference_output/20260601_154442_284608_reference_output.xlsx`
- `tests/golden/backups/excel_outputs/reference_output/20260601_162702_313519_reference_output.xlsx`

### doc (документация) — 10 файлов
- `ARCHITECTURE.md`, `CHANGELOG_WEEK.md`, `FEATURE_TABLE.csv`, `features.json`, `INTEGRATION.md`, `PROJECT.md`, `PROMPT_AI_SVERKA.md`, `QA_PROGRESS.md`, `QA_REPORT.md`, `README.md`

### generated (сгенерированные файлы) — 1 файл
- `.mypy_baseline.txt`

### deprecated (устаревшие) — 0 файлов
- В области анализа устаревших файлов не обнаружено.
