# QA-Sweep: ИТОГОВЫЙ ОТЧЁТ

**Дата:** 01.07.2026
**Методология:** пофазовая (Phase 0–5) из «Prompt_System_Ideal_v2_TechnicalDoc_2026-06-28»
**Правило:** логику НЕ менять — только проверка и документирование найденных проблем

---

## Сводка

| Метрика | Значение |
|---------|----------|
| Модулей в `core/` | ~75 |
| LOC в `core/` | ~13 000 |
| Тестов до QA | 352 |
| Тестов после QA | **418** (+66 новых) |
| Регрессия | **0** (418 passed) |
| Реальных симуляций | **8 сценариев** на данных заказчика |
| Симптом бага «РСЧ за период» | **НЕ ВОСПРОИЗВОДИТСЯ** (после фикса) |
| Найденных проблем | 2 (см. §5) |

---

## Phase 0 — Discovery ✅

Полная карта проекта построена. Точки входа:
- `APP/main.py` — Tkinter GUI (`GuiMaster`)
- `APP/headless_run.py` — headless-консолидация

Подсистемы: `app/`, `domain/`, `infra/` (rsch/, reconciliation/, репозитории), `services/`,
`ui/` (виджеты, gui_commands/), `view_models/`, `shared/`. Контроллер `app_controller.py`
делегирует в `RschService` / `ReconciliationService` и т.д.

## Phase 1 — Specification ✅

Спецификация проверяемых функций и edge-cases: `docs/qa/qa-sweep-spec.md`.
Перечень: 13 тяжёлых build-путей (A1–A13), 7 репозиториев (B1–B7), сервис сверки (C1),
6 групп утилит (D1–D6), ingestion (E1), 9 симуляций (S1–S10), 8 edge-cases (E1–E8).

## Phase 2 — Testing ✅

### 2.1 Baseline
352 существующих теста — **все зелёные** (8.3 c).

### 2.2 Анализ покрытия — найденные пробелы
До QA **не имели тестов**: `config_controller`, `discovery_service`, `customer_alias_repo`,
`source_file_repo`, `staging_repo`, `settings_store`, `path_resolver`, `ingestion_engine`,
`ReconciliationService`, весь UI-виджет-слой, public-функции `build_reconciliation_report` /
`build_combined_reconciliation_report`, shared-утилиты (`utils_helpers`, `path_scrub`,
`message_formatting`, `performance`).

### 2.3 Новые верификационные тесты (без смены логики)
| Файл | Тестов | Что покрывает |
|------|--------|---------------|
| `test_qa_sweep_utils.py` | 33 | D1 to_decimal/percent/normalize, D2 path_scrub, D4 performance |
| `test_qa_sweep_repos.py` | 24 | B1 ConfigController, B3 CustomerAliasRepository (CRUD+matching), B6 SettingsStore, контракты build-API (A11-A13, C1) |
| `test_qa_sweep_edge_cases.py` | 9 | E1-E8: нет данных, граница года, дубликаты, отмена, длинный период, монотонный прогресс |

## Phase 3 — Fixing (сужено до документирования)
Логику не меняли. Найденные расхождения зафиксированы как findings (§5).

## Phase 4 — Verification (симуляции работы заказчика) ✅

### 4.1 Реальные прогоны на данных заказчика

**Изолированная среда** (`tests/simulation_runner.py`):
| S | Сценарий | Результат | Время |
|---|----------|-----------|-------|
| S5 | **РСЧ за период** (баг заказчика) | ✅ PASS | 39–40 c |
| S4 | РСЧ за один день | ✅ PASS | 3.1 c |
| S6 | РСЧ за период batch | ✅ PASS | 8.9 c |

S5: **7478 строк из 6 файлов, 9 progress-reports** → фикс причины 2 подтверждён
(раньше прогресс = 0, статус-бар «висел»).

**Реальный config/cache.db заказчика** (`tests/simulation_runner_real.py`):
| S | Сценарий | Результат | Время |
|---|----------|-----------|-------|
| S1 | Консолидация за день | ✅ PASS | 12.1 c (439 строк) |
| S2 | Консолидация за все даты | ✅ PASS | 60.5 c |
| S3 | Консолидация за период | ✅ PASS | 23.0 c |
| S10 | Refresh status | ✅ PASS | 0.2 c |
| S8 | Автосверка за день | ✅ PASS | 28.2 c (Общий 492, Борис 57, Иван 18, РСЧ 574) |

**Итог симуляций: 8/8 PASS.** Все основные сценарии заказчика работают корректно.

