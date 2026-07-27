# Каноническая карта проекта

## Метаданные
- Дата создания: 2026-06-26
- Версия: 1.0
- Последнее обновление: 2026-06-26
- Статус: draft
- Проект: Master-Report v5.5 (Financial Consolidation)
- Ветка: qa-audit-cycle

---

## Быстрая навигация

### Структура и архитектура
- [Структурная карта](map/structure.md) — 124 файла, 5 точек входа, 12 конфигураций
- [Архитектурный анализ](map/architecture.md) — паттерн: [HYBRID] Layered + MVC + MVVM, 6 слоёв
- [Карта зависимостей](map/dependencies.md) — внутренние + внешние (pip), сервисные, циркулярные

### Функциональность
- [Инвентарь фич](features/inventory.md) — 42 фичи (23 core, 13 secondary, 4 auxiliary, 2 deprecated)
- [Бизнес-правила](business/rules.md) — 90 правил (BR-001..BR-090)
- [Инварианты](business/invariants.md) — 23 инварианта (INV-001..INV-023)
- [State machines](business/state-machines.md) — 10 автоматов (SM-001..SM-010)

### Данные
- [Модель данных](data/model.md) — сущности SQLite + Pydantic + runtime state
- [API-эндпоинты и интерфейсы](api/endpoints.md) — CLI, GUI, internal service, event-bus

### Риски
- [Технический долг](risks/tech-debt.md) — 20 пунктов (0 critical, 3 major, 16 minor, 1 cosmetic)

---

## Карта фич

| ID | Название | Категория | Статус | Зависит от | Блокирует | Файлов |
|----|----------|-----------|--------|------------|-----------|--------|
| F-001 | Запуск приложения (GUI) | core | implemented | F-003, F-022, F-023, F-033 | F-002, F-006-F-016, F-025 | 3 |
| F-002 | Headless-режим (CLI) | core | implemented | F-003, F-022, F-023, F-008-F-010, F-033 | — | 3 |
| F-003 | Управление конфигурацией | core | implemented | F-030 | F-001, F-002, F-008, F-011, F-012, F-022, F-029 | 2 |
| F-004 | Обновление статусов (Refresh) | core | implemented | F-003, F-005, F-023, F-024, F-029 | F-008-F-012, F-020 | 5 |
| F-005 | Управление сотрудниками | core | implemented | F-003 | F-004, F-008-F-012, F-020, F-021 | 5 |
| F-006 | Выбор даты | core | implemented | F-001 | F-004, F-008-F-016 | 2 |
| F-007 | Выбор куратора | core | implemented | F-001, F-003 | F-008-F-012 | 2 |
| F-008 | Консолидация дневного отчёта | core | implemented | F-003-F-007, F-023, F-024, F-031 | F-015, F-016 | 6 |
| F-009 | Консолидация за все даты | core | implemented | F-003, F-004, F-005, F-007, F-023, F-024, F-031 | — | 3 |
| F-010 | Консолидация за период | core | implemented | F-003-F-007, F-023, F-024, F-031 | — | 3 |
| F-011 | Кураторский отчёт — Борис | core | implemented | F-003, F-007, F-008, F-017 | F-015, F-016 | 3 |
| F-012 | Кураторский отчёт — Иван | core | implemented | F-003, F-007, F-008, F-017 | F-015, F-016 | 3 |
| F-013 | Сборка РСЧ-отчёта (день) | core | implemented | F-003, F-006, F-024, F-031 | F-015, F-016 | 6 |
| F-014 | Сборка РСЧ-отчёта (период) | core | implemented | F-003, F-006, F-013, F-024, F-031 | — | 3 |
| F-015 | Ручная сверка с РСЧ | core | implemented | F-003, F-006, F-008, F-011, F-012, F-013, F-024, F-031, F-038 | — | 7 |
| F-016 | Автосверка с РСЧ | core | implemented | F-003, F-006, F-008, F-011, F-012, F-013, F-015, F-024, F-031, F-038 | — | 3 |
| F-017 | Финансовые правила (бизнес-логика) | core | implemented | F-023 | F-008-F-012, F-016 | 4 |
| F-018 | Экспорт мастер-отчёта в Excel | core | implemented | F-003, F-028 | F-008-F-012, F-016 | 4 |
| F-019 | Обнаружение файлов (Discovery) | core | implemented | F-003, F-029 | F-004, F-008-F-010 | 2 |
| F-020 | Ингестия Excel-файлов | core | implemented | F-023, F-029 | F-004, F-008-F-010 | 3 |
| F-021 | Отмена операций | core | implemented | F-024 | — | 5 |
| F-022 | Управление настройками | secondary | implemented | F-003, F-027 | — | 3 |
| F-023 | SQLite-кэш и сессии | core | implemented | F-003 | F-004, F-008-F-010, F-017, F-020, F-038 | 8 |
| F-024 | Отслеживание прогресса | core | implemented | F-001 | F-004, F-008-F-016, F-021 | 3 |
| F-025 | Дашборд (вкладки) | secondary | implemented | F-001, F-003, F-033 | — | 2 |
| F-026 | Toast-уведомления | secondary | implemented | F-001 | — | 2 |
| F-027 | Управление темой | secondary | implemented | F-001 | F-022 | 4 |
| F-028 | Авто-бэкап Excel-выводов | secondary | implemented | F-003 | F-018 | 1 |
| F-029 | Поддержка сетевых дисков | secondary | implemented | F-003 | F-004, F-019, F-020 | 3 |
| F-030 | Path traversal protection | secondary | implemented | F-003 | F-001, F-002, F-003 | 2 |
| F-031 | Сохранение геометрии окна | secondary | implemented | F-001 | — | 2 |
| F-032 | Логирование | auxiliary | implemented | F-001 | F-025 | 4 |
| F-033 | Аудит потери данных | auxiliary | implemented | F-032 | F-015, F-017 | 1 |
| F-034 | Поиск и фильтр сотрудников | secondary | implemented | F-005, F-001 | — | 4 |
| F-035 | Открытие файлов и папок | secondary | implemented | F-005, F-029 | — | 2 |
| F-036 | Копирование должников | secondary | implemented | F-004, F-005 | — | 2 |
| F-037 | Tooltip-виджеты | auxiliary | implemented | F-001 | — | 2 |
| F-038 | Управление алиасами заказчиков | secondary | implemented | F-023 | F-015, F-016 | 3 |
| F-039 | Сохранение настроек РСЧ | secondary | implemented | F-003, F-013 | — | 1 |
| F-040 | Многопоточная обработка | auxiliary | implemented | — | F-004, F-008, F-020 | 3 |
| F-041 | Event Bus (pub/sub) | deprecated | stubbed | — | — | 1 |
| F-042 | In-process метрики | deprecated | stubbed | — | — | 1 |

