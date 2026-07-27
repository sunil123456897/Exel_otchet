# Инвентарь фич

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Источник: docs/map/structure.md + docs/map/architecture.md + features.json + анализ кода

## Сводка
- Всего фич: 42
- Core: 23
- Secondary: 13
- Auxiliary: 4
- Deprecated: 2

## Инвентарь

### F-001: Запуск приложения (GUI)
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь запускает приложение через ЗАПУСК.bat или `APP/main.py`. Настройка DPI-awareness для HiDPI-дисплеев, инициализация RotatingFileHandler-логгера (startup_log.txt, 10MB×5), вызов Bootstrap.setup() для сборки всех зависимостей, создание главного окна Tkinter (GuiMaster), обработка ошибок запуска через messagebox, graceful shutdown при закрытии окна.
- Точки входа в коде: APP/main.py, APP/core/bootstrap.py, APP/core/ui/gui_master.py
- Зависит от: F-003, F-022, F-023, F-033
- Блокирует: F-002, F-006, F-007, F-008, F-009, F-010, F-011, F-012, F-013, F-014, F-015, F-016, F-025
- Бизнес-правила:
  - Проверка обязательной зависимости python-calamine; при отсутствии — RuntimeError + messagebox + sys.exit(1)
  - DPI-awareness: SetProcessDpiAwareness(2) (per-monitor v2), fallback на SetProcessDPIAware()
  - Bootstrap._integrity_warning показывается через messagebox после создания Tk root
  - shutdown() вызывается при WM_DELETE_WINDOW: persistence.wait_for_writes(), executor.shutdown, join потоков (timeout 10s), persistence.close()
- Известные проблемы: нет
- Файлов затронуто: 3

### F-002: Headless-режим (CLI)
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: CI/CD или оператор запускает консолидацию без GUI через `APP/headless_run.py`. Поддержка флага `--date DD.MM.YYYY` (консолидация за конкретную дату) или без аргумента (все даты). Signal handling (SIGTERM/SIGINT → cancel_event), timeout через env HEADLESS_RUN_TIMEOUT (по умолч. 600с), graceful shutdown в finally-блоке.
- Точки входа в коде: APP/headless_run.py, APP/core/bootstrap.py, APP/core/app_controller.py
- Зависит от: F-003, F-022, F-023, F-008, F-009, F-033
- Блокирует: (нет — используется CI/CD)
- Бизнес-правила:
  - Формат даты: DD.MM.YYYY, парсинг через datetime.strptime, при ошибке — CRITICAL log + exit(1)
  - Timeout: env HEADLESS_RUN_TIMEOUT, по умолч. 600с; при превышении — cancel_event.set() + exit(1)
  - SIGTERM/SIGINT → cancel_event.set() + sys.exit(1)
- Известные проблемы: нет
- Файлов затронуто: 3

### F-003: Управление конфигурацией
- Категория: core
- Статус: implemented
- User-facing: no
- Описание: Загрузка, валидация и сохранение config.yaml через ruamel.yaml (с сохранением комментариев). Pydantic-валидация секций paths/database/locking/network. Path traversal protection. При отсутствии config.yaml — создание из config.example.yaml. Сохранение с ограничением прав 0o600.
- Точки входа в коде: APP/core/infra/config_controller.py, APP/core/bootstrap.py
- Зависит от: F-030
- Блокирует: F-001, F-002, F-008, F-011, F-012, F-022, F-029
- Бизнес-правила:
  - config.yaml загружается через ruamel.yaml; при отсутствии — копия из config.example.yaml
  - Pydantic-валидация: PathsConfig, DatabaseConfig, LockingConfig, NetworkConfig с safe defaults
  - При невалидной секции — warning + safe defaults (не блокирует запуск)
  - chmod 0o600 на config.yaml и employees.yaml
  - resolve_path: относительные пути → абсолютные относительно config_dir
  - Allowlist roots: configured source_roots + config_dir + project_root
  - Absolute/UNC/drive-letter пути проверяются через allowlist
- Известные проблемы: config_missing.yaml — дубликат config.example.yaml, точное назначение неясно
- Файлов затронуто: 2

### F-004: Обновление статуса сотрудников (Refresh)
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь нажимает «🔄 Обновить статус» (или меняет дату — срабатывает debounce 250мс). Приложение сканирует сетевые папки, находит файлы сотрудников, проверяет наличие отчёта за выбранную дату в каждом файле (через кэш discovery + file_cache), и отображает статус: 🟢 ГОТОВО / 🟠 НЕТ ДАТЫ / 🔴 НЕТ ФАЙЛА / [ERR] ОШИБКА. Многопоточная проверка (ThreadPoolExecutor), timeout 30s на зависшие сетевые запросы.
- Точки входа в коде: APP/core/app_controller.py, APP/core/ui/gui_commands/_employee.py, APP/core/view_models/employee_list_viewmodel.py, APP/core/infra/discovery_service.py, APP/core/app/file_processor.py, APP/core/ui/ui_stats_panel.py
- Зависит от: F-003, F-005, F-023, F-029, F-024
- Блокирует: F-008, F-009, F-010, F-011, F-012, F-020
- Бизнес-правила:
  - Проверка master lock перед обновлением; если занят — toast error, пустой результат
  - Статус «🟢 ГОТОВО»: файл существует + содержит лист за выбранную дату
  - Статус «🟠 НЕТ ДАТЫ»: файл существует, но лист за дату не найден
  - Статус «🔴 НЕТ ФАЙЛА»: файл не существует по привязанному пути
  - target_date > today → всегда «НЕТ ДАТЫ» (нельзя собрать отчёт за будущее)
  - file_cache: mtime + size совпадают → cache hit; иначе — повторное чтение дат
  - Timeout 30s на as_completed; незавершённые futures cancel(), partial result показывается
  - rename_detected: если файл переименован, сохраняется обновлённый config
- Известные проблемы: нет
- Файлов затронуто: 5

