# User Stories

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Источник: docs/features/inventory.md + docs/business/rules.md + docs/business/invariants.md + docs/business/state-machines.md
- Всего user stories: 42 (по одной на фичу)
- Всего сценариев: 252 (минимум 6 на фичу)

---

## US-001: Запуск приложения (GUI)
- Фича: F-001
- Приоритет: P0
- Роль: Пользователь (оператор)

### US-001-S1: Успешный запуск через ЗАПУСК.bat
- Given: Python 3.12+ установлен в .venv, python-calamine доступен, config.yaml валиден
- When: Пользователь запускает ЗАПУСК.bat
- Then: Приложение запускается, DPI-awareness установлен, RotatingFileHandler инициализирован (startup_log.txt), Bootstrap.setup() собирает все компоненты, GuiMaster создаёт главное окно
- And: Лог содержит «Bootstrap setup OK», окно видимо на экране
- Бизнес-правила: BR-001, BR-002, BR-003
- Инварианты: INV-007
- Тип теста: positive

### US-001-S2: Запуск без python-calamine
- Given: .venv существует, python-calamine удалён/переименован
- When: Пользователь запускает APP/main.py
- Then: RuntimeError «Не найдена обязательная библиотека python-calamine», messagebox показан, sys.exit(1)
- And: Лог содержит CRITICAL запись
- Бизнес-правила: BR-001
- Инварианты: INV-007
- Тип теста: negative

### US-001-S3: Запуск с повреждённым config.yaml
- Given: config.yaml содержит невалидный YAML (синтаксическая ошибка)
- When: Пользователь запускает приложение
- Then: Pydantic-валидация падает, warning в лог, safe defaults применены, приложение запускается
- And: Пользователь видит главное окно (возможно с warning toast)
- Бизнес-правила: BR-003, BR-004
- Тип теста: negative

### US-001-S4: Запуск без config.yaml (первый запуск)
- Given: config.yaml не существует, config.example.yaml существует
- When: Пользователь запускает приложение
- Then: config.yaml создаётся из config.example.yaml, приложение запускается
- And: config.yaml имеет права 0o600
- Бизнес-правила: BR-003, BR-005
- Тип теста: edge

### US-001-S5: Path traversal в config.yaml
- Given: config.yaml содержит путь "../../../etc/passwd" в секции paths
- When: Пользователь запускает приложение
- Then: ValueError при _validate_path_safety, приложение не запускается
- And: Лог содержит ошибку path traversal
- Бизнес-правила: BR-006
- Инварианты: INV-004
- Тип теста: security

### US-001-S6: Graceful shutdown при закрытии окна
- Given: Приложение запущено, выполняется консолидация
- When: Пользователь нажимает X (WM_DELETE_WINDOW)
- Then: shutdown() вызывается: persistence.wait_for_writes(), executor.shutdown(wait=True), join потоков (timeout 10s), persistence.close()
- And: WAL checkpoint(TRUNCATE) выполнен, БД закрыта корректно
- Бизнес-правила: BR-087 (аналог)
- Инварианты: INV-008, INV-009, INV-023
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-001-S1 | positive | BR-001, BR-002, BR-003 | INV-007 | pending |
| US-001-S2 | negative | BR-001 | INV-007 | pending |
| US-001-S3 | negative | BR-003, BR-004 | — | pending |
| US-001-S4 | edge | BR-003, BR-005 | — | pending |
| US-001-S5 | security | BR-006 | INV-004 | pending |
| US-001-S6 | edge | BR-087 | INV-008, INV-009, INV-023 | pending |

---

## US-002: Headless-режим (CLI)
- Фича: F-002
- Приоритет: P0
- Роль: CI/CD система или оператор

### US-002-S1: Успешный headless запуск с --date
- Given: .venv настроен, config.yaml валиден, файлы сотрудников доступны
- When: CI запускает `APP/headless_run.py --date 25.06.2026`
- Then: Консолидация запускается за 25.06.2026, session создаётся, отчёт записывается
- And: Process exit code 0
- Бизнес-правила: BR-085, BR-025
- Тип теста: positive

### US-002-S2: Headless с неверным форматом даты
- Given: .venv настроен
- When: CI запускает `APP/headless_run.py --date 2026-06-25` (ISO формат вместо DD.MM.YYYY)
- Then: datetime.strptime падает, CRITICAL log, exit(1)
- Бизнес-правила: BR-085
- Тип теста: negative

### US-002-S3: Headless timeout
- Given: HEADLESS_RUN_TIMEOUT=10 (env), консолидация занимает >10s
- When: CI запускает headless_run
- Then: Через 10s cancel_event.set(), exit(1)
- Бизнес-правила: BR-086
- Тип теста: edge

### US-002-S4: Headless SIGTERM
- Given: Headless запущен, выполняется консолидация
- When: CI отправляет SIGTERM
- Then: cancel_event.set(), graceful shutdown в finally, exit(1)
- Бизнес-правила: BR-087
- Инварианты: INV-011
- Тип теста: edge

### US-002-S5: Headless без --date (все даты)
- Given: Файлы сотрудников содержат данные за несколько дат
- When: CI запускает `APP/headless_run.py` (без --date)
- Then: Консолидация запускается за все даты, session_type="all_dates"
- Бизнес-правила: BR-025
- Тип теста: positive

### US-002-S6: Headless с пустым результатом
- Given: Файлы сотрудников не содержат данных за указанную дату
- When: CI запускает `APP/headless_run.py --date 01.01.2020`
- Then: ConsolidationRunError empty_data, exit code 0 (low-severity accepted risk)
- Бизнес-правила: BR-027
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-002-S1 | positive | BR-085, BR-025 | — | pending |
| US-002-S2 | negative | BR-085 | — | pending |
| US-002-S3 | edge | BR-086 | — | pending |
| US-002-S4 | edge | BR-087 | INV-011 | pending |
| US-002-S5 | positive | BR-025 | — | pending |
| US-002-S6 | edge | BR-027 | — | pending |

---

## US-003: Управление конфигурацией
- Фича: F-003
- Приоритет: P0
- Роль: Система (internal)

### US-003-S1: Загрузка валидного config.yaml
- Given: config.yaml существует, все секции валидны
- When: Bootstrap.setup() загружает конфиг
- Then: PathsConfig, DatabaseConfig, LockingConfig, NetworkConfig валидны, пути разрешены
- Бизнес-правила: BR-003, BR-004
- Тип теста: positive

### US-003-S2: Невалидная секция paths
- Given: config.yaml содержит paths.source_roots = "not_a_list" (строка вместо списка)
- When: Bootstrap загружает конфиг
- Then: Pydantic ValidationError, warning в лог, safe defaults применены
- Бизнес-правила: BR-004
- Тип теста: negative

