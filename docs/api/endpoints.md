# API-эндпоинты и интерфейсы

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Тип: Desktop GUI (внутренние интерфейсы, CLI, GUI-команды)

## Сводка
- Всего интерфейсов: 52
- CLI-команд: 2
- GUI-команд: 20
- Внутренних сервисных интерфейсов: 28
- Event-bus событий: 2 (модуль EventBus — dead code, не используется за пределами собственного модуля)
- Требуют аутентификации: 0 (N/A для desktop)

## Интерфейсы

---

### EP-001: [CLI] Headless-консолидация за конкретную дату
- Фича: F-002
- Тип: cli-command
- Метод: флаг `--date DD.MM.YYYY`
- Путь: `APP/headless_run.py --date DD.MM.YYYY`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `--date` (str, опциональный) — дата консолидации в формате `DD.MM.YYYY`
- Response — Success:
  - Лог `INFO: DONE: <сообщение>` в stdout; процесс завершается с кодом 0
  - Вызывается `AppController.run_consolidation(target_date, on_progress, on_complete, cancel_event)`
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | exit(1) | Bootstrap failed | `RuntimeError` из `Bootstrap.setup` (отсутствует python-calamine) |
  | exit(1) | Неверный формат даты | `datetime.strptime` выбрасывает `ValueError` |
  | exit(1) | Timeout | Превышен `HEADLESS_RUN_TIMEOUT` (по умолч. 600с) |
  | exit(1) | SIGTERM/SIGINT | Сигнал прерывания → `cancel_event.set()` |
  | exit(1) | Необработанное исключение | Любой `Exception` в основном блоке |
- Побочные эффекты:
  - Создаёт/обновляет Master-отчёт (.xlsx)
  - Записывает в лог (logging.basicConfig, INFO level)
  - Вызывает `app_ctl.shutdown()` в finally-блоке
- Тесты: нет прямых тестов headless_run.py; косвенно — `tests/test_phase0_gui_marshaling.py`
- Файл-обработчик: `APP/headless_run.py:63-68`

---

### EP-002: [CLI] Headless-консолидация за все даты
- Фича: F-002
- Тип: cli-command
- Метод: запуск без аргументов
- Путь: `APP/headless_run.py` (без `--date`)
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет (аргумент `--date` отсутствует)
- Response — Success:
  - Лог `INFO: DONE: <сообщение>` в stdout; процесс завершается с кодом 0
  - Вызывается `AppController.run_consolidation_all_dates(on_progress, on_complete, cancel_event)`
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | exit(1) | Bootstrap failed | `RuntimeError` из `Bootstrap.setup` |
  | exit(1) | Timeout | Превышен `HEADLESS_RUN_TIMEOUT` |
  | exit(1) | SIGTERM/SIGINT | Сигнал прерывания |
  | exit(1) | Необработанное исключение | Любой `Exception` |
- Побочные эффекты:
  - Создаёт/обновляет Master-отчёт (.xlsx) со всеми датами
  - Записывает в лог
  - Вызывает `app_ctl.shutdown()` в finally-блоке
- Тесты: нет прямых тестов
- Файл-обработчик: `APP/headless_run.py:69-73`

---

### EP-003: [GUI] Обновить статус сотрудников (Refresh)
- Фича: F-004
- Тип: gui-command
- Метод: кнопка `🔄 Обновить` в sidebar; автотриггер при смене даты (debounce 250мс)
- Путь: sidebar → `GuiMaster.refresh_status()` → `GuiCommands.refresh_status()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `selected_date` (datetime) — из `sidebar.get_date()`
- Response — Success:
  - Таблица сотрудников обновляется: статусы 🟢/🟠/🔴/[ERR]
  - StatsPanel обновляется (ready count, total count, readiness %)
  - `operation_state.end()` освобождает слот
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | toast error | Master-файл занят | `check_master_lock` возвращает False |
  | toast error | Ошибка обновления | `on_refresh_error(message)` — исключение в потоке |
- Побочные эффекты:
  - Сканирует сетевые папки (DiscoveryService)
  - Обновляет discovery_cache в БД
  - Записывает в лог
  - Может сохранять config (rename_detected)
- Тесты: нет прямых; косвенно через `tests/test_operation_state.py`
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:32-59`

---

### EP-004: [GUI] Консолидация за день
- Фича: F-008
- Тип: gui-command
- Метод: кнопка `📊 Консолидировать` в sidebar
- Путь: sidebar → `GuiMaster.run_consolidation()` → `GuiCommands.run_consolidation()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `selected_date` (datetime) — из `sidebar.get_date()`
    - `curator` (str|None) — из `sidebar.get_curator()`
- Response — Success:
  - Toast success "Master-отчет" + диалог "Открыть файл?"
  - `dashboard_tabs.record_result("Master", True, msg, path)`
  - Master-отчёт .xlsx создан
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | messagebox | Не сдано отчетов, отмена | `missing_names` непустой + пользователь нажал "Нет" |
  | toast error | Файл занят в Excel | `_is_report_writable` возвращает False |
  | toast error | Нет данных | `empty_data` код из `_execute_consolidation` |
  | toast warning | Отменено пользователем | `CancelledByUser` маркер в msg |
  | toast error | Ошибка сборки | Любое исключение в потоке |
- Побочные эффекты:
  - Создаёт Master-отчёт .xlsx
  - Записывает session в БД (sessions, source_files, staging_data)
  - Записывает template_errors в БД
  - Создаёт backup существующего .xlsx
  - Записывает в лог
- Тесты: нет прямых GUI-тестов; `tests/test_phase2_logic_service.py` (LogicService)
- Файл-обработчик: `APP/core/ui/gui_commands/_consolidation.py:24-40`

---

### EP-005: [GUI] Консолидация за все даты
- Фича: F-009
- Тип: gui-command
- Метод: кнопка `📊 Все даты` в sidebar
- Путь: sidebar → `GuiMaster.run_consolidation_all_dates()` → `GuiCommands.run_consolidation_all_dates()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `curator` (str|None) — из `sidebar.get_curator()`
- Response — Success:
  - Toast success + диалог "Открыть файл?"
  - Master-отчёт со всеми датами создан
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | messagebox | Не сдано отчетов, отмена | `missing_names` + "Нет" |
  | toast error | Файл занят | `_is_report_writable` False |
  | toast warning | Отменено | `CancelledByUser` |
  | toast error | Ошибка | Исключение в потоке |