### F-005: Управление сотрудниками
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь добавляет, удаляет сотрудников и привязывает к ним Excel-файлы. Сотрудники хранятся в employees.yaml. При привязке файлов вычисляется MD5-хэш и inode для smart tracking. Поиск/фильтр сотрудников по имени в таблице.
- Точки входа в коде: APP/core/infra/config_controller.py, APP/core/ui/gui_commands/_employee.py, APP/core/view_models/employee_list_viewmodel.py, APP/core/ui/ui_employee_table.py, APP/core/ui/ui_dialogs.py
- Зависит от: F-003
- Блокирует: F-004, F-008, F-009, F-010, F-011, F-012, F-020, F-021
- Бизнес-правила:
  - add_employee: имя trim, пустое имя игнорируется, дубликаты не проверяются на уровне config
  - delete_employee: удаление по точному имени + инвалидация discovery_cache
  - attach_files: вычисление MD5 + inode + absolute path; append vs replace режимы
  - Дедупликация путей при attach (по строковому представлению пути)
  - Поиск: case-insensitive, совпадение по имени/status_text/path_text
- Известные проблемы: нет
- Файлов затронуто: 5

### F-006: Выбор даты
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь выбирает дату через DateEntry (tkcalendar) в sidebar. Изменение даты с debounce 250мс запускает refresh статусов. Выбор периода (начало/конец) для месячных отчётов. Автовыбор периода: если сегодня 1-е число — предыдущий месяц, иначе — с 1-го числа текущего месяца до сегодня.
- Точки входа в коде: APP/core/ui/ui_sidebar.py, APP/core/ui/debounce.py
- Зависит от: F-001
- Блокирует: F-004, F-008, F-009, F-010, F-013, F-014, F-015, F-016
- Бизнес-правила:
  - Формат даты: dd.mm.yyyy, locale ru_RU
  - Debounce 250мс на изменение даты (предотвращает множественные refresh при кликах)
  - Период по умолчанию: 1-е число → последний день предыдущего месяца; иначе — 1-е число месяца до сегодня
  - Валидация периода: start_date > end_date → ошибка
- Известные проблемы: нет
- Файлов затронуто: 2

### F-007: Выбор куратора
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь выбирает куратора через Combobox в sidebar: «Общий отчет», «Куратор Борис», «Куратор Иван». Выбор определяет фильтрацию сотрудников и путь выходного отчёта при консолидации.
- Точки входа в коде: APP/core/ui/ui_sidebar.py, APP/core/app_controller.py
- Зависит от: F-001, F-003
- Блокирует: F-008, F-009, F-010, F-011, F-012
- Бизнес-правила:
  - Куратор «Общий» → curator=None, все сотрудники (минус excluded_keys)
  - Куратор «Борис» → curator="boris", фильтр по employees_key в имени сотрудника
  - Куратор «Иван» → curator="ivan", фильтр по employees_key в имени сотрудника
  - Фильтрация: case-insensitive, substring match (key in lowered_name)
- Известные проблемы: нет
- Файлов затронуто: 2

### F-008: Консолидация дневного отчёта
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь нажимает «⚡ СОБРАТЬ ДЕНЬ». Приложение собирает мастер-отчёт за выбранную дату: обнаружение файлов, многопоточное чтение Excel (Calamine), валидация строк, применение финансовых правил, агрегация в SQLite, запись в Excel через openpyxl. Прогресс-бар, возможность отмены. Предупреждение о должниках перед запуском.
- Точки входа в коде: APP/core/app_controller.py, APP/core/ui/gui_commands/_consolidation.py, APP/core/view_models/consolidation_viewmodel.py, APP/core/app/file_processor.py, APP/core/app/message_formatting.py, APP/core/domain/logic_service.py, APP/core/infra/export_writer.py
- Зависит от: F-003, F-004, F-005, F-006, F-007, F-023, F-024, F-031
- Блокирует: F-015, F-016
- Бизнес-правила:
  - Проверка writable отчёта перед запуском; если занят — error toast
  - Предупреждение: «Не сдано отчетов: N. Продолжить?» — messagebox.askyesno
  - Session: UUID, meta {type:"daily", date:target}, статус в БД (running/completed/failed/cancelled)
  - Фильтрация сотрудников по куратору
  - run_engine: многопоточное чтение, валидация, staging в БД
  - logic_service.consolidate: применение финансовых правил (F-017)
  - writer.write_report: запись в Excel с стилями, гиперссылками, backup
  - Пустой consolidated_data → статус failed, сообщение «Нет данных за дату»
  - Template errors и file errors попадают в сообщение о завершении
  - Статус completed_with_warnings если есть actionable warnings или runtime warnings
- Известные проблемы: нет
- Файлов затронуто: 6

### F-009: Консолидация за все даты
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь нажимает «🌍 СОБРАТЬ ВСЕ ДАТЫ». Приложение собирает мастер-отчёт по всем доступным датам из всех файлов сотрудников (без фильтра по дате). Поведное discovery сотрудников (use_fresh_employees=True). Та же логика, что F-008, но session_type="all_dates".
- Точки входа в коде: APP/core/app_controller.py, APP/core/ui/gui_commands/_consolidation.py, APP/core/view_models/consolidation_viewmodel.py
- Зависит от: F-003, F-004, F-005, F-007, F-023, F-024, F-031
- Блокирует: (нет)
- Бизнес-правила:
  - use_fresh_employees=True — повторное обнаружение файлов с диска
  - target_date_str=None, start_date_str=None, end_date_str=None
  - session_type="all_dates"
  - Те же проверки writable, предупреждение о должниках, отмена
- Известные проблемы: нет
- Файлов затронуто: 3

### F-010: Консолидация за период (месяц)
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь выбирает период (start_date, end_date) и нажимает «СОБРАТЬ ЗА ПЕРИОД». Приложение собирает мастер-отчёт за диапазон дат. Валидация: start ≤ end. session_type="monthly".
- Точки входа в коде: APP/core/app_controller.py, APP/core/ui/gui_commands/_consolidation.py, APP/core/view_models/consolidation_viewmodel.py
- Зависит от: F-003, F-004, F-005, F-006, F-007, F-023, F-024, F-031
- Блокирует: (нет)
- Бизнес-правила:
  - Валидация: start_date > end_date → messagebox.showerror, отмена
  - session_type="monthly", start_date_str и end_date_str в формате DD.MM.YYYY
  - Те же проверки writable, предупреждение о должниках, отмена
- Известные проблемы: нет
- Файлов затронуто: 3