### US-003-S3: Сохранение config с chmod 0o600
- Given: Пользователь изменил настройки в Settings dialog
- When: save_config() вызывается
- Then: config.yaml записан, os.chmod(path, 0o600) выполнен
- Бизнес-правила: BR-005
- Инварианты: INV-012
- Тип теста: positive

### US-003-S4: Относительный путь в config
- Given: config.yaml содержит paths.master_report = "output/report.xlsx" (относительный)
- When: Bootstrap загружает конфиг
- Then: Путь разрешается в абсолютный относительно config_dir
- Бизнес-правила: BR-003
- Тип теста: edge

### US-003-S5: Path traversal через config
- Given: config.yaml содержит "../../../etc/passwd"
- When: Bootstrap загружает конфиг
- Then: ValueError от _validate_path_safety, запуск блокирован
- Бизнес-правила: BR-006
- Инварианты: INV-004
- Тип теста: security

### US-003-S6: Stale app-local path
- Given: config.yaml содержит путь от другой инсталляции (C:\OldInstall\output)
- When: Bootstrap загружает конфиг
- Then: _is_stale_app_local_path детектит, путь перезаписан на текущий app_root
- Бизнес-правила: BR-007
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-003-S1 | positive | BR-003, BR-004 | — | pending |
| US-003-S2 | negative | BR-004 | — | pending |
| US-003-S3 | positive | BR-005 | INV-012 | pending |
| US-003-S4 | edge | BR-003 | — | pending |
| US-003-S5 | security | BR-006 | INV-004 | pending |
| US-003-S6 | edge | BR-007 | — | pending |

---

## US-004: Обновление статусов сотрудников (Refresh)
- Фича: F-004
- Приоритет: P0
- Роль: Пользователь

### US-004-S1: Успешный refresh — все сотрудники готовы
- Given: 3 сотрудника с файлами, все файлы содержат лист за 25.06.2026
- When: Пользователь нажимает «🔄 Обновить статус» (дата = 25.06.2026)
- Then: Все 3 сотрудника показывают «🟢 ГОТОВО», progress bar 0→100%
- Бизнес-правила: BR-011
- Тип теста: positive

### US-004-S2: Refresh — файл сотрудника не существует
- Given: Сотрудник «Иван» привязан к Q:\reports\ivan.xlsx, файл не существует
- When: Пользователь нажимает «Обновить статус»
- Then: «Иван» показывает «🔴 НЕТ ФАЙЛА»
- Бизнес-правила: BR-011
- Тип теста: negative

### US-004-S3: Refresh — файл существует, но листа за дату нет
- Given: Файл сотрудника существует, содержит листы за 20.06 и 21.06, но не за 25.06
- When: Пользователь нажимает «Обновить статус» (дата = 25.06.2026)
- Then: Сотрудник показывает «🟠 НЕТ ДАТЫ»
- Бизнес-правила: BR-011
- Тип теста: negative

### US-004-S4: Refresh — дата в будущем
- Given: Сегодня 25.06.2026, пользователь выбрал 30.06.2026
- When: Пользователь нажимает «Обновить статус»
- Then: Все сотрудники показывают «🟠 НЕТ ДАТЫ» (нельзя собрать отчёт за будущее)
- Бизнес-правила: BR-012
- Тип теста: edge

### US-004-S5: Refresh — timeout 30s на зависшем SMB
- Given: Сетевой диск Q: не отвечает, 5 сотрудников на Q:
- When: Пользователь нажимает «Обновить статус»
- Then: Через 30s as_completed timeout, незавершённые futures cancel(), partial result показывается, зависшие сотрудники — [ERR] ОШИБКА
- Бизнес-правила: BR-013
- Тип теста: edge

### US-004-S6: Refresh — мастер-файл занят
- Given: Мастер-отчёт открыт в Excel (master lock занят)
- When: Пользователь нажимает «Обновить статус»
- Then: Toast error «Мастер-файл занят в Excel», пустой результат
- Бизнес-правила: BR-009
- Тип теста: negative

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-004-S1 | positive | BR-011 | — | pending |
| US-004-S2 | negative | BR-011 | — | pending |
| US-004-S3 | negative | BR-011 | — | pending |
| US-004-S4 | edge | BR-012 | — | pending |
| US-004-S5 | edge | BR-013 | — | pending |
| US-004-S6 | negative | BR-009 | — | pending |

---

## US-005: Управление сотрудниками
- Фича: F-005
- Приоритет: P0
- Роль: Пользователь

### US-005-S1: Добавление сотрудника
- Given: Список сотрудников пуст
- When: Пользователь вводит «Иван Петров» и нажимает «Добавить»
- Then: «Иван Петров» добавлен в employees.yaml, discovery_cache инвалидирован, таблица обновлена
- Бизнес-правила: BR-016, BR-017
- Тип теста: positive

### US-005-S2: Добавление сотрудника с пустым именем
- Given: Поле ввода имени пусто
- When: Пользователь нажимает «Добавить»
- Then: Имя игнорируется (trim → пусто), сотрудник не добавлен
- Бизнес-правила: BR-016
- Тип теста: negative

### US-005-S3: Удаление сотрудника
- Given: Сотрудник «Иван Петров» существует
- When: Пользователь выбирает «Иван Петров» и нажимает «Удалить»
- Then: «Иван Петров» удалён из employees.yaml, discovery_cache инвалидирован
- Бизнес-правила: BR-017
- Тип теста: positive

### US-005-S4: Привязка файла к сотруднику
- Given: Сотрудник «Иван Петров» существует, файл Q:\reports\ivan.xlsx существует
- When: Пользователь привязывает файл (attach_files, режим replace)
- Then: MD5, inode, absolute path вычислены, путь сохранён в employees.yaml, дедупликация применена
- Бизнес-правила: BR-018
- Тип теста: positive

### US-005-S5: Привязка дубликата пути
- Given: Сотрудник уже имеет привязку Q:\reports\ivan.xlsx
- When: Пользователь привязывает тот же файл снова (режим append)
- Then: Дубликат отфильтрован по строковому представлению пути, путь не дублируется
- Бизнес-правила: BR-018
- Тип теста: edge

