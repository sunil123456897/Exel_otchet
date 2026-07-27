# Бизнес-правила

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Источник: docs/features/inventory.md + анализ кода APP/core/

---

## BR-001: Проверка обязательной зависимости python-calamine
- Фича: F-001
- Тип: validation
- Правило: При запуске приложения (GUI и CLI) проверяется наличие библиотеки python-calamine. При отсутствии — RuntimeError + messagebox (GUI) + sys.exit(1).
- Реализация в коде: APP/core/bootstrap.py:440-477 (Bootstrap.setup)
- Код: `if importlib.util.find_spec("python_calamine") is None: raise RuntimeError("Не найдена обязательная библиотека python-calamine")`
- Триггер: Старт приложения (до загрузки конфига)
- Действие при нарушении: RuntimeError, GUI messagebox, sys.exit(1)
- Связанные правила: BR-002

## BR-002: DPI-awareness для HiDPI-дисплеев
- Фича: F-001
- Тип: transformation
- Правило: SetProcessDpiAwareness(2) (per-monitor v2) вызывается до создания Tk root. Fallback на SetProcessDPIAware() при ошибке.
- Реализация в коде: APP/main.py:24-30
- Код: `ctypes.windll.shcore.SetProcessDpiAwareness(2)`
- Триггер: Старт GUI (до Tk root)
- Действие при нарушении: Fallback на SetProcessDPIAware()
- Связанные правила: —

## BR-003: Загрузка config.yaml с fallback на example
- Фича: F-003
- Тип: conditional
- Правило: config.yaml загружается через ruamel.yaml. При отсутствии файла — копия из config.example.yaml создаётся автоматически.
- Реализация в коде: APP/core/infra/config_controller.py
- Код: `if not config_path.exists(): shutil.copy2(example_path, config_path)`
- Триггер: Bootstrap.setup()
- Действие при нарушении: Создаётся новый config.yaml из example
- Связанные правила: BR-004, BR-005

## BR-004: Pydantic-валидация секций конфига
- Фича: F-003
- Тип: validation
- Правило: Секции paths, database, locking, network валидируются через Pydantic-модели (PathsConfig, DatabaseConfig, LockingConfig, NetworkConfig). При невалидной секции — warning + safe defaults (не блокирует запуск).
- Реализация в коде: APP/core/infra/config_controller.py
- Код: `PathsConfig(**raw_paths)` с fallback на defaults при ValidationError
- Триггер: Загрузка config.yaml
- Действие при нарушении: Warning в лог, safe defaults
- Связанные правила: BR-003

## BR-005: chmod 0o600 на config.yaml и employees.yaml
- Фича: F-003
- Тип: constraint
- Правило: Файлы config.yaml и employees.yaml получают права 0o600 (только владелец читает/пишет) при сохранении.
- Реализация в коде: APP/core/infra/config_controller.py
- Код: `os.chmod(path, 0o600)`
- Триггер: save_config()
- Действие при нарушении: — (best-effort)
- Связанные правила: —

## BR-006: Path traversal protection
- Фича: F-030
- Тип: validation
- Правило: Относительные пути в config.yaml не должны выходить за app_root. Абсолютные/UNC/drive-letter пути проверяются через allowlist (configured source_roots + config_dir + project_root). При обнаружении traversal — ValueError.
- Реализация в коде: APP/core/bootstrap.py, APP/core/infra/config_controller.py (_validate_path_safety)
- Код: `if not resolved.is_relative_to(app_root) and not allow_external: raise ValueError(...)`
- Триггер: Загрузка путей из config.yaml
- Действие при нарушении: ValueError, блокировка запуска
- Связанные правила: BR-003

## BR-007: Stale app-local path detection
- Фича: F-030
- Тип: transformation
- Правило: Если путь в config.yaml указывает на директорию от другой инсталляции (stale), он перезаписывается на текущий app_root.
- Реализация в коде: APP/core/infra/config_controller.py (_is_stale_app_local_path)
- Триггер: Загрузка путей из config.yaml
- Действие при нарушении: Перезапись пути
- Связанные правила: BR-006

## BR-008: Проверка writable отчёта перед запуском
- Фича: F-008, F-009, F-010, F-011, F-012, F-013, F-015
- Тип: validation
- Правило: Перед запуском консолидации/РСЧ/сверки проверяется, что выходной файл отчёта доступен для записи (не открыт в Excel). При занятости — error toast, отмена операции.
- Реализация в коде: APP/core/app_controller.py:185-194 (_is_report_writable), APP/core/infra/utils.py (is_file_writable)
- Код: `is_file_writable(path, retry_count, retry_backoff)` — retry_count и retry_backoff из config.locking
- Триггер: Перед запуском операции
- Действие при нарушении: Error toast «Мастер-файл занят в Excel», отмена
- Связанные правила: BR-009

## BR-009: Проверка master lock перед refresh
- Фича: F-004
- Тип: validation
- Правило: Перед обновлением статусов сотрудников проверяется master lock. Если мастер-файл занят — toast error, пустой результат.
- Реализация в коде: APP/core/app_controller.py:707 (refresh_status → check_master_lock)
- Код: `if not check_master_lock(self.config_controller): on_complete([], {}, False)`
- Триггер: refresh_status()
- Действие при нарушении: Toast error «Мастер-файл занят в Excel», пустой результат
- Связанные правила: BR-008

## BR-010: Предупреждение о должниках перед консолидацией
- Фича: F-008, F-009, F-010
- Тип: conditional
- Правило: Перед запуском консолидации показывается messagebox.askyesno «Не сдано отчетов: N. Продолжить?». При No — отмена.
- Реализация в коде: APP/core/ui/gui_commands/_consolidation.py
- Триггер: Перед запуском консолидации
- Действие при нарушении: Отмена операции
- Связанные правила: —

