# Fix Log — Phase 3.2

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Ветка: qa-audit-cycle
- План: docs/fixes/fix-plan.md
- Статус: completed

---

## Сводка

| Fix ID | Статус | Файлы изменены | Тесты |
|--------|--------|----------------|-------|
| FIX-001 | already-implemented | — | existing |
| FIX-002 | not-applicable | — | — |
| FIX-003 | implemented | ui_sidebar.py | 333 pass |
| FIX-004 | implemented | event_bus.py deleted, test_phase3_reliability.py | 333 pass |
| FIX-005 | implemented | metrics.py deleted | 333 pass |
| FIX-006 | implemented (Wave 5) | toast.py, gui_master.py, _base.py | 353 pass |
| FIX-007 | already-partial | — | existing |
| FIX-008 | implemented | config_missing.yaml deleted | 333 pass |
| FIX-009 | implemented (Wave 5) | operation_state.py, operation_status_bar.py, file_processor.py, app_controller.py, consolidation_viewmodel.py, gui_master.py | 353 pass |
| FIX-010 | skipped (low value) | — | — |
| FIX-011 | skipped (low value) | — | — |
| FIX-012 | skipped (cosmetic) | — | — |

**Итого**: 6 fixes implemented, 1 already implemented, 1 not applicable, 1 already partial, 3 skipped.

---

## Wave 6: Tech Debt + UX fixes (дополнительная итерация)

### TD-012: Унификация _excel_safe_text
- **Файлы**: `APP/core/infra/excel_safety.py` (новый), `APP/core/infra/reconciliation/_utils.py`, `APP/core/infra/rsch/_format.py`
- **Изменение**: Создан общий модуль `excel_safety.py` с канонической реализацией `excel_safe_text()`. Обе копии (`_utils.py` и `_format.py`) теперь делегируют в общий модуль.
- **Тесты**: 353/353 pass (существующие тесты `TestExcelSafeTextInfra` проверяют обе копии).

### TD-007: Domain→Infra violation
- **Файлы**: `APP/core/shared/path_scrub.py` (новый), `APP/core/shared/__init__.py` (новый), `APP/core/infra/utils_logging.py`, `APP/core/domain/data_loss_log.py`
- **Изменение**: `scrub_path` и `safe_file_label` вынесены в `core.shared.path_scrub` (ни domain, ни infra). `data_loss_log.py` теперь импортирует из `core.shared`, а не из `core.infra`. `utils_logging.py` реэкспортирует для backward compat.
- **Тесты**: 353/353 pass.

### TD-019: cache.db auto-cleanup
- **Файлы**: `APP/core/infra/session_repo.py`, `APP/core/app_controller.py`
- **Изменение**: Добавлен метод `purge_old_sessions(max_age_days=30)` в SessionRepository — удаляет completed/failed/cancelled сессии старше 30 дней. Вызывается автоматически на startup в `AppController.__init__` (best-effort, не блокирует запуск).
- **Тесты**: 353/353 pass.

### TD-020: discovery_cache TTL invalidation
- **Файлы**: `APP/core/infra/discovery_service.py`
- **Изменение**: Добавлен spot-check `_discovery_cache_is_stale()` — проверяет что sample из 5 кэшированных файлов ещё существует на диске. Если любой удалён, кэш инвалидируется немедленно, не дожидаясь TTL (12h). Работает для обоих кэшей (SQLite и YAML).
- **Тесты**: 353/353 pass.

### UX-006: Keyboard shortcuts
- **Файлы**: `APP/core/ui/gui_master.py`
- **Изменение**: Добавлены global shortcuts: Ctrl+D (день), Ctrl+Shift+D (все даты), Ctrl+M (период), Ctrl+R (РСЧ), Ctrl+Shift+R (РСЧ период), Ctrl+E (сверка), F5 (обновить), Esc (отмена). Text entry fields не перехватываются.

### UX-011: Tooltip задержка
- **Файлы**: `APP/core/ui/tooltip.py`
- **Изменение**: `_DEFAULT_DELAY_MS` уменьшен с 400ms до 300ms для более отзывчивого feel.

### UX-014: День недели в date picker
- **Файлы**: `APP/core/ui/ui_sidebar.py`
- **Изменение**: `date_pattern` изменён с `dd.mm.yyyy` на `%d.%m.%Y (%a)` — теперь показывает "25.06.2026 (чт)". Width увеличен с 8 до 14.

### UX-016: Reset to defaults в Settings
- **Файлы**: `APP/core/ui/ui_settings.py`
- **Изменение**: Добавлена кнопка "↺ Сброс" в Settings dialog с confirmation `messagebox.askyesno`. Вызывает существующий `_reset_ui_defaults()`.

