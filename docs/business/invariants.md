# Инварианты системы

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Источник: docs/features/inventory.md + анализ кода APP/core/

---

## INV-001: Decimal type contract
- Область: global
- Инвариант: Все числовые поля FinancialRowSchema (amount, income, expense, total, commission, brokers, transit, rate, currency_amount) ВСЕГДА имеют тип Decimal после валидации. Никогда str, float или int.
- Проверяется в: APP/core/domain/data_schemas.py:46-91 (to_decimal field_validator), APP/core/domain/utils_helpers.py (to_decimal, to_decimal_percent)
- Может быть нарушен при: Прямое присваивание str/float в обход Pydantic-валидации (не происходит в коде)
- Последствия нарушения: TypeError в downstream вычислениях (quantize, abs, сравнения), некорректные финансовые расчёты

## INV-002: Session status transition
- Область: feature:F-008, feature:F-023
- Инвариант: Session status всегда одно из: running, completed, completed_with_warnings, failed, cancelled. Переходы: running → {completed, completed_with_warnings, failed, cancelled}. Из terminal состояний переходов нет.
- Проверяется в: APP/core/app_controller.py (update_session_status calls), APP/core/infra/session_repo.py:177-193
- Может быть нарушен при: Прямой SQL UPDATE в обход AppController (не происходит)
- Последствия нарушения: Некорректная отчётность по сессиям, зависшие статусы

## INV-003: Excel formula injection protection
- Область: feature:F-017, feature:F-018
- Инвариант: НИ одно значение ячейки Excel в выходных отчётах не начинается с =, +, -, @ и не содержит tab/newline без prepended "'". Защита от formula injection.
- Проверяется в: APP/core/domain/logic_service.py:219-236 (_sanitize), APP/core/infra/export_writer.py
- Может быть нарушен при: Запись в Excel в обход _sanitize (не происходит)
- Последствия нарушения: Excel formula injection vulnerability (CSV/Excel injection attacks)

## INV-004: Path traversal protection
- Область: feature:F-030
- Инвариант: НИ один путь из config.yaml не выходит за пределы allowlist (source_roots + config_dir + project_root) или app_root (для относительных путей).
- Проверяется в: APP/core/bootstrap.py, APP/core/infra/config_controller.py (_validate_path_safety)
- Может быть нарушен при: Прямое редактирование config.yaml с malicious путями (блокируется при загрузке)
- Последствия нарушения: Path traversal, доступ к произвольным файлам системы

## INV-005: Backup before overwrite
- Область: feature:F-018, feature:F-028
- Инвариант: Перед перезаписью существующего Excel-файла ВСЕГДА создаётся backup (если файл существует и не ~$ lock).
- Проверяется в: APP/core/infra/excel_backup.py (backup_existing_excel_output)
- Может быть нарушен при: Backup failure (best-effort, caller aborts save)
- Последствия нарушения: Потеря данных пользователя при сбое записи

## INV-006: atomic_save_workbook
- Область: feature:F-018, feature:F-029
- Инвариант: Запись Excel-файлов происходит атомарно (temp file + rename). Никогда partial write в целевой файл.
- Проверяется в: APP/core/infra/utils.py (atomic_save_workbook)
- Может быть нарушен при: Crash между temp write и rename (temp file остаётся, целевой не тронут)
- Последствия нарушения: Partial Excel файл (повреждённый), но целевой файл не затронут

## INV-007: python-calamine обязательная зависимость
- Область: global
- Инвариант: python-calamine ВСЕГДА доступен при работе приложения. Проверяется при старте.
- Проверяется в: APP/core/bootstrap.py:440-477 (Bootstrap.setup)
- Может быть нарушен при: Удаление python-calamine из venv после старта (блокируется при следующем запуске)
- Последствия нарушения: Невозможность чтения Excel-файлов, приложение не запускается

## INV-008: DBWriterThread drain at shutdown
- Область: feature:F-023
- Инвариант: При shutdown все pending writes DBWriterThread завершаются (wait_for_writes) перед закрытием БД.
- Проверяется в: APP/core/infra/session_repo.py:226-228, APP/core/bootstrap.py (shutdown)
- Может быть нарушен при: Kill -9 процесса (не graceful shutdown)
- Последствия нарушения: Потеря staging_data последней сессии

## INV-009: WAL checkpoint at close
- Область: feature:F-023
- Инвариант: При закрытии БД выполняется PRAGMA wal_checkpoint(TRUNCATE) для flush WAL в main DB.
- Проверяется в: APP/core/infra/session_repo.py:230-251 (close)
- Может быть нарушен при: Crash до checkpoint (WAL файл остаётся, данные не потеряны но WAL растёт)
- Последствия нарушения: Рост WAL файла, замедление при следующем запуске

## INV-010: OperationState singleton busy protection
- Область: feature:F-024
- Инвариант: В любой момент времени выполняется НЕ более одной длительной операции. begin() отказывает если is_busy.
- Проверяется в: APP/core/ui/operation_state.py
- Может быть нарушен при: Прямой вызов _start_thread в обход OperationState (не происходит)
- Последствия нарушения: Конкурентные операции, race conditions, некорректный прогресс

## INV-011: Cancel control points
- Область: feature:F-021
- Инвариант: cancel_event проверяется на контрольных точках: после discovery, после engine, после consolidate, перед write. При cancel — graceful stop + mark_partial.
- Проверяется в: APP/core/app_controller.py:606-609, 621-624
- Может быть нарушен при: Длительная операция без control point (например, один большой SQL query)
- Последствия нарушения: Отмена не срабатывает до конца операции

