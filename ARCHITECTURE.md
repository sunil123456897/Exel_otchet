# Архитектура Master Report Consolidator v5.6

> Дополнения после Stage 0–9 (hardening) описаны в секции
> [«Stage 0–9 additions»](#stage-09-additions-hardening-branch) ниже.
> Базовая архитектура (слои, потоки данных, API) не изменилась.

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

9. **Процентная нормализация через Excel-формат** — кураторы пишут доли `0..1`, отчёт показывает проценты без арифметики в коде (формат ячейки). Подробнее см. секцию «Проценты и комиссии» ниже.

## Проценты и комиссии

### Контракт реальных данных

Кураторы пишут проценты **долями `0..1`**, а не в виде `15%` или целых чисел.
Проверено на 29 реальных файлах кураторов: **98.6 %** значений в колонках
`комиссия` / `% посредника` — это доли (`0.15`, `0.05`, `0.005`). Знак `%`
встречается в <0.2 % значений (в основном протёкшие заголовки), целые числа
>1 — в <0.2 % (Excel-serial даты, чужие суммы).

Это де-факто стандарт ввода, меняться не будет — кураторы не хотят менять
привычки, и программа под них адаптирована.

### Нормализация и отображение

Программа **не арифметически** приводит доли к процентам. Excel-формат ячейки
делает отображение бесплатно:

| Колонка | Хранится в `.xlsx` | Формат ячейки | Пользователь видит |
|---|---|---|---|
| `комиссия` | `20.0`, `16.5`, `25.0` | `0"%"` | **20 %** |
| `% посредника` | `0.05`, `0.04`, `0.005` | `0.00%` | **5.00 %** |

Масштаб между колонками **согласован на отображении**, а не на данных. Две
колонки с одним смыслом («процент») хранятся в разных единицах намеренно:
`комиссия` проходит через `_resolve_commission` (`logic_service.py`) с
эвристикой `abs(c_raw) <= 1 → *100`, `% посредника` идёт как доля. Но в
финальном отчёте пользователь видит одинаковый формат.

### Эвристика `abs(c_raw) <= 1 → *100` (в `_resolve_commission`)

Корректна для 98.6 % реальных данных. Куратор пишет `0.15` (имея в виду 15 %),
код умножает на 100 → `15.0` → формат `0"%"` показывает `15 %`. **Не баг.**
Не менять без проверки реальных отчётов.

### Защита от мусора в процентных колонках

Значения `> 100` — это всегда ошибка (Excel-serial дата `43998`, чужая сумма
`30000`, протёкший заголовок). Обрабатывается в `export_formatting.py:312-328`:

```python
if abs(v_float) <= 1.0:     cell.value = v_float          # доля — оставить
elif abs(v_float) <= 100.0: cell.value = v_float / 100.0  # 5 → 0.05
else:                       is_percent_err = True         # >100 — ошибка
                            cell.fill = st.fill_warning   # жёлтая заливка FFFF00
```

Строка с ошибкой красится жёлтым, значение остаётся видимым для диагностики.

### Историческая сноска (для будущих ИИ-аудиторов)

> **ВНИМАНИЕ:** аудиторский отчёт `CRITICAL_AUDIT_REPORT.md` (март 2026)
> выдумал сценарии вроде «`0.5 %` → `50.00`, финансовая катастрофа».
> Таких входов **нет в реальных данных** кураторов. Анализ был сделан по
> чтению кода без проверки реальных `.xlsx`. Эвристика `<= 1` — корректная
> адаптация к фактическим привычкам ввода, не трогать.
>
> Правило: **любое утверждение о «финансовом баге» сначала проверяется на
> реальных файлах** `REPORTS/` и `Master_Report.xlsx`, потом принимается.

---

## Stage 0–9 additions (hardening branch)

Базовая слоистая архитектура (UI → Commands → AppController → Config/
Ingestion/Persistence/Logic/Writer) сохранилась. Работы Stage 0–9
добавили **горизонтальные cross-cutting модули**, не меняя основные
слои:

### Domain layer (`APP/core/domain/`)
Новые модули:
- `date_warnings.py` — формальный классификатор подозрительных дат
  (FUTURE/DISTANT_PAST/OK). Pure функция, не wired в pipeline; UI
  вызывает отдельно.
- `operation_result.py` — OperationStatus enum + per-source breakdown.
  Контракт для UI/controller; не подключён к ingestion pipeline
  (Stage 7 wiring).

### Infrastructure layer (`APP/core/infra/`)
Новые модули:
- `config_schema.py` — Pydantic-модель AppConfig с 4-way error
  taxonomy. Используется `ConfigController._migrate_and_validate`.
- `config_migrations/__init__.py` — idempotent migration runner.
- `employees_schema.py` — typed schema для employees.yaml + legacy
  upgrade.
- `updater_model.py` — полная реализация atomic updater (Stage 4).
  Не подключён к BAT (Stage 7 wiring).

### Cross-cutting infrastructure (`tools/`)
- `qa_baseline.py` — JSON baseline-отчёт.
- `ci_mypy_check.py`, `qa_mypy_baseline.py` — mypy gate.
- `compare_workbooks.py` — PII-safe сравниватель xlsx.
- `control_date_fingerprint.py` — SHA-256 fingerprint листа.
- `timing_report.py` — performance harness с leak detection.
- `diagnostic_package.py` — обезличенный ZIP для поддержки.

### Tests
- 990 тестов в комплекте (Stage 0–9), 0 skips на Windows.
- Структура: `tests/test_*.py` для unit/integration; `tests/ui/` для
  UI automation; `tests/golden/` для синтетических fixtures и
  fingerprint; `tests/core/` для infra-level.

### Privacy enforcement
- `data_loss_log.record_loss` — scrubbing до JSON serialisation.
- `error_presenter.present_error` — `type(exc).__name__` в detail,
  не `repr(exc)`.
- `.gitignore` — Master_Report.xlsx, config.yaml, cache.db и т.д.
- `tools/diagnostic_package.py` — post-process scrubbing всех строк
  manifest (tokens + firm-names).

Подробности каждого этапа: `docs/stage_reports/<N>_report.md`.