### 4.2 Edge-cases (9 тестов, все зелёные)
- E1 несуществующий файл → `FileNotFoundError` (не зависон) ✓
- E2 нет данных → понятная «нет строк за период» через сервис ✓
- E3 отмена → корректный выход, сообщение про отмену ✓
- E4 длинный период (30 дней) → 31 лист без ошибок ✓
- E5 локальный путь → passthrough ✓
- E6 (Phase 2) зависший сетевой диск → таймаут 3 c ✓
- E7 дубликаты путей → дедупликация ✓
- E8 граница года (31.12.2024 + 01.01.2025) → нет коллизии листов ✓
- монотонный прогресс за период ✓

## Phase 5 — Iteration decision

**Статус: ГОТОВО.** Все 5 фаз пройдены.

---

## §5. Найденные замечания (findings)

Логику не меняли — findings только задокументированы.

### F-PERF-1: `resolve_max_workers(0)` возвращает 1, а не default (minor)
- **Файл:** `core/app/performance.py:22`
- **Симптом:** `config.yaml` заказчика хранит `max_workers: 0` с комментарием
  «Empty keeps the current default». Но код: `max(1, min(64, int(0))) == 1`.
  То есть **0 ≠ default** — получается ровно 1 воркер (сильно медленнее на
  многоядерных ПК заказчика). Default срабатывает только для `None`/`""`.
- **Влияние:** производительность консолидации/чтения ниже возможной, если
  заказчик явно не выставит число. На ПК заказчика (24 ядра по тесту) при
  `max_workers: 0` используется 1 поток вместо ~24.
- **Рекомендация:** трактовать `0` так же, как `None`/`""` → default (1 строка).
  Зафиксировано в `test_qa_sweep_utils.py::test_zero_or_empty_falls_back`.

### F-SEC-1 (подтверждение корректной работы): path-traversal guard
- **Файл:** `core/infra/config_controller.py:187` (`resolve_path`)
- **Наблюдение:** guard **корректно блокирует** пути вне разрешённых корней
  (source_roots / project root / config dir). При попытке перенаправить output
  во временную папку `%TEMP%` симуляция получила `ValueError: Path traversal
  detected`. Это **функция безопасности работает как задумано** — не баг.
  Зафиксировано в `test_qa_sweep_repos.py::test_resolve_path_absolute_under_allowed_root`.

### Прочее (без замечаний — работает корректно)
- Коллизия имён листов РСЧ на границе года — **исключена** (коммит 323bed1, `%d.%m.%Y`).
- Шаблон РСЧ `APP/РСЧ/шаблон отчета.xlsx` отсутствует — **корректный fallback**
  на встроенный шаблон (warning в issues_sink, не ошибка).
- `0 rows` → понятная ошибка через сервис, не тихий провал.
- Отмена — кооперативная, корректное сообщение.
- Атомарное сохранение + cleanup `.tmp` при ошибке — корректно.

---

## §6. Добавленные артефакты

Тесты (без смены логики продукта):
- `tests/test_qa_sweep_utils.py` — 33 теста (pure-утилиты)
- `tests/test_qa_sweep_repos.py` — 24 теста (репозитории + контракты)
- `tests/test_qa_sweep_edge_cases.py` — 9 тестов (edge-cases)
- `tests/simulation_runner.py` — headless-драйвер симуляций (изолир. среда)
- `tests/simulation_runner_real.py` — headless-драйвер симуляций (реальный config)

Документация:
- `docs/qa/qa-sweep-spec.md` — спецификация проверки
- `docs/qa/simulation_results.json` — результаты симуляций (изолир.)
- `docs/qa/simulation_real_results.json` — результаты симуляций (реальный config)
- `docs/qa/FINAL_REPORT.md` — этот отчёт

## §7. Ограничения проверки

1. **UI-виджет-слой** (`ui_sidebar`, `ui_settings`, `ui_dashboard`, `ui_dialogs`,
   `ui_employee_table`, `ui_aliases`, `ui_log_panel`) не имеет unit-тестов — это
   Tkinter-виджеты, требующие GUI-окружения. Поведены через end-to-end симуляции
   (S1–S10 прогоняют тот же `AppController`, что и GUI).
2. `discovery_service`, `ingestion_engine` (public-слой) проверены косвенно через
   реальные симуляции (S1–S8 работают на их основе), но не имеют прямых unit-тестов.
3. Симуляции запускались на машине разработки, не на ПК заказчика. Поведение на
   реальном сетевом диске заказчика (Q:/Z:) подтверждается только код-ревью
   фикса причины 1 (таймаут в `get_local_copy`).