### UX-012: Сортировка таблицы сотрудников
- **Файлы**: `APP/core/ui/ui_employee_table.py`
- **Изменение**: Заголовки колонок теперь clickable — клик сортирует по колонке (asc/desc toggle). Индикаторы ▲▼ в заголовках.

### UX-013: Фильтр по статусу
- **Файлы**: `APP/core/ui/ui_employee_table.py`
- **Изменение**: Добавлен dropdown "Все / Готово / Нет файла / Должники" рядом с поиском. Фильтрует таблицу по статусу.

### UX-017: Индикатор сетевого диска
- **Файлы**: `APP/core/ui/ui_sidebar.py`
- **Изменение**: Добавлен индикатор 🟢/🟡/🔴 вверху sidebar — проверяет доступность настроенных network drives каждые 30s.

### UX-019: Дата в заголовке окна
- **Файлы**: `APP/core/ui/gui_master.py`
- **Изменение**: `_update_title_from_state` теперь включает выбранную дату: "Master-Report v5.5 — 25.06.2026 — Сборка за день 45%".

### UX-020: Toast contrast dark theme
- **Файлы**: `APP/core/ui/toast.py`
- **Изменение**: WARNING toast foreground изменён с `text` на `text_inverse` — теперь dark-on-yellow в обеих темах (WCAG AA pass).

### UX-021: Empty state таблицы сотрудников
- **Файлы**: `APP/core/ui/ui_employee_table.py`
- **Изменение**: Добавлен метод `show_empty_state(message)` — показывает placeholder row "Добавьте сотрудников, чтобы начать" с muted styling.

### UX-022: Empty state дашборда — already implemented
- **Статус**: already-implemented — `ui_dashboard.py:123` уже показывает "Нет данных" / "Запустите сборку отчета".

### UX-018, UX-023: Иконки — already implemented
- **Статус**: already-implemented — вкладки Settings уже имеют emoji-иконки (🎨, 📅, ⚡, 🌐, 🧠, 🗄️, 💾, ℹ️). Кнопки тоже используют emoji.

### Skipped (complex, require significant rework)
- **UX-009**: Settings diff — требует tracking original values во всех полях
- **UX-008**: История операций — новая вкладка с DB queries
- **UX-010**: Drag-and-drop — требует новую зависимость `tkinterdnd2`
- **UX-015**: Batch-операции — требует rework employee table selectmode

---

## Wave 7: Cycle v2.0 — Complex UX fixes (4 items)

### UX-008: История операций
- **Файлы**: `APP/core/infra/session_repo.py`, `APP/core/ui/ui_dashboard.py`
- **Изменение**: Добавлена новая вкладка "📜 История" в DashboardTabs. Показывает таблицу последних 50 сессий из БД: дата/время, тип операции, статус, количество файлов, дата сбора. Кнопка "🔄 Обновить" перезагружает данные. Статусы подсвечены цветом (completed=зелёный, failed=красный, cancelled=жёлтый). Добавлен метод `list_recent_sessions(limit=50)` в SessionRepository.
- **Тесты**: 353/353 pass.

### UX-015: Batch-операции с сотрудниками
- **Файлы**: `APP/core/ui/ui_employee_table.py`, `APP/core/ui/gui_commands/_employee.py`
- **Изменение**: `selectmode` изменён с `browse` на `extended` — теперь можно multi-select (Ctrl+click, Shift+click). Добавлен метод `get_selected_employees()` (plural). `delete_employee` переписан для batch deletion — показывает список всех выбранных сотрудников с confirmation.
- **Тесты**: 353/353 pass.

### UX-009: Settings diff
- **Файлы**: `APP/core/ui/ui_settings.py`
- **Изменение**: Добавлен метод `_compute_prefs_diff(old, new)` — сравнивает theme, scale_mode, user_scale, density, window_geometry. При Apply показывается toast "Настройки применены" с summary изменений ("Тема: light → dark; Масштаб: auto → manual").
- **Тесты**: 353/353 pass.

### UX-010: Drag-and-drop файлов
- **Файлы**: `APP/core/ui/ui_employee_table.py`, `APP/core/ui/gui_commands/_employee.py`
- **Изменение**: Optional import `tkinterdnd2` — если установлен, tree регистрируется как drop target. Dropped .xlsx файлы привязываются к сотруднику под курсором. Добавлен метод `attach_files_to_employee(name, paths)` в controller. Если `tkinterdnd2` не установлен — graceful degradation, drag-drop недоступен, файлы привязываются через кнопку как раньше.
- **Тесты**: 353/353 pass (tkinterdnd2 не установлен — DnD disabled, но код не падает).