### F-011: Кураторский отчёт — Борис
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь выбирает «Куратор Борис» и запускает консолидацию. Формируется отдельный отчёт Бориса с фильтрацией сотрудников по employees_key и применением BorisCuratorStrategy (сохранение intermediary2 значений из исходного отчёта). Выходной путь берётся из config.curators.boris.output_path.
- Точки входа в коде: APP/core/app_controller.py, APP/core/domain/logic_service.py, APP/core/infra/export_writer.py
- Зависит от: F-003, F-007, F-008, F-017
- Блокирует: F-015, F-016
- Бизнес-правила:
  - curator="boris", curator_config из config.curators.boris
  - Фильтр сотрудников: employees_key (substring match, case-insensitive)
  - BorisCuratorStrategy: при raw_b2 != 0 → pb2_val = abs(to_decimal_percent(pb2_raw)), broker2_calc = abs(raw_b2)
  - output_path из curator_config.output_path
  - Проверка writable отчёта куратора
  - Если enabled=False в config → curator_config=None, отчёт не формируется
- Известные проблемы: нет
- Файлов затронуто: 3

### F-012: Кураторский отчёт — Иван
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь выбирает «Куратор Иван» и запускает консолидацию. Формируется отдельный отчёт Ивана с фильтрацией сотрудников и применением IvanCuratorStrategy (intermediary значения не сохраняются — только базовая стратегия). Выходной путь из config.curators.ivan.output_path.
- Точки входа в коде: APP/core/app_controller.py, APP/core/domain/logic_service.py, APP/core/infra/export_writer.py
- Зависит от: F-003, F-007, F-008, F-017
- Блокирует: F-015, F-016
- Бизнес-правила:
  - curator="ivan", curator_config из config.curators.ivan
  - IvanCuratorStrategy: pb2_val=0, broker2_calc=0 (intermediary не сохраняется)
  - Фильтр сотрудников: employees_key (substring match, case-insensitive)
  - output_path из curator_config.output_path
  - Если enabled=False → curator_config=None
- Известные проблемы: нет
- Файлов затронуто: 3

### F-013: Сборка РСЧ-отчёта (день)
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь нажимает «🧾 СОБРАТЬ РСЧ». Выбирает исходные файлы РСЧ (с сохранением recent_sources в config), выбирает выходной путь. Приложение собирает РСЧ-отчёт за выбранную дату: чтение исходных workbooks, сбор строк за дату, форматирование по шаблону, запись в Excel. Запуск в фоне, прогресс, отмена.
- Точки входа в коде: APP/core/services/rsch_service.py, APP/core/ui/gui_commands/_rsch.py, APP/core/infra/rsch/_build.py, APP/core/infra/rsch/_collect.py, APP/core/infra/rsch/_format.py, APP/core/infra/rsch/_template.py, APP/core/app/message_formatting.py
- Зависит от: F-003, F-006, F-024, F-031
- Блокирует: F-015, F-016
- Бизнес-правила:
  - Выбор файлов: saved sources (askyesnocancel «Использовать сохраненный набор?») или новый выбор через multi-file dialog
  - Сохранение recent_sources и last_output_dir в config.rsch
  - target_date: извлечение из selected_date (date())
  - written_rows == 0 → ValueError «РСЧ: нет строк за выбранную дату»
  - issues (проблемы с листами) попадают в сообщение через build_issue_preview
  - Шаблон: builtin template или РСЧ/шаблон отчета.xlsx
  - Стили: income (зелёный), expense (красный), warning (жёлтый)
  - backup_existing_excel_output перед перезаписью
- Известные проблемы: нет
- Файлов затронуто: 6

### F-014: Сборка РСЧ-отчёта (период)
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь выбирает период и нажимает «СОБРАТЬ РСЧ ЗА ПЕРИОД». Приложение собирает один РСЧ-отчёт с листами по каждой дате в диапазоне. Валидация start ≤ end. Сохранение recent_sources.
- Точки входа в коде: APP/core/services/rsch_service.py, APP/core/ui/gui_commands/_rsch.py, APP/core/infra/rsch/_build.py
- Зависит от: F-003, F-006, F-013, F-024, F-031
- Блокирует: (нет)
- Бизнес-правила:
  - Валидация: start_date > end_date → messagebox.showerror
  - start_date.date() и end_date.date() извлекаются из datetime
  - written_rows == 0 → ValueError «РСЧ: нет строк за выбранный период»
  - Один workbook с листами по каждой дате диапазона
  - Сохранение recent_sources, last_output_dir
- Известные проблемы: нет
- Файлов затронуто: 3

### F-015: Ручная сверка с РСЧ
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь нажимает «✅ СВЕРИТЬ С РСЧ». Выбирает уже готовые мастер-отчёты (Общий, Борис, Иван) и РСЧ-отчёт через file dialogs. Приложение строит отчёт расхождений: сравнение строк master и РСЧ по сумме/исполнителю/заказчику, статус «Сверено»/«Проверить»/«Ошибка», гиперссылки на исходные файлы. Запуск в фоне, отмена.
- Точки входа в коде: APP/core/services/reconciliation_service.py, APP/core/ui/gui_commands/_reconciliation.py, APP/core/infra/reconciliation/_build.py, APP/core/infra/reconciliation/_collect.py, APP/core/infra/reconciliation/_resolve.py, APP/core/infra/reconciliation/_types.py, APP/core/infra/reconciliation/_utils.py
- Зависит от: F-003, F-006, F-008, F-011, F-012, F-013, F-024, F-031, F-038
- Блокирует: (нет)
- Бизнес-правила:
  - Выбор 3 мастер-отчётов (Общий, Борис, Иван) + РСЧ-отчёт + выходной путь
  - build_combined_reconciliation_report: 3 листа (Общий, Борис, Иван) + сводный
  - Сопоставление: точное совпадение суммы + исполнителя + заказчика (или алиаса) → «Сверено»
  - Частичное совпадение → «Проверить»
  - Использование customer_aliases для маппинга заказчиков
  - Гиперссылки на исходные файлы в строках сверки
  - Сообщение: «Отчет расхождений собран: Общий N, Борис N, Иван N строк.»
  - drive_letters для локального копирования сетевых файлов
- Известные проблемы: нет
- Файлов затронуто: 7

