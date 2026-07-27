# Traceability-матрица Master-Report v5.6

> **Цель:** связать сценарии → автотесты → результаты → покрытие в единую проверяемую матрицу.
> Это закрывает главный пробел существующей документации: `docs/specs/user-stories.md` (252 сценария), `edge-cases.md` (168), `features.json` (34 фичи) и 456 pytest-тестов существовали **разрозненно**.
>
> **Дата:** 2026-07-09 · **Тестов:** 456 collected · **Code-gates:** 18/18 PASS · **Тест-файлов:** 37

---

## Как читать эту матрицу

| Колонка | Что значит |
|---|---|
| **Feature** | Идентификатор фичи (F-XXX из `docs/features/inventory.md`) + краткое имя |
| **BDD-сценарий** | Ссылка на Given/When/Then в `04_TEST_PLAN.md` или `docs/specs/user-stories.md` |
| **Автотесты** | pytest-файл(ы), покрывающие фичу |
| **Ручной TC** | ID из чек-листа `04_TEST_PLAN.md` раздел 3 (если UI-проверка нужна вручную) |
| **Статус** | ✅ покрыто автотестом · 🖐 требует ручного · ⚠ частично |

---

## 1. Сводка покрытия по категориям

| Категория | Фичей | Автотесты | Ручные TC | Статус |
|---|---|---|---|---|
| **Запуск / bootstrap** | F-001, F-002 | test_phase2_db_repositories, test_db_pragmas_and_migrations | TC-1xx (ЗАПУСК.bat, иконка, welcome) | ✅ логика / 🖐 UI |
| **Консолидация** | F-003, F-008, F-011 | test_phase2_logic_service, test_percentage_matching_bugs, test_phase3_fix006_fix009, test_export_writer_edge_cases | TC-4xx (день/период/все) | ✅ логика / 🖐 UI |
| **РСЧ** | F-013, F-015 | test_rsch_period_hang, test_special_marker_no_highlight, test_expense_only_no_highlight, tests/core/infra/test_rsch_report | TC-4xx | ✅ логика / 🖐 UI |
| **Сверка / автосверка** | F-017 | tests/core/infra/test_reconciliation_report, test_phase0_reconciliation_fail_soft | TC-4xx | ✅ логика / 🖐 UI |
| **Сотрудники (CRUD)** | F-004, F-005, F-006 | test_phase2_db_repositories (source_file_repo) | TC-3xx | ✅ логика / 🖐 UI |
| **БД / persistence** | F-026, F-027 | test_db_pragmas_and_migrations, test_purge_sessions_cascade, test_phase2_db_repositories, test_qa_sweep_repos | TC-7xx | ✅ полностью |
| **UI / темы** | F-035, F-036, F-039 | test_theme_manager, test_system_theme, test_operation_state, test_operation_status_bar, test_debounce, test_geometry, test_tooltip, test_dashboard_state_extended | TC-6xx (смена темы, контрасты) | ✅ логика / 🖐 визуал |
| **Экспорт / форматирование** | F-019, F-020 | test_phase1_export_decimal, test_export_writer_edge_cases, test_excel_hyperlink_no_network, test_phase0_workbook_release, test_phase1_schema_validator | TC-4xx | ✅ полностью |
| **Чтение / ingestion** | F-021 | test_phase2_ingestion_reader, test_phase1_gui_marshaling, test_file_processor_time_module | — | ✅ полностью |
| **Надёжность / edge** | (cross) | test_phase3_reliability, test_qa_sweep_edge_cases, test_qa_sweep_utils, test_phase2_critical_edge_cases, test_partial_renamer, test_data_loss_log, test_finish_helper, test_audit_refactoring | TC-6xx, EC-01…20 | ✅ полностью |

---

## 2. Code-gates → гарантии (workspace/verify_gate.py)

Эти 18 автоматических проверок гарантируют, что архитектурные инварианты не нарушены.

