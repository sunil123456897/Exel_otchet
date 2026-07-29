# Changelog

Все заметные изменения проекта Master-Report.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Группировка — по этапам TЗ «Master-Report 10/10 без защиты».

## [Unreleased] — Stage 0–9 (hardening branch)

### Stage 0 — Baseline freeze and CI fix

#### Added
- `tools/qa_baseline.py` — единый JSON-отчёт baseline (PII-free).
  Режимы quick (collect-only) и full (pytest + coverage probe).
  Включает timing import-APP и token-audit (`.github_token`
  gitignored? token-shaped strings в fixtures?).
- `tools/ci_mypy_check.py` — CI mypy gate, читающий **stdout** (mypy
  пишет diagnostics туда, не в stderr, как предполагала старая версия).
  Нормализация path/backslash и line numbers, чтобы сдвиг строк не
  выглядел как new error.
- `tools/qa_mypy_baseline.py` — перегенерация baseline как reviewable
  action (никогда автоматически из CI).
- `tests/test_single_version_source.py` — single source of truth для
  `__version__`: BAT читает `APP/__init__.py`, UI не имеет hardcoded
  fallback.

#### Fixed
- CI mypy gate был silent no-op: читал только stderr, куда mypy не
  пишет. Все 684 ошибок проходили unchecked.
- `ЗАПУСК.bat` показывал `v5.5`, при том что `APP.__version__ = "5.6"`.
- pytest в CI skip'ался, если `tests/` отсутствовал — позволяло
  публиковать непроверенный код.

### Stage 1 — Golden regression of financial results

#### Added
- `tools/compare_workbooks.py` — PII-safe сравниватель xlsx. Никогда
  не печатает значения ячеек — только координаты и счётчики различий.
  Режимы: sheet set, размер, значения, формулы, типы, merged cells,
  freeze panes, auto-filter, print area, styles (без style_id).
- `tools/control_date_fingerprint.py` — SHA-256 fingerprint листа
  книги. Подкоманды capture/verify.
- `tests/golden/control_date.json` — обезличенный fingerprint
  контрольной даты `18.05.2026` (446×11 = 4906 ячеек, 0 различий).
- `tests/golden/synthetic_fixtures.py` — 14 синтетических PII-free
  сценариев: master_day, master_period, rsch, reconciliation, returns,
  currency, transit, duplicates, formulas, empty_partial, и т.д.
- `tests/golden/test_financial_invariants.py` — 8 инвариантов
  LogicService: order-independence, idempotency, source preservation,
  Decimal preservation, determinism, row-count conservation,
  empty-row drop, return-not-zeroed.

#### Security
- `Master_Report.xlsx`, `APP/config.yaml`, `APP/cache.db`, `APP/employees.yaml`,
  `REPORTS/`, `РСЧ/`, `Ване/`, `рсч всех/`, `backups/` — добавлены в
  `.gitignore`. Раньше один `git add .` залил бы финансовые данные
  фирмы в репозиторий.

### Stage 2 — Configuration versioning and migration

#### Added
- `APP/core/infra/config_schema.py` — Pydantic-схема AppConfig с
  секциями database/locking/network/logic/paths/curators/rsch/
  performance/backup. Четырёхполосная error-taxonomy: MISSING_FIELD,
  WRONG_TYPE, UNKNOWN_FIELD, UNREACHABLE_PATH. UNREACHABLE_PATH
  отделён от WRONG_TYPE — сетевой сбой не выглядит typo.
- `APP/core/infra/config_migrations/` — последовательный idempotent
  migration runner. Refuses downgrade, preserve operator keys.
- `APP/core/infra/employees_schema.py` — typed schema для employees.yaml.
  Legacy-string → dict-fingerprint normalisation, duplicate/empty-name
  detection.
- Интеграция в `ConfigController.load_config` с atomic save через
  temp+rename.

### Stage 3 — Excel read reliability and data quality

#### Added
- `APP/core/domain/date_warnings.py` — формальный классификатор
  подозрительных дат (FUTURE / DISTANT_PAST / OK). Ловит "2029
  anomaly" из ТЗ.
- `APP/core/domain/operation_result.py` — OperationStatus enum
  (COMPLETED / COMPLETED_WITH_WARNINGS / FAILED / CANCELLED) с
  per-source breakdown.