### F-016: Автосверка с РСЧ
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь нажимает «✅ АВТОСВЕРКА». Приложение автоматически пересобирает все 3 мастер-отчёта (Общий, Борис, Иван) за выбранную дату, затем собирает РСЧ-отчёт, затем строит отчёт расхождений. Один клик вместо ручного выбора файлов. Если данных РСЧ нет — автосверка пропускается. Если данных мастера нет (empty_data) — для кураторов пишется пустой отчёт.
- Точки входа в коде: APP/core/app_controller.py, APP/core/ui/gui_commands/_reconciliation.py, APP/core/infra/reconciliation/_build.py, APP/core/app/message_formatting.py
- Зависит от: F-003, F-006, F-008, F-011, F-012, F-013, F-015, F-024, F-031, F-038
- Блокирует: (нет)
- Бизнес-правила:
  - _run_auto_master_report для каждого куратора: blocking консолидация
  - ConsolidationRunError с code="empty_data" → для куратора: write_empty_daily_report; для общего: RuntimeError
  - РСЧ rows == 0 → «Нет данных РСЧ за дату. Автосверка пропущена.» (success, no path)
  - ValueError от build_combined → «Сверка за дату: {error}» (success, no path)
  - Проверка cancel_event на каждом этапе (после master reports, после РСЧ)
  - Сообщение: «Автосверка собрана: Общий N, Борис N, Иван N строк. РСЧ: N строк.»
  - Partial files: при отмене — mark_partial для output_path и rsch_output
- Известные проблемы: нет
- Файлов затронуто: 3

### F-017: Применение финансовых правил (бизнес-логика)
- Категория: core
- Статус: implemented
- User-facing: no
- Описание: Валидация и трансформация сырых строк из Excel в формат мастер-отчёта. Отбрасывание мусора/заголовков, определение приход/расход/возврат, расчёт комиссии (процент или абсолют), расчёт посредников, curator strategies, защита от Excel formula injection.
- Точки входа в коде: APP/core/domain/logic_service.py, APP/core/domain/data_schemas.py, APP/core/domain/utils_helpers.py, APP/core/domain/interfaces.py
- Зависит от: F-023
- Блокирует: F-008, F-009, F-010, F-011, F-012, F-016
- Бизнес-правила:
  - Validator: отбрасывание пустых строк, header-like строк (word-boundary matching), junk totals (итого/всего), junk markers (заказчик/исполнитель/приход/расход)
  - Service fields (_приватные ключи) пропускаются в junk/header эвристиках
  - FinancialRowSchema: Pydantic-валидация, Decimal precision
  - Приход/Расход: income_overrides (доп/доп сф/% посред) → приход; return_keywords (возврат) → расход (отрицательный); amount < 0 → расход
  - Комиссия: commission_is_percent=True и |c_raw| <= 1 → c_raw * 100; иначе abs(c_raw)
  - Посредник 1: abs(amount * pb_val / 100) если pb_val > 0
  - CuratorStrategy: Boris сохраняет intermediary2; Ivan — нет
  - Excel formula injection: sanitize (=, +, -, @, tab, newline → prepend "'")
  - Transit/rate/currency_amount: fail-soft (_parse_decimal_or_warn)
  - exclude_keywords: строки с «недопустимо»/«исключить»/«исключение» → is_critical
  - Template warnings: soft_structure errors не считаются actionable
- Известные проблемы: нет
- Файлов затронуто: 4

### F-018: Экспорт мастер-отчёта в Excel
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Запись консолидированных данных в Excel-файл через openpyxl. Применение стилей (заголовки, числовые форматы, подсветка ошибок), гиперссылки на исходные файлы, backup существующего файла перед перезаписью. Preflight проверка пути.
- Точки входа в коде: APP/core/infra/export_writer.py, APP/core/infra/export_formatting.py, APP/core/infra/excel_hyperlinks.py, APP/core/infra/excel_backup.py
- Зависит от: F-003, F-028
- Блокирует: F-008, F-009, F-010, F-011, F-012, F-016
- Бизнес-правила:
  - Preflight: output dir exists + writable; иначе ExportPreflightError
  - Backup: backup_existing_excel_output перед перезаписью (keep=10 по умолч.)
  - Заголовки: DEFAULT_HEADERS (Источник, ЗАКАЗЧИК, ИСПОЛНИТЕЛЬ, Приход, Расход, Комиссия, ИТОГ, ...)
  - Стили: ExcelStyles (цвета, шрифты, заливка, границы)
  - Гиперссылки: apply_cell_hyperlink на ячейки Источник
  - Formula injection: _safe_text (=, +, -, @ → prepend "'")
  - Template errors: записываются в отдельный лист/секцию
  - write_empty_daily_report: для автосверки при empty_data (кураторы)
  - atomic_save_workbook для безопасной записи
- Известные проблемы: нет
- Файлов затронуто: 4

### F-019: Обнаружение файлов (Discovery)
- Категория: core
- Статус: implemented
- User-facing: no
- Описание: Сканирование сетевых папок (Q:, Z:) и локальных путей для обнаружения Excel-файлов сотрудников. Автодетект curator roots («Отчет кураторов 1/2/3»). Кэширование discovery. Хеширование путей. Обнаружение переименований файлов.
- Точки входа в коде: APP/core/infra/discovery_service.py, APP/core/infra/path_resolver.py
- Зависит от: F-003, F-029
- Блокирует: F-004, F-008, F-009, F-010
- Бизнес-правила:
  - source_roots из config.paths; если не заданы — автодетект по drive_letters + «Отчет кураторов 1/2/3»
  - Legacy REPORTS path: автодетект curator roots добавляется
  - path_exists_with_timeout для проверки существования (timeout на сетевые запросы)
  - Discovery cache: инвалидация при add/delete_employee, attach_files
  - rename_detected: флаг при обнаружении переименования файла
  - Deduplication корней сканирования
- Известные проблемы: нет
- Файлов затронуто: 2