## BR-011: Статусы сотрудников при refresh
- Фича: F-004
- Тип: transformation
- Правило: Статус сотрудника определяется по наличию файла и листа за выбранную дату:
  - 🟢 ГОТОВО: файл существует + содержит лист за выбранную дату
  - 🟠 НЕТ ДАТЫ: файл существует, но лист за дату не найден
  - 🔴 НЕТ ФАЙЛА: файл не существует по привязанному пути
  - [ERR] ОШИБКА: ошибка при чтении файла
- Реализация в коде: APP/core/app_controller.py:280-362 (_check_employee_refresh_status, _run_refresh_status)
- Триггер: refresh_status()
- Действие при нарушении: [ERR] ОШИБКА с описанием
- Связанные правила: BR-012

## BR-012: target_date > today → всегда «НЕТ ДАТЫ»
- Фича: F-004
- Тип: constraint
- Правило: Если выбранная дата больше сегодняшней, статус сотрудника всегда «НЕТ ДАТЫ» (нельзя собрать отчёт за будущее).
- Реализация в коде: APP/core/app_controller.py:270-279 (_has_target_date)
- Триггер: refresh_status() при target_date > today
- Действие при нарушении: —
- Связанные правила: BR-011

## BR-013: Timeout 30s на refresh status
- Фича: F-004
- Тип: constraint
- Правило: При обновлении статусов as_completed имеет timeout 30s. Незавершённые futures cancel(), partial result показывается.
- Реализация в коде: APP/core/app_controller.py:363-435 (_run_refresh_status)
- Код: `for future in as_completed(futures, timeout=30):`
- Триггер: refresh_status()
- Действие при нарушении: Cancel незавершённых, partial result
- Связанные правила: BR-011

## BR-014: file_cache по mtime + size
- Фича: F-004, F-020
- Тип: conditional
- Правило: Кэш discovery/file_cache валиден если mtime и size файла совпадают с закэшированными. Иначе — повторное чтение.
- Реализация в коде: APP/core/infra/source_file_repo.py (get_file_cache), APP/core/app/file_processor.py
- Триггер: Чтение файла
- Действие при нарушении: Cache miss, повторное чтение
- Связанные правила: —

## BR-015: rename_detected при обнаружении переименования
- Фича: F-004, F-019
- Тип: transformation
- Правило: Если файл сотрудника переименован, флаг rename_detected=True, обновлённый путь сохраняется в config.
- Реализация в коде: APP/core/infra/discovery_service.py, APP/core/app_controller.py:131 (rename_detected property)
- Триггер: Discovery при refresh
- Действие при нарушении: Обновление config
- Связанные правила: BR-003

## BR-016: add_employee — trim имени, пустое игнорируется
- Фича: F-005
- Тип: validation
- Правило: При добавлении сотрудника имя обрезается (trim). Пустое имя игнорируется. Дубликаты не проверяются на уровне config.
- Реализация в коде: APP/core/infra/config_controller.py, APP/core/ui/gui_commands/_employee.py
- Триггер: add_employee()
- Действие при нарушении: Игнорирование пустого имени
- Связанные правила: —

## BR-017: delete_employee — инвалидация discovery_cache
- Фича: F-005
- Тип: transformation
- Правило: При удалении сотрудника по точному имени discovery_cache инвалидируется.
- Реализация в коде: APP/core/infra/config_controller.py, APP/core/app_controller.py
- Триггер: delete_employee()
- Действие при нарушении: —
- Связанные правила: BR-014

## BR-018: attach_files — MD5 + inode + absolute path
- Фича: F-005
- Тип: transformation
- Правило: При привязке файлов к сотруднику вычисляется MD5-хэш, inode и absolute path. Дедупликация путей по строковому представлению. Режимы append и replace.
- Реализация в коде: APP/core/infra/config_controller.py, APP/core/ui/gui_commands/_employee.py
- Триггер: attach_files()
- Действие при нарушении: —
- Связанные правила: —

## BR-019: Поиск сотрудников — case-insensitive substring
- Фича: F-034
- Тип: validation
- Правило: Поиск сотрудников case-insensitive, совпадение по имени/status_text/path_text (any).
- Реализация в коде: APP/core/view_models/employee_list_viewmodel.py, APP/core/ui/ui_employee_table.py
- Код: `any(search_query in x.lower() for x in (name, status_text, path_text))`
- Триггер: Ввод в поле поиска (debounce)
- Действие при нарушении: —
- Связанные правила: BR-020

## BR-020: Debounce 250мс на изменение даты и поиск
- Фича: F-006, F-034
- Тип: constraint
- Правило: Изменение даты и ввод в поле поиска имеют debounce 250мс для предотвращения множественных refresh при кликах.
- Реализация в коде: APP/core/ui/debounce.py
- Триггер: Изменение даты / ввод поиска
- Действие при нарушении: —
- Связанные правила: BR-019

## BR-021: Период по умолчанию для месячных отчётов
- Фича: F-006
- Тип: transformation
- Правило: Автовыбор периода: если сегодня 1-е число — предыдущий месяц (1-е до последний день); иначе — с 1-го числа текущего месяца до сегодня.
- Реализация в коде: APP/core/ui/ui_sidebar.py
- Триггер: Инициализация периода
- Действие при нарушении: —
- Связанные правила: BR-022

## BR-022: Валидация периода — start ≤ end
- Фича: F-006, F-010, F-014
- Тип: validation
- Правило: При выборе периода проверяется start_date ≤ end_date. При нарушении — messagebox.showerror, отмена.
- Реализация в коде: APP/core/ui/ui_sidebar.py, APP/core/app_controller.py:515-525 (_normalize_consolidation_dates)
- Триггер: Выбор периода / запуск консолидации за период
- Действие при нарушении: messagebox.showerror, отмена
- Связанные правила: BR-021