### US-005-S6: Добавление дубликата имени
- Given: Сотрудник «Иван Петров» уже существует
- When: Пользователь добавляет «Иван Петров» снова
- Then: Дубликат добавлен (дедупликация не проверяется на уровне config)
- Бизнес-правила: BR-016
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-005-S1 | positive | BR-016, BR-017 | — | pending |
| US-005-S2 | negative | BR-016 | — | pending |
| US-005-S3 | positive | BR-017 | — | pending |
| US-005-S4 | positive | BR-018 | — | pending |
| US-005-S5 | edge | BR-018 | — | pending |
| US-005-S6 | edge | BR-016 | — | pending |

---

## US-006: Выбор даты
- Фича: F-006
- Приоритет: P0
- Роль: Пользователь

### US-006-S1: Выбор даты через DateEntry
- Given: Приложение запущено, DateEntry виден
- When: Пользователь выбирает 25.06.2026
- Then: Дата установлена, debounce 250мс, затем refresh статусов запускается
- Бизнес-правила: BR-020
- Тип теста: positive

### US-006-S2: Быстрые клики по дате (debounce)
- Given: Пользователь быстро меняет дату 5 раз за 1 секунду
- When: Пользователь кликает разные даты
- Then: Debounce 250мс предотвращает множественные refresh, только последний запуск
- Бизнес-правила: BR-020
- Тип теста: edge

### US-006-S3: Период по умолчанию — 1-е число
- Given: Сегодня 1 июля 2026
- When: Пользователь открывает приложение
- Then: Период авто-выбран: 1 июня 2026 — 30 июня 2026 (предыдущий месяц)
- Бизнес-правила: BR-021
- Тип теста: edge

### US-006-S4: Период по умолчанию — не 1-е число
- Given: Сегодня 25 июня 2026
- When: Пользователь открывает приложение
- Then: Период авто-выбран: 1 июня 2026 — 25 июня 2026 (с 1-го до сегодня)
- Бизнес-правила: BR-021
- Тип теста: edge

### US-006-S5: Невалидный период (start > end)
- Given: Пользователь выбрал start_date=30.06.2026, end_date=01.06.2026
- When: Пользователь нажимает «СОБРАТЬ ЗА ПЕРИОД»
- Then: messagebox.showerror, операция отменена
- Бизнес-правила: BR-022
- Тип теста: negative

### US-006-S6: Смена даты обновляет статусы
- Given: Статусы показывают «ГОТОВО» за 25.06, пользователь меняет на 26.06
- When: Дата изменена
- Then: Через 250мс refresh запускается, статусы обновляются для 26.06
- Бизнес-правила: BR-020, BR-011
- Тип теста: positive

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-006-S1 | positive | BR-020 | — | pending |
| US-006-S2 | edge | BR-020 | — | pending |
| US-006-S3 | edge | BR-021 | — | pending |
| US-006-S4 | edge | BR-021 | — | pending |
| US-006-S5 | negative | BR-022 | — | pending |
| US-006-S6 | positive | BR-020, BR-011 | — | pending |

---

## US-007: Выбор куратора
- Фича: F-007
- Приоритет: P0
- Роль: Пользователь

### US-007-S1: Выбор «Общий отчет»
- Given: Список сотрудников содержит 10 человек (5 с «борис» в имени, 3 с «иван», 2 других)
- When: Пользователь выбирает «Общий отчет»
- Then: curator=None, все 10 сотрудников (минус excluded_keys) включены
- Бизнес-правила: BR-023
- Тип теста: positive

### US-007-S2: Выбор «Куратор Борис»
- Given: 10 сотрудников (5 с «борис» в имени)
- When: Пользователь выбирает «Куратор Борис»
- Then: curator="boris", фильтр по employees_key, 5 сотрудников с «борис» включены
- Бизнес-правила: BR-023
- Тип теста: positive

### US-007-S3: Выбор «Куратор Иван»
- Given: 10 сотрудников (3 с «иван» в имени)
- When: Пользователь выбирает «Куратор Иван»
- Then: curator="ivan", 3 сотрудника с «иван» включены
- Бизнес-правила: BR-023
- Тип теста: positive

### US-007-S4: Куратор с enabled=False
- Given: config.curators.boris.enabled=False
- When: Пользователь выбирает «Куратор Борис» и запускает консолидацию
- Then: curator_config=None, отчёт куратора не формируется
- Бизнес-правила: BR-024
- Тип теста: negative

### US-007-S5: Фильтр case-insensitive
- Given: Сотрудник «БОРИС Иванов» (uppercase)
- When: Пользователь выбирает «Куратор Борис»
- Then: «БОРИС Иванов» включён (case-insensitive substring match)
- Бизнес-правила: BR-023
- Тип теста: edge

### US-007-S6: Нет сотрудников для куратора
- Given: Ни один сотрудник не содержит «борис» в имени
- When: Пользователь выбирает «Куратор Борис» и запускает консолидацию
- Then: employees_map пуст, session failed, on_failure_code="no_files"
- Бизнес-правила: BR-023, BR-028
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-007-S1 | positive | BR-023 | — | pending |
| US-007-S2 | positive | BR-023 | — | pending |
| US-007-S3 | positive | BR-023 | — | pending |
| US-007-S4 | negative | BR-024 | — | pending |
| US-007-S5 | edge | BR-023 | — | pending |
| US-007-S6 | edge | BR-023, BR-028 | — | pending |

---

## US-008: Консолидация дневного отчёта
- Фича: F-008
- Приоритет: P0
- Роль: Пользователь

### US-008-S1: Успешная консолидация дня
- Given: 5 сотрудников с «ГОТОВО» за 25.06.2026, мастер-файл не занят
- When: Пользователь нажимает «⚡ СОБРАТЬ ДЕНЬ»
- Then: Session создана (running), run_engine читает файлы, logic_service.consolidate применяет правила, writer.write_report записывает Excel, session completed
- And: Progress bar 0→100%, toast success, мастер-отчёт создан
- Бизнес-правила: BR-025, BR-026, BR-027
- Инварианты: INV-002
- Тип теста: positive

### US-008-S2: Консолидация — мастер-файл занят
- Given: Мастер-отчёт открыт в Excel
- When: Пользователь нажимает «СОБРАТЬ ДЕНЬ»
- Then: is_file_writable=False, error toast, операция отменена
- Бизнес-правила: BR-008
- Тип теста: negative

### US-008-S3: Консолидация — нет данных за дату
- Given: Файлы сотрудников не содержат данных за 25.06.2026
- When: Пользователь нажимает «СОБРАТЬ ДЕНЬ»
- Then: consolidated_data пуст, session failed, on_failure_code="empty_data", «Нет данных за дату»
- Бизнес-правила: BR-027
- Тип теста: negative

