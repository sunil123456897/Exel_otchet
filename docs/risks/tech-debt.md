# Технический долг и риски

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Источник: Все артефакты Phase 0 + анализ кода APP/

---

## 1. Технический долг

### TD-001: God Object — AppController (1026 строк)
- Категория: architecture
- Severity: major
- Местоположение: APP/core/app_controller.py (1026 строк, 48 методов)
- Описание: AppController объединяет ответственности: оркестрация консолидации, refresh статусов, авто-сверка, RSCH-отчёты, CRUD алиасов, фильтрация кураторов, normalisation дат, thread management. 48 методов, 1026 строк — нарушает Single Responsibility Principle.
- Последствия: Сложность модификации, высокий риск регрессии при изменениях, сложность тестирования.
- Рекомендация: Разделить на отдельные сервисы: ConsolidationService, RefreshService, AutoReconciliationService, RschCoordinator, AliasService. AppController оставить как фасад.
- Оценка усилий: 3-5 дней
- Зависимости: — (рефакторинг, не блокирует работу)

### TD-002: God Object — ingestion_reader.py (1012 строк)
- Категория: architecture
- Severity: major
- Местоположение: APP/core/infra/ingestion_reader.py (1012 строк)
- Описание: CalamineReader объединяет: парсинг Excel, извлечение дат из имён листов, извлечение дат из metadata, кэширование строк, игнорирование листов, обработку маркеров колонок.
- Последствия: Сложность модификации логики чтения, риск регрессии.
- Рекомендация: Разделить на: SheetDateExtractor, RowParser, ColumnMarkerMatcher, RowCache.
- Оценка усилий: 2-3 дня
- Зависимости: —

### TD-003: Дублирование _excel_safe_text
- Категория: maintainability
- Severity: minor
- Местоположение: APP/core/infra/reconciliation/_utils.py:423-428, APP/core/infra/rsch/_format.py:218-223, APP/core/domain/logic_service.py:227-236 (_sanitize)
- Описание: Функция `_excel_safe_text` определена идентично в двух местах (reconciliation/_utils.py и rsch/_format.py). Также `_sanitize` в logic_service.py делает почти то же самое (но с дополнительными символами tab/newline).
- Последствия: Изменение логики sanitization в одном месте не применится в другом. Риск inconsistency.
- Рекомендация: Вынести в общий модуль `core/infra/excel_sanitize.py` и импортировать везде. Унифицировать с _sanitize (добавить tab/newline в общий вариант).
- Оценка усилий: 2 часа
- Зависимости: —

### TD-004: Dead Code — event_bus.py
- Категория: maintainability
- Severity: minor
- Местоположение: APP/core/infra/event_bus.py
- Описание: Event Bus (pub/sub) определён но НЕ импортируется ни одним модулем в APP/. Функциональность заменена прямыми callback-ами и OperationState listeners.
- Последствия: Поддержка неиспользуемого кода, путаница для новых разработчиков.
- Рекомендация: Удалить файл ИЛИ задокументировать как «reserved for future use» с пометкой [DEPRECATED].
- Оценка усилий: 30 минут
- Зависимости: —

### TD-005: Dead Code — metrics.py
- Категория: maintainability
- Severity: minor
- Местоположение: APP/core/infra/metrics.py
- Описание: In-process метрики (counters, gauges, timers) определены но НЕ импортируются ни одним модулем в APP/. Функциональность не используется.
- Последствия: Поддержка неиспользуемого кода.
- Рекомендация: Удалить файл ИЛИ интегрировать в OperationState/DBWriterThread для реального мониторинга.
- Оценка усилий: 30 минут (удаление) / 2 дня (интеграция)
- Зависимости: —

### TD-006: Дубликат config_missing.yaml
- Категория: maintainability
- Severity: minor
- Местоположение: APP/config_missing.yaml (MD5 идентичен APP/config.example.yaml)
- Описание: Файл config_missing.yaml — точный дубликат config.example.yaml (одинаковый MD5 hash). Назначение неясно, не используется в коде.
- Последствия: Путаница, риск рассинхронизации при изменении example.
- Рекомендация: Удалить config_missing.yaml. Если был нужен для тестов — задокументировать.
- Оценка усилий: 10 минут
- Зависимости: —

### TD-007: Domain→Infra violation (data_loss_log.py)
- Категория: architecture
- Severity: major
- Местоположение: APP/core/domain/data_loss_log.py (импортирует core.infra.utils_logging)
- Описание: Domain слой (data_loss_log.py) импортирует из Infra слоя (utils_logging.scrub_path). Нарушает Dependency Inversion Principle — Domain не должен зависеть от Infra.
- Последствия: Нарушение слоистой архитектуры, сложность замены Infra.
- Рекомендация: Перенести scrub_path в Domain (utils_helpers.py) ИЛИ внедрить интерфейс ILogger в Domain с реализацией в Infra.
- Оценка усилий: 4 часа
- Зависимости: —