## BR-023: Фильтрация сотрудников по куратору
- Фича: F-007
- Тип: transformation
- Правило: Куратор «Общий» → curator=None, все сотрудники (минус excluded_keys). Куратор «Борис» → curator="boris", фильтр по employees_key (substring, case-insensitive). Куратор «Иван» → curator="ivan", аналогично.
- Реализация в коде: APP/core/app_controller.py:195-241 (_get_enabled_curator_employee_keys, _filter_employees_for_curator)
- Код: `key in lowered_name` (substring match)
- Триггер: Выбор куратора + консолидация
- Действие при нарушении: —
- Связанные правила: BR-024

## BR-024: curator enabled=False → curator_config=None
- Фича: F-011, F-012
- Тип: conditional
- Правило: Если в config.curators.{boris|ivan}.enabled=False → curator_config=None, отчёт куратора не формируется.
- Реализация в коде: APP/core/app_controller.py:169-179 (_get_curator_config)
- Триггер: _get_curator_config()
- Действие при нарушении: —
- Связанные правила: BR-023

## BR-025: Session — UUID, meta, статус в БД
- Фича: F-008, F-009, F-010, F-023
- Тип: transformation
- Правило: Каждая консолидация создаёт session_id (UUID), meta {type, date/start/end}, статус в БД: running → completed/completed_with_warnings/failed/cancelled.
- Реализация в коде: APP/core/app_controller.py:541, 567, 576, 600, 622, 629, 673-678
- Триггер: _execute_consolidation()
- Действие при нарушении: —
- Связанные правила: BR-026

## BR-026: Session status — completed_with_warnings
- Фича: F-008
- Тип: conditional
- Правило: Статус «completed_with_warnings» если есть actionable warnings (error_type != "soft_structure") ИЛИ runtime warnings (range_note, file_error_note). Иначе «completed».
- Реализация в коде: APP/core/app_controller.py:669-678
- Код: `has_actionable_warnings = any(error.get("error_type") not in {"soft_structure"} for error in errors)`
- Триггер: Завершение консолидации
- Действие при нарушении: —
- Связанные правила: BR-025

## BR-027: Пустой consolidated_data → failed
- Фича: F-008
- Тип: validation
- Правило: Если consolidated_data пуст после consolidate() → статус failed, on_failure_code="empty_data", сообщение «Нет данных за дату».
- Реализация в коде: APP/core/app_controller.py:628-643
- Триггер: После consolidate()
- Действие при нарушении: —
- Связанные правила: BR-025

## BR-028: run_engine failure → failed, no_files
- Фича: F-008
- Тип: validation
- Правило: Если run_engine возвращает False (нет файлов) → статус failed, on_failure_code="no_files", сообщение _build_no_files_message.
- Реализация в коде: APP/core/app_controller.py:587-604
- Триггер: После run_engine()
- Действие при нарушении: —
- Связанные правила: BR-025

## BR-029: Cancel control points
- Фича: F-021
- Тип: conditional
- Правило: cancel_event проверяется на контрольных точках: после discovery, после engine, после consolidate, перед write. При cancel — статус «cancelled», _cancel_message, mark_partial для output paths.
- Реализация в коде: APP/core/app_controller.py:606-609, 621-624
- Триггер: cancel_event.is_set()
- Действие при нарушении: —
- Связанные правила: BR-030

## BR-030: .partial.xlsx для незавершённых файлов
- Фича: F-021
- Тип: transformation
- Правило: При отмене операции частично записанные файлы переименовываются в .partial.xlsx (как в браузерах). format_partial_note добавляет текстовую заметку.
- Реализация в коде: APP/core/app/partial.py (mark_partial, format_partial_note)
- Триггер: Cancel во время write
- Действие при нарушении: —
- Связанные правила: BR-029

## BR-031: Validator — отбрасывание пустых строк
- Фича: F-017
- Тип: validation
- Правило: Строка отбрасывается если customer, contractor, filters пустые И amount пустой/ноль.
- Реализация в коде: APP/core/domain/logic_service.py:62-77 (validate_row)
- Код: `if not customer and not contractor and not filters and _is_empty_zero(amount_val): return False`
- Триггер: validate_row()
- Действие при нарушении: Строка отбрасывается
- Связанные правила: BR-032, BR-033

## BR-032: Validator — header-like detection (word-boundary)
- Фича: F-017
- Тип: validation
- Правило: Строка отбрасывается если она выглядит как leaked column header. Используется word-boundary matching (regex `(?<!\w)word(?!\w)`) чтобы «Приходько» не совпадало с «приход». Значения с цифрами считаются данными, не заголовками.
- Реализация в коде: APP/core/domain/logic_service.py:47-60 (_is_header_like)
- Код: `if any(c.isdigit() for c in s_norm): return False` + `re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", s_norm)`
- Триггер: validate_row()
- Действие при нарушении: Строка отбрасывается
- Связанные правила: BR-031

## BR-033: Validator — service fields (_приватные ключи) пропускаются
- Фича: F-017
- Тип: validation
- Правило: Service metadata fields (ключи, начинающиеся с «_») пропускаются в junk/header эвристиках. Они несут диагностику (например, _template_warning_reason) и могут содержать header words.
- Реализация в коде: APP/core/domain/logic_service.py:88-89 (_is_service_field)
- Код: `def _is_service_field(key: str) -> bool: return isinstance(key, str) and key.startswith("_")`
- Триггер: validate_row()
- Действие при нарушении: —
- Связанные правила: BR-032