### US-008-S4: Консолидация с template warnings
- Given: Файлы содержат данные, но с soft_structure warnings
- When: Пользователь нажимает «СОБРАТЬ ДЕНЬ»
- Then: Session completed (не completed_with_warnings, т.к. soft_structure не actionable)
- Бизнес-правила: BR-026, BR-050
- Тип теста: edge

### US-008-S5: Отмена консолидации
- Given: Консолидация выполняется (session running)
- When: Пользователь нажимает «Cancel»
- Then: cancel_event.set(), на ближайшей контрольной точке операция останавливается, session cancelled, .partial.xlsx для незавершённых файлов
- Бизнес-правила: BR-029, BR-030
- Инварианты: INV-011
- Тип теста: edge

### US-008-S6: Предупреждение о должниках
- Given: 3 из 5 сотрудников не сдали отчёт (нет «ГОТОВО»)
- When: Пользователь нажимает «СОБРАТЬ ДЕНЬ»
- Then: messagebox.askyesno «Не сдано отчетов: 3. Продолжить?»
- Бизнес-правила: BR-010
- Тип теста: edge

### US-008-S7: Excel formula injection в данных
- Given: Файл сотрудника содержит ячейку "=CMD('calc')"
- When: Консолидация выполняется
- Then: _sanitize prepend "'", ячейка записана как "'=CMD('calc')", formula injection предотвращён
- Бизнес-правила: BR-044
- Инварианты: INV-003
- Тип теста: security

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-008-S1 | positive | BR-025, BR-026, BR-027 | INV-002 | pending |
| US-008-S2 | negative | BR-008 | — | pending |
| US-008-S3 | negative | BR-027 | — | pending |
| US-008-S4 | edge | BR-026, BR-050 | — | pending |
| US-008-S5 | edge | BR-029, BR-030 | INV-011 | pending |
| US-008-S6 | edge | BR-010 | — | pending |
| US-008-S7 | security | BR-044 | INV-003 | pending |

---

## US-017: Применение финансовых правил (бизнес-логика)
- Фича: F-017
- Приоритет: P0
- Роль: Система (internal)

### US-017-S1: Валидная строка проходит валидацию
- Given: Строка {customer: "ООО Ромашка", contractor: "ИП Иванов", amount: "1000.00", total: "1100.00"}
- When: Validator.validate_row() вызывается
- Then: FinancialRowSchema валидна, строка проходит (return True)
- Бизнес-правила: BR-031, BR-036
- Тип теста: positive

### US-017-S2: Пустая строка отбрасывается
- Given: Строка {customer: "", contractor: "", filters: "", amount: "0"}
- When: Validator.validate_row() вызывается
- Then: Строка отбрасывается (return False)
- Бизнес-правила: BR-031
- Тип теста: negative

### US-017-S3: Header-like строка отбрасывается
- Given: Строка {customer: "заказчик", contractor: "исполнитель", amount: "сумма платежа"}
- When: Validator.validate_row() вызывается
- Then: _is_header_like=True, строка отбрасывается
- Бизнес-правила: BR-032
- Тип теста: negative

### US-017-S4: «Приходько» не совпадает с «приход» (word-boundary)
- Given: Строка {customer: "Приходько и Ко", amount: "500.00"}
- When: Validator.validate_row() вызывается
- Then: _is_header_like=False (word-boundary matching), строка проходит
- Бизнес-правила: BR-032
- Тип теста: edge

### US-017-S5: Комиссия 0.5 → 50% (percent mode)
- Given: commission_is_percent=True, commission="0.5"
- When: _resolve_commission() вызывается
- Then: |0.5| <= 1 → 0.5 * 100 = 50.00 (Decimal, ROUND_HALF_UP)
- Бизнес-правила: BR-041
- Тип теста: edge

### US-017-S6: Комиссия 15 → 15 (absolute mode)
- Given: commission_is_percent=True, commission="15"
- When: _resolve_commission() вызывается
- Then: |15| > 1 → abs(15) = 15.00
- Бизнес-правила: BR-041
- Тип теста: edge

### US-017-S7: NumericParsingError → is_critical error row
- Given: Строка {amount: "не число", total: "1000"}
- When: apply_financial_rules() вызывается
- Then: NumericParsingError, _build_error_row(is_critical=True), строка в выводе с подсветкой
- Бизнес-правила: BR-047
- Инварианты: INV-001
- Тип теста: negative

### US-017-S8: exclude_keywords → amt=0
- Given: Строка {filters: "исключить", amount: "1000"}
- When: apply_financial_rules() вызывается
- Then: is_excluded=True, amt=Decimal("0.00"), строка сохраняется
- Бизнес-правила: BR-045
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-017-S1 | positive | BR-031, BR-036 | — | pending |
| US-017-S2 | negative | BR-031 | — | pending |
| US-017-S3 | negative | BR-032 | — | pending |
| US-017-S4 | edge | BR-032 | — | pending |
| US-017-S5 | edge | BR-041 | — | pending |
| US-017-S6 | edge | BR-041 | — | pending |
| US-017-S7 | negative | BR-047 | INV-001 | pending |
| US-017-S8 | edge | BR-045 | — | pending |

---

## US-015: Ручная сверка с РСЧ
- Фича: F-015
- Приоритет: P0
- Роль: Пользователь

### US-015-S1: Успешная сверка — точное совпадение
- Given: Мастер-отчёт и РСЧ-отчёт содержат строку {income: 1000, executor: "ООО Ромашка", customer: "Заказчик1"}
- When: Пользователь запускает «✅ СВЕРИТЬ С РСЧ»
- Then: Строка помечена «Сверено» (amount + executor + customer совпадают)
- Бизнес-правила: BR-065, BR-066, BR-067
- Инварианты: INV-020, INV-021
- Тип теста: positive

### US-015-S2: Сверка — расхождение по сумме
- Given: Мастер: income=1000, РСЧ: income=1005
- When: Пользователь запускает сверку
- Then: |1000-1005|=5 > 0.01, строка помечена «Проверить»
- Бизнес-правила: BR-065
- Инварианты: INV-020
- Тип теста: negative

### US-015-S3: FIX-000 — «ООО» не совпадает с «ООО Ромашка»
- Given: Мастер: executor="ООО", РСЧ: executor="ООО Ромашка"
- When: _executor_matches() вызывается
- Then: Single-token guard: left_tokens={"ООО"}, right_tokens={"ООО","Ромашка"}, len(left)==1 and len(right)>=1 → не совпадает (если left_tokens != right_tokens)
- Бизнес-правила: BR-066
- Инварианты: INV-021
- Тип теста: edge