## INV-012: config.yaml chmod 0o600
- Область: feature:F-003
- Инвариант: config.yaml и employees.yaml ВСЕГДА имеют права 0o600 после сохранения.
- Проверяется в: APP/core/infra/config_controller.py
- Может быть нарушен при: Ручное chmod пользователем (восстанавливается при следующем save_config)
- Последствия нарушения: Доступ к конфигу другим пользователям системы

## INV-013: Data loss log redaction
- Область: feature:F-033
- Инвариант: В logs/data_loss.log НИ когда не записываются полные денежные суммы (3+ digits + separator). Всегда redacted.
- Проверяется в: APP/core/domain/data_loss_log.py (_AMOUNT_RE)
- Может быть нарушен при: Прямая запись в лог в обход record_loss (не происходит)
- Последствия нарушения: PII leak денежных сумм в логи

## INV-014: FinancialRowSchema extra="allow"
- Область: feature:F-017
- Инвариант: FinancialRowSchema позволяет extra fields (extra="allow") для service metadata (_приватные ключи). Эти поля не валидируются Pydantic но сохраняются.
- Проверяется в: APP/core/domain/data_schemas.py:8 (model_config = ConfigDict(extra="allow"))
- Может быть нарушен при: —
- Последствия нарушения: Потеря service metadata (_source_info, _template_warning_reason)

## INV-015: Thread-safe data_loss_log
- Область: feature:F-033
- Инвариант: data_loss_log thread-safe через _LOCK. Параллельные записи из worker threads не интерферируют.
- Проверяется в: APP/core/domain/data_loss_log.py (_LOCK)
- Может быть нарушен при: —
- Последствия нарушения: Перемешанные строки в логе

## INV-016: Thread-safe OperationState
- Область: feature:F-024
- Инвариант: OperationState thread-safe. begin/end/request_cancel могут вызываться из любого потока.
- Проверяется в: APP/core/ui/operation_state.py
- Может быть нарушен при: —
- Последствия нарушения: Race condition в UI (двойной прогресс, зависший статус)

## INV-017: Tk API marshalling
- Область: feature:F-024
- Инвариант: Все обращения к Tk API из worker threads маршаллируются через root.after(0, ...).
- Проверяется в: APP/core/ui/operation_state.py, APP/core/ui/gui_master.py
- Может быть нарушен при: Прямой вызов Tk widget methods из worker thread (не происходит)
- Последствия нарушения: Tk crash, segfault

## INV-018: Discovery cache invalidation
- Область: feature:F-019
- Инвариант: Discovery cache инвалидируется при add/delete_employee, attach_files. Не хранит устаревшие пути.
- Проверяется в: APP/core/infra/discovery_service.py, APP/core/app_controller.py
- Может быть нарушен при: Внешнее переименование файла без refresh (rename_detected обновляет при следующем refresh)
- Последствия нарушения: Устаревшие пути в кэше, некорректные статусы

## INV-019: file_cache consistency (mtime + size)
- Область: feature:F-004, feature:F-020
- Инвариант: file_cache валиден только если mtime И size файла совпадают с закэшированными. Любое изменение файла → cache miss.
- Проверяется в: APP/core/infra/source_file_repo.py (get_file_cache), APP/core/app/file_processor.py
- Может быть нарушен при: Изменение файла без изменения mtime/size (крайне редко)
- Последствия нарушения: Устаревший кэш, некорректные данные

## INV-020: Reconciliation amount tolerance
- Область: feature:F-015
- Инвариант: При сверке суммы считаются равными если |left - right| <= 0.01. Точность до копейки.
- Проверяется в: APP/core/infra/reconciliation/_resolve.py:21-22 (_amount_equal)
- Может быть нарушен при: —
- Последствия нарушения: Ложные «Проверить» при округлении, или ложные «Сверено» при больших расхождениях

## INV-021: Executor matching single-token guard (FIX-000)
- Область: feature:F-015
- Инвариант: Single-token executor names (например «ООО») НЕ совпадают с multi-token names (например «ООО Ромашка») через subset heuristic. Совпадение только если canonical/compact text совпадает.
- Проверяется в: APP/core/infra/reconciliation/_resolve.py:41-54 (_executor_matches, single-token guard)
- Может быть нарушен при: Удаление single-token guard (FIX-000 revert) — было обнаружено в текущей рабочей копии, восстановлено из HEAD
- Последствия нарушения: Ложные «Сверено» при разных исполнителях с общим токеном (ООО → ООО Ромашка)

## INV-022: customer_aliases used in reconciliation
- Область: feature:F-015, feature:F-038
- Инвариант: Сверка использует customer_aliases для маппинга заказчиков. Без алиасов — только прямое/loose matching.
- Проверяется в: APP/core/infra/reconciliation/_build.py, APP/core/infra/customer_alias_repo.py
- Может быть нарушен при: alias_repo=None (get_customer_aliases возвращает [], но сверка работает с прямым matching)
- Последствия нарушения: Ложные «Проверить» для заказчиков с разными написаниями

## INV-023: Graceful shutdown sequence
- Область: global
- Инвариант: shutdown() выполняется в порядке: persistence.wait_for_writes() → executor.shutdown(wait=True) → join потоков (timeout 10s) → persistence.close(). Никогда не закрывает БД до завершения writes.
- Проверяется в: APP/main.py:86-98, APP/core/bootstrap.py (shutdown)
- Может быть нарушен при: Kill -9 (не graceful)
- Последствия нарушения: Потеря данных, повреждение БД