## BR-034: Validator — junk totals (итого/всего)
- Фича: F-017
- Тип: validation
- Правило: Если в строке (исключая name fields) найдены ≥2 junk_totals маркера (итого, всего, итог, итог дня, итоги дня) → строка отбрасывается.
- Реализация в коде: APP/core/domain/logic_service.py:105-114
- Код: `if non_name_marker_hits >= 2: return False`
- Триггер: validate_row()
- Действие при нарушении: Строка отбрасывается
- Связанные правила: BR-031

## BR-035: Validator — junk markers (≥3 в строке с 2+ name fields)
- Фича: F-017
- Тип: validation
- Правило: Если name_fields_filled ≥ 2 И в строке найдены ≥3 junk_markers (заказчик, исполнитель, приход, расход) → строка отбрасывается.
- Реализация в коде: APP/core/domain/logic_service.py:124-131
- Код: `if sum(1 for m in self._junk_markers if m in row_str) >= 3: return False`
- Триггер: validate_row()
- Действие при нарушении: Строка отбрасывается
- Связанные правила: BR-031

## BR-036: Pydantic-валидация FinancialRowSchema
- Фича: F-017
- Тип: validation
- Правило: После junk/header проверок строка валидируется через Pydantic FinancialRowSchema. При ValidationError — warning в лог, строка отбрасывается.
- Реализация в коде: APP/core/domain/logic_service.py:133-139
- Код: `FinancialRowSchema(**row)` + `except ValidationError: return False`
- Триггер: validate_row()
- Действие при нарушении: Строка отбрасывается
- Связанные правила: BR-037

## BR-037: FinancialRowSchema — Decimal coercion
- Фича: F-017
- Тип: transformation
- Правило: Все числовые поля FinancialRowSchema (amount, income, expense, total, commission, brokers, transit, rate, currency_amount) coerced to Decimal через field_validator. None/"" → Decimal("0.00"). Строки очищаются (пробелы, запятые→точки, лишние точки/минусы). Unparseable → Decimal("0.00").
- Реализация в коде: APP/core/domain/data_schemas.py:46-91 (to_decimal validator)
- Код: `s = str(v).replace(" ", "").replace(",", ".")` + очистка + `Decimal(s_clean)`
- Триггер: FinancialRowSchema(**row)
- Действие при нарушении: Decimal("0.00")
- Связанные правила: BR-036

## BR-038: FinancialRowSchema — date format DD.MM.YYYY
- Фича: F-017
- Тип: validation
- Правило: Поле date валидируется через datetime.strptime(v, "%d.%m.%Y"). При ошибке — возвращается как-is (str), не блокирует.
- Реализация в коде: APP/core/domain/data_schemas.py:33-44 (validate_date)
- Триггер: FinancialRowSchema(**row)
- Действие при нарушении: Возврат строки как-is
- Связанные правила: BR-036

## BR-039: Приход/Расход — income_overrides и return_keywords
- Фича: F-017
- Тип: transformation
- Правило: Определение направления потока денег:
  - income_overrides (доп, доп сф, доп.сф, % посред) → приход (is_add=True)
  - return_keywords (возврат) → расход отрицательный (is_ret=True)
  - amount < 0 → расход положительный (abs)
  - иначе → приход
- Реализация в коде: APP/core/domain/logic_service.py:280-303 (_resolve_flow), 379-393 (apply_financial_rules)
- Код: `if is_add: return amount, Decimal("0.00")` / `if is_ret: return Decimal("0.00"), -abs(amount)` / `if amount < 0: return Decimal("0.00"), abs(amount)`
- Триггер: apply_financial_rules()
- Действие при нарушении: —
- Связанные правила: BR-040

## BR-040: income_overrides — word-boundary matching
- Фича: F-017
- Тип: validation
- Правило: income_overrides используют pre-compiled word-boundary regex patterns (`(?<!\w)kw`) чтобы «доп» совпадало с «доп оплата», но НЕ с «недопустимо».
- Реализация в коде: APP/core/domain/logic_service.py:214-217
- Код: `self._inc_over_patterns = [re.compile(r"(?<!\w)" + re.escape(kw)) for kw in self.inc_over]`
- Триггер: apply_financial_rules()
- Действие при нарушении: —
- Связанные правила: BR-039

## BR-041: Комиссия — percent vs absolute
- Фича: F-017
- Тип: transformation
- Правило: Если commission_is_percent=True И |c_raw| <= 1 → c_raw * 100 (процент). Иначе → abs(c_raw) (абсолют). ROUND_HALF_UP до 0.01.
- Реализация в коде: APP/core/domain/logic_service.py:305-318 (_resolve_commission)
- Код: `if self.commission_is_percent and c_raw != 0 and abs(c_raw) <= 1: return abs(c_raw * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`
- Триггер: apply_financial_rules()
- Действие при нарушении: —
- Связанные правила: BR-037

## BR-042: Посредник 1 — расчёт
- Фича: F-017
- Тип: transformation
- Правило: b1_val = abs(raw_b1). pb_val = abs(to_decimal_percent(pb_raw)).
- Реализация в коде: APP/core/domain/logic_service.py:460-462, 480
- Триггер: apply_financial_rules()
- Действие при нарушении: —
- Связанные правила: BR-043

## BR-043: CuratorStrategy — Boris vs Ivan
- Фича: F-011, F-012, F-017
- Тип: transformation
- Правило: BorisCuratorStrategy: при raw_b2 != 0 → pb2_val = abs(to_decimal_percent(pb2_raw)), broker2_calc = abs(raw_b2). IvanCuratorStrategy: pb2_val=0, broker2_calc=0 (intermediary не сохраняется). Базовая CuratorStrategy: тоже 0.
- Реализация в коде: APP/core/domain/logic_service.py:151-195 (CuratorStrategy, BorisCuratorStrategy, IvanCuratorStrategy)
- Триггер: apply_financial_rules() при curator_config
- Действие при нарушении: —
- Связанные правила: BR-042