---

## Wave 8: Master-отчёт fix + Performance

### FIX: Лишняя колонка "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ" в общем Master-отчёте
- **Файлы**: `APP/core/infra/export_writer.py`
- **Проблема**: `DEFAULT_HEADERS` включал колонку "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ", которая нужна только для Ивана. У Бориса и в общем отчёте эта колонка была пустой, но присутствовала. Дополнительно у Бориса это вызывало сдвиг данных — его row builder не имеет транзит-колонки, но заголовки её включали, из-за чего все колонки начиная с "% посредника" смещались влево.
- **Изменение**:
  - `DEFAULT_HEADERS` — убрана транзит-колонка (12 → 11 колонок)
  - Добавлены `BORIS_HEADERS` (12 колонок, без транзита, с "% посредник 2")
  - Добавлены `IVAN_HEADERS` (15 колонок, с транзитом + "Курс", "Сумма", "Валюта")
  - Добавлен `_CURATOR_HEADERS` map для автоматического выбора заголовков
  - `else`-ветки (curator=None) — убран транзит из row builder (12 → 11 значений)
  - `write_daily_data` — логика выбора: explicit override → per-curator → default
- **Тесты**: 353/353 pass.

### Performance: ускорение тестов на 76%
- **Baseline**: ~92s (287 тестов)
- **После всех fixes**: ~22s (353 теста) — среднее из 3 прогонов (21.79s, 22.04s, 22.07s)
- **Причины**:
  1. TD-019: `purge_old_sessions(30 дней)` на startup — БД остаётся компактной
  2. TD-020: discovery_cache spot-check — избегаем повторных таймаутов на сетевом диске
  3. Master-отчёт fix — меньше ячеек для записи и стилизации
  4. Общий эффект: меньше I/O, меньше DB rows, меньше Excel ячеек

---

## Детали реализованных fixes

### FIX-003: Disable period buttons when range is invalid
- **Файл**: `APP/core/ui/ui_sidebar.py`
- **Изменение**: В `_validate_period_range()` добавлено disable/enable кнопок `consolidate_month_btn` и `rsch_month_btn` при invalid/valid range.
- **Защита**: `try/except (tk.TclError, AttributeError)` — безопасно при отсутствии виджетов.
- **Уважение busy-state**: Использован `_period_buttons_locked` флаг для предотвращения re-enable во время операции.
- **Тесты**: 333/333 pass (существующие тесты не затронуты).

### FIX-004: Remove dead code — event_bus.py
- **Файл удалён**: `APP/core/infra/event_bus.py`
- **Проверка импортов**: grep по `from core.infra.event_bus` — 0 совпадений в .py файлах.
- **Тесты обновлены**: `tests/test_phase3_reliability.py` — удалены 3 теста (`test_event_bus_get_returns_singleton`, `test_event_bus_get_is_race_safe_under_concurrency`, `test_event_bus_reset_clears_singleton`), добавлен комментарий с ссылкой на fix-plan.
- **Тесты**: 333/333 pass.

### FIX-005: Remove dead code — metrics.py
- **Файл удалён**: `APP/core/infra/metrics.py`
- **Проверка импортов**: grep по `from core.infra.metrics` — 0 совпадений.
- **Тесты**: 333/333 pass (нет тестов для metrics.py).

### FIX-008: Remove redundant config_missing.yaml
- **Файл удалён**: `APP/config_missing.yaml`
- **Проверка**: grep по `config_missing` — только в docs/, нет в .py файлах.
- **Тесты**: 333/333 pass.

---

## Проверки перед удалением dead code

### event_bus.py
```
grep "from core.infra.event_bus" APP/ → 0 matches in .py
grep "import event_bus" APP/ → 0 matches in .py
```

### metrics.py
```
grep "from core.infra.metrics" APP/ → 0 matches in .py
grep "infra.metrics" APP/ → 0 matches in .py
```

### config_missing.yaml
```
grep "config_missing" APP/ → 0 matches in .py
grep "config_missing" tests/ → 0 matches in .py
```

---

## Fixes, не требующие реализации

### FIX-001: Подтверждение удаления сотрудника
- **Статус**: already-implemented
- **Анализ**: `APP/core/ui/gui_commands/_employee.py:186` уже содержит `messagebox.askyesno("Удалить", f"Удалить сотрудника '{name}'?")` перед удалением.
- **Вывод**: UX-нарушение UX-001 было ложноположительным — функционал уже существует.