- Побочные эффекты:
  - Создаёт Master-отчёт .xlsx (все даты)
  - re-discover сотрудников с диска (`use_fresh_employees=True`)
  - Записывает session/ошибки в БД
  - Backup + лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/gui_commands/_consolidation.py:42-57`

---

### EP-006: [GUI] Консолидация за месяц (период)
- Фича: F-010
- Тип: gui-command
- Метод: кнопка `📅 За период` в sidebar (раздел периода)
- Путь: sidebar → `GuiMaster.run_consolidation_month()` → `GuiCommands.run_consolidation_month()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `start_date` (datetime) — из `sidebar.get_month_range()`
    - `end_date` (datetime) — из `sidebar.get_month_range()`
    - `curator` (str|None)
- Response — Success:
  - Toast success + диалог "Открыть файл?"
  - Master-отчёт за период создан
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | messagebox showerror | Дата начала > даты окончания | `start_date > end_date` |
  | messagebox | Не сдано отчетов, отмена | `missing_names` + "Нет" |
  | toast error | Файл занят | `_is_report_writable` False |
  | toast warning | Отменено | `CancelledByUser` |
  | toast error | Ошибка | Исключение |
- Побочные эффекты:
  - Создаёт Master-отчёт .xlsx (период)
  - Записывает session/ошибки в БД
  - Backup + лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/gui_commands/_consolidation.py:59-83`

---

### EP-007: [GUI] РСЧ-отчёт за день
- Фича: F-011
- Тип: gui-command
- Метод: кнопка `📋 РСЧ` в sidebar
- Путь: sidebar → `GuiMaster.run_rsch_report()` → `GuiCommands.run_rsch_report()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (List[Path]) — из диалога выбора файлов (или сохранённый набор)
    - `output_path` (Path) — из `filedialog.asksaveasfilename`
    - `selected_date` (datetime)
- Response — Success:
  - Toast success "РСЧ" + диалог "Открыть файл?"
  - `dashboard_tabs.record_result("РСЧ", True, msg, path)`
  - РСЧ-отчёт .xlsx создан
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Пользователь отменил выбор файлов | `_resolve_rsch_sources` возвращает [] |
  | return (молча) | Пользователь отменил сохранение | `filedialog.asksaveasfilename` пустой |
  | toast error | Нет строк за дату | `build_rsch_report` возвращает 0 |
  | toast warning | Отменено | `CancelledByUser` |
  | toast error | Ошибка сборки РСЧ | Исключение в `RschService` |
- Побочные эффекты:
  - Создаёт РСЧ-отчёт .xlsx
  - Сохраняет `rsch.recent_sources` и `rsch.last_output_dir` в config.yaml
  - Записывает в лог
- Тесты: нет прямых; `tests/test_phase0_reconciliation_fail_soft.py` (косвенно)
- Файл-обработчик: `APP/core/ui/gui_commands/_rsch.py:26-54`

---

### EP-008: [GUI] РСЧ-отчёт за период
- Фича: F-011
- Тип: gui-command
- Метод: кнопка `📅 РСЧ за период` в sidebar
- Путь: sidebar → `GuiMaster.run_rsch_report_month()` → `GuiCommands.run_rsch_report_month()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (List[Path])
    - `output_path` (Path)
    - `start_date`, `end_date` (datetime)
- Response — Success:
  - Toast success "РСЧ" + диалог "Открыть файл?"
  - РСЧ-отчёт за период (один файл, листы на каждую дату)
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | messagebox showerror | Дата начала > окончания | `start_date > end_date` |
  | return | Отмена выбора файлов | `source_paths` пустой |
  | return | Отмена сохранения | `output` пустой |
  | toast error | Нет строк за период | `build_rsch_report` 0 |
  | toast warning | Отменено | `CancelledByUser` |
  | toast error | Ошибка | Исключение |
- Побочные эффекты:
  - Создаёт РСЧ-отчёт .xlsx (период)
  - Сохраняет preferences в config.yaml
  - Лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/gui_commands/_rsch.py:56-91`

---

### EP-009: [GUI] Сверка (ручная)
- Фича: F-012
- Тип: gui-command
- Метод: кнопка `🔍 Сверка` в sidebar
- Путь: sidebar → `GuiMaster.run_reconciliation_report()` → `GuiCommands.run_reconciliation_report()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `master_paths` (Dict[str, Path]) — 3 файла: "Общий", "Борис", "Иван" (через `filedialog.askopenfilename`)
    - `rsch_path` (Path) — готовый РСЧ-отчёт
    - `output_path` (Path) — куда сохранить отчёт расхождений
    - `selected_date` (datetime)
- Response — Success:
  - Toast success "Сверка" + диалог "Открыть файл?"
  - `dashboard_tabs.record_result("Сверка", True, msg, path)`
  - Отчёт расхождений .xlsx создан (3 листа)
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return | Отмена выбора любого из master-файлов | `filedialog.askopenfilename` пустой |
  | return | Отмена выбора РСЧ-файла | `rsch_path` пустой |
  | return | Отмена сохранения | `output` пустой |
  | toast warning | Отменено | `CancelledByUser` |
  | toast error | Ошибка сверки | Исключение в `ReconciliationService` |
- Побочные эффекты:
  - Создаёт отчёт расхождений .xlsx (3 листа: Общий/Борис/Иван)
  - Записывает в лог
- Тесты: `tests/test_phase0_reconciliation_fail_soft.py` (софт-фейлы сверки)
- Файл-обработчик: `APP/core/ui/gui_commands/_reconciliation.py:29-83`

---

### EP-010: [GUI] Автосверка за день
- Фича: F-013
- Тип: gui-command
- Метод: кнопка `🤖 Автосверка` в sidebar
- Путь: sidebar → `GuiMaster.run_auto_reconciliation_day()` → `GuiCommands.run_auto_reconciliation_day()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (List[Path]) — РСЧ-файлы (через `_resolve_rsch_sources`)
    - `output_path` (Path) — отчёт расхождений
    - `selected_date` (datetime)
- Response — Success:
  - Toast success "Автосверка" + диалог "Открыть файл?"
  - Перестраивает 3 master-отчёта + РСЧ + отчёт расхождений
  - Сообщение: "Автосверка собрана: Общий N, Борис N, Иван N строк. РСЧ: N строк."
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return | Отмена выбора файлов | `source_paths` пустой |
  | return | Отмена сохранения | `output` пустой |
  | toast success (info) | Нет данных РСЧ | `rsch_rows == 0` — автосверка пропущена |
  | toast success (info) | ValueError в сверке | `ValueError` в `build_combined_reconciliation_report` |
  | toast warning | Отменено | `CancelledByUser` на любом checkpoint |
  | toast error | Ошибка автосверки | Любое `Exception` |
  | RuntimeError | Нет данных за дату (общий) | `empty_data` код без curator |
  | RuntimeError | Файл занят | `_is_report_writable` False |
