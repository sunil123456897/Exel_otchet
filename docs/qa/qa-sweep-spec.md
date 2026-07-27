# QA-Sweep: спецификация полной проверки проекта

Цель: убедиться, что все функции работают в точности как задумано. **Логику
не меняем.** Найденные проблемы — только документируем (фиксы — отдельно и
согласованно).

## Источник методологии
«Prompt_System_Ideal_v2_TechnicalDoc_2026-06-28», Phase 0–5: Discovery →
Specification → Testing → Fixing → Verification → Iteration. Здесь Phase 3
(«Fixing») сужена до документирования, т.к. заказчиком разрешён только аудит.

## Phase 1 — Перечень проверяемых функций (фичи/команды)

### A. Тяжёлые build-пути (основной риск)
| ID | Функция | Файл | Покрытие тестами |
|----|---------|------|------------------|
| A1 | `run_consolidation` (day) | app_controller:794 | есть (partial) |
| A2 | `run_consolidation_all_dates` | app_controller:814 | НЕТ |
| A3 | `run_consolidation_month` (period) | app_controller:833 | НЕТ |
| A4 | `run_rsch_report` (day) | app_controller:1068 | НЕТ (только косвенно) |
| A5 | `run_rsch_report_period` (period) | app_controller:1089 | добавлен (Phase 2 prev) |
| A6 | `run_rsch_report_period_batch` | app_controller:1112 | НЕТ |
| A7 | `run_rsch_report_batch` | app_controller:1126 | НЕТ |
| A8 | `run_reconciliation_report` | app_controller:1054 | НЕТ |
| A9 | `run_auto_reconciliation_day` | app_controller:947 | НЕТ |
| A10| `refresh_status` | app_controller:714 | НЕТ |
| A11| `build_rsch_report` (public) | infra/rsch/_build:397 | косвенно |
| A12| `build_reconciliation_report` | infra/reconciliation/_build:306 | НЕТ |
| A13| `build_combined_reconciliation_report` | infra/reconciliation/_build:354 | НЕТ |

### B. Репозитории / персистентность (нет тестов)
| ID | Модуль |
|----|--------|
| B1 | config_controller.ConfigController |
| B2 | discovery_service.DiscoveryService.get_employees_map |
| B3 | customer_alias_repo (CRUD) |
| B4 | source_file_repo.SourceFileRepository |
| B5 | staging_repo.StagingDataRepository |
| B6 | settings_store.SettingsStore |
| B7 | path_resolver.resolve_employee_path |

### C. Сервисный слой (нет тестов)
| ID | Модуль |
|----|--------|
| C1 | ReconciliationService.run_reconciliation_report |

### D. Shared-утилиты (нет тестов)
| ID | Модуль / функция |
|----|------------------|
| D1 | domain/utils_helpers (to_decimal, to_decimal_percent, normalize_text) |
| D2 | shared/path_scrub (scrub_path, safe_file_label) |
| D3 | app/message_formatting (build_success_message и др.) |
| D4 | app/performance (resolve_max_workers) |
| D5 | infra/excel_safety, excel_backup, excel_hyperlinks |
| D6 | infra/export_formatting |

### E. Ingestion (нет тестов на публичный слой)
| ID | Модуль |
|----|--------|
| E1 | ingestion_engine.IngestionEngine (get_available_dates, scan_directory, read_file) |

## Phase 4 — Симуляции работы заказчика (на реальных данных)

Используем настоящие файлы:
- Источники РСЧ: `рсч всех/*.xlsx` (6 файлов)
- Источники сотрудников: `REPORTS/Отчет кураторов 3/**/*.xlsx`
- Уже собранные: `Master_Report.xlsx`, `РСЧ/РСЧ_отчет_*.xlsx`

Сценарии симуляций:
| S | Сценарий | Что проверяем |
|---|----------|---------------|
| S1 | Консолидация за день (есть данные) | A1 → Master_Report |
| S2 | Консолидация за все даты | A2 |
| S3 | Консолидация за период | A3 |
| S4 | РСЧ за день (реальные источники) | A4 → РСЧ_отчет |
| S5 | **РСЧ за период** (баг заказчика!) | A5 — критично |
| S6 | РСЧ за период batch | A6 |
| S7 | Сверка отчётов | A8 |
| S8 | Автосверка за день | A9 |
| S9 | Refresh status | A10 |

### Edge-cases (симуляции)
| E | Сценарий | Что проверяем |
|---|----------|---------------|
| E1 | РСЧ за период с несуществующим файлом | понятная ошибка, не зависон |
| E2 | РСЧ за период по пустым данным (нет строк) | RuntimeError «нет строк» |
| E3 | РСЧ за период с отменой | CancelledByUser, корректный выход |
| E4 | РСЧ за период длинный (год) | производительность, прогресс |
| E5 | get_local_copy на локальном пути | passthrough |
| E6 | get_local_copy на зависшем сетевом | таймаут (фикс причины 1) |
| E7 | Дублирующиеся пути источников | дедуп |
| E8 | Период через границу года | коллизия имён листов |