| Gate | Что проверяет | Статус |
|---|---|---|
| T1 | pytest: 0 collection errors, ≥4 passed (фактически 456) | ✅ |
| T2 | tests/ не ignored, готов к git add (35 файлов) | ✅ |
| T3 | cacheprovider отключён (lastfailed не влияет) | ✅ |
| T4 | `.github_token` ignored (CWE-532/200 закрыт) | ✅ |
| T5 | Нет `Token@github` в URL (CWE-312/532/214 закрыт) | ✅ |
| T6 | `workspace/`, `.agents/` ignored | ✅ |
| U1 | Премиальная navy-палитра, 0 Tailwind-leftover | ✅ |
| U2 | Segoe UI Semibold + Cascadia Mono/Consolas fallback | ✅ |
| U3 | DateEntry + tk.Menu перетематизируются | ✅ |
| U4 | Нет desynced/stale palette hex вне theme.py | ✅ |
| U5 | Dead-стили themed, status-bar тесты green | ✅ |
| U6 | WCAG AA контрасты (body 15.8:1 L / 14.5:1 D) | ✅ |
| U7 | partial-tag зарегистрирован + row-wash + Semibold | ✅ |
| U8 | Mono.Treeview для path-heavy деревьев | ✅ |
| U9 | Hover во всех 4 dashboard trees | ✅ |
| U10 | app.ico multi-res + единый __version__ + emoji убран | ✅ |
| U11 | Empty-state + welcome-dialog + 6 action tooltips | ✅ |
| U12 | Shortcuts dialog (F1) + error presenter (no str(e)) | ✅ |

**Команда проверки:** `python workspace/verify_gate.py` → ожидать `RESULT: verify_gate == 0 (ALL GATES PASSED)`.

---

## 3. BDD-сценарий → pytest-test (ключевые маппинги)

Выборка критических flow. Полный BDD-набор — в `04_TEST_PLAN.md` раздел 4 и `docs/specs/user-stories.md` (252 сценария).

| BDD-сценарий | pytest-покрытие | Результат |
|---|---|---|
| Успешная консолидация за день | `test_phase2_logic_service::*`, `test_phase3_fix006_fix009::TestRunEngineOnCurrentFile` | ✅ |
| Консолидация с неправильным % (комиссия ≤1 → ×100) | `test_percentage_matching_bugs::*` | ✅ |
| Отмена консолидации (partial-файлы) | `test_partial_renamer::*` | ✅ |
| РСЧ за период не «виснет» (баг заказчика) | `test_rsch_period_hang::*` | ✅ |
| Сверка fail-soft (нет Master → пустой отчёт) | `test_phase0_reconciliation_fail_soft::*`, `tests/core/infra/test_reconciliation_report::*` | ✅ |
| Decimal precision в экспорте (не float) | `test_phase1_export_decimal::*` | ✅ |
| Бэкап перед перезаписью Excel | `test_phase0_workbook_release::*`, `test_export_writer_edge_cases::*` | ✅ |
| Purge старых сессий (>30 дней) | `test_purge_sessions_cascade::*` | ✅ |
| WAL + PRAGMA integrity при старте | `test_db_pragmas_and_migrations::*` | ✅ |
| Переключение темы не ломает ttk-стили | `test_theme_manager::*`, `test_system_theme::*` | ✅ |
| OperationState блокирует кнопки во время операции | `test_operation_state::*`, `test_operation_status_bar::*` | ✅ |
| Tooltip уничтожается с виджетом (нет утечки) | `test_tooltip::*` | ✅ |
| Парсинг суммы «1 234,56» → Decimal | `test_phase2_critical_edge_cases::*`, `test_phase1_schema_validator::*` | ✅ |

---

## 4. Ручное UI-тестирование → что НЕ автоматизировано

Tkinter UI плохо поддаётся UI-автоматизации (нет accessibility-дерева как у веб). Эти сценарии требуют **ручной** проверки по чек-листу `04_TEST_PLAN.md` раздел 3:

| Зона | Что проверять вручную | Чек-лист |
|---|---|---|
| **Иконка/бренд** | app.ico в taskbar, title без эмодзи, welcome-dialog first-run | TC-101…115 |
| **Sidebar взаимодействие** | DateEntry открытие/выбор, все 6 кнопок, сворачивание ЗА ПЕРИОД, валидация даты | TC-201…230 |
| **Таблица сотрудников** | row-wash статусы, hover, поиск, фильтр, сортировка, контекстное меню, drag-and-drop | TC-301…320 |
| **Операции (визуал)** | прогресс в title, toast успеха, «открыть файл?», блокировка кнопок | TC-401…425 |
| **Темы/визуал** | light↔dark в рантайме (включая DateEntry/меню), контрасты, hover-эффекты | TC-601…620 |
| **Visual Regression** | 12 baseline-скриншотов (sidebar/таблица/тосты/dialogs в обеих темах) | VS-01…12 |