- Побочные эффекты:
  - Создаёт 3 master-отчёта .xlsx (Общий/Борис/Иван)
  - Создаёт РСЧ-отчёт .xlsx
  - Создаёт отчёт расхождений .xlsx (3 листа)
  - Сохраняет rsch preferences в config.yaml
  - Записывает в лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/gui_commands/_reconciliation.py:85-111`

---

### EP-011: [GUI] Добавить сотрудника
- Фича: F-005
- Тип: gui-command
- Метод: кнопка `➕ Добавить` в sidebar
- Путь: sidebar → `GuiMaster.add_employee_dialog()` → `GuiCommands.add_employee_dialog()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `name` (str) — из диалога `ask_employee_name`
- Response — Success:
  - Сотрудник добавлен в employees.yaml
  - `refresh_status()` запускается
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Пустое имя | `name` пустой после trim |
  | return (молча) | Отмена диалога | `ask_employee_name` возвращает None |
- Побочные эффекты:
  - Записывает в employees.yaml (`ConfigController.add_employee`)
  - Инвалидирует discovery_cache
  - Вызывает refresh_status
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:86-93`

---

### EP-012: [GUI] Привязать файлы сотруднику
- Фича: F-005
- Тип: gui-command
- Метод: кнопка `📎 Привязать` в sidebar
- Путь: sidebar → `GuiMaster.attach_file_dialog()` → `GuiCommands.attach_file_dialog()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `name` (str) — выбранное имя сотрудника
    - `paths` (List[str]) — пути к файлам
    - `append` (bool) — режим добавления vs замены
- Response — Success:
  - Файлы привязаны (MD5 + inode + absolute path)
  - `refresh_status()` запускается
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Отмена диалога | `show_attach_file_dialog` отменён |
  | log error | Файл не существует | `Path(fp).exists()` False — пропускается |
  | log error | Ошибка генерации метаданных | `os.stat` / чтение MD5 не удалось |
- Побочные эффекты:
  - Вычисляет MD5-хэш + inode для каждого файла
  - Записывает в employees.yaml
  - Дедупликация путей
  - Инвалидирует discovery_cache
  - Вызывает refresh_status
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:95-108`

---

### EP-013: [GUI] Открыть папку Master-отчёта
- Фича: F-020
- Тип: gui-command
- Метод: кнопка `📂 Папка Master` в EmployeeTable
- Путь: EmployeeTable → `GuiMaster.open_master_folder()` → `GuiCommands.open_master_folder()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет
- Response — Success:
  - Открывается родительская папка Master-отчёта в OS-проводнике (`open_path`)
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Путь не существует | `p.parent.exists()` False |
  | return (молча) | Нет master path | `get_master_path` возвращает None |
- Побочные эффекты: нет (только открытие проводника)
- Тесты: нет
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:110-113`

---

### EP-014: [GUI] Копировать должников в буфер обмена
- Фича: F-020
- Тип: gui-command
- Метод: кнопка `📋 Должники` в EmployeeTable
- Путь: EmployeeTable → `GuiMaster.copy_missing_to_clipboard()` → `GuiCommands.copy_missing_to_clipboard()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет (дата берётся из sidebar)
- Response — Success:
  - Список должников скопирован в буфер обмена
  - Toast info "Должники" "Список скопирован в буфер обмена"
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Нет должников | `missing` пустой список |
- Побочные эффекты:
  - Записывает в системный буфер обмена
- Тесты: нет
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:115-133`

---

### EP-015: [GUI] Фильтр сотрудников (поиск)
- Фича: F-005
- Тип: gui-command
- Метод: поле поиска в EmployeeTable (debounce 300мс)
- Путь: EmployeeTable → `GuiMaster.filter_tree()` → `GuiCommands.filter_tree()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `search_query` (str) — из `employee_table.get_search_query()`
- Response — Success:
  - Таблица фильтруется (case-insensitive по имени/status_text/path_text)
  - StatsPanel обновляется
- Response — Errors: нет (синхронная операция)
- Побочные эффекты: нет
- Тесты: нет
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:135-137`

---

### EP-016: [GUI] Открыть папку сотрудника (контекстное меню)
- Фича: F-020
- Тип: gui-command
- Метод: пункт контекстного меню `📁 Открыть папку` (правый клик по строке)
- Путь: EmployeeTable context menu → `GuiMaster.open_employee_folder()` → `GuiCommands.open_employee_folder()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `name` (str) — выбранный сотрудник
- Response — Success:
  - Открываются уникальные родительские папки всех привязанных файлов
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Нет путей | `paths` пустой |
  | return (молча) | Не выбран сотрудник | `get_selected_employee` None |
- Побочные эффекты: нет
- Тесты: нет
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:139-155`

---

### EP-017: [GUI] Открыть файл сотрудника (контекстное меню / двойной клик)
- Фича: F-020
- Тип: gui-command
- Метод: пункт `📊 Открыть файл` или двойной клик по строке
- Путь: EmployeeTable → `GuiMaster.open_employee_file()` → `GuiCommands.open_employee_file()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `name` (str) — выбранный сотрудник
- Response — Success:
  - Если 1 файл — открывается напрямую
  - Если несколько — диалог `askyesnocancel`: "Да" — открыть все, "Нет" — открыть папки, "Отмена" — ничего
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Нет путей | `paths` пустой |
  | return (молча) | Отмена (None) | `askyesnocancel` → None |
- Побочные эффекты: нет
- Тесты: нет
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:157-182`

---

### EP-018: [GUI] Удалить сотрудника
- Фича: F-005
- Тип: gui-command
- Метод: пункт контекстного меню `❌ Удалить сотрудника`
- Путь: EmployeeTable context menu → `GuiMaster.delete_employee()` → `GuiCommands.delete_employee()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `name` (str) — выбранный сотрудник
- Response — Success:
  - Сотрудник удалён из employees.yaml
  - `refresh_status()` запускается
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Не выбран | `name` None |
  | return (молча) | Отмена подтверждения | `askyesno` → False |
- Побочные эффекты:
  - Удаляет из employees.yaml
  - Инвалидирует discovery_cache
  - Вызывает refresh_status
- Тесты: нет
- Файл-обработчик: `APP/core/ui/gui_commands/_employee.py:184-189`

---

### EP-019: [GUI] Открыть настройки
- Фича: F-033
- Тип: gui-command
- Метод: кнопка `⚙️ Настройки` в sidebar
- Путь: sidebar → `GuiMaster.open_settings()` (через `_open_settings_fallback`)
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет
- Response — Success:
  - Открывается модальный `SettingsDialog`
  - Применяются prefs (theme, scale, density) при Apply/OK
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | log exception | Ошибка применения темы | `ThemeManager.set_theme` исключение |
  | log exception | Ошибка recompute sidebar | `_recompute_width` исключение |
- Побочные эффекты:
  - Сохраняет UI prefs в config.yaml (через SettingsStore)
  - Применяет тему/масштаб к живому GUI