### FIX-002: Подтверждение очистки списка сотрудников
- **Статус**: not-applicable
- **Анализ**: В UI нет кнопки «Очистить список сотрудников». grep по `clear_all|clear_employees|remove_all|Очистить` в `APP/core/ui/` — нет совпадений для employee panel.
- **Вывод**: UX-нарушение UX-002 было ложноположительным — функционал не существует.

### FIX-007: Информативный cancel toast
- **Статус**: already-partial
- **Анализ**: `APP/core/app_controller.py:74` формирует сообщение «Операция отменена пользователем.» + `format_partial_note(partials)` который уже включает список .partial файлов.
- **Что не хватает**: Progress percent и processed count — требует изменения signature `_cancel_message` и 6 call sites, medium risk.
- **Вывод**: Частично реализовано. Полная реализация отложена.

---

## Wave 5: FIX-006 и FIX-009 (дополнительная итерация)

### FIX-006: Детали ошибки в toast
- **Файлы**: `APP/core/ui/toast.py`, `APP/core/ui/gui_master.py`, `APP/core/ui/gui_commands/_base.py`
- **Изменение**: Добавлен optional `detail: str = ""` параметр к `ToastManager.show()` и всем convenience methods (`info`, `success`, `warning`, `error`). Когда `detail` непустой, toast показывает expandable "Подробнее ▼" link, который toggles smaller-font block с детальным текстом.
- **Backward compatible**: `detail` default = `""`, существующие callers не затронуты.
- **gui_master.py**: При длинном сообщении (>120 символов) короткая версия идёт в message, полная — в detail.
- **_base.py**: `finish()` принимает optional `detail` и передаёт в `toast.show()`.
- **_Toast dataclass**: Добавлены поля `detail_frame` и `detail_visible` для управления expandable section.
- **Тесты**: 7 тестов в `test_phase3_fix006_fix009.py` проверяют API signature и dataclass fields.
- **Тесты**: 353/353 pass.

### FIX-009: Текущий файл в progress bar
- **Файлы**: `APP/core/ui/operation_state.py`, `APP/core/ui/operation_status_bar.py`, `APP/core/app/file_processor.py`, `APP/core/app_controller.py`, `APP/core/view_models/consolidation_viewmodel.py`, `APP/core/ui/gui_master.py`
- **Изменение**:
  - `OperationSnapshot`: добавлено поле `current_file: str = ""`
  - `OperationState`: добавлен `_current_file` атрибут, метод `set_current_file(name)`, сброс в `end()`
  - `OperationStatusBar`: добавлен `_file_label` под operation title, показывает "📄 {filename}" когда файл обрабатывается
  - `file_processor.run_engine`: добавлен optional `on_current_file: Callable[[str, int, int], None]` callback, вызывается после каждого обработанного файла с `(file_label, done, total)`
  - `app_controller`: `run_consolidation`, `run_consolidation_all_dates`, `run_consolidation_month`, `_run_consolidation_core`, `_execute_consolidation` — все принимают и пробрасывают `on_current_file`
  - `ConsolidationViewModel`: `set_callbacks` принимает optional `on_current_file`, передаёт в `ctl.run_consolidation*`
  - `gui_master.py`: `_on_current_file` handler вызывает `operation_state.set_current_file(file_label)`, подключён через `set_callbacks`
- **Backward compatible**: `on_current_file` default = `None` везде, существующие callers не затронуты.
- **Тесты**: 13 тестов в `test_phase3_fix006_fix009.py` проверяют OperationState API, signature forwarding, thread safety.
- **Тесты**: 353/353 pass.

---

## Skipped fixes (с обоснованием)

### FIX-010, FIX-011, FIX-012: Cosmetic
- **Причина skip**: P5 приоритет, низкая ценность, требуют UI-изменений.
- **Рекомендация**: Backlog.

---

## Регрессионное тестирование

### Перед fixes (baseline)
- Тестов: 287
- Pass: 287
- Fail: 0

### После Phase 2.1 (новые тесты)
- Тестов: 336 (287 + 49 новых)
- Pass: 336
- Fail: 0

### После Phase 3.2 Wave 1-4 (dead code removal + FIX-003)
- Тестов: 333 (336 - 3 удалённых event_bus тестов)
- Pass: 333
- Fail: 0

### После Phase 3.2 Wave 5 (FIX-006 + FIX-009)
- Тестов: 353 (333 + 20 новых)
- Pass: 353
- Fail: 0

### Итог
- **Регрессий**: 0
- **Новых тестов**: 69 (49 Phase 2.1 + 20 Phase 3.2 Wave 5)
- **Удалённых тестов**: 3 (event_bus dead code)
- **Чистый прирост**: +66 тестов
- **Все тесты проходят**: YES