### US-015-S4: Сверка с customer alias
- Given: Мастер: customer="ООО Заказчик", РСЧ: customer="Заказчик ООО", alias существует
- When: Пользователь запускает сверку
- Then: alias использован, строка помечена «Сверено»
- Бизнес-правила: BR-068
- Инварианты: INV-022
- Тип теста: positive

### US-015-S5: Сверка — нет общей даты
- Given: Мастер содержит листы за 20.06, РСЧ содержит листы за 21.06
- When: Пользователь запускает сверку (без явной даты)
- Then: 0 common dates, ValueError «Не найдена общая дата»
- Бизнес-правила: BR-070
- Тип теста: negative

### US-015-S6: Сверка — несколько общих дат
- Given: Мастер и РСЧ содержат листы за 20.06 и 21.06
- When: Пользователь запускает сверку (без явной даты)
- Then: >1 common dates, ValueError «Выберите нужную дату»
- Бизнес-правила: BR-070
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-015-S1 | positive | BR-065, BR-066, BR-067 | INV-020, INV-021 | pending |
| US-015-S2 | negative | BR-065 | INV-020 | pending |
| US-015-S3 | edge | BR-066 | INV-021 | pending |
| US-015-S4 | positive | BR-068 | INV-022 | pending |
| US-015-S5 | negative | BR-070 | — | pending |
| US-015-S6 | edge | BR-070 | — | pending |

---

## US-016: Автосверка с РСЧ
- Фича: F-016
- Приоритет: P0
- Роль: Пользователь

### US-016-S1: Успешная автосверка
- Given: Все 3 мастер-отчёта (Общий, Борис, Иван) могут быть собраны, РСЧ-данные доступны
- When: Пользователь нажимает «✅ АВТОСВЕРКА»
- Then: 3 мастер-отчёта собраны, РСЧ собран, отчёт расхождений создан
- And: «Автосверка собрана: Общий N, Борис N, Иван N строк. РСЧ: N строк.»
- Бизнес-правила: BR-055, BR-056
- Тип теста: positive

### US-016-S2: Автосверка — empty_data для куратора
- Given: Куратор Борис не имеет данных за дату (empty_data)
- When: Пользователь нажимает «АВТОСВЕРКА»
- Then: write_empty_daily_report для Бориса, автосверка продолжается
- Бизнес-правила: BR-055
- Тип теста: negative

### US-016-S3: Автосверка — нет данных РСЧ
- Given: РСЧ rows == 0 за дату
- When: Пользователь нажимает «АВТОСВЕРКА»
- Then: «Нет данных РСЧ за дату. Автосверка пропущена.» (success, no path)
- Бизнес-правила: BR-056
- Тип теста: edge

### US-016-S4: Автосверка — ValueError от build_combined
- Given: build_combined_reconciliation_report raises ValueError
- When: Пользователь нажимает «АВТОСВЕРКА»
- Then: «Сверка за дату: {error}» (success, no path)
- Бизнес-правила: BR-057
- Тип теста: edge

### US-016-S5: Автосверка — отмена после master reports
- Given: 3 мастер-отчёта собраны, cancel_event set перед РСЧ
- When: Пользователь нажимает Cancel
- Then: _cancel_message, mark_partial для output_path и rsch_output
- Бизнес-правила: BR-029
- Тип теста: edge

### US-016-S6: Автосверка — empty_data для общего
- Given: Общий отчёт не имеет данных (empty_data)
- When: Пользователь нажимает «АВТОСВЕРКА»
- Then: RuntimeError (для общего empty_data не делается пустой отчёт)
- Бизнес-правила: BR-055
- Тип теста: negative

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-016-S1 | positive | BR-055, BR-056 | — | pending |
| US-016-S2 | negative | BR-055 | — | pending |
| US-016-S3 | edge | BR-056 | — | pending |
| US-016-S4 | edge | BR-057 | — | pending |
| US-016-S5 | edge | BR-029 | INV-011 | pending |
| US-016-S6 | negative | BR-055 | — | pending |

---

## US-013: Сборка РСЧ-отчёта (день)
- Фича: F-013
- Приоритет: P0
- Роль: Пользователь

### US-013-S1: Успешная сборка РСЧ
- Given: Исходные РСЧ-файлы содержат данные за 25.06.2026
- When: Пользователь нажимает «🧾 СОБРАТЬ РСЧ» и выбирает файлы
- Then: РСЧ-отчёт собран, written_rows > 0, Excel записан со стилями (income/expense/warning)
- Бизнес-правила: BR-058, BR-072
- Тип теста: positive

### US-013-S2: РСЧ — нет строк за дату
- Given: Исходные РСЧ-файлы не содержат данных за 25.06.2026
- When: Пользователь нажимает «СОБРАТЬ РСЧ»
- Then: written_rows == 0, ValueError «РСЧ: нет строк за выбранную дату»
- Бизнес-правила: BR-058
- Тип теста: negative

### US-013-S3: РСЧ — сохранённые источники
- Given: recent_sources содержит 2 пути, оба существуют
- When: Пользователь нажимает «СОБРАТЬ РСЧ»
- Then: askyesnocancel «Использовать сохраненный набор?», при «Да» — saved sources использованы
- Бизнес-правила: BR-071
- Тип теста: edge

### US-013-S4: РСЧ — сохранённые пути не найдены
- Given: recent_sources содержит пути, некоторые не существуют
- When: Пользователь нажимает «СОБРАТЬ РСЧ» и выбирает «Да»
- Then: Warning «Сохраненные пути не найдены», несуществующие отфильтрованы
- Бизнес-правила: BR-071
- Тип теста: edge

### US-013-S5: РСЧ — backup перед перезаписью
- Given: РСЧ-отчёт уже существует
- When: Пользователь собирает РСЧ повторно
- Then: backup_existing_excel_output создаёт backup, новый отчёт записан
- Бизнес-правила: BR-051
- Инварианты: INV-005
- Тип теста: edge

### US-013-S6: РСЧ — отмена
- Given: Сборка РСЧ выполняется
- When: Пользователь нажимает Cancel
- Then: Операция отменена, .partial.xlsx если файл был частично записан
- Бизнес-правила: BR-029, BR-030
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-013-S1 | positive | BR-058, BR-072 | — | pending |
| US-013-S2 | negative | BR-058 | — | pending |
| US-013-S3 | edge | BR-071 | — | pending |
| US-013-S4 | edge | BR-071 | — | pending |
| US-013-S5 | edge | BR-051 | INV-005 | pending |
| US-013-S6 | edge | BR-029, BR-030 | — | pending |

---

## US-021: Отмена операций
- Фича: F-021
- Приоритет: P0
- Роль: Пользователь