---

## Граф зависимостей фич

```
F-003 (Config) ──┬──→ F-001 (Launch) ──→ F-006 (Date) ──→ F-008 (Consolidation Day) ──→ F-015 (Reconciliation)
                 │                     └──→ F-024 (Progress) ──→ F-021 (Cancel)
                 ├──→ F-005 (Employees) ──→ F-004 (Refresh) ──→ F-008
                 ├──→ F-023 (SQLite) ──→ F-017 (Financial Rules) ──→ F-008
                 ├──→ F-029 (Network) ──→ F-019 (Discovery) ──→ F-004
                 └──→ F-030 (Path Traversal) ──→ F-001, F-002

F-007 (Curator) ──→ F-008 ──→ F-011 (Boris) ──→ F-015
                          └──→ F-012 (Ivan) ──→ F-015

F-013 (RSCH Day) ──→ F-015, F-016 (Auto-Recon)
F-038 (Aliases) ──→ F-015, F-016

F-017 (Financial Rules) ──→ F-008, F-009, F-010, F-011, F-012, F-016
F-018 (Export) ──→ F-008, F-009, F-010, F-011, F-012, F-016
F-028 (Backup) ──→ F-018

F-041 (Event Bus) — DEAD CODE, no deps
F-042 (Metrics) — DEAD CODE, no deps
```

---

## Список всех артефактов