### TD-008: MVVM-слой не изолирован (GuiMaster → AppController напрямую)
- Категория: architecture
- Severity: minor
- Местоположение: APP/core/ui/gui_master.py:22 (импортирует AppController напрямую)
- Описание: GuiMaster импортирует AppController напрямую, минуя ViewModel. ViewModel-и используются лишь для employee list и consolidation state. Большинство GUI-команд обращаются напрямую к AppController через self.ctx.controller. Гибрид MVC+MVVM не консистентен.
- Последствия: Неконсистентная архитектура, сложность тестирования UI.
- Рекомендация: Либо полностью перейти на MVVM (все GUI-команды через ViewModel), либо задокументировать как MVC (убрать ViewModel-и). Текущий гибрид — долг.
- Оценка усилий: 3-5 дней (полный MVVM) / 1 день (упрощение до MVC)
- Зависимости: TD-001

### TD-009: Широкие except Exception: pass (20+ мест)
- Категория: maintainability
- Severity: minor
- Местоположение: APP/core/ui/theme.py (14 мест), APP/core/ui/gui_master.py (2), APP/core/ui/ui_settings.py (2), APP/core/infra/settings_store.py (1), APP/core/ui/gui_master_settings.py (1), APP/core/infra/rsch/_build.py (2)
- Описание: 20+ мест с `except Exception: pass` — silent error swallowing. Большинство в theme.py (UI cleanup, best-effort) и gui_master.py (Tk widget destruction). Некоторые могут скрывать реальные ошибки.
- Последствия: Скрытые ошибки, сложность отладки.
- Рекомендация: Для UI cleanup (widget destruction) — оставить как-is (Tk widgets могут быть уже уничтожены). Для остальных — добавить logging.warning с контекстом.
- Оценка усилий: 4 часа
- Зависимости: —

### TD-010: Длинные файлы (>500 строк)
- Категория: maintainability
- Severity: minor
- Местоположение: 12 файлов >500 строк (см. список ниже)
- Описание: 12 файлов превышают 500 строк: app_controller.py (1026), ingestion_reader.py (1012), theme.py (715), ui_dashboard.py (690), export_writer.py (597), _collect.py (597), ui_settings.py (568), _build.py (479), logic_service.py (448), ui_sidebar.py (442), _build.py (432), dashboard_state.py (430).
- Последствия: Сложность навигации, медленный рендеринг в IDE.
- Рекомендация: Разделить крупные UI-файлы по вкладкам/панелям. Разделить app_controller (см. TD-001). Разделить ingestion_reader (см. TD-002).
- Оценка усилий: 5-7 дней (включая TD-001, TD-002)
- Зависимости: TD-001, TD-002

### TD-011: Отсутствие conftest.py и __init__.py в tests/
- Категория: testing
- Severity: minor
- Местоположение: tests/ (нет conftest.py, нет __init__.py)
- Описание: Тесты запускаются напрямую через pytest без conftest.py. Нет общих fixtures, нет общих импортов. Каждый тестовый файл сам настраивает PYTHONPATH.
- Последствия: Дублирование setup кода в тестах, риск inconsistency.
- Рекомендация: Добавить tests/conftest.py с общими fixtures (test_config, test_db, sample_excel). Добавить tests/__init__.py для package.
- Оценка усилий: 1 день
- Зависимости: —

### TD-012: config_missing.yaml — неиспользуемый файл
- Категория: maintainability
- Severity: minor
- Местоположение: APP/config_missing.yaml
- Описание: Дубликат config.example.yaml, не упоминается в коде. (Дубль TD-006, оставлен для полноты.)
- Последствия: —
- Рекомендация: Удалить.
- Оценка усилий: 10 минут
- Зависимости: —

### TD-013: config_schema.py — orphan Pydantic-схема (две схемы конфига)
- Категория: architecture
- Severity: major
- Местоположение: APP/core/infra/config_schema.py (324 строки)
- Описание: Полноценная типизированная Pydantic-схема `AppConfig`
  (`validate_config_dict` / `classify_paths` / `ensure_config_version`).
  Подтверждено grep'ом: **из живого кода не вызывается ни одна из этих
  функций** — `bootstrap.py` использует собственную параллельную схему
  (`PathsConfig`/`DatabaseConfig`/...) и собственную валидацию
  (`_validate_and_normalize_config`). `config_schema.py` дёргают только её
  собственные тесты. Это либо незаконченный редизайн конфигурации, либо
  мёртвый код.
- Последствия: Два источника истины для формы конфига; риск расхождения
  между Pydantic-схемой и реальной валидацией в bootstrap.