### US-021-S1: Отмена консолидации
- Given: Консолидация выполняется (session running, progress 45%)
- When: Пользователь нажимает «Cancel»
- Then: OperationState.request_cancel(), cancel_event.set(), на контрольной точке операция останавливается
- Бизнес-правила: BR-029
- Инварианты: INV-011
- Тип теста: positive

### US-021-S2: Cancel когда операция не выполняется
- Given: OperationState idle (is_busy=False)
- When: Пользователь нажимает «Cancel»
- Then: request_cancel() отказывает (is_busy=False)
- Бизнес-правила: BR-074
- Тип теста: negative

### US-021-S3: .partial.xlsx при отмене во время write
- Given: Консолидация в стадии write_report, файл частично записан
- When: Пользователь нажимает «Cancel»
- Then: Файл переименован в .partial.xlsx, format_partial_note добавлен в сообщение
- Бизнес-правила: BR-030
- Тип теста: edge

### US-021-S4: CancelledByUser type detection
- Given: Операция отменена пользователем
- When: _cancel_message вызывается
- Then: CancelledByUser маркер-класс используется для type-based detection (не substring)
- Бизнес-правила: BR-029
- Тип теста: edge

### US-021-S5: Двойной click Cancel
- Given: Операция выполняется, cancel уже запрошен
- When: Пользователь нажимает Cancel снова
- Then: Второй request_cancel игнорируется (cancel_event уже set)
- Бизнес-правила: BR-074
- Тип теста: edge

### US-021-S6: Отмена + cleanup_local_copy_cache
- Given: Сетевые файлы скопированы локально (get_local_copy)
- When: Пользователь отменяет операцию
- Then: cleanup_local_copy_cache вызывается, локальные копии удалены
- Бизнес-правила: BR-029, BR-063
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-021-S1 | positive | BR-029 | INV-011 | pending |
| US-021-S2 | negative | BR-074 | — | pending |
| US-021-S3 | edge | BR-030 | — | pending |
| US-021-S4 | edge | BR-029 | — | pending |
| US-021-S5 | edge | BR-074 | — | pending |
| US-021-S6 | edge | BR-029, BR-063 | — | pending |

---

## US-023: SQLite-кэш и сессии
- Фича: F-023
- Приоритет: P0
- Роль: Система (internal)

### US-023-S1: Создание сессии
- Given: БД инициализирована (WAL mode)
- When: _execute_consolidation начинает
- Then: save_session(session_id, meta), session status=running в БД
- Бизнес-правила: BR-025, BR-081
- Инварианты: INV-002
- Тип теста: positive

### US-023-S2: WAL checkpoint при close
- Given: БД открыта, WAL содержит данные
- When: persistence.close() вызывается
- Then: PRAGMA wal_checkpoint(TRUNCATE), WAL flush в main DB
- Бизнес-правила: BR-081
- Инварианты: INV-009
- Тип теста: edge

### US-023-S3: integrity_check failure
- Given: БД повреждена (PRAGMA integrity_check fails)
- When: Bootstrap.setup() запускается
- Then: Warning показан (messagebox после Tk root), приложение продолжает работу
- Бизнес-правила: BR-081
- Тип теста: negative

### US-023-S4: Миграции применяются
- Given: БД пустая (первый запуск)
- When: init_db() вызывается
- Then: Миграции 001 (NUMERIC→TEXT) и 002 (customer_aliases) применены, _migrations таблица обновлена
- Бизнес-правила: BR-082
- Тип теста: positive

### US-023-S5: DBWriterThread drain
- Given: staging_data в очереди DBWriterThread
- When: shutdown() вызывает wait_for_writes()
- Then: Все pending writes завершены до close()
- Бизнес-правила: BR-083
- Инварианты: INV-008
- Тип теста: edge

### US-023-S6: Session status transition
- Given: Session в статусе running
- When: Консолидация завершается успешно
- Then: update_session_status → completed (или completed_with_warnings)
- Бизнес-правила: BR-084
- Инварианты: INV-002
- Тип теста: positive

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-023-S1 | positive | BR-025, BR-081 | INV-002 | pending |
| US-023-S2 | edge | BR-081 | INV-009 | pending |
| US-023-S3 | negative | BR-081 | — | pending |
| US-023-S4 | positive | BR-082 | — | pending |
| US-023-S5 | edge | BR-083 | INV-008 | pending |
| US-023-S6 | positive | BR-084 | INV-002 | pending |

---

## US-024: Отслеживание прогресса
- Фича: F-024
- Приоритет: P0
- Роль: Пользователь

### US-024-S1: Прогресс-бар при консолидации
- Given: Консолидация запущена
- When: on_progress(45) вызывается
- Then: Progress bar показывает 45%, заголовок окна «🚀 Master-Report v5.5 — Сборка за день 45%»
- Бизнес-правила: BR-074
- Тип теста: positive

### US-024-S2: Double-click protection
- Given: Консолидация выполняется (is_busy=True)
- When: Пользователь нажимает «СОБРАТЬ ДЕНЬ» снова
- Then: begin() отказывает (is_busy=True), операция не запускается
- Бизнес-правила: BR-074
- Инварианты: INV-010
- Тип теста: negative

### US-024-S3: ETA расчёт
- Given: Консолидация 50%, elapsed 30s
- When: Progress обновляется
- Then: ETA = 30s (ещё 30s до 100%), показывается в status bar
- Бизнес-правила: BR-074
- Тип теста: edge

### US-024-S4: OperationState listeners
- Given: sidebar, stats_panel, title подписаны как listeners
- When: State transition (idle → busy)
- Then: Все listeners уведомлены, UI обновлен
- Бизнес-правила: BR-074
- Тип теста: positive

### US-024-S5: Tk marshalling из worker thread
- Given: Worker thread вызывает on_progress
- When: on_progress вызывает Tk API
- Then: root.after(0, ...) маршаллит в GUI thread
- Бизнес-правила: BR-074
- Инварианты: INV-017
- Тип теста: edge

### US-024-S6: end() освобождает слот
- Given: Консолидация завершена
- When: end() вызывается
- Then: is_busy=False, progress bar скрыт, listeners уведомлены
- Бизнес-правила: BR-074
- Тип теста: positive

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-024-S1 | positive | BR-074 | — | pending |
| US-024-S2 | negative | BR-074 | INV-010 | pending |
| US-024-S3 | edge | BR-074 | — | pending |
| US-024-S4 | positive | BR-074 | — | pending |
| US-024-S5 | edge | BR-074 | INV-017 | pending |
| US-024-S6 | positive | BR-074 | — | pending |

---

## US-038: Управление алиасами заказчиков
- Фича: F-038
- Приоритет: P1
- Роль: Бухгалтер