### F-020: Ингестия Excel-файлов (чтение)
- Категория: core
- Статус: implemented
- User-facing: no
- Описание: Чтение Excel-файлов через python-calamine (CalamineReader). Извлечение дат из имён листов и метаданных xlsx (workbook.xml). Многопоточное чтение с row cache. Изоляция Calamine в subprocess для crash resilience. Retry-логика (3 попытки, backoff 1s). Локальные копии сетевых файлов.
- Точки входа в коде: APP/core/infra/ingestion_engine.py, APP/core/infra/ingestion_reader.py, APP/core/app/file_processor.py
- Зависит от: F-023, F-029
- Блокирует: F-004, F-008, F-009, F-010
- Бизнес-правила:
  - python-calamine — обязательная зависимость (проверка в Bootstrap)
  - CalamineReader: парсинг через python_calamine.CalamineWorkbook
  - Извлечение дат: из имён листов (extract_date_from_sheet), из workbook.xml metadata (fast path)
  - Игнорируемые листы: «АНАЛИТИКА», «СВОД», листы начинающиеся с «_»
  - date_matches_target: формат DD.MM.YYYY, DD.MM.yy; без года — подстановка текущего года
  - 01.01.1900 игнорируется как невалидная дата
  - Retry: 3 попытки, backoff 1.0s (config.locking)
  - Isolate Calamine: subprocess worker для изоляции crash (config.performance.isolate_calamine)
  - get_local_copy: копирование сетевого файла локально для чтения
  - row_cache: кэширование распарсенных строк по mtime+size
  - Markers: config.sh1.markers (16 маркеров колонок)
- Известные проблемы: нет
- Файлов затронуто: 3

### F-021: Отмена операций
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Пользователь нажимает «Cancel» в status bar во время длительной операции. Операция останавливается на ближайшей контрольной точке. Частично записанные файлы переименовываются в .partial.xlsx. Сетевой кэш очищается. Сообщение об отмене с пометкой CancelledByUser.
- Точки входа в коде: APP/core/ui/operation_state.py, APP/core/ui/operation_status_bar.py, APP/core/ui/gui_master.py, APP/core/app_controller.py, APP/core/app/partial.py
- Зависит от: F-024
- Блокирует: (нет)
- Бизнес-правила:
  - OperationState.request_cancel(): только если is_busy; устанавливает cancel_event
  - CancelledByUser: маркер-класс (str subclass) для type-based detection вместо substring matching
  - _cancel_message: cleanup_local_copy_cache + mark_partial для всех output paths
  - .partial.xlsx: переименование незавершённых файлов (как в браузерах)
  - format_partial_note: текстовая заметка о partial-файлах в сообщении
  - Проверка cancel_event на контрольных точках: после discovery, после engine, после consolidate, перед write
  - Session status → «cancelled» в БД
- Известные проблемы: нет
- Файлов затронуто: 5

### F-022: Управление настройками (Settings Dialog)
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Пользователь открывает диалог настроек (8 вкладок): пути, база данных, логика, кураторы, сеть, производительность, внешний вид (тема/масштаб/плотность), резервные копии. Deep copy конфига, live preview темы/масштаба, Apply/OK/Cancel. Настройки сохраняются в config.yaml (секция ui: для UI-преференций).
- Точки входа в коде: APP/core/ui/ui_settings.py, APP/core/ui/gui_master_settings.py, APP/core/infra/settings_store.py
- Зависит от: F-003, F-027
- Блокирует: (нет)
- Бизнес-правила:
  - Deep copy конфига: изменения не применяются до Apply/OK
  - Cancel: восстановление snapshot темы/масштаба/плотности
  - UIPreferences: theme (light/dark/system), scale_mode (auto/manual), user_scale (0.80–1.50), density (compact/normal/comfortable), sidebar_width (0–800)
  - Валидация: _VALID_THEMES, _VALID_SCALE_MODES, _VALID_DENSITIES, _SCALE_MIN/MAX, _SIDEBAR_MIN/MAX
  - save_config при Apply/OK
  - Scrollable canvas для каждой вкладки
- Известные проблемы: нет
- Файлов затронуто: 3

### F-023: SQLite-кэш и сессии
- Категория: core
- Статус: implemented
- User-facing: no
- Описание: Гибридный кэш на SQLite: сессии консолидации, staging_data (raw строки), consolidated_results, source_files (метаданные), file_cache (mtime/size/dates), row_cache, discovery_cache, template_errors, customer_aliases. WAL mode, PRAGMA integrity_check, миграции. DBWriterThread для асинхронной записи.
- Точки входа в коде: APP/core/infra/db_connection.py, APP/core/infra/session_repo.py, APP/core/infra/source_file_repo.py, APP/core/infra/staging_repo.py, APP/core/bootstrap.py, APP/db_schema.sql, APP/migrations/001_numeric_to_text.sql, APP/migrations/002_customer_aliases.sql
- Зависит от: F-003
- Блокирует: F-004, F-008, F-009, F-010, F-017, F-020, F-038
- Бизнес-правила:
  - 10 таблиц: _migrations, sessions, source_files, staging_data, consolidated_results, template_errors, file_cache, row_cache, discovery_cache, customer_aliases
  - WAL mode, PRAGMA journal_mode=WAL, PRAGMA integrity_check при старте
  - Миграции: 001 (NUMERIC→TEXT для financial columns), 002 (customer_aliases)
  - DecimalEncoder для JSON-сериализации Decimal
  - sanitize_data: очистка данных перед записью
  - DBWriterThread: асинхронная запись staging_data через queue
  - Session status: running, completed, completed_with_warnings, failed, cancelled
  - wait_for_writes: блокирующее ожидание завершения DBWriterThread при shutdown
  - PRAGMA integrity_check при GUI-старте; warning при failure
  - allow_local_fallback: fallback на локальную БД при недоступности сетевой
- Известные проблемы: нет
- Файлов затронуто: 8

### F-024: Отслеживание прогресса операций
- Категория: core
- Статус: implemented
- User-facing: yes
- Описание: Глобальная state machine для длительных операций. OperationState (thread-safe singleton): begin/end/request_cancel, listeners. Progress bar в status bar: имя операции, прогресс 0-100%, elapsed time, ETA, Cancel button. Прогресс в заголовке окна. Toast-уведомления при завершении.
- Точки входа в коде: APP/core/ui/operation_state.py, APP/core/ui/operation_status_bar.py, APP/core/ui/gui_master.py, APP/core/ui/ui_stats_panel.py
- Зависит от: F-001
- Блокирует: F-004, F-008, F-009, F-010, F-013, F-014, F-015, F-016, F-021
- Бизнес-правила:
  - OperationType: NONE, REFRESH, CONSOLIDATION_DAY/ALL/MONTH, RSCH_DAY/MONTH, RECONCILIATION, AUTO_RECONCILIATION
  - begin(): только если не занято (is_busy); иначе — отказ (double-click protection)
  - end(): освобождение слота, reset progress
  - Listeners: уведомляются при каждом state transition (sidebar, stats_panel, title)
  - Прогресс в заголовке окна: «🚀 Master-Report v5.5 — Сборка за день 45%»
  - Polling 500ms для fallback обновления заголовка
  - ETA: расчёт по elapsed time и progress
  - Marshalling: root.after(0, ...) для Tk API из worker threads