- Тесты: `tests/test_system_theme.py`, `tests/test_theme_manager.py`
- Файл-обработчик: `APP/core/ui/gui_master_settings.py:68-83`

---

### EP-020: [GUI] Сменить тему (light/dark/system)
- Фича: F-033
- Тип: gui-command
- Метод: dropdown темы в sidebar + автополлинг (5с) для "system"
- Путь: sidebar theme_var → `GuiMaster.set_theme(name)`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `name` (str) — "light" | "dark" | "system"
- Response — Success:
  - Тема применена, ttk styles переконфигурированы
  - EmployeeTable и DashboardTabs обновляют тему
  - Toast info "Тема" "Применена тема: <resolved>"
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | fallback to light | Неизвестная тема | `resolved` не в ("light", "dark") |
- Побочные эффекты:
  - Переконфигурирует ttk styles
  - Обновляет bg главного окна
- Тесты: `tests/test_theme_manager.py`, `tests/test_system_theme.py`
- Файл-обработчик: `APP/core/ui/gui_master.py:391-411`

---

### EP-021: [GUI] Запрос отмены операции
- Фича: F-022
- Тип: gui-command
- Метод: кнопка Cancel в OperationStatusBar
- Путь: OperationStatusBar → `GuiMaster._request_cancel()`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет
- Response — Success:
  - `operation_state.request_cancel()` → `cancel_event.set()`
  - Toast info "Отмена" "Операция будет остановлена на ближайшей контрольной точке"
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return (молча) | Нет активной операции | `operation_state.is_busy` False |
  | return (молча) | Запрос отмены не принят | `request_cancel()` False |
- Побочные эффекты:
  - Устанавливает `cancel_event` → воркер проверяет на checkpoint
- Тесты: `tests/test_operation_state.py`, `tests/test_operation_status_bar.py`
- Файл-обработчик: `APP/core/ui/gui_master.py:205-210`

---

### EP-022: [GUI] Добавить алиас заказчика
- Фича: F-014
- Тип: gui-command
- Метод: кнопка `➕ Добавить` в вкладке "Алиасы сверки"
- Путь: AliasesTab → `app_controller.add_customer_alias(master, rsch, notes)`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `master_customer` (str, обязательный) — заказчик куратора
    - `rsch_customer` (str, обязательный) — заказчик РСЧ
    - `notes` (str, опциональный, default="") — заметки
- Response — Success:
  - Алиас добавлен в БД (customer_aliases)
  - Возвращает `alias_id` (int)
  - `AliasesTab.refresh()` обновляет таблицу
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | messagebox showerror | Пустые поля | `master` или `rsch` пустые после trim |
  | messagebox showerror | Алиасы не настроены | `alias_repo is None` → RuntimeError |
  | messagebox showerror | Ошибка БД | Исключение в `add_alias` |
- Побочные эффекты:
  - INSERT в customer_aliases таблицу
  - Инвалидирует кэш алиасов
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/ui_aliases.py:125-126`, `APP/core/app_controller.py:1124-1128`

---

### EP-023: [GUI] Изменить алиас заказчика
- Фича: F-014
- Тип: gui-command
- Метод: кнопка `✏️ Изменить` / двойной клик по строке
- Путь: AliasesTab → `app_controller.update_customer_alias(alias_id, master, rsch, notes)`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `alias_id` (int, обязательный)
    - `master_customer` (str, обязательный)
    - `rsch_customer` (str, обязательный)
    - `notes` (str, опциональный)
- Response — Success:
  - Алиас обновлён в БД
  - `AliasesTab.refresh()` обновляет таблицу
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | messagebox showinfo | Не выбрана строка | `selection` пустой |
  | messagebox showerror | Пустые поля | master/rsch пустые |
  | messagebox showerror | Алиасы не настроены | `alias_repo is None` |
- Побочные эффекты:
  - UPDATE в customer_aliases
  - Инвалидирует кэш
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/ui_aliases.py:128-140`, `APP/core/app_controller.py:1130-1136`

---

### EP-024: [GUI] Удалить алиас заказчика
- Фича: F-014
- Тип: gui-command
- Метод: кнопка `🗑️ Удалить` в AliasesTab
- Путь: AliasesTab → `app_controller.delete_customer_alias(alias_id)`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `alias_id` (int, обязательный)
- Response — Success:
  - Алиас удалён из БД
  - `AliasesTab.refresh()` обновляет таблицу
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | messagebox showinfo | Не выбрана строка | `alias_id` None |
  | messagebox showerror | Алиасы не настроены | `alias_repo is None` |
  | messagebox showerror | Ошибка БД | Исключение в `delete_alias` |
- Побочные эффекты:
  - DELETE из customer_aliases
  - Инвалидирует кэш
- Тесты: нет прямых
- Файл-обработчик: `APP/core/ui/ui_aliases.py:142-156`, `APP/core/app_controller.py:1138-1140`

---

### EP-025: [Internal] AppController.refresh_status
- Фича: F-004
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.refresh_status`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `selected_date` (datetime, обязательный)
    - `on_progress` (Callable[[float], None], обязательный)
    - `on_complete` (Callable[[List[tuple], Dict, bool], None], обязательный)
    - `curator` (str|None, опциональный)
    - `on_error` (Callable[[str], None]|None, опциональный)
- Response — Success:
  - `on_complete(rows, stats, True)` — список кортежей статусов, Dict статистики, флаг успеха
  - `on_progress(float)` — прогресс 0-100
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete([], {}, False) + on_error | Master-файл занят | `check_master_lock` False |
  | on_error(message) | Ошибка в потоке | Исключение в `_run_refresh_status` |
- Побочные эффекты:
  - Запускает фоновый поток (`_start_thread`)
  - Сканирует файлы (DiscoveryService)
  - Обновляет discovery_cache/file_cache в БД
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:698-723`

---