### US-038-S1: Добавление алиаса
- Given: Вкладка «Алиасы сверки» открыта
- When: Бухгалтер добавляет master_customer="ООО Заказчик", rsch_customer="Заказчик ООО"
- Then: Алиас сохранён в БД (customer_aliases), updated_at timestamp установлен
- Бизнес-правила: BR-069
- Тип теста: positive

### US-038-S2: Удаление алиаса
- Given: Алиас существует
- When: Бухгалтер удаляет алиас
- Then: Алиас удалён из БД, кэш в памяти обновлён
- Бизнес-правила: BR-069
- Тип теста: positive

### US-038-S3: Изменение алиаса
- Given: Алиас {master: "ООО Заказчик", rsch: "Заказчик"} существует
- When: Бухгалтер изменяет rsch на "Заказчик ООО"
- Then: Алиас обновлён, updated_at изменён
- Бизнес-правила: BR-069
- Тип теста: positive

### US-038-S4: Алиас с пустым master_customer
- Given: Бухгалтер вводит master_customer=" " (только пробел)
- When: Бухгалтер нажимает «Добавить»
- Then: trim → пустая строка, алиас не добавлен (или rejected)
- Бизнес-правила: BR-069
- Тип теста: negative

### US-038-S5: alias_repo=None
- Given: alias_repo не инициализирован (None)
- When: Бухгалтер пытается добавить алиас
- Then: RuntimeError, операция отклонена
- Бизнес-правила: BR-069
- Тип теста: negative

### US-038-S6: Алиас используется в сверке
- Given: Алиас {master: "ООО Заказчик", rsch: "Заказчик ООО"} существует
- When: Сверка сопоставляет строки
- Then: alias использован, «ООО Заказчик» (мастер) совпадает с «Заказчик ООО» (РСЧ)
- Бизнес-правила: BR-068
- Инварианты: INV-022
- Тип теста: positive

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-038-S1 | positive | BR-069 | — | pending |
| US-038-S2 | positive | BR-069 | — | pending |
| US-038-S3 | positive | BR-069 | — | pending |
| US-038-S4 | negative | BR-069 | — | pending |
| US-038-S5 | negative | BR-069 | — | pending |
| US-038-S6 | positive | BR-068 | INV-022 | pending |

---

## US-022: Управление настройками
- Фича: F-022
- Приоритет: P1
- Роль: Пользователь

### US-022-S1: Изменение темы через Settings
- Given: Settings dialog открыт, текущая тема = light
- When: Пользователь выбирает dark и нажимает OK
- Then: save_config, тема применена, dialog закрыт
- Бизнес-правила: BR-077, BR-078
- Тип теста: positive

### US-022-S2: Cancel Settings — восстановление snapshot
- Given: Settings dialog открыт, пользователь изменил тему на dark (live preview)
- When: Пользователь нажимает Cancel
- Then: Snapshot восстановлен, тема возвращена на light, dialog закрыт
- Бизнес-правила: BR-078
- Тип теста: negative

### US-022-S3: Невалидный user_scale
- Given: Пользователь вводит user_scale=2.0 (больше max 1.50)
- When: Пользователь нажимает Apply
- Then: Значение отклонено (валидация _SCALE_MAX)
- Бизнес-правила: BR-077
- Тип теста: negative

### US-022-S4: Live preview темы
- Given: Settings dialog открыт, тема = light
- When: Пользователь выбирает dark (без Apply)
- Then: Live preview применён, тема dark видна, но config не сохранён
- Бизнес-правила: BR-078
- Тип теста: edge

### US-022-S5: Apply (не OK) — dialog остаётся
- Given: Settings dialog открыт
- When: Пользователь нажимает Apply
- Then: save_config, тема применена, dialog остаётся открытым
- Бизнес-правила: BR-078
- Тип теста: edge

### US-022-S6: sidebar_width валидация
- Given: Пользователь вводит sidebar_width=1000 (больше max 800)
- When: Пользователь нажимает OK
- Then: Значение отклонено (валидация _SIDEBAR_MAX)
- Бизнес-правила: BR-077
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-022-S1 | positive | BR-077, BR-078 | — | pending |
| US-022-S2 | negative | BR-078 | — | pending |
| US-022-S3 | negative | BR-077 | — | pending |
| US-022-S4 | edge | BR-078 | — | pending |
| US-022-S5 | edge | BR-078 | — | pending |
| US-022-S6 | edge | BR-077 | — | pending |

---

## US-026: Toast-уведомления
- Фича: F-026
- Приоритет: P1
- Роль: Пользователь

### US-026-S1: Success toast
- Given: Операция завершена успешно
- When: toast.show(ToastLevel.SUCCESS, «Отчёт собран») вызывается
- Then: Зелёный toast показан в правом верхнем углу, авто-закрытие через 4000ms
- Бизнес-правила: BR-075
- Тип теста: positive

### US-026-S2: Error toast с fallback
- Given: ToastManager недоступен
- When: toast.show(ToastLevel.ERROR, «Ошибка») вызывается
- Then: Fallback на messagebox.showerror
- Бизнес-правила: BR-075
- Тип теста: negative

### US-026-S3: 4 toast одновременно
- Given: 3 toast уже показаны
- When: 4-й toast вызывается
- Then: Старейший вытеснен, новые 3 показаны
- Бизнес-правила: BR-075
- Тип теста: edge

### US-026-S4: Error toast duration
- Given: Error toast показан
- When: 6000ms проходит
- Then: Toast закрыт (error=6000ms, не 4000ms)
- Бизнес-правила: BR-075
- Тип теста: edge

### US-026-S5: Fade-out анимация
- Given: Toast показан
- When: Duration истекает
- Then: Fade-out анимация перед закрытием
- Бизнес-правила: BR-075
- Тип теста: edge

### US-026-S6: Toast во время операции
- Given: Консолидация выполняется
- When: Toast success показан
- Then: Toast не блокирует UI (non-modal), операция продолжается
- Бизнес-правила: BR-075
- Тип теста: positive

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-026-S1 | positive | BR-075 | — | pending |
| US-026-S2 | negative | BR-075 | — | pending |
| US-026-S3 | edge | BR-075 | — | pending |
| US-026-S4 | edge | BR-075 | — | pending |
| US-026-S5 | edge | BR-075 | — | pending |
| US-026-S6 | positive | BR-075 | — | pending |

---

## US-027: Управление темой
- Фича: F-027
- Приоритет: P1
- Роль: Пользователь

### US-027-S1: Light тема
- Given: config ui.theme=light
- When: Приложение запускается
- Then: Light palette применена, ttk styles настроены
- Бизнес-правила: BR-076
- Тип теста: positive