- Известные проблемы: нет
- Файлов затронуто: 3

### F-025: Дашборд (вкладки)
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Многостраничный дашборд с вкладками: Сотрудники (таблица), Панель (состояние + быстрые действия), Отчеты (список отчётов, открытие), Диагностика (light diagnostics, логи), Логи (read_recent_logs/errors), Алиасы сверки, Настройки. Runtime state сохраняется в runtime_state.json.
- Точки входа в коде: APP/core/ui/ui_dashboard.py, APP/core/ui/dashboard_state.py
- Зависит от: F-001, F-003, F-033
- Блокирует: (нет)
- Бизнес-правила:
  - 7 вкладок: Сотрудники, Панель, Отчеты, Диагностика, Логи, Алиасы сверки, Настройки
  - Default tab: Сотрудники
  - RuntimeResult: сохранение результатов операций в runtime_state.json
  - build_diagnostic_summary: состояние конфига, БД, путей
  - read_recent_logs/errors: чтение последних N строк из логов
  - run_light_diagnostics: быстрые проверки здоровья
  - collect_report_paths: поиск сгенерированных отчётов
  - safe_open_existing_path: открытие файлов через open_path
- Известные проблемы: нет
- Файлов затронуто: 2

### F-026: Toast-уведомления
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Non-modal toast-уведомления (до 3 одновременно): success (зелёный), warning (жёлтый), error (красный), info (синий). Fade-out анимация. Авто-закрытие по таймеру (success 4s, error 6s). ToastManager управляет позиционированием и стеком.
- Точки входа в коде: APP/core/ui/toast.py, APP/core/ui/gui_commands/_base.py
- Зависит от: F-001
- Блокирует: (нет)
- Бизнес-правила:
  - ToastLevel: SUCCESS, WARNING, ERROR, INFO
  - До 3 одновременно; новые вытесняют старые
  - Duration: success=4000ms, error=6000ms (настраивается)
  - Fade-out анимация
  - Position: правый верхний угол окна
  - Fallback: если ToastManager недоступен → messagebox.showerror/showinfo
- Известные проблемы: нет
- Файлов затронуто: 2

### F-027: Управление темой
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: ThemeManager v2: цветовые палитры (light/dark), ttk styles, adaptive scaling, FONTS/SPACING/RADIUS/CONTROL. Автоопределение тёмной темы ОС (Windows registry, macOS osascript, Linux gsettings). Polling каждые 5s для «Системной» темы. Live preview в settings dialog. Density modes: compact/normal/comfortable.
- Точки входа в коде: APP/core/ui/theme.py, APP/core/ui/system_theme.py, APP/core/ui/gui_master.py, APP/core/ui/gui_master_settings.py
- Зависит от: F-001
- Блокирует: F-022
- Бизнес-правила:
  - Темы: light, dark, system (автоопределение ОС)
  - system_theme: Windows (registry HKCU\Control Panel\Colors), macOS (osascript), Linux (gsettings)
  - Polling 5s для system theme
  - Scaling: auto (DPI-based) или manual (0.80–1.50)
  - Density: compact, normal, comfortable — влияет на SPACING/RADIUS
  - register(canvas, bg_key): canvas-виджеты регистрируются для re-theme
  - apply_preferences: scale_mode, user_scale, density → _rebuild_tokens → apply_styles
  - add_scale_listener: подписка на изменения масштаба
  - attach_resize_listener: адаптация при изменении размера окна
- Известные проблемы: нет
- Файлов затронуто: 4

### F-028: Авто-бэкап Excel-выводов
- Категория: secondary
- Статус: implemented
- User-facing: no
- Описание: Перед перезаписью существующего Excel-файла (мастер-отчёт, РСЧ, сверка) создаётся backup-копия в подпапке backups/excel_outputs/{stem}/. Ротация: хранится N последних backup-копий (по умолч. 10, настраивается через config.backup.excel_keep). Timestamp в имени файла.
- Точки входа в коде: APP/core/infra/excel_backup.py
- Зависит от: F-003
- Блокирует: F-018
- Бизнес-правила:
  - backup_existing_excel_output: copy2 перед перезаписью
  - Backup dir: source.parent / "backups" / "excel_outputs" / source.stem
  - Timestamp: YYYYMMDD_HHMMSS_microseconds
  - Prune: keep N последних (по mtime); старые удаляются
  - resolve_excel_backup_keep: int(value), default 10, min 1
  - ~$ files (Excel lock) не бэкапятся
  - Best-effort: backup failure → caller aborts save
- Известные проблемы: нет
- Файлов затронуто: 1

### F-029: Поддержка сетевых дисков
- Категория: secondary
- Статус: implemented
- User-facing: no
- Описание: Сканирование сетевых дисков (Q:, Z:) для обнаружения файлов сотрудников. Локальное копирование сетевых файлов для чтения (get_local_copy). path_exists_with_timeout для проверки существования с timeout. Очистка кэша локальных копий (cleanup_local_copy_cache). Drive letters настраиваются в config.network.
- Точки входа в коде: APP/core/infra/utils.py, APP/core/infra/discovery_service.py, APP/core/infra/path_resolver.py
- Зависит от: F-003
- Блокирует: F-004, F-019, F-020
- Бизнес-правила:
  - Drive letters: config.network.drive_letters (по умолч. Q, Z)
  - get_local_copy: копирование сетевого файла в temp dir; кэш по хэшу пути
  - cleanup_local_copy_cache: удаление старых копий (max_age_days, min_delete_age_seconds)
  - path_exists_with_timeout: проверка существования с timeout (защита от зависших SMB)
  - atomic_save_workbook: безопасная запись через temp file + rename
  - is_file_writable: проверка writable (retry_count, retry_backoff из config.locking)
  - open_path: открытие файла/папки через OS (Windows: os.startfile, macOS: open, Linux: xdg-open)
- Известные проблемы: Сетевые задержки могут вызывать timeout при refresh (30s)
- Файлов затронуто: 3