- `tests/corrupt_fixtures.py` — 8 программных генераторов повреждённых
  xlsx для тестирования parser isolation.

#### Security
- `data_loss_log.record_loss` теперь применяет PII-scrubbing к каждому
  строковому полю (source, reason, value) **до** json.dumps, не после.
  Регексы scrub_path написаны под single-backslash пути; в JSON они
  удваиваются, и matching тихо падал. Имена пользователей попадали
  в лог как есть.

### Stage 4 — Atomic update and rollback

#### Added
- `APP/core/infra/updater_model.py` — полная Python-реализация
  атомарного updater'а: lock → preflight → fetch → L0 (size+sha+path-
  safety) → staging → L1 (entry-point files) → backup → atomic switch
  → launch → wait-for-startup-ok → rollback on failure.
  Cross-process lock (PID-file), offline ZIP via plug-in fetch_fn.

### Stage 5 — Technical debt reduction (mypy strict + boundaries)

#### Added
- `tests/test_architecture_boundaries.py` — 47 параметризованных
  тестов архитектурных границ: domain не импортирует tkinter/openpyxl,
  UI не делает финансовую математику, инвентарь domain стабилен.

#### Changed
- Аннотации типов добавлены в `core/domain/{data_loss_log,data_schemas,
  logic_service}.py` и `core/services/{reconciliation,rsch}_service.py`.
- mypy strict baseline: 312 → 303 нормализованных находок.

### Stage 6 — Test coverage expansion

#### Added
- `tests/test_property_based.py` — Hypothesis-based property тесты
  для финансовой логики (10 тестов). Нашёл edge case с Decimal
  rounding modes (0.0250 → 0.02 banker's vs 0.03 HALF_UP).
- `tests/test_fault_injection.py` — fault injection и integration
  тесты (18): SQLite rollback, WAL mode, file-handle leaks,
  Excel backup atomicity, cancel_event latency, thread safety.

### Stage 7 — Windows UI/UX acceptance

#### Added
- `tests/test_ui_acceptance.py` — 16 тестов: first-run flag
  robustness, error presenter invariants (no str(exc) leak, no
  raise when both toast+messagebox fail).
- `docs/archive/stage_reports/stage_7_acceptance_matrix.md` — формальный
  ручной приёмочный чек-лист на 8 секций (~50 пунктов): DPI, Excel
  versions, network drives, error presentation, first-run, data
  integrity, update & rollback.

#### Security
- `error_presenter` detail-секция показывает `type(exc).__name__`
  вместо `repr(exc)`. `repr(ValueError('token'))` буквально содержит
  token — это реальная leak-поверхность.

### Stage 8 — Performance and long-run resilience

#### Added
- `tools/timing_report.py` — воспроизводимый timing harness (4
  benchmark'а + leak detection).
- `tests/test_performance_sla.py` — 8 SLA-тестов с generous thresholds
  (10× от floor) и строгими leak-тестами (0 новых threads после 100
  итераций).
- `tests/golden/timing_baseline.json` — reference-снимок таймингов.

### Stage 9 — Backup, recovery and diagnostics

#### Added
- `tools/diagnostic_package.py` — сборщик обезличенного ZIP для
  поддержки. Содержит version, paths availability (без самих путей),
  config shape (только типы), DB schema (без row data), log tails
  (scrubbed).
- `tests/test_backup_restore.py` — 10 тестов: backup каждого артефакта
  проверен на byte-identical или семантически-эквивалентное
  восстановление.
- `tests/test_diagnostic_package.py` — 17 privacy-тестов: tokens,
  paths, amounts, customer names не утекают в diagnostic ZIP.
- `docs/support_runbook.md` — operator-facing runbook: 8 типовых
  проблем с пошаговым решением, сроки реакции поддержки, что НЕ делать.

## [5.6] — UI redesign premium

Premium UI redesign: palette, icons, components. Изменения UI
затрагивают только presentation layer; бизнес-логика и API не
изменились. См. `docs/prototype/` для визуальных mockups.

## [5.5] — Initial public version

Первый рабочий релиз: GUI, ingestion, consolidation, reconciliation,
RSCH. Все базовые сценарии использования покрыты.
