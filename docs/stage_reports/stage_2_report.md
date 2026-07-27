# Stage 2 Report — Configuration versioning and migration

```text
Этап: 2 (Версионирование и миграция конфигурации)
Цель: Любая новая версия принимает старую рабочую конфигурацию без
       ручного редактирования и тихой потери настроек.
Исходная проблема:
  - load_config возвращал "голый" dict без валидации. Любой typo в
    config.yaml (например, timeout: "abc") тихо превращался в
    неправильное поведение без диагностического сообщения.
  - config_version отсутствовал. Нельзя было отличить старый конфиг от
    нового; миграция была невозможна по определению.
  - employees.yaml существовал в двух форматах (legacy-строки и
    dict-with-fingerprint); никакой валидации и никакого пути миграции.
Изменённые файлы:
  - APP/core/infra/config_controller.py (MR-0201/0202):
      * __init__: добавлен self.config_issues: list[dict] (всегда есть).
      * load_config: теперь вызывает _migrate_and_validate, который
        запускает миграцию и валидацию, сохраняет issues для UI.
      * _migrate_and_validate: ленивый импорт схемы, аккуратная обработка
        ошибок (миграционный сбой → сохраняется raw, приложение работает).
      * _atomic_save_yaml: запись через temp + os.replace (атомарно).
      * mypy fix: явный dict(migrated) для strict-совместимости.
Новые модули:
  - APP/core/infra/config_schema.py (MR-0201):
      * Pydantic-схема AppConfig с секциями database/locking/network/
        logic/paths/curators/rsch/performance/backup.
      * CURRENT_CONFIG_VERSION = 1.
      * 4-way error taxonomy: MISSING_FIELD, WRONG_TYPE, UNKNOWN_FIELD,
        UNREACHABLE_PATH. UNREACHABLE_PATH отделён от WRONG_TYPE, чтобы
        отвалившийся сетевой диск не выглядел как typo в YAML.
      * validate_config_dict, classify_paths, ensure_config_version.
      * extra="allow" везде — операторские custom-секции сохраняются.
  - APP/core/infra/config_migrations/__init__.py (MR-0202):
      * migrate_to_current: последовательный runner.
      * Idempotent: повторный запуск не меняет данные (тест
        test_migration_chain_is_idempotent).
      * Preserve-key guarantee: если миграция удаляет key, runner
        восстанавливает его и логирует warning.
      * Refuses downgrade: future version → ValueError.
      * v0→v1 = implicit stamp (без структурных изменений).
  - APP/core/infra/employees_schema.py (MR-0203):
      * EmployeeFile, EmployeeIssue Pydantic-модели.
      * normalise_employee_entries: legacy-string → dict-fingerprint.
      * validate_employees_dict: duplicate/empty-name detection,
        optional path-existence check.
      * migrate_employees_dict, recompute_fingerprints.
      * Mixed format tolerated + flagged.
Новые тесты:
  - tests/test_config_schema.py (MR-0201/0202): 18 тестов — schema
    defaults, wrong-type classification, unknown field preserved+reported,
    config_version coercion (str/int/bool), path classification, migration
    chain (idempotent, refuse-downgrade, non-int version), round-trip,
    ConfigIssue serialization.
  - tests/test_employees_schema.py (MR-0203): 14 тестов — legacy upgrade,
    dict round-trip, mixed format, bad entries, empty values, duplicate
    names, empty names, missing path (opt-in), migration idempotency,
    fingerprint recompute (populates + skips missing).
  - tests/test_config_matrix.py (MR-0204): 16 тестов — config.example.yaml
    round-trip, multi-curator anonymised, v0/v1 supported, corrupted YAML,
    unknown fields, missing config_version, special-char paths
    (Cyrillic/UNC/network/POSIX), read-only file, interrupted migration
    (simulated failure), round-trip stability, classify_paths full walk.
Команды проверки (фактический gate):
  pytest test_config_schema test_employees_schema test_config_matrix    # 48 passed
  byte-for-byte stability (migrate twice → identical sha256)            # STABLE: True
  app starts with anonymised old-style config                           # STARTS OK: True
  full suite regression                                                 # 786 passed
  mypy gate                                                             # PASS (0 new)
Результат:
  - 48 новых тестов этапа 2 passed, всего 786 в комплекте
  - Byte-for-byte идемпотентность миграции подтверждена (sha256 stable)
  - Приложение стартует с обезличенной старой конфигурацией без config_version
  - UNREACHABLE_PATH отделён от WRONG_TYPE — сетевой сбой не выглядит typo
  - Операторские custom-секции (extra="allow") сохраняются при валидации
  - Mixed-format employees.yaml легально загружается и помечается
  - mypy strict gate: 0 новых ошибок (baseline 312)
Оставшиеся риски:
  - R-2.1 [низкий]: config_version = 1 без зарегистрированных миграций
    v1→v2. Это означает, что любая будущая смена схемы потребует сначала
    создать migration-функцию и зарегистрировать её. Сама механика
    протестирована (test_migration_failure_does_not_corrupt_data с
    simulated v1→v2), но реальная миграция появится только когда версия
    поменяется.
  - R-2.2 [низкий]: ConfigController._migrate_and_validate при сбое
    миграции возвращает raw dict и приложение продолжает работать, но
    без обновлённой версии на диске. Это сознательно — лучше работать на
    старом конфиге, чем молча повредить его. Однако если у пользователя
    будущая версия (CURRENT_CONFIG_VERSION на новой сборке), ему нужно
    обновить приложение.
  - R-2.3 [информационно]: validate_config_dict при неправильном типе
    секции (например, database: null) восстанавливает секцию через
    defaults и фиксирует WRONG_TYPE issue. Это лучше, чем краш, но
    оператор должен увидеть warning в UI (UI-интеграция — этап 7).
  - R-2.4 [информационно]: classify_paths сейчас проверяет только
    paths.* и curators.<name>.{output_path, direct_paths}. Если в
    будущей версии появятся новые path-поля, их нужно явно добавить в
    classify_paths. Это сознательная явность — магия autodiscovery тут
    опасна.
Решение gate: PASS
```