- Решение: **намеренно оставлено** (решение мейнтейнера 2026-07-29) — секция
  «не уверен — сохраняй». `config_migrations` всё же использует
  `CURRENT_CONFIG_VERSION` из этого модуля. Если в будущем унифицировать —
  маршрут: вшить `validate_config_dict` в bootstrap, удалить параллельные
  модели `bootstrap.py`, прогнать `tests/test_config_*`.
- Оценка усилий: 1-2 дня (унификация) / 0 (оставить как есть)
- Зависимости: —

## 1.1. Разрешённый долг (исправлено в hardening-цикле 2026-07)

Эти пункты из более ранних редакций этого документа теперь закрыты; запись
оставлена для истории.

- **TD-011 (conftest.py отсутствует) — ИСПРАВЛЕНО.** Добавлен
  `tests/conftest.py` (регистрирует `--run-e2e` + auto-skip `@e2e`), см.
  этап 3c hardening-цикла.
- **SEC-002/003 (config atomics / PII) — частично усилено.** `config.yaml` и
  `employees.yaml` теперь пишутся атомарно (temp + `os.replace` через
  `atomic_save_yaml`), поэтому сбой посередине записи больше не оставляет
  конфиг оператора пустым/наполовину записанным.

## 1.2. Незакрытый долг — tools/ вне ruff-гейта

Качественный шлюз README заявляет `ruff check APP`. Директория `tools/`
(QA/CI/dev-скрипты, не production-код приложения) под этот гейт НЕ попадает,
и в ней накапливалось 12 мелких ruff-нарушений (по состоянию на 2026-07-29):
3× неиспользуемый импорт (`diagnostic_package.py`, `merge_to_pdf.py`,
`test_user_flows.py`), 5× неоднозначное имя переменной `l`
(`ci_mypy_check.py`, `qa_baseline.py`, `qa_mypy_baseline.py`), 2×
неиспользуемая локальная переменная. Ни одно не влияет на runtime
приложения. Намеренно НЕ исправлено в этом цикле (расширение гейта на
`tools/` — отдельное решение; автозафиксимы только 3 F401). Зафиксировано
здесь, чтобы не потерять; безвредно до отдельной чистки.

## 2. Риски безопасности

### SEC-001: Excel Formula Injection (mitigated)
- Тип: injection
- Severity: minor (mitigated)
- Местоположение: APP/core/domain/logic_service.py:219-236 (_sanitize), APP/core/infra/reconciliation/_utils.py:423 (_excel_safe_text), APP/core/infra/rsch/_format.py:218
- Описание: Пользовательские данные из Excel записываются обратно в Excel-отчёты. Без sanitization — formula injection (=, +, -, @). Защита реализована (_sanitize, _excel_safe_text), но дублирована в 3 местах (см. TD-003).
- Эксплойт-сценарий: Вредоносный Excel с ячейкой "=CMD(...)" → при консолидации попадает в мастер-отчёт → при открытии в Excel выполняется команда.
- Рекомендация: Унифицировать sanitization (TD-003). Текущая защита работает, но риск inconsistency при изменении.
- OWASP категория: A03 (Injection)

### SEC-002: Path Traversal (mitigated)
- Тип: misconfiguration
- Severity: minor (mitigated)
- Местоположение: APP/core/bootstrap.py, APP/core/infra/config_controller.py (_validate_path_safety)
- Описание: config.yaml может содержать пути. Без валидации — path traversal (../../etc/passwd). Защита реализована (_validate_path_safety, allowlist).
- Эксплойт-сценарий: Редактирование config.yaml с malicious путём → доступ к произвольным файлам.
- Рекомендация: Текущая защита работает. Добавить unit-тесты для edge cases (symlinks, junction points на Windows).
- OWASP категория: A01 (Broken Access Control)

### SEC-003: PII в data_loss.log (mitigated)
- Тип: data-leak
- Severity: minor (mitigated)
- Местоположение: APP/core/domain/data_loss_log.py
- Описание: data_loss.log записывает context финансовых операций. Без redaction — PII leak денежных сумм. Защита реализована (_AMOUNT_RE redaction).
- Эксплойт-сценарий: Доступ к logs/data_loss.log → извлечение денежных сумм операций.
- Рекомендация: Текущая защита работает. Проверить что redaction покрывает все форматы (1.234,56, 1,234.56, 1234.56).
- OWASP категория: A02 (Cryptographic Failures)

### SEC-004: SQLite DB file permissions
- Тип: misconfiguration
- Severity: minor
- Местоположение: APP/cache.db
- Описание: SQLite DB файл (cache.db) не получает chmod 0o600 при создании (в отличие от config.yaml и employees.yaml). Может быть доступен другим пользователям системы.
- Эксплойт-сценарий: Доступ к cache.db → чтение staging_data, consolidated_results, customer_aliases.
- Рекомендация: Добавить os.chmod(db_path, 0o600) после создания БД.
- OWASP категория: A01 (Broken Access Control)