### EP-026: [Internal] AppController.run_consolidation
- Фича: F-008
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_consolidation`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `selected_date` (datetime, обязательный)
    - `on_progress` (Callable[[float], None], обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `curator` (str|None, опциональный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, msg, Path)` — Master-отчёт создан
  - `on_progress(float)` — прогресс 0-100
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, "Файл занят...", None) | Файл занят | `_is_report_writable` False |
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event.is_set()` |
  | on_complete(False, msg, None) | Нет данных | `empty_data` код |
  | on_complete(False, msg, None) | Ошибка | Исключение в `_execute_consolidation` |
- Побочные эффекты:
  - Запускает фоновый поток
  - Создаёт session в БД
  - Читает файлы через IngestionEngine
  - Записывает staging_data в БД
  - Создаёт Master-отчёт .xlsx (MasterWriter)
  - Backup существующего файла
  - Лог
- Тесты: нет прямых; `tests/test_phase2_logic_service.py` (LogicService.consolidate)
- Файл-обработчик: `APP/core/app_controller.py:776-792`

---

### EP-027: [Internal] AppController.run_consolidation_all_dates
- Фича: F-009
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_consolidation_all_dates`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `on_progress` (Callable[[float], None], обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `curator` (str|None, опциональный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, msg, Path)` — Master-отчёт со всеми датами
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, "Файл занят...", None) | Файл занят | `_is_report_writable` False |
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` |
  | on_complete(False, msg, None) | Ошибка | Исключение |
- Побочные эффекты:
  - re-discover сотрудников (`use_fresh_employees=True`)
  - Создаёт Master-отчёт (все даты)
  - Session/ошибки в БД
  - Backup + лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:794-809`

---

### EP-028: [Internal] AppController.run_consolidation_month
- Фича: F-010
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_consolidation_month`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `start_date` (datetime, обязательный)
    - `end_date` (datetime, обязательный)
    - `on_progress` (Callable[[float], None], обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `curator` (str|None, опциональный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, msg, Path)` — Master-отчёт за период
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, "Файл занят...", None) | Файл занят | `_is_report_writable` False |
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` |
  | on_complete(False, msg, None) | Ошибка | Исключение |
- Побочные эффекты:
  - Создаёт Master-отчёт (период)
  - Session/ошибки в БД
  - Backup + лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:811-829`

---

### EP-029: [Internal] AppController.run_rsch_report
- Фича: F-011
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_rsch_report` → `RschService.run_rsch_report`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (Path|Sequence[Path], обязательный)
    - `output_path` (Path, обязательный)
    - `selected_date` (datetime, обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, "РСЧ отчет собран: N строк из M файлов", Path)`
  - Сообщение включает проблемы с листами, если `issues` непустой
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` |
  | on_complete(False, "Ошибка сборки РСЧ: ...", None) | Нет строк | `build_rsch_report` возвращает 0 → ValueError |
  | on_complete(False, "Ошибка сборки РСЧ: ...", None) | Ошибка | Любое `Exception` |
- Побочные эффекты:
  - Запускает фоновый поток
  - Создаёт РСЧ-отчёт .xlsx (`build_rsch_report`)
  - Лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1044-1055`, `APP/core/services/rsch_service.py:35-93`

---

### EP-030: [Internal] AppController.run_rsch_report_period
- Фича: F-011
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_rsch_report_period` → `RschService.run_rsch_report_period`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (Path|Sequence[Path], обязательный)
    - `output_path` (Path, обязательный)
    - `start_date` (datetime, обязательный)
    - `end_date` (datetime, обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, "РСЧ отчет за период собран: N строк из M файлов", Path)`
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` |
  | on_complete(False, "Ошибка сборки РСЧ за период: ...", None) | Нет строк | 0 rows → ValueError |
  | on_complete(False, "Ошибка сборки РСЧ за период: ...", None) | Ошибка | `Exception` |
- Побочные эффекты:
  - Создаёт РСЧ-отчёт .xlsx (период, листы на каждую дату)
  - Лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1057-1069`, `APP/core/services/rsch_service.py:95-150`

---

### EP-031: [Internal] AppController.run_rsch_report_period_batch
- Фича: F-011
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_rsch_report_period_batch` → `RschService.run_rsch_report_period_batch`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (Path|Sequence[Path], обязательный)
    - `output_dir` (Path, обязательный) — директория для отдельных файлов
    - `start_date` (datetime, обязательный)
    - `end_date` (datetime, обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, "РСЧ отчеты за период собраны: N файлов, M строк", output_dir)`
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` на любой итерации |
  | on_complete(False, "Ошибка сборки РСЧ за период: ...", None) | Нет строк за весь период | `files_written == 0` |
  | on_complete(False, msg, None) | Ошибка | `Exception` |
- Побочные эффекты:
  - Создаёт `output_dir` (mkdir parents)
  - Создаёт отдельный .xlsx на каждую дату (`РСЧ_отчет_DD.MM.YYYY.xlsx`)
  - Лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1071-1083`, `APP/core/services/rsch_service.py:152-225`

---

### EP-032: [Internal] AppController.run_rsch_report_batch
- Фича: F-011
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_rsch_report_batch` → `RschService.run_rsch_report_batch`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (Sequence[Path], обязательный)
    - `output_paths` (Sequence[Path], обязательный) — по одному на каждый source
    - `selected_date` (datetime, обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, msg, None)` — отдельные РСЧ-отчёты на каждый source
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` |
  | on_complete(False, msg, None) | Ошибка | `Exception` |
- Побочные эффекты:
  - Создаёт отдельные .xlsx файлы
  - Лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1085-1096`, `APP/core/services/rsch_service.py:227-298`

---

### EP-033: [Internal] AppController.run_reconciliation_report
- Фича: F-012
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_reconciliation_report` → `ReconciliationService.run_reconciliation_report`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `master_paths` (Dict[str, Path], обязательный) — {"Общий": P, "Борис": P, "Иван": P}
    - `rsch_path` (Path, обязательный)
    - `output_path` (Path, обязательный)
    - `selected_date` (datetime, обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, "Отчет расхождений собран: Общий N, Борис N, Иван N строк.", Path)`
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` |
  | on_complete(False, "Ошибка сверки отчетов: ...", None) | Ошибка | `Exception` в `build_combined_reconciliation_report` |
- Побочные эффекты:
  - Запускает фоновый поток
  - Создаёт отчёт расхождений .xlsx (3 листа)
  - Использует алиасы из `alias_repo`
  - Лог
- Тесты: `tests/test_phase0_reconciliation_fail_soft.py`
- Файл-обработчик: `APP/core/app_controller.py:1030-1042`, `APP/core/services/reconciliation_service.py:33-72`

---

### EP-034: [Internal] AppController.run_auto_reconciliation_day
- Фича: F-013
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.run_auto_reconciliation_day`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `source_paths` (Path|Sequence[Path], обязательный) — РСЧ-файлы
    - `output_path` (Path, обязательный)
    - `selected_date` (datetime, обязательный)
    - `on_complete` (Callable[[bool, str, Path|None], None], обязательный)
    - `cancel_event` (threading.Event|None, опциональный)
- Response — Success:
  - `on_complete(True, "Автосверка собрана: Общий N, Борис N, Иван N строк. РСЧ: M строк.", Path)`
  - Перестраивает 3 master-отчёта + РСЧ + отчёт расхождений
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | on_complete(False, CancelledByUser, None) | Отмена | `cancel_event` на checkpoint |
  | on_complete(True, "Нет данных РСЧ...", None) | Нет РСЧ-данных | `rsch_rows == 0` (success, пропущена) |
  | on_complete(True, "Сверка: ValueError...", None) | ValueError в сверке | `ValueError` (success с сообщением) |
  | on_complete(False, "Ошибка автосверки: ...", None) | Ошибка | `Exception` |
  | RuntimeError (в потоке) | Нет данных (общий, без curator) | `empty_data` + curator None |
  | RuntimeError (в потоке) | Файл занят | `_is_report_writable` False |
  | RuntimeError (в потоке) | Не настроен curator | `_get_curator_config` None |
- Побочные эффекты:
  - Запускает фоновый поток
  - Создаёт 3 master-отчёта .xlsx (через `_run_consolidation_blocking`)
  - При empty_data + curator: создаёт пустой отчёт (`write_empty_daily_report`)
  - Создаёт РСЧ-отчёт .xlsx (`РСЧ_отчет_DD.MM.YYYY.xlsx` в parent output)
  - Создаёт отчёт расхождений .xlsx (3 листа)
  - Лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:923-1028`

---

### EP-035: [Internal] AppController.shutdown
- Фича: F-001
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.shutdown`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет
- Response — Success:
  - Лог "Завершение: ожидаю завершения записей в БД..."
  - `persistence.wait_for_writes()` — ожидание завершения DB-записей
  - `executor.shutdown(wait=True)` — остановка пула потоков
  - Join активных потоков (timeout 10s)
  - `persistence.close()` — закрытие БД
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | лог warning | WAL checkpoint failed | Исключение в `close()` (non-fatal) |
  | лог warning | unclean flag not removed | `unlink` не удался |
- Побочные эффекты:
  - Закрывает БД (WAL checkpoint TRUNCATE)
  - Останавливает ThreadPoolExecutor
  - Join потоков
  - Удаляет `.unclean` flag файл
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1098-1114`

---

### EP-036: [Internal] AppController.get_customer_aliases
- Фича: F-014
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.get_customer_aliases`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет
- Response — Success:
  - Возвращает `List[CustomerAlias]` — все алиасы из БД
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return [] | Алиасы не настроены | `alias_repo is None` |
- Побочные эффекты: читает из БД (кэш в memory)
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1118-1122`

---

### EP-037: [Internal] AppController.add_customer_alias
- Фича: F-014
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.add_customer_alias`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `master_customer` (str, обязательный)
    - `rsch_customer` (str, обязательный)
    - `notes` (str, опциональный, default="")
- Response — Success:
  - Возвращает `int` — новый alias_id
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | RuntimeError | Алиасы не настроены | `alias_repo is None` |
- Побочные эффекты:
  - INSERT в customer_aliases
  - Инвалидирует кэш алиасов
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1124-1128`

---

### EP-038: [Internal] AppController.update_customer_alias
- Фича: F-014
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.update_customer_alias`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `alias_id` (int, обязательный)
    - `master_customer` (str, обязательный)
    - `rsch_customer` (str, обязательный)
    - `notes` (str, опциональный, default="")
- Response — Success:
  - Возвращает None (UPDATE выполнен)
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | RuntimeError | Алиасы не настроены | `alias_repo is None` |
- Побочные эффекты:
  - UPDATE в customer_aliases
  - Инвалидирует кэш
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1130-1136`

---

### EP-039: [Internal] AppController.delete_customer_alias
- Фича: F-014
- Тип: internal-service
- Метод: функция
- Путь: `core.app_controller.AppController.delete_customer_alias`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `alias_id` (int, обязательный)
- Response — Success:
  - Возвращает None (DELETE выполнен)
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | RuntimeError | Алиасы не настроены | `alias_repo is None` |
- Побочные эффекты:
  - DELETE из customer_aliases
  - Инвалидирует кэш
- Тесты: нет прямых
- Файл-обработчик: `APP/core/app_controller.py:1138-1140`

---

### EP-040: [Internal] LogicService.apply_financial_rules
- Фича: F-015
- Тип: internal-service
- Метод: функция
- Путь: `core.domain.logic_service.LogicService.apply_financial_rules`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `raw_rows` (List[Dict[str, Any]], обязательный) — сырые строки из ingestion
    - `curator` (str|None, опциональный) — куратор для strategy
    - `curator_config` (Dict|None, опциональный) — конфиг куратора
- Response — Success:
  - Возвращает `List[Dict[str, Any]]` — обработанные строки с комиссиями, приход/расход, флагами
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | is_critical row | NumericParsingError в amount | Критическая ошибка парсинга → строка с is_critical=True |
  | is_critical row | NumericParsingError в total | Критическая ошибка → строка с is_critical=True |
  | Decimal("0.00") | ValueError в amount | Некритичная ошибка → ноль |
  | is_warn=True | Transit parse error | Некритичная → предупреждение, строка сохранена |
  | drop row | Пустая строка (amt=0, tot=0, no broker, no transit) | Строка пропускается |
- Побочные эффекты:
  - Лог DATA INTEGRITY ERROR при критических ошибках
  - Лог warning при некритичных
- Тесты: `tests/test_phase2_logic_service.py` (18 тестов)
- Файл-обработчик: `APP/core/domain/logic_service.py:379-501`

---

### EP-041: [Internal] LogicService.consolidate
- Фича: F-015
- Тип: internal-service
- Метод: функция
- Путь: `core.domain.logic_service.LogicService.consolidate`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `session_id` (str, обязательный) — ID сессии в БД
    - `curator` (str|None, опциональный)
    - `curator_config` (Dict|None, опциональный)
- Response — Success:
  - Возвращает `List[Dict[str, Any]]` — консолидированные строки после `apply_financial_rules`
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | наследует от apply_financial_rules | Ошибки парсинга | См. EP-040 |
- Побочные эффекты:
  - Читает `persistence.get_consolidated_data(session_id)` из БД
  - Делегирует в `apply_financial_rules`
- Тесты: `tests/test_phase2_logic_service.py`
- Файл-обработчик: `APP/core/domain/logic_service.py:503-515`

---

### EP-042: [Internal] IngestionEngine.get_available_dates
- Фича: F-029
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.ingestion_engine.IngestionEngine.get_available_dates`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `file_path` (Path, обязательный)
    - `remote_mtime` (float|None, опциональный)
    - `remote_size` (int|None, опциональный)
    - `strict_io` (bool, опциональный, default=False)
- Response — Success:
  - Возвращает `List[str]` — отсортированный список дат (DD.MM.YYYY) из имён листов
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return [] | Ошибка чтения (non-strict) | Исключение + `strict_io=False` |
  | raise | Ошибка чтения (strict) | Исключение + `strict_io=True` |
  | raise RuntimeError | Calamine worker error | `payload.ok` False (изолированный режим) |
- Побочные эффекты:
  - Создаёт локальную копию файла (`get_local_copy`) для сетевых путей
  - Удаляет temp-файл после чтения
  - Может запускать subprocess (`_run_calamine_worker`) для изоляции
- Тесты: `tests/test_phase2_ingestion_reader.py`
- Файл-обработчик: `APP/core/infra/ingestion_engine.py:293-344`

---

### EP-043: [Internal] IngestionEngine.read_file
- Фича: F-029
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.ingestion_engine.IngestionEngine.read_file`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `file_path` (Path, обязательный)
    - `strict_io` (bool, опциональный, default=False)
    - `target_date_str` (str|None, опциональный) — фильтр по дате
    - `start_date_str` (str|None, опциональный)
    - `end_date_str` (str|None, опциональный)
- Response — Success:
  - Возвращает `List[Dict[str, Any]]` — строки из Excel-файла
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return [] | Файл не найден (non-strict) | `file_path.exists()` False + `strict_io=False` |
  | raise FileNotFoundError | Файл не найден (strict) | `strict_io=True` |
  | raise RuntimeError | Calamine worker error | `payload.ok` False |
  | retry (3 попытки) | Транзиентная сетевая ошибка | `Exception` + retry с backoff |
- Побочные эффекты:
  - Создаёт локальную копию (для изоляции)
  - Запускает subprocess для изолированного calamine
  - Удаляет temp-файлы
- Тесты: `tests/test_phase2_ingestion_reader.py`
- Файл-обработчик: `APP/core/infra/ingestion_engine.py:390-464`

---

### EP-044: [Internal] IngestionEngine.scan_directory
- Фича: F-029
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.ingestion_engine.IngestionEngine.scan_directory`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `root_path` (Path, обязательный) — корневая папка для сканирования
- Response — Success:
  - Возвращает `List[Dict[str, Any]]` — список файлов с {path, id, fp, size, mtime}
  - Рекурсивное сканирование, пропускает `~$`-файлы и не-.xlsx/.xlsb
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return [] | Папка не найдена | `root_path.exists()` False |
  | log error (продолжает) | Ошибка сканирования файла | `Exception` на отдельном файле |
  | log error (продолжает) | Ошибка сканирования директории | `Exception` на scandir |
- Побочные эффекты:
  - Лог `[SCAN] Сканирую папку: ...`
  - Не вычисляет MD5 (пропускает для скорости)
- Тесты: нет прямых
- Файл-обработчик: `APP/core/infra/ingestion_engine.py:346-388`

---

### EP-045: [Internal] DiscoveryService.get_employees_map
- Фича: F-005
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.discovery_service.DiscoveryService.get_employees_map`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `allow_network_scan` (bool, опциональный, default=True) — разрешить сетевое сканирование
- Response — Success:
  - Возвращает `Dict[str, List[Dict[str, Any]]]` — сотрудник → список файлов с метаданными
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | rename_detected=True | Файл переименован | inode совпадает, путь изменился |
- Побочные эффекты:
  - Сканирует сетевые папки (`scan_directory`)
  - Загружает/сохраняет discovery_cache в БД
  - Обновляет `last_discovered_count`
  - Может сохранять config (rename_detected)
- Тесты: нет прямых
- Файл-обработчик: `APP/core/infra/discovery_service.py:381-421`

---

### EP-046: [Internal] MasterWriter.write_report
- Фича: F-016
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.export_writer.MasterWriter.write_report`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `data` (List[Dict[str, Any]], обязательный) — консолидированные строки
    - `path` (Path, обязательный) — путь к Master-отчёту
    - `template_errors` (List[Dict]|None, опциональный)
    - `curator` (str|None, опциональный)
    - `curator_config` (Dict|None, опциональный)
- Response — Success:
  - Возвращает `True` — файл записан
  - Группирует строки по датам, создаёт лист на каждую дату
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return False | Файл занят | `is_file_writable` False |
  | log warning + skip | Строка без даты | `r.get("Дата")` None/пустой |
  | log warning + skip | None строка | `r is None` |
- Побочные эффекты:
  - Создаёт/перезаписывает .xlsx файл
  - Backup существующего файла (`backup_existing_excel_output`)
  - Применяет стили, формулы, гиперссылки
  - Excel formula injection protection (`_safe_text`)
  - Лог
- Тесты: `tests/test_phase1_export_decimal.py`, `tests/test_export_writer_edge_cases.py`, `tests/test_phase0_workbook_release.py`
- Файл-обработчик: `APP/core/infra/export_writer.py:541-584`

---

### EP-047: [Internal] MasterWriter.write_daily_data
- Фича: F-016
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.export_writer.MasterWriter.write_daily_data`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `date` (datetime, обязательный)
    - `rows` (List[Dict], обязательный)
    - `wb` (openpyxl.Workbook|None, опциональный) — существующий workbook
    - `sh_name_override` (str|None, опциональный)
    - `curator` (str|None, опциональный)
    - `headers` (List[str]|None, опциональный)
- Response — Success:
  - Создаёт лист с именем `date.strftime("%d.%m.%Y")` (или override)
  - Добавляет заголовки, данные, стили, total row
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | log error | Не удалось сохранить | `_save_workbook` False |
- Побочные эффекты:
  - Создаёт/удаляет лист в workbook
  - Применяет стили, freeze_panes, auto-adjust
  - Закрывает workbook если owns (finally)
- Тесты: `tests/test_phase1_export_decimal.py`
- Файл-обработчик: `APP/core/infra/export_writer.py:455-508`

---

### EP-048: [Internal] MasterWriter.write_empty_daily_report
- Фича: F-013
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.export_writer.MasterWriter.write_empty_daily_report`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `path` (Path, обязательный)
    - `date` (datetime, обязательный)
    - `curator` (str|None, опциональный)
    - `curator_config` (Dict|None, опциональный)
- Response — Success:
  - Возвращает `True` — пустой отчёт записан (только заголовки + total)
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return False | Не удалось создать workbook | `_get_workbook` None |
  | return False | Не удалось сохранить | `_save_workbook` False |
- Побочные эффекты:
  - Создаёт .xlsx с пустыми данными (заголовки + total row)
  - Закрывает workbook в finally
- Тесты: нет прямых
- Файл-обработчик: `APP/core/infra/export_writer.py:510-539`

---

### EP-049: [Internal] ConfigController.load_config
- Фича: F-003
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.config_controller.ConfigController.load_config`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет (использует `self.config_path`)
- Response — Success:
  - Возвращает `Dict[str, Any]` — загруженный config
  - При отсутствии config.yaml: создаёт из config.example.yaml + chmod 0o600
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | return {} | Ошибка загрузки | `Exception` при чтении |
  | return {} | Файл не найден и нет example | `config.example.yaml` не существует |
  | log warning | chmod failed | `OSError` при chmod |
- Побочные эффекты:
  - Создаёт config.yaml из config.example.yaml при отсутствии
  - chmod 0o600 на config.yaml
  - Лог
- Тесты: нет прямых
- Файл-обработчик: `APP/core/infra/config_controller.py:52-89`

---

### EP-050: [Internal] ConfigController.save_config
- Фича: F-003
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.config_controller.ConfigController.save_config`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры: нет (сохраняет `self.config`)
- Response — Success:
  - Записывает config в YAML (ruamel.yaml, preserve comments)
  - chmod 0o600
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | log error | Ошибка сохранения | `Exception` при записи |
  | log warning | chmod failed | `OSError` |
- Побочные эффекты:
  - Перезаписывает config.yaml
  - chmod 0o600
- Тесты: нет прямых
- Файл-обработчик: `APP/core/infra/config_controller.py:91-106`

---

### EP-051: [Internal] ConfigController.resolve_path
- Фича: F-003
- Тип: internal-service
- Метод: функция
- Путь: `core.infra.config_controller.ConfigController.resolve_path`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `path_str` (str, обязательный) — относительный или абсолютный путь
- Response — Success:
  - Возвращает `Path` — разрешённый абсолютный путь
  - Относительные пути → относительно config_dir
  - Абсолютные/UNC/drive-letter → проверяются через allowlist roots
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | raise ValueError | Path traversal | Путь вне allowlist roots (configured source_roots + config_dir + project_root) |
  | raise ValueError | Invalid path | `Path.resolve()` выбрасывает OSError/ValueError |
- Побочные эффекты: нет
- Тесты: нет прямых
- Файл-обработчик: `APP/core/infra/config_controller.py:169-205`

---

### EP-052: [Internal] SessionRepository (методы persistence)
- Фича: F-023
- Тип: internal-service
- Метод: функции (множественные)
- Путь: `core.infra.session_repo.SessionRepository.*`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры (по методу):
    - `save_session(session_id: str, metadata: Dict)` — INSERT в sessions
    - `save_template_error(session_id: str, error_info: Dict)` — INSERT в template_errors
    - `save_template_errors_batch(session_id: str, errors: List[Dict])` — batch INSERT
    - `get_template_errors(session_id: str) -> List[Dict]` — SELECT из template_errors
    - `get_session_status(session_id: str) -> Dict` — SELECT session + file stats
    - `update_session_status(session_id: str, status: str)` — UPDATE sessions
    - `update_file_status(file_id: int, status: str, error_message: str|None)` — UPDATE source_files
    - `save_file_metadata(session_id: str, files: List[Dict]) -> List[int]` — делегирует SourceFileRepository
    - `save_staging_data(file_id: int, rows: List[Dict])` — делегирует StagingDataRepository
    - `get_consolidated_data(session_id: str) -> List[Dict]` — SELECT staging_data
    - `wait_for_writes()` — ожидание завершения DB-потока
    - `close()` — WAL checkpoint + закрытие
    - `get_file_cache(file_path: str) -> Dict|None` — кэш дат файла
    - `save_file_cache(file_path, mtime, size, dates, fingerprint)` — сохранение кэша
    - `get_row_cache(file_path, mtime, size, date_key) -> List[Dict]|None` — кэш строк
    - `save_row_cache(file_path, mtime, size, date_key, rows)` — сохранение кэша строк
    - `get_discovery_cache(roots_key: str) -> List[Dict]|None` — кэш discovery
    - `save_discovery_cache(roots_key: str, files: List[Dict])` — сохранение discovery
- Response — Success:
  - Методы чтения возвращают данные; методы записи возвращают None/IDs
  - `save_file_metadata` возвращает `List[int]` — ID файлов
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | rollback + raise | Ошибка транзакции | `Exception` в BEGIN IMMEDIATE |
  | retry (execute_with_retry) | Транзиентная ошибка БД | SQLite busy/locked |
  | log warning (non-fatal) | WAL checkpoint failed | `Exception` в `close()` |
- Побочные эффекты:
  - INSERT/UPDATE/SELECT в SQLite
  - WAL checkpoint при close
  - Удаляет `.unclean` flag
  - Асинхронная запись через DBWriterThread (write_queue)
- Тесты: `tests/test_phase2_db_repositories.py` (9 тестов), `tests/test_phase3_reliability.py`
- Файл-обработчик: `APP/core/infra/session_repo.py:50-288`

---

### EP-053: [Event-bus] EventBus.publish / subscribe / poll [DEPRECATED — dead code]
- Фича: N/A (не связана с активной фичей)
- Тип: event-bus
- Метод: методы класса
- Путь: `core.infra.event_bus.EventBus.publish` / `subscribe` / `poll`
- Аутентификация: N/A (desktop)
- Авторизация: N/A (desktop)
- Request:
  - Входные параметры:
    - `publish(event: Event)` — `Event(type: EventType, data: Any)`
    - `subscribe(event_type: EventType, callback: Callable[[Event], None])`
    - `unsubscribe(event_type: EventType, callback)`
    - `poll()` — drain queue (вызывается из GUI-потока)
- Response — Success:
  - `publish` — кладёт Event в queue
  - `subscribe` — добавляет callback в listeners
  - `poll` — вызывает все callbacks для каждого event из queue
- Response — Errors:
  | Статус | Причина | Условие |
  |--------|--------|---------|
  | log warning | Callback error | `Exception` в callback (не прерывает poll) |
- Побочные эффекты:
  - Singleton (`EventBus.get()`) — process-wide
  - Thread-safe (queue + lock)
- Тесты: `tests/test_phase3_reliability.py` (3 теста: singleton, race-safe, reset)
- Файл-обработчик: `APP/core/infra/event_bus.py:62-90`
- **Примечание**: [DEPRECATED] Модуль `event_bus.py` существует, но НЕ импортируется ни одним модулем в `APP/` (подтверждено grep). События `EventType.PROGRESS_UPDATED`, `OPERATION_STARTED`, `OPERATION_FINISHED`, `ERROR_OCCURRED`, `TITLE_REFRESH` определены, но ни один модуль не публикует их. Фактическая коммуникация между потоками осуществляется через `root.after(0, ...)` и `OperationState.add_listener`. Замена: `OperationState` + `root.after()` marshalling. Тесты существуют, но тестируют только инфраструктуру самого EventBus, а не интеграцию.

---

## Критерий завершения

- [x] Все CLI-команды задокументированы (EP-001, EP-002)
- [x] Все GUI-команды задокументированы (EP-003 — EP-024)
- [x] Все публичные методы ключевых сервисов задокументированы (EP-025 — EP-052)
- [x] Каждый интерфейс имеет все возможные responses (success + errors)
- [x] Побочные эффекты перечислены
- [x] Тесты отмечены (есть/нет, с путями)