## Ключевые решения этапа 2

1. **Четырёхполосная классификация ошибок** вместо одной "валидация
   упала". Критично: `UNREACHABLE_PATH` отделён от `WRONG_TYPE`. Реальный
   кейс — у оператора отвалился сетевой диск Q:. Старый код мог бы
   сказать "config invalid" и отказаться загружать. Новый говорит:
   "config valid, но 2 пути сейчас недоступны — это проблема окружения,
   не опечатка". UI (этап 7) покажет это как warning, не как error.

2. **`extra="allow"` везде.** Сознательное решение: оператор может
   добавить свою секцию (например, `company_internal.firm_id`), и она
   переживёт валидацию, миграцию и round-trip. Альтернатива
   (`extra="forbid"`) была бы строже, но ломала бы каждую установку при
   любой смене схемы.

3. **Миграция как явная, тестируемая операция.** `migrate_to_current`
   -- чистая функция (dict → dict + log lines). Никаких side effects на
   диск — persist делает вызывающий код через `_atomic_save_yaml`.
   Любой сбой → возврат raw, приложение продолжает работать.

4. **Legacy employees-формат tolerated, не forced.** Если у оператора
   `Амалия: ["/old.xlsx"]` (строка), это загружается как
   `EmployeeFile(path="/old.xlsx", id=None, fp=None)`. Никаких
   принудительных миграций. Оператор может запустить
   `recompute_fingerprints` чтобы обновить metadata, когда захочет.

5. **Атомарная persist-запись** через `tmp + os.replace`. Если процесс
   убили в середине записи config.yaml, останется либо старый, либо
   новый — но никогда partially-written.

## Что НЕ сделано (и почему)

- **UI для отображения config_issues не построен.** ТЗ этапа 2 не
  требует UI (это этап 7). Сейчас issues доступны как
  `config_controller.config_issues` — готовый атрибут для будущего UI.

- **Автоматическая миграция employees.yaml на диске не выполняется.**
  Это сознательно: принудительная перезапись `employees.yaml` может
  затереть ручные правки оператора. Migration доступна как
  инструмент (`migrate_employees_dict`), но вызывается явно.

- **Pydantic-settings / environment overrides не добавлены.** ТЗ не
  требует; конфигурация исключительно из YAML.

## Коммиты (логические единицы, после разрешения владельца)

1. `feat(config): Pydantic schema + 4-way error taxonomy + config_version`
   (config_schema.py, test_config_schema.py)
2. `feat(config): sequential idempotent migration runner`
   (config_migrations/__init__.py)
3. `feat(config): integrate migration+validation into ConfigController`
   (config_controller.py)
4. `feat(config): employees.yaml schema + legacy upgrade + fingerprint recompute`
   (employees_schema.py, test_employees_schema.py)
5. `test(config): matrix — corrupted/unknown/special-paths/readonly/interrupted`
   (test_config_matrix.py)