### SEC-005: Нет аутентификации (desktop app, by design)
- Тип: auth-bypass
- Severity: none (by design)
- Местоположение: APP/ (всё приложение)
- Описание: Desktop GUI приложение без аутентификации. Любой пользователь с доступом к машине может запустить приложение и получить доступ ко всем функциям. By design — приложение для одного оператора на рабочей станции.
- Эксплойт-сценарий: Физический доступ к машине → полный доступ.
- Рекомендация: N/A для desktop. Если потребуется multi-user — добавить OS-level auth.
- OWASP категория: N/A

## 3. Проблемы производительности

### PERF-001: Calamine subprocess isolation overhead
- Тип: blocking-io
- Severity: minor
- Местоположение: APP/core/infra/ingestion_engine.py (isolate_calamine)
- Описание: При isolate_calamine=True каждый файл читается в отдельном subprocess. Защита от crash, но overhead на process spawn (~100ms на файл).
- Оценка влияния: +100ms на файл при isolate_calamine=True. Для 50 файлов — +5s.
- Рекомендация: Сделать isolate_calamine=False по умолчанию (только для crash-prone сред). Текущее значение по умолчанию — проверить в config.example.yaml.

### PERF-002: Discovery cache не persistent между запусками
- Тип: unnecessary-recompute
- Severity: minor
- Местоположение: APP/core/infra/discovery_service.py
- Описание: Discovery cache (найденные файлы) хранится в SQLite, но invalidate при add/delete_employee. При каждом запуске — полный discovery сетевых папок (может быть медленно на SMB).
- Оценка влияния: +5-30s на запуск при медленной сети.
- Рекомендация: Добавить TTL для discovery cache (например, 1 час). Если cache < 1 hour old и не было изменений — использовать без re-scan.
- Зависимости: BR-014 (file_cache consistency)

### PERF-003: get_local_copy копирует весь файл
- Тип: blocking-io
- Severity: minor
- Местоположение: APP/core/infra/utils.py (get_local_copy)
- Описание: При чтении сетевого файла — полное копирование в temp dir. Для больших файлов (>10MB) — задержка.
- Оценка влияния: +1-5s на файл >10MB.
- Рекомендация: Использовать memory-mapped чтение ИЛИ streaming read для больших файлов. Текущий подход безопасен но медленнее.

### PERF-004: Theme polling 5s
- Тип: unnecessary-recompute
- Severity: cosmetic
- Местоположение: APP/core/ui/system_theme.py, APP/core/ui/theme.py
- Описание: При теме «system» — polling каждые 5s для детекта изменения темы ОС. Редко меняется, но polling работает постоянно.
- Оценка влияния: Минимальное (один registry read за 5s).
- Рекомендация: Использовать OS event hook (Windows: WM_SETTINGCHANGE) вместо polling. Низкий приоритет.

### PERF-005: WAL checkpoint только при close
- Тип: blocking-io
- Severity: minor
- Местоположение: APP/core/infra/session_repo.py:230-251 (close)
- Описание: WAL checkpoint(TRUNCATE) выполняется только при close. При длительной работе WAL может расти.
- Оценка влияния: Рост WAL файла, замедление reads при большом WAL.
- Рекомендация: Периодический checkpoint (например, каждые 100 writes ИЛИ каждые 5 минут).
- Зависимости: BR-081

## 4. Сводка

| Категория | Critical | Major | Minor | Cosmetic | Total |
|-----------|----------|-------|-------|----------|-------|
| Architecture | 0 | 3 | 1 | 0 | 4 |
| Security | 0 | 0 | 4 | 0 | 4 |
| Performance | 0 | 0 | 4 | 1 | 5 |
| Maintainability | 0 | 0 | 7 | 0 | 7 |
| Testing | 0 | 0 | 1 | 0 | 1 |
| **Total** | **0** | **3** | **16** | **1** | **20** |

### Приоритеты исправления
1. **High priority**: TD-001 (AppController god object), TD-002 (ingestion_reader god object), TD-007 (domain→infra violation)
2. **Medium priority**: TD-003 (дублирование _excel_safe_text), TD-004/TD-005 (dead code), SEC-004 (DB permissions)
3. **Low priority**: Остальные (длинные файлы, широкие except, polling, WAL checkpoint)

### Положительные находки
- Нет TODO/FIXME/HACK комментариев — код чистый
- Нет hardcoded secrets/passwords/API keys
- Нет SQL injection (все queries parameterized)
- Нет закомментированного кода
- Excel formula injection защищён (в 3 местах, дублировано)
- Path traversal защищён
- PII redaction в data_loss.log
- atomic_save_workbook для безопасной записи
- Graceful shutdown sequence
- WAL mode для SQLite