## BR-044: Excel formula injection protection
- Фича: F-017, F-018
- Тип: security
- Правило: Значения ячеек санитизируются: если первый символ =, +, -, @ ИЛИ есть tab/newline → prepend "'" перед записью в Excel.
- Реализация в коде: APP/core/domain/logic_service.py:219-236 (_sanitize), APP/core/infra/export_writer.py
- Код: `_SANITIZE_CHARS = frozenset(("=", "+", "-", "@", "\t", "\r", "\n"))` + `return "'" + s`
- Триггер: _build_result_row / write_report
- Действие при нарушении: —
- Связанные правила: —

## BR-045: exclude_keywords → is_critical
- Фича: F-017
- Тип: validation
- Правило: Строки с exclude_keywords (недопустимо, исключить, исключение) в filters → amt=0, is_critical=False (но строка сохраняется в выводе).
- Реализация в коде: APP/core/domain/logic_service.py:394, 453-454
- Код: `is_excluded = any(kw in f_val for kw in self.exclude_kw)` + `if is_excluded: amt = Decimal("0.00")`
- Триггер: apply_financial_rules()
- Действие при нарушении: —
- Связанные правила: BR-039

## BR-046: Drop empty rows (amt=0, tot=0, no brokers, no transit, not is_add)
- Фича: F-017
- Тип: validation
- Правило: Строка отбрасывается если amt=0 И tot=0 И нет broker values И нет transit values И не is_add И не is_critical.
- Реализация в коде: APP/core/domain/logic_service.py:443-451
- Код: `if amt == 0 and tot == 0 and not has_broker_values and not has_transit_values and not is_add and not is_critical: continue`
- Триггер: apply_financial_rules()
- Действие при нарушении: Строка отбрасывается
- Связанные правила: BR-039

## BR-047: NumericParsingError → is_critical error row
- Фича: F-017
- Тип: validation
- Правило: При NumericParsingError в amount или total → строка записывается с is_critical=True (через _build_error_row), НЕ silently substitute zero. Строка попадает в вывод с подсветкой ошибки.
- Реализация в коде: APP/core/domain/logic_service.py:400-421
- Код: `if isinstance(e, NumericParsingError): res.append(self._build_error_row(r, is_critical=True)); continue`
- Триггер: apply_financial_rules() при parse error
- Действие при нарушении: —
- Связанные правила: BR-048

## BR-048: fail-soft для transit/rate/currency_amount
- Фича: F-017
- Тип: transformation
- Правило: transit_obligation, exchange_rate, currency_amount используют _parse_decimal_or_warn (fail-soft): при parse error → Decimal("0.00") + warning flag, строка НЕ отбрасывается.
- Реализация в коде: APP/core/domain/logic_service.py:280-285 (_parse_decimal_or_warn), 343-345
- Код: `transit_val, _ = self._parse_decimal_or_warn(r.get("transit_obligation", 0))`
- Триггер: _build_result_row()
- Действие при нарушении: Decimal("0.00"), is_warn=True
- Связанные правила: BR-047

## BR-049: Transit parse error → warning, не critical
- Фича: F-017
- Тип: validation
- Правило: При NumericParsingError в transit fields → downgrade to warning (is_warn=True), has_transit_values=True (assume transit might exist), строка сохраняется.
- Реализация в коде: APP/core/domain/logic_service.py:429-441
- Код: `has_transit_values = True; is_warn = True`
- Триггер: apply_financial_rules() при transit parse error
- Действие при нарушении: —
- Связанные правила: BR-048

## BR-050: Template warnings — soft_structure не actionable
- Фича: F-008, F-017
- Тип: conditional
- Правило: Template warnings с error_type="soft_structure" не считаются actionable. Статус «completed_with_warnings» только при actionable warnings (error_type != "soft_structure").
- Реализация в коде: APP/core/app_controller.py:669-671
- Код: `has_actionable_warnings = any(error.get("error_type") not in {"soft_structure"} for error in errors)`
- Триггер: Завершение консолидации
- Действие при нарушении: —
- Связанные правила: BR-026

## BR-051: Backup перед перезаписью Excel
- Фича: F-018, F-028
- Тип: transformation
- Правило: Перед перезаписью существующего Excel-файла создаётся backup в подпапке backups/excel_outputs/{stem}/. Timestamp YYYYMMDD_HHMMSS_microseconds в имени. Ротация: keep N последних (по умолч. 10, config.backup.excel_keep).
- Реализация в коде: APP/core/infra/excel_backup.py (backup_existing_excel_output)
- Триггер: write_report перед перезаписью
- Действие при нарушении: Best-effort; backup failure → caller aborts save
- Связанные правила: —

## BR-052: ~$ files (Excel lock) не бэкапятся
- Фича: F-028
- Тип: validation
- Правило: Файлы с префиксом ~$ (Excel lock files) не бэкапятся.
- Реализация в коде: APP/core/infra/excel_backup.py
- Триггер: backup_existing_excel_output()
- Действие при нарушении: —
- Связанные правила: BR-051

## BR-053: atomic_save_workbook
- Фича: F-018, F-029
- Тип: transformation
- Правило: Запись Excel через temp file + rename (atomic) для безопасной записи. Защита от partial writes при crash.
- Реализация в коде: APP/core/infra/utils.py (atomic_save_workbook)
- Триггер: write_report()
- Действие при нарушении: —
- Связанные правила: BR-051

## BR-054: Preflight — output dir exists + writable
- Фича: F-018
- Тип: validation
- Правило: Перед записью отчёта проверяется: output dir exists И writable. Иначе ExportPreflightError.
- Реализация в коде: APP/core/infra/export_writer.py
- Триггер: write_report()
- Действие при нарушении: ExportPreflightError
- Связанные правила: BR-008