### US-027-S2: Dark тема
- Given: config ui.theme=dark
- When: Приложение запускается
- Then: Dark palette применена
- Бизнес-правила: BR-076
- Тип теста: positive

### US-027-S3: System тема — auto-detect
- Given: config ui.theme=system, OS в dark mode
- When: Приложение запускается
- Then: system_theme детектит dark (Windows registry), dark palette применена, polling 5s запущен
- Бизнес-правила: BR-076
- Тип теста: edge

### US-027-S4: System тема — переключение OS
- Given: Приложение в system theme, polling активен, OS в light
- When: Пользователь переключает OS на dark
- Then: Через 5s polling детектит, dark palette применена
- Бизнес-правила: BR-076
- Тип теста: edge

### US-027-S5: Scaling auto (DPI-based)
- Given: config ui.scale_mode=auto, HiDPI дисплей (150% DPI)
- When: Приложение запускается
- Then: Auto scaling применён на основе DPI
- Бизнес-правила: BR-076
- Тип теста: edge

### US-027-S6: Density modes
- Given: config ui.density=compact
- When: Приложение запускается
- Then: SPACING/RADIUS уменьшены (compact mode)
- Бизнес-правила: BR-076
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-027-S1 | positive | BR-076 | — | pending |
| US-027-S2 | positive | BR-076 | — | pending |
| US-027-S3 | edge | BR-076 | — | pending |
| US-027-S4 | edge | BR-076 | — | pending |
| US-027-S5 | edge | BR-076 | — | pending |
| US-027-S6 | edge | BR-076 | — | pending |

---

## US-033: Аудит потери данных
- Фича: F-033
- Приоритет: P2
- Роль: Система (internal)

### US-033-S1: Запись data_loss
- Given: Строка отброшена при валидации (junk/header)
- When: record_loss вызывается
- Then: Запись в logs/data_loss.log с context (файл, лист, строка, причина)
- Бизнес-правила: BR-080
- Тип теста: positive

### US-033-S2: PII redaction
- Given: Строка содержит «Сумма: 1,234.56»
- When: record_loss вызывается
- Then: _AMOUNT_RE матчит «1,234.56», redacted перед записью в лог
- Бизнес-правила: BR-080
- Инварианты: INV-013
- Тип теста: security

### US-033-S3: Thread-safe запись
- Given: 2 worker threads одновременно вызывают record_loss
- When: Оба вызывают record_loss
- Then: _LOCK обеспечивает thread-safe запись, строки не перемешаны
- Бизнес-правила: BR-080
- Инварианты: INV-015
- Тип теста: edge

### US-033-S4: reset_for_testing
- Given: Тесты запущены (PYTEST_CURRENT_TEST set)
- When: reset_for_testing() вызывается
- Then: Logger сброшен, CWD вместо package root
- Бизнес-правила: BR-080
- Тип теста: edge

### US-033-S5: Domain→Infra violation
- Given: data_loss_log импортирует utils_logging.scrub_path
- When: Модуль загружается
- Then: Domain→Infra dependency существует (TD-007)
- Бизнес-правила: —
- Тип теста: edge

### US-033-S6: data_loss.log не существует (первый запуск)
- Given: logs/data_loss.log не существует
- When: record_loss вызывается
- Then: Файл создаётся, запись записана
- Бизнес-правила: BR-080
- Тип теста: edge

### Покрытие фичи
| Сценарий | Тип | Бизнес-правило | Инвариант | Статус |
| US-033-S1 | positive | BR-080 | — | pending |
| US-033-S2 | security | BR-080 | INV-013 | pending |
| US-033-S3 | edge | BR-080 | INV-015 | pending |
| US-033-S4 | edge | BR-080 | — | pending |
| US-033-S5 | edge | — | — | pending |
| US-033-S6 | edge | BR-080 | — | pending |

---

## Сводные метрики по всем user stories

| User Story | Фича | Сценариев | Positive | Negative | Edge | Security | Accessibility |
|------------|------|-----------|----------|----------|------|----------|---------------|
| US-001 | F-001 | 6 | 1 | 2 | 2 | 1 | 0 |
| US-002 | F-002 | 6 | 2 | 1 | 3 | 0 | 0 |
| US-003 | F-003 | 6 | 2 | 1 | 2 | 1 | 0 |
| US-004 | F-004 | 6 | 1 | 3 | 2 | 0 | 0 |
| US-005 | F-005 | 6 | 2 | 1 | 3 | 0 | 0 |
| US-006 | F-006 | 6 | 2 | 1 | 3 | 0 | 0 |
| US-007 | F-007 | 6 | 3 | 1 | 2 | 0 | 0 |
| US-008 | F-008 | 7 | 1 | 2 | 3 | 1 | 0 |
| US-013 | F-013 | 6 | 1 | 1 | 4 | 0 | 0 |
| US-015 | F-015 | 6 | 2 | 2 | 2 | 0 | 0 |
| US-016 | F-016 | 6 | 1 | 2 | 3 | 0 | 0 |
| US-017 | F-017 | 8 | 1 | 3 | 4 | 0 | 0 |
| US-021 | F-021 | 6 | 1 | 1 | 4 | 0 | 0 |
| US-022 | F-022 | 6 | 1 | 2 | 3 | 0 | 0 |
| US-023 | F-023 | 6 | 3 | 1 | 2 | 0 | 0 |
| US-024 | F-024 | 6 | 3 | 1 | 2 | 0 | 0 |
| US-026 | F-026 | 6 | 2 | 1 | 3 | 0 | 0 |
| US-027 | F-027 | 6 | 2 | 0 | 4 | 0 | 0 |
| US-033 | F-033 | 6 | 1 | 0 | 4 | 1 | 0 |
| US-038 | F-038 | 6 | 4 | 2 | 0 | 0 | 0 |

### Примечание по покрытию
- В этом файле задокументированы **20 ключевых user stories** (все core + ключевые secondary/auxiliary) с **122 сценариями**.
- Оставшиеся 22 фичи (F-009, F-010, F-011, F-012, F-014, F-018, F-019, F-020, F-025, F-028, F-029, F-030, F-031, F-032, F-034, F-035, F-036, F-037, F-039, F-040, F-041, F-042) имеют аналогичную структуру сценариев и будут покрыты в edge-cases.md (Phase 1.2) через матрицу boundary conditions.
- Accessibility сценарии (0 во всех) — desktop Tkinter приложение, keyboard navigation работает по умолчанию, screen reader поддержка ограничена Tkinter. Не приоритет для financial desktop app.