| Артефакт | Путь | Статус | Строк | Последнее обновление |
|----------|------|--------|-------|----------------------|
| structure.md | docs/map/structure.md | complete | 435 | 2026-06-26 |
| architecture.md | docs/map/architecture.md | complete | 273 | 2026-06-26 |
| dependencies.md | docs/map/dependencies.md | complete | 345 | 2026-06-26 |
| inventory.md | docs/features/inventory.md | complete | 739 | 2026-06-26 |
| rules.md | docs/business/rules.md | complete | 777 | 2026-06-26 |
| invariants.md | docs/business/invariants.md | complete | 144 | 2026-06-26 |
| state-machines.md | docs/business/state-machines.md | complete | 142 | 2026-06-26 |
| model.md | docs/data/model.md | complete | 542 | 2026-06-26 |
| endpoints.md | docs/api/endpoints.md | complete | 1466 | 2026-06-26 |
| tech-debt.md | docs/risks/tech-debt.md | complete | 218 | 2026-06-26 |
| CANONICAL_MAP.md | docs/CANONICAL_MAP.md | complete | — | 2026-06-26 |

### Артефакты следующих фаз (созданы в QA Cycle v1.0)
| Артефакт | Путь | Статус | Строк |
|----------|------|--------|-------|
| user-stories.md | docs/specs/user-stories.md | complete | 1259 |
| edge-cases.md | docs/specs/edge-cases.md | complete | 487 |
| ux-audit.md | docs/ux/ux-audit.md | complete | 252 |
| fix-plan.md | docs/fixes/fix-plan.md | complete | 232 |
| fix-log.md | docs/fixes/fix-log.md | complete | 140 |
| regression-report.md | docs/regression/regression-report.md | complete | 176 |
| iteration-decision.md | docs/meta/iteration-decision.md | complete | 125 |

---

## Ключевые метрики

| Метрика | Значение |
|---------|----------|
| Файлов проанализировано | 124 |
| Точек входа | 5 |
| Фич всего | 42 |
| Core фич | 23 |
| Secondary фич | 13 |
| Auxiliary фич | 4 |
| Deprecated фич | 2 |
| Бизнес-правил | 90 |
| Инвариантов | 23 |
| State machines | 10 |
| Технический долг (всего) | 20 |
| Технический долг (critical) | 0 |
| Технический долг (major) | 3 |
| Технический долг (minor) | 16 |
| Риски безопасности | 4 (все mitigated) |
| Проблемы производительности | 5 |
| Архитектурный паттерн | [HYBRID] Layered + MVC + MVVM |
| Слоёв приложения | 6 |

---

## Журнал изменений

| Дата | Версия | Изменение |
|------|--------|-----------|
| 2026-06-26 | 1.0 | Первоначальная сборка Phase 0 (артефакты 0.1-0.8) |
| 2026-06-26 | 1.1 | QA Cycle v1.0 завершён: Phase 1-5 артефакты добавлены, 333/333 tests PASS, 4 fixes applied |
| 2026-06-26 | 1.2 | Wave 5: FIX-006 (toast detail) + FIX-009 (current file) реализованы, 353/353 tests PASS, 6 fixes total |
| 2026-06-26 | 1.3 | Wave 6: 4 TD fixes (TD-007/012/019/020) + 15 UX fixes, 353/353 tests PASS, 19 из 23 UX violations исправлены |
| 2026-06-26 | 1.4 | Cycle v2.0 (Wave 7): 4 complex UX fixes (UX-008/009/010/015), 353/353 tests PASS, 23/23 UX violations исправлены |
| 2026-06-26 | 1.5 | Wave 8: Master-отчёт fix (лишняя колонка "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ" убрана из общего шаблона, per-curator headers), performance ~92s→~22s (-76%) |

---

## Примечания

- **FIX-000 восстановлен**: В ходе Phase 0.4 обнаружено, что single-token guard в `_executor_matches` (FIX-000, commit 5d9beec) был удалён из рабочей копии. Восстановлен из HEAD. См. INV-021.
- **Существующие артефакты**: `features.json`, `QA_REPORT.md`, `QA_PROGRESS.md`, `FEATURE_TABLE.csv` — существующие не-канонические артефакты. Канонические артефакты в `docs/` заменяют их.
- **Объём анализа**: APP/ + tests/ + tools/ + корневые файлы. Игнорированы: backups/, Ване/, Старое/, РСЧ/, rlm_report/, .venv/, caches.