## BR-055: write_empty_daily_report для автосверки
- Фича: F-016, F-018
- Тип: transformation
- Правило: При автосверке, если ConsolidationRunError с code="empty_data" для куратора → write_empty_daily_report (пустой отчёт). Для общего → RuntimeError.
- Реализация в коде: APP/core/app_controller.py:877-897 (_write_empty_auto_reconciliation_report), 898-922 (_run_auto_master_report)
- Триггер: run_auto_reconciliation_day() при empty_data
- Действие при нарушении: —
- Связанные правила: BR-027

## BR-056: Автосверка — РСЧ rows == 0 → skip
- Фича: F-016
- Тип: conditional
- Правило: При автосверке, если РСЧ rows == 0 → «Нет данных РСЧ за дату. Автосверка пропущена.» (success, no path).
- Реализация в коде: APP/core/app_controller.py:923-1029 (run_auto_reconciliation_day)
- Триггер: run_auto_reconciliation_day() при пустом РСЧ
- Действие при нарушении: —
- Связанные правила: BR-055

## BR-057: Автосверка — ValueError от build_combined
- Фича: F-016
- Тип: conditional
- Правило: При автосверке, если build_combined raises ValueError → «Сверка за дату: {error}» (success, no path).
- Реализация в коде: APP/core/app_controller.py
- Триггер: run_auto_reconciliation_day() при ValueError
- Действие при нарушении: —
- Связанные правила: BR-056

## BR-058: RSCH — written_rows == 0 → ValueError
- Фича: F-013, F-014
- Тип: validation
- Правило: При сборке РСЧ-отчёта, если written_rows == 0 → ValueError «РСЧ: нет строк за выбранную дату/период».
- Реализация в коде: APP/core/infra/rsch/_build.py
- Триггер: build_rsch_report()
- Действие при нарушении: ValueError
- Связанные правила: —

## BR-059: Ignorируемые листы при ингестии
- Фича: F-020
- Тип: validation
- Правило: При чтении Excel игнорируются листы: «АНАЛИТИКА», «СВОД», листы начинающиеся с «_».
- Реализация в коде: APP/core/infra/ingestion_engine.py, APP/core/infra/ingestion_reader.py
- Триггер: Чтение workbook
- Действие при нарушении: —
- Связанные правила: BR-060

## BR-060: date_matches_target — форматы дат
- Фича: F-020
- Тип: validation
- Правило: Извлечение дат из имён листов: DD.MM.YYYY, DD.MM.yy. Без года — подстановка текущего года. 01.01.1900 игнорируется как невалидная.
- Реализация в коде: APP/core/infra/ingestion_reader.py (extract_date_from_sheet, date_matches_target)
- Триггер: Чтение имён листов
- Действие при нарушении: —
- Связанные правила: BR-059

## BR-061: Retry при чтении Excel — 3 попытки, backoff 1s
- Фича: F-020
- Тип: constraint
- Правило: При ошибке чтения Excel — retry 3 попытки, backoff 1.0s (из config.locking).
- Реализация в коде: APP/core/infra/ingestion_engine.py
- Триггер: Ошибка чтения Excel
- Действие при нарушении: —
- Связанные правила: —

## BR-062: Calamine isolation в subprocess
- Фича: F-020
- Тип: conditional
- Правило: Если config.performance.isolate_calamine=True → Calamine запускается в subprocess для crash resilience.
- Реализация в коде: APP/core/infra/ingestion_engine.py
- Триггер: Чтение Excel при isolate_calamine=True
- Действие при нарушении: —
- Связанные правила: BR-061

## BR-063: get_local_copy для сетевых файлов
- Фича: F-020, F-029
- Тип: transformation
- Правило: Сетевые файлы копируются локально перед чтением (get_local_copy). Кэш по хэшу пути. cleanup_local_copy_cache удаляет старые копии (max_age_days, min_delete_age_seconds).
- Реализация в коде: APP/core/infra/utils.py (get_local_copy, cleanup_local_copy_cache)
- Триггер: Чтение сетевого файла
- Действие при нарушении: —
- Связанные правила: BR-061

## BR-064: path_exists_with_timeout
- Фича: F-029
- Тип: constraint
- Правило: Проверка существования пути с timeout для защиты от зависших SMB-запросов.
- Реализация в коде: APP/core/infra/utils.py (path_exists_with_timeout)
- Триггер: Проверка существования сетевого пути
- Действие при нарушении: Timeout
- Связанные правила: BR-063

## BR-065: Сверка — amount matching
- Фича: F-015
- Тип: validation
- Правило: Суммы master и РСЧ считаются совпадающими если |left - right| <= 0.01. Проверяются income и expense (включая случаи с отрицательными значениями и abs).
- Реализация в коде: APP/core/infra/reconciliation/_resolve.py:21-38 (_amount_equal, _row_amount_matches)
- Код: `return abs(left - right) <= Decimal("0.01")`
- Триггер: Сопоставление строк сверки
- Действие при нарушении: —
- Связанные правила: BR-066, BR-067

## BR-066: Сверка — executor matching (FIX-000)
- Фича: F-015
- Тип: validation
- Правило: Исполнители master и РСЧ считаются совпадающими если:
  1. canonical text совпадает ИЛИ compact text совпадает
  2. executor alias keys пересекаются
  3. tokens (len >= 2) — one is subset of other, НО single-token vs multi-token → не совпадает (FIX-000: предотвращает «ООО» == «ООО Ромашка»)
- Реализация в коде: APP/core/infra/reconciliation/_resolve.py:41-54 (_executor_matches)
- Код: single-token guard (len(left_tokens)==1 and len(right_tokens)>=1 → проверка только если left_tokens==right_tokens и compact совпадает)
- Триггер: Сопоставление строк сверки
- Действие при нарушении: —
- Связанные правила: BR-065