**Объём ручной проверки:** 213 маркируемых пунктов (`[ ]`), из них ~150 — UI-специфичные (не покрываются автотестами).

---

## 5. Несоответствия, выявленные при составлении документации

Эти расхождения найдены doc-writer агентами при сверке кода и должны быть исправлены (не блокируют документацию, но влияют на тестирование):

| # | Расхождение | Где | Действие |
|---|---|---|---|
| 1 | **F1 не показывается в ShortcutsDialog** — `_bind_shortcuts` регистрирует 9 биндов (включая F1), но `shortcuts_dialog.py:SHORTCUTS` содержит только 8 пар (без F1) | `shortcuts_dialog.py:30-39` | Добавить `("<F1>", "Горячие клавиши")` в SHORTCUTS |
| 2 | **Версия в ЗАПУСК.bat** — title bat-файла `v5.5`, а `APP/__init__.py:__version__ = "5.6"` | `ЗАПУСК.bat:12` | Синхронизировать с `__version__` (как в `gui_master.py`) |
| 3 | **CANONICAL_MAP метрики устарели** — говорит «333→353 теста», фактически 456 | `docs/CANONICAL_MAP.md` | Обновить счётчик |
| 4 | **OpenBLAS memory error** — `gui_error_log.txt` от 08.07.2026 блокирует запуск GUI на текущей машине | окружение (не код) | Отдельная задача (numpy/OpenBLAS env var) |

---

## 6. Definition of Done (критерии 100% приёмки)

Релиз готов к продаже заказчику, когда **все** условия выполнены:

| ID | Критерий | Как проверить | Статус |
|---|---|---|---|
| D-01 | 456 автотестов passed | `.venv/Scripts/python.exe -m pytest tests/ -q` | ✅ |
| D-02 | 0 failed, 0 errors | там же | ✅ |
| D-03 | verify_gate exit 0 (18/18) | `python workspace/verify_gate.py` | ✅ |
| D-04 | ruff clean | `.venv/Scripts/python.exe -m ruff check APP/core` | ✅ |
| D-05 | WCAG AA контрасты | U6-gate (body 15.8:1/14.5:1) | ✅ |
| D-06 | Нет секретов в git | T4-gate + `git log --all -p \| grep token` | ✅ |
| D-07 | Иконка приложения | U10-gate (app.ico multi-res) | ✅ |
| D-08 | Ручной чек-лист 213 пунктов | `04_TEST_PLAN.md` раздел 3, отметить `[x]` | 🖐 требует прохождения |
| D-09 | BDD-сценарии passed | `04_TEST_PLAN.md` раздел 4 (19 сценариев) | 🖐 требует прохождения |
| D-10 | Visual regression: 0 diff | 12 baseline-скриншотов (VS-01…12) | 🖐 требует baseline |
| D-11 | 0 critical/major дефектов | регресс после прохождения D-08…D-10 | 🖐 зависит |
| D-12 | Performance: refresh <2s (23 сотр.) | ручной замер | 🖐 требует замера |

**Итог:** автоматизируемая часть (D-01…D-07) — ✅ полностью готова. Ручная часть (D-08…D-12) — требует прохождения QA по чек-листу `04_TEST_PLAN.md`.

---

## 7. Источники и стандарты

Документация построена по:
- **IEEE 829** — Standard for Software Test Documentation (структура тест-плана)
- **Divio 4-type framework** — tutorial (User Guide) / reference (UI Spec, Design System) / how-to (Test Plan) / explanation (Index)
- **BDD/Gherkin** — declarative-сценарии Given/When/Then (Cucumber best practices)
- **Visual Regression Testing** — baseline + diff методология (Applitools/Percy)
- **WCAG 2.1** — contrast ratios для доступности

**Каноническая база (не дублируется, ссылается):**
- `docs/features/inventory.md` — 42 фичи
- `docs/business/{rules,invariants,state-machines}.md` — 90 BR / 23 INV / 10 SM
- `docs/specs/{user-stories,edge-cases}.md` — 252 BDD + 168 edge
- `docs/api/endpoints.md` — 52 эндпоинта
- `docs/data/model.md` — модель данных
- `docs/qa/FINAL_REPORT.md` — QA-Sweep отчёт
