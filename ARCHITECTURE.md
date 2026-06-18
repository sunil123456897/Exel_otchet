# Архитектура Master Report Consolidator v5.5

## Слои приложения (сверху вниз)

```
┌──────────────────────────────────────────────────────────────────┐
│                        UI / GUI Layer                            │
│  gui_master.py  ←  ui_sidebar  ui_dashboard  ui_stats_panel     │
│                        ui_employee_table  ui_log_panel  toasts   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ commands, чтение состояния
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Commands Layer                               │
│  gui_commands/  (EmployeeMixin, ConsolidationMixin,              │
│                  RschMixin, ReconciliationMixin)                 │
└────────────────────────────┬─────────────────────────────────────┘
                             │ app_controller.run_*
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                   AppController (ЯДРО)                            │
│  ▸ refresh_status()        ▸ run_consolidation()                 │
│  ▸ run_rsch_report()       ▸ run_reconciliation_report()         │
│  ▸ run_auto_reconciliation_day()                                 │
│                                                                  │
│  Владеет:  config_controller, ingestion_engine, persistence,     │
│            validator, logic_service, writer                      │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
│ Config   │ │ Ingestion│ │Persistence│ │  Logic   │ │   Writers    │
│Control   │ │ Engine   │ │(SQLite)  │ │ Service  │ │              │
│          │ │          │ │          │ │          │ │ MasterWriter │
│ .yaml    │ │ Calamine │ │ sessions │ │ validate │ │ + пакеты:    │
│ CRUD     │ │ Reader   │ │ cache    │ │ match    │ │              │
│          │ │ + openpyxl│ │          │ │          │ │reconciliation│
│ resolve  │ │          │ │          │ │          │ │    rsch      │
│ _path()  │ │Discovery │ │          │ │          │ │              │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────────┘

       ┌──────────────────┐
       │  OperationState  │  ← потокобезопасный конечный автомат операций:
       │  + EventBus (FD)  │     GUI подписывается через add_listener,
       └──────────────────┘     обновления маршалируются в GUI-поток
                                через root.after(0, …). EventBus существует
                                как publish/subscribe-шина, но в текущем
                        потоке данных не задействован — прогресс идёт
                        через OperationState listeners.
```

## Поток данных (типичный сценарий «Собрать день»)

```
1. GUI: sidebar.get_date() + sidebar.get_curator()
2. gui_commands._consolidation.py: run_consolidation()
3. AppController.run_consolidation()
4. ConfigController.get_employees()         → список сотрудников
5. IngestionEngine → CalamineReader.read()  → строки из .xlsx
6. DiscoveryService.resolve_employee_path() → актуальные файлы
7. LogicService.consolidate()               → агрегация строк
8. MasterWriter.write_report()              → выходной .xlsx
9. OperationState.end() + on_complete()     → GUI: тост/таблица/заголовок
                                              (колбэки маршалированы в
                                              GUI-поток через root.after)
```

## Новые пакеты (рефакторинг Этап 5)

### `core/infra/reconciliation/` (1500 → 6 модулей)

| Модуль | Строк | Назначение |
|---|---|---|
| `__init__.py` | 30 | Public API: `build_reconciliation_report`, `build_combined_reconciliation_report` |
| `_types.py` | 55 | `MasterReconciliationRow`, `RschReconciliationRow`, `ReconciliationRow` |
| `_utils.py` | 400+ | `_to_decimal`, `_excel_safe_text`, `_normalize_text`, статус-константы, матчинг |
| `_resolve.py` | 240 | Поиск общих дат/листов, `_executor_matches`, `_customer_matches` |
| `_collect.py` | 500 | Чтение: `_collect_master_rows`, `_collect_rsch_rows`, хедер-маппинг |
| `_build.py` | 430 | Запись: `_build_workbook`, `_write_reconciliation_sheet`, стили |

### `core/infra/rsch/` (1300 → 5 модулей)

| Модуль | Строк | Назначение |
|---|---|---|
| `__init__.py` | 10 | Public API: `build_rsch_report` |
| `_format.py` | 230 | Константы (`RSCH_HEADERS`), `_normalize_text`, `_to_decimal`, `_display_len` |
| `_collect.py` | 430 | Чтение: Calamine + openpyxl, `_CalamineWorksheetAdapter` |
| `_template.py` | 380 | Стили, `_resolve_template_style_layout`, `_ensure_header_style` |
| `_build.py` | 520 | Запись: `build_rsch_report`, `_write_rsch_sheet`, форматирование |

## Ключевые решения

1. **Mixin-паттерн для GUI-команд** — каждая фича (employee, consolidation, rsch, reconciliation) — отдельный Mixin. Композиция в `GuiCommands`.

2. **OperationState** — глобальная блокировка: пока одна операция выполняется, все кнопки disabled. Предотвращает гонки между сборкой и свёркой.

3. **Path Traversal Guard** — `resolve_path` разрешает пути внутри `APP/` и внутри корня проекта (`Version5/`), блокирует выход за пределы.

4. **data_only=True** для мастер-файлов — `cell.hyperlink` работает и без `data_only=False`, числовые значения не превращаются в 0.

5. **mypy baseline** — строгая типизация внедряется постепенно: `.mypy_baseline.txt` фиксирует существующие ошибки, pre-commit хук блокирует только новые.

6. **Services layer** — `core/services/` выделяет бизнес-оркестрацию из `AppController`:
   - `RschService` — 4 варианта сборки РСЧ-отчётов
   - `ReconciliationService` — сверка мастер-отчётов с РСЧ
   - `AppController` делегирует сервисам, сохраняя публичный API для GUI

7. **Auto-backup перед миграциями** — `_backup_db()` создаёт `cache.db.backup_{timestamp}` перед применением неприменённых миграций. Миграции, ссылающиеся на несуществующие таблицы (fresh DB), graceful skip.

8. **TTL-очистка cache.db** — при запуске удаляются `row_cache`/`file_cache` старше 7 дней и `discovery_cache` старше 12 часов.