### F-030: Path traversal protection
- Категория: secondary
- Статус: implemented
- User-facing: no
- Описание: Защита от path traversal атак через config.yaml. Все пути валидируются: относительные пути не должны выходить за app_root; абсолютные/UNC/drive-letter пути проверяются через allowlist (configured source_roots + config_dir + project_root). При обнаружении traversal — ValueError.
- Точки входа в коде: APP/core/bootstrap.py, APP/core/infra/config_controller.py
- Зависит от: F-003
- Блокирует: F-001, F-002, F-003
- Бизнес-правила:
  - _validate_path_safety: resolved.is_relative_to(app_root) или allow_external
  - OSError fallback: strict string check (startswith с boundary)
  - _is_effectively_absolute: Path.is_absolute() или UNC (\\\\) или drive-letter (C:\)
  - Allowlist roots: source_roots + config_dir + project_root
  - _is_path_under: проверка что path находится под root
  - _is_stale_app_local_path: детект путей от другой инсталляции
  - Stale paths: перезапись на текущий app_root при обнаружении
- Известные проблемы: нет
- Файлов затронуто: 2

### F-031: Сохранение геометрии окна
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Сохранение и восстановление позиции/размера главного окна. Геометрия сохраняется в ~/.master_report_geometry. При запуске: если сохранённая геометрия в пределах экрана — используется; иначе — auto-fit (82% ширины, 88% высоты, центрирование). Off-screen fallback.
- Точки входа в коде: APP/core/ui/geometry.py, APP/core/ui/gui_master.py
- Зависит от: F-001
- Блокирует: (нет)
- Бизнес-правила:
  - load_geometry: чтение из ~/.master_report_geometry
  - is_geometry_visible: проверка что окно в пределах экрана
  - _fit_window_geometry: min(preferred, 82% width / 88% height), центрирование
  - _resolve_initial_geometry: saved (если visible) → auto-fit
  - minsize: max(640, 50% screen_w) × max(420, 50% screen_h)
  - save_geometry: при закрытии окна
- Известные проблемы: нет
- Файлов затронуто: 2

### F-032: Логирование
- Категория: auxiliary
- Статус: implemented
- User-facing: no
- Описание: Многоуровневое логирование: RotatingFileHandler (startup_log.txt, 10MB×5) + StreamHandler для main.py; GUI logging через setup_gui_logging (LogPanel widget). scrub_path для безопасного логирования путей (хэширование). safe_file_label для коротких имён файлов.
- Точки входа в коде: APP/main.py, APP/core/infra/utils_logging.py, APP/core/ui/ui_log_panel.py, APP/core/ui/gui_master.py
- Зависит от: F-001
- Блокирует: F-025
- Бизнес-правила:
  - RotatingFileHandler: 10MB, 5 backups, UTF-8
  - Level: INFO (по умолчанию)
  - scrub_path: хэширование путей для безопасности логов
  - safe_file_label: короткое имя файла для UI
  - setup_gui_logging: перенаправление логов в LogPanel (scrolledtext)
  - Format: «%(asctime)s - %(name)s - %(levelname)s - %(message)s»
- Известные проблемы: нет
- Файлов затронуто: 4

### F-033: Аудит потери данных (Data Loss Log)
- Категория: auxiliary
- Статус: implemented
- User-facing: no
- Описание: Запись каждого случая тихого отбрасывания или преобразования пользовательских данных в logs/data_loss.log. Позволяет операторам выявлять паттерны (сломанный шаблон, неверное имя колонки, сетевой сбой). Редактирование денежных сумм в логе (redact PII: 3+ digits + separator).
- Точки входа в коде: APP/core/domain/data_loss_log.py
- Зависит от: F-032
- Блокирует: F-015, F-017
- Бизнес-правила:
  - Logger: «data_loss», level INFO, propagate=False
  - Log file: logs/data_loss.log
  - Redact: _AMOUNT_RE = \d{3,}[.,]\d{2} → замена перед записью
  - record_loss: запись с context (файл, лист, строка, причина)
  - reset_for_testing: сброс для тестов
  - Thread-safe: _LOCK
  - PYTEST_CURRENT_TEST: CWD вместо package root для тестов
- Известные проблемы: domain→infra violation (data_loss_log импортирует utils_logging)
- Файлов затронуто: 1

### F-034: Поиск и фильтр сотрудников
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Пользователь вводит текст в поле поиска таблицы сотрудников. Таблица фильтруется в реальном времени (debounce) по совпадению в имени, статусе или пути. Case-insensitive.
- Точки входа в коде: APP/core/ui/ui_employee_table.py, APP/core/view_models/employee_list_viewmodel.py, APP/core/ui/debounce.py, APP/core/ui/gui_commands/_employee.py
- Зависит от: F-005, F-001
- Блокирует: (нет)
- Бизнес-правила:
  - search_query: lowercased
  - Фильтр: any(search_query in x.lower() for x in (name, status_text, path_text))
  - Debounce на ввод (Debouncer в ui_employee_table)
  - _sync_employee_ui: перерисовка таблицы после фильтра
- Известные проблемы: нет
- Файлов затронуто: 4

### F-035: Открытие файлов и папок
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Пользователь может открыть: папку мастер-отчёта, папку сотрудника, файл сотрудника. При нескольких файлах у сотрудника — диалог «Да/Нет/Отмена» (открыть все файлы / открыть папки / ничего). Открытие через OS (os.startfile / open / xdg-open).
- Точки входа в коде: APP/core/ui/gui_commands/_employee.py, APP/core/infra/utils.py
- Зависит от: F-005, F-029
- Блокирует: (нет)
- Бизнес-правила:
  - open_master_folder: open_path(master_path.parent)
  - open_employee_folder: уникальные parent-папки всех путей сотрудника
  - open_employee_file: 1 файл → открыть; >1 → askyesnocancel (Да=все файлы, Нет=папки, Отмена=ничего)
  - open_path: Windows os.startfile, macOS open, Linux xdg-open
- Известные проблемы: нет
- Файлов затронуто: 2