## BR-067: Сверка — customer matching (loose + weak)
- Фича: F-015
- Тип: validation
- Правило: Заказчики master и РСЧ сопоставляются:
  1. _customer_matches: normalize, substring (left in right или right in left)
  2. _customer_matches_loose: compact text (len >= 6) substring ИЛИ ≥2 common tokens
  3. _customer_matches_weak: ≥2 weak customer tokens
- Реализация в коде: APP/core/infra/reconciliation/_resolve.py:57-92
- Триггер: Сопоставление строк сверки
- Действие при нарушении: —
- Связанные правила: BR-065, BR-068

## BR-068: Customer aliases в сверке
- Фича: F-015, F-038
- Тип: transformation
- Правило: Customer aliases (master_customer ↔ rsch_customer) используются сверкой для автоматического сопоставления. Точное совпадение суммы + исполнителя + заказчика (или алиаса) → «Сверено». Частичное → «Проверить» (подсказка добавить алиас).
- Реализация в коде: APP/core/infra/reconciliation/_build.py, APP/core/infra/customer_alias_repo.py
- Триггер: Сопоставление строк сверки
- Действие при нарушении: —
- Связанные правила: BR-067

## BR-069: Customer alias CRUD
- Фича: F-038
- Тип: validation
- Правило: CRUD алиасов: add_alias, update_alias, delete_alias, get_all_aliases. Поля master_customer (trim), rsch_customer (trim), notes. updated_at timestamp. alias_repo=None → get_customer_aliases возвращает [], add/update/delete → RuntimeError.
- Реализация в коде: APP/core/infra/customer_alias_repo.py, APP/core/app_controller.py:1118-1138
- Триггер: CRUD операции с алиасами
- Действие при нарушении: RuntimeError при alias_repo=None
- Связанные правила: BR-068

## BR-070: Сверка — resolve target date
- Фича: F-015
- Тип: validation
- Правило: При сверке определяется target date:
  1. Если передана явно — проверяется наличие листа за дату в обоих файлах
  2. Если нет — ищутся common dates (полные DD.MM.YYYY + day-month DD.MM)
  3. Если 1 common date — используется
  4. Если 0 — ValueError «Не найдена общая дата»
  5. Если >1 — ValueError «Выберите нужную дату»
- Реализация в коде: APP/core/infra/reconciliation/_resolve.py:152-175 (_resolve_target_date), 187-220 (_resolve_combined_target_date)
- Триггер: build_combined_reconciliation_report()
- Действие при нарушении: ValueError
- Связанные правила: BR-060

## BR-071: RSCH — выбор файлов (saved sources)
- Фича: F-013, F-039
- Тип: conditional
- Правило: При сборке РСЧ: askyesnocancel «Использовать сохраненный набор?». Да → saved sources (несуществующие отфильтровываются + warning). Нет → новый выбор через multi-file dialog. Сохранение recent_sources и last_output_dir в config.rsch.
- Реализация в коде: APP/core/ui/gui_commands/_rsch.py (_resolve_rsch_sources)
- Триггер: run_rsch_report()
- Действие при нарушении: —
- Связанные правила: BR-003

## BR-072: RSCH — стили income/expense/warning
- Фича: F-013
- Тип: transformation
- Правило: При записи РСЧ-отчёта применяются стили: income (зелёный), expense (красный), warning (жёлтый).
- Реализация в коде: APP/core/infra/rsch/_format.py, APP/core/infra/rsch/_template.py
- Триггер: build_rsch_report()
- Действие при нарушении: —
- Связанные правила: BR-058

## BR-073: max_workers для ThreadPoolExecutor
- Фича: F-040
- Тип: constraint
- Правило: max_workers = min(32, os.cpu_count() * 2) по умолчанию. Override из config.performance.max_workers, min 1. thread_name_prefix="hermes-worker".
- Реализация в коде: APP/core/app/performance.py (default_max_workers, resolve_max_workers)
- Код: `default_max_workers = min(32, os.cpu_count() * 2)`
- Триггер: Создание ThreadPoolExecutor
- Действие при нарушении: —
- Связанные правила: BR-013

## BR-074: OperationState — double-click protection
- Фича: F-024
- Тип: validation
- Правило: begin() только если не is_busy. Иначе — отказ (double-click protection).
- Реализация в коде: APP/core/ui/operation_state.py
- Триггер: begin() операции
- Действие при нарушении: Отказ
- Связанные правила: BR-029

## BR-075: Toast — до 3 одновременно
- Фича: F-026
- Тип: constraint
- Правило: До 3 toast-уведомлений одновременно. Новые вытесняют старые. Duration: success=4000ms, error=6000ms. Fallback: если ToastManager недоступен → messagebox.
- Реализация в коде: APP/core/ui/toast.py
- Триггер: show toast
- Действие при нарушении: Fallback на messagebox
- Связанные правила: —

## BR-076: ThemeManager — system theme polling
- Фича: F-027
- Тип: constraint
- Правило: При теме «system» — polling каждые 5s для детекта изменения темы ОС. Windows: registry HKCU\Control Panel\Colors. macOS: osascript. Linux: gsettings.
- Реализация в коде: APP/core/ui/system_theme.py, APP/core/ui/theme.py
- Триггер: Тема = system
- Действие при нарушении: —
- Связанные правила: —

## BR-077: UIPreferences — валидация
- Фича: F-022
- Тип: validation
- Правило: UIPreferences валидируются: theme (light/dark/system), scale_mode (auto/manual), user_scale (0.80–1.50), density (compact/normal/comfortable), sidebar_width (0–800).
- Реализация в коде: APP/core/ui/ui_settings.py, APP/core/ui/gui_master_settings.py
- Триггер: Apply/OK в settings dialog
- Действие при нарушении: Отклонение невалидных значений
- Связанные правила: BR-076