### F-036: Копирование должников в буфер обмена
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Пользователь копирует список сотрудников, не сдавших отчёт за выбранную дату, в буфер обмена. Формат: «Должники за DD.MM:\n- Имя1\n- Имя2...». Toast-уведомление об успехе.
- Точки входа в коде: APP/core/ui/gui_commands/_employee.py, APP/core/view_models/employee_list_viewmodel.py
- Зависит от: F-004, F-005
- Блокирует: (нет)
- Бизнес-правила:
  - get_missing_names: сотрудники без «🟢 ГОТОВО» в статусе
  - Формат: «Должники за DD.MM:\n» + «- {name}» для каждого
  - clipboard_clear + clipboard_append
  - Toast info «Список скопирован в буфер обмена» (2500ms)
- Известные проблемы: нет
- Файлов затронуто: 2

### F-037: Tooltip-виджеты
- Категория: auxiliary
- Статус: implemented
- User-facing: yes
- Описание: Лёгкие tooltip-подсказки для ttk-виджетов при наведении курсора. Fade-in анимация. Без сторонних зависимостей. Используется для кнопок sidebar (например, «Обновить статус»).
- Точки входа в коде: APP/core/ui/tooltip.py, APP/core/ui/ui_sidebar.py
- Зависит от: F-001
- Блокирует: (нет)
- Бизнес-правила:
  - Hover → показ tooltip после delay
  - Fade-in анимация
  - Без сторонних зависимостей (чистый Tkinter)
- Известные проблемы: нет
- Файлов затронуто: 2

### F-038: Управление алиасами заказчиков
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: Бухгалтеры управляют соответствиями между заказчиками кураторов (master) и заказчиками РСЧ через отдельную вкладку «Алиасы сверки». CRUD-операции: добавить, изменить, удалить алиас. Таблица с сортировкой, двойной клик для редактирования. Алиасы используются сверкой для автоматического сопоставления строк.
- Точки входа в коде: APP/core/ui/ui_aliases.py, APP/core/infra/customer_alias_repo.py, APP/core/app_controller.py
- Зависит от: F-023
- Блокирует: F-015, F-016
- Бизнес-правила:
  - CustomerAlias: master_customer ↔ rsch_customer + notes
  - CRUD: add_alias, update_alias, delete_alias, get_all_aliases
  - Кэш в памяти; reload() после bulk-редактирования
  - Поля: master_customer (trim), rsch_customer (trim), notes
  - updated_at: timestamp последнего изменения
  - Сверка: точное совпадение суммы + исполнителя + заказчика (или алиаса) → «Сверено»
  - Частичное совпадение → «Проверить» — подсказка добавить алиас
  - alias_repo=None → get_customer_aliases возвращает [], add/update/delete → RuntimeError
- Известные проблемы: нет
- Файлов затронуто: 3

### F-039: Сохранение настроек РСЧ (recent sources)
- Категория: secondary
- Статус: implemented
- User-facing: yes
- Описание: При сборке РСЧ-отчёта выбранные исходные файлы и выходная директория сохраняются в config.rsch.recent_sources и config.rsch.last_output_dir. При следующем запуске пользователю предлагается использовать сохранённый набор (askyesnocancel). Несуществующие пути отфильтровываются.
- Точки входа в коде: APP/core/ui/gui_commands/_rsch.py
- Зависит от: F-003, F-013
- Блокирует: (нет)
- Бизнес-правила:
  - recent_sources: список путей (str), дедупликация
  - last_output_dir: директория последнего сохранения
  - mode: «combined» (единый отчёт)
  - _resolve_rsch_sources: saved (askyesnocancel) → existing_saved или новый выбор
  - Несуществующие saved paths: warning «Сохраненные пути не найдены»
  - _resolve_config_path: абсолютные пути как-is; относительные через resolve_path
  - save_config после сохранения preferences
- Известные проблемы: нет
- Файлов затронуто: 1

### F-040: Многопоточная обработка файлов
- Категория: auxiliary
- Статус: implemented
- User-facing: no
- Описание: Настройка и управление пулом потоков для многопоточного чтения Excel-файлов и проверки статусов. max_workers = min(32, CPU_COUNT*2) по умолчанию; override из config.performance.max_workers. ThreadPoolExecutor с thread_name_prefix «hermes-worker».
- Точки входа в коде: APP/core/app/performance.py, APP/core/app/file_processor.py, APP/core/app_controller.py
- Зависит от: (нет)
- Блокирует: F-004, F-008, F-020
- Бизнес-правила:
  - default_max_workers: min(32, os.cpu_count() * 2)
  - resolve_max_workers: config.performance.max_workers override, min 1
  - ThreadPoolExecutor: max_workers, thread_name_prefix=«hermes-worker»
  - executor.shutdown(wait=True) при graceful shutdown
  - as_completed с timeout для refresh status (30s)
- Известные проблемы: нет
- Файлов затронуто: 3

### F-041: Event Bus (pub/sub)
- Категория: deprecated
- Статус: stubbed
- User-facing: no
- Описание: Thread-safe publish-subscribe event bus для декаплинга FileProcessor/AppController от GuiMaster. Типы событий: PROGRESS_UPDATED, OPERATION_STARTED, OPERATION_FINISHED, ERROR_OCCURRED, TITLE_REFRESH. Queue-based drain из GUI thread.
- Точки входа в коде: APP/core/infra/event_bus.py
- Зависит от: (нет)
- Блокирует: (нет)
- Бизнес-правила:
  - EventType enum: PROGRESS_UPDATED, OPERATION_STARTED, OPERATION_FINISHED, ERROR_OCCURRED, TITLE_REFRESH
  - Queue-based: publish из любого потока, drain из GUI thread
  - Thread-safe
- Известные проблемы: DEAD CODE — не импортируется ни одним модулем в APP/; функциональность заменена прямыми callback-ами и OperationState listeners
- Файлов затронуто: 1

### F-042: In-process метрики
- Категория: deprecated
- Статус: stubbed
- User-facing: no
- Описание: Thread-safe счётчики для мониторинга консолидации: increment (counters), set_gauge, timers, log_summary. Предназначено для отслеживания rows_processed, files_read, active_threads.
- Точки входа в коде: APP/core/infra/metrics.py
- Зависит от: (нет)
- Блокирует: (нет)
- Бизнес-правила:
  - Counters: increment(name, amount)
  - Gauges: set_gauge(name, value)
  - Timers: start/stop
  - log_summary: вывод всех метрик
  - Thread-safe (_lock)
- Известные проблемы: DEAD CODE — не импортируется ни одним модулем в APP/; функциональность не используется
- Файлов затронуто: 1