## BR-078: Settings — deep copy, live preview
- Фича: F-022
- Тип: transformation
- Правило: Settings dialog использует deep copy конфига. Изменения не применяются до Apply/OK. Cancel → восстановление snapshot темы/масштаба/плотности. Live preview темы/масштаба.
- Реализация в коде: APP/core/ui/ui_settings.py, APP/core/ui/gui_master_settings.py
- Триггер: Settings dialog
- Действие при нарушении: —
- Связанные правила: BR-077

## BR-079: Geometry — save/load
- Фича: F-031
- Тип: transformation
- Правило: Геометрия окна сохраняется в ~/.master_report_geometry. При запуске: если сохранённая геометрия в пределах экрана — используется; иначе — auto-fit (82% ширины, 88% высоты, центрирование). minsize: max(640, 50% screen_w) × max(420, 50% screen_h).
- Реализация в коде: APP/core/ui/geometry.py
- Триггер: Запуск / закрытие окна
- Действие при нарушении: Auto-fit fallback
- Связанные правила: —

## BR-080: Data loss log — redact PII
- Фича: F-033
- Тип: security
- Правило: При записи в logs/data_loss.log денежные суммы редактируются: _AMOUNT_RE = \d{3,}[.,]\d{2} → замена. record_loss записывает context (файл, лист, строка, причина). Thread-safe (_LOCK).
- Реализация в коде: APP/core/domain/data_loss_log.py
- Триггер: data_loss событие
- Действие при нарушении: —
- Связанные правила: —

## BR-081: SQLite — WAL mode + integrity_check
- Фича: F-023
- Тип: constraint
- Правило: SQLite в WAL mode (PRAGMA journal_mode=WAL). PRAGMA integrity_check при GUI-старте; warning при failure. WAL checkpoint(TRUNCATE) при close.
- Реализация в коде: APP/core/infra/db_connection.py, APP/core/infra/session_repo.py:230-251
- Триггер: init_db / close
- Действие при нарушении: Warning при integrity failure
- Связанные правила: BR-082

## BR-082: SQLite — миграции
- Фича: F-023
- Тип: transformation
- Правило: Миграции применяются при init_db: 001 (NUMERIC→TEXT для financial columns), 002 (customer_aliases). Таблица _migrations отслеживает применённые.
- Реализация в коде: APP/db_schema.sql, APP/migrations/, APP/core/infra/db_connection.py
- Триггер: init_db()
- Действие при нарушении: —
- Связанные правила: BR-081

## BR-083: DBWriterThread — асинхронная запись
- Фича: F-023
- Тип: transformation
- Правило: staging_data записываются асинхронно через DBWriterThread (queue-based). wait_for_writes — блокирующее ожидание при shutdown.
- Реализация в коде: APP/core/infra/staging_repo.py, APP/core/infra/session_repo.py:226-228
- Триггер: save_staging_data / shutdown
- Действие при нарушении: —
- Связанные правила: BR-081

## BR-084: Session status values
- Фича: F-023
- Тип: constraint
- Правило: Session status может быть: running, completed, completed_with_warnings, failed, cancelled. Другие значения не допускаются.
- Реализация в коде: APP/core/app_controller.py (update_session_status calls), APP/core/infra/session_repo.py:177-193
- Триггер: update_session_status()
- Действие при нарушении: —
- Связанные правила: BR-025, BR-026

## BR-085: Headless — формат даты DD.MM.YYYY
- Фича: F-002
- Тип: validation
- Правило: В headless-режиме флаг --date парсится через datetime.strptime(v, "%d.%m.%Y"). При ошибке — CRITICAL log + exit(1).
- Реализация в коде: APP/headless_run.py
- Триггер: headless_run --date
- Действие при нарушении: CRITICAL log, exit(1)
- Связанные правила: BR-038

## BR-086: Headless — timeout
- Фича: F-002
- Тип: constraint
- Правило: В headless-режиме timeout из env HEADLESS_RUN_TIMEOUT (по умолч. 600с). При превышении — cancel_event.set() + exit(1).
- Реализация в коде: APP/headless_run.py
- Триггер: headless_run
- Действие при нарушении: cancel + exit(1)
- Связанные правила: BR-029

## BR-087: Headless — signal handling
- Фича: F-002
- Тип: conditional
- Правило: SIGTERM/SIGINT → cancel_event.set() + sys.exit(1). Graceful shutdown в finally-блоке.
- Реализация в коде: APP/headless_run.py
- Триггер: SIGTERM/SIGINT
- Действие при нарушении: —
- Связанные правила: BR-029

## BR-088: open_path — OS-specific
- Фича: F-035
- Тип: transformation
- Правило: Открытие файла/папки: Windows os.startfile, macOS open, Linux xdg-open.
- Реализация в коде: APP/core/infra/utils.py (open_path)
- Триггер: open_path()
- Действие при нарушении: —
- Связанные правила: —

## BR-089: open_employee_file — multiple files dialog
- Фича: F-035
- Тип: conditional
- Правило: При открытии файла сотрудника: 1 файл → открыть; >1 → askyesnocancel (Да=все файлы, Нет=папки, Отмена=ничего).
- Реализация в коде: APP/core/ui/gui_commands/_employee.py
- Триггер: open_employee_file()
- Действие при нарушении: —
- Связанные правила: BR-088

## BR-090: Копирование должников в буфер
- Фича: F-036
- Тип: transformation
- Правило: get_missing_names: сотрудники без «🟢 ГОТОВО». Формат: «Должники за DD.MM:\n» + «- {name}». clipboard_clear + clipboard_append. Toast info 2500ms.
- Реализация в коде: APP/core/ui/gui_commands/_employee.py, APP/core/view_models/employee_list_viewmodel.py
- Триггер: copy_debtors
- Действие при нарушении: —
- Связанные правила: BR-011
