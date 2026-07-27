# Модель данных

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Источник: docs/map/structure.md + docs/features/inventory.md + APP/db_schema.sql + APP/migrations/ + анализ кода

---

## 1. Сущности

### Entity-001: _migrations
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 7–10); также создаётся в APP/core/infra/db_connection.py (`_run_migrations`)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | filename | TEXT | да | — | PRIMARY KEY | да (PK) |
  | applied_at | TIMESTAMP | нет | CURRENT_TIMESTAMP | — | нет |
- Связи:
  - нет (справочная таблица учёта миграций)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — нет зависимых сущностей
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: запись добавляется в транзакции вместе с DDL миграции (db_connection.py `_run_migrations`, BEGIN IMMEDIATE + commit)
  - beforeUpdate: [NOT SPECIFIED] — строки не обновляются
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-002: sessions
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 13–18); репозиторий APP/core/infra/session_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | session_id | TEXT | да | — | PRIMARY KEY | да (PK) |
  | created_at | TIMESTAMP | нет | CURRENT_TIMESTAMP | — | нет |
  | status | TEXT | нет | 'in_progress' | допустимые значения: in_progress, completed, failed (на уровне кода) | нет |
  | metadata | TEXT | нет | NULL | JSON с параметрами запуска | нет |
- Связи:
  - → Entity-003 source_files (one-to-many, через source_files.session_id)
  - → Entity-005 consolidated_results (one-to-many, через consolidated_results.session_id)
  - → Entity-006 template_errors (one-to-many, через template_errors.session_id)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — SQLite NO ACTION (foreign_keys=ON, но без ON DELETE)
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES] — SQLite NO ACTION
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `SessionRepository.save_session` (session_repo.py:50) — INSERT в транзакции BEGIN IMMEDIATE
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: `SessionRepository.update_session_status` (session_repo.py:177) — UPDATE status
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-003: source_files
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 21–30); репозиторий APP/core/infra/source_file_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | id | INTEGER | да | — | PRIMARY KEY AUTOINCREMENT | да (PK) |
  | session_id | TEXT | да | — | NOT NULL, FOREIGN KEY → sessions(session_id) | да (idx_files_session) |
  | file_path | TEXT | да | — | NOT NULL | нет |
  | file_hash | TEXT | нет | NULL | MD5 fingerprint | нет |
  | inode | INTEGER | нет | NULL | NTFS/Unix filesystem ID для rename detection | нет |
  | status | TEXT | нет | 'pending' | допустимые: pending, indexed, processed, error (на уровне кода) | нет |
  | error_message | TEXT | нет | NULL | — | нет |
- Связи:
  - → Entity-002 sessions (many-to-one, FK session_id)
  - → Entity-004 staging_data (one-to-many, через staging_data.file_id)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — SQLite NO ACTION
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `SourceFileRepository.save_file_metadata` (source_file_repo.py:55) — дедупликация по (session_id, file_path), INSERT в BEGIN IMMEDIATE; запись через writer thread (очередь)
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: `SessionRepository.update_file_status` (session_repo.py:195) — UPDATE status, error_message
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-004: staging_data
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 33–46); репозиторий APP/core/infra/staging_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | id | INTEGER | да | — | PRIMARY KEY AUTOINCREMENT | да (PK) |
  | file_id | INTEGER | да | — | NOT NULL, FOREIGN KEY → source_files(id) | да (idx_staging_file) |
  | row_index | INTEGER | нет | NULL | — | нет |
  | raw_content_json | TEXT | нет | NULL | все колонки исходного Excel (JSON) | нет |
  | date_val | TEXT | нет | NULL | дата в формате DD.MM.YYYY | да (idx_staging_employee_date, составной) |
  | amount | TEXT | нет | NULL | хранится как TEXT для сохранения точности Decimal (миграция 001) | нет |
  | employee_name | TEXT | нет | NULL | — | да (idx_staging_employee_date, составной) |
  | source_type | TEXT | нет | NULL | e.g. "Staff", "OPT" | нет |
  | status | TEXT | нет | 'raw' | допустимые: raw, validated, rejected | нет |
  | validation_error | TEXT | нет | NULL | — | нет |
- Связи:
  - → Entity-003 source_files (many-to-one, FK file_id)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — SQLite NO ACTION
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `StagingDataRepository.save_staging_data` → `DBWriterThread._process_batch` (staging_repo.py:103) — батчинг (BATCH_SIZE=500), INSERT executemany в BEGIN IMMEDIATE; retry 1 раз при transient ошибке; запись о data_loss при numeric_coercion
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: [NOT SPECIFIED] — строки не обновляются
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-005: consolidated_results
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 49–59)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | id | INTEGER | да | — | PRIMARY KEY AUTOINCREMENT | да (PK) |
  | session_id | TEXT | да | — | NOT NULL, FOREIGN KEY → sessions(session_id) | да (idx_consolidated_session) |
  | date_val | TEXT | нет | NULL | — | нет |
  | employee_name | TEXT | нет | NULL | — | нет |
  | total_amount | TEXT | нет | NULL | TEXT для точности Decimal (миграция 001) | нет |
  | commission | TEXT | нет | NULL | TEXT для точности Decimal (миграция 001) | нет |
  | net_amount | TEXT | нет | NULL | TEXT для точности Decimal (миграция 001) | нет |
  | logic_applied | TEXT | нет | NULL | rationale for transformation | нет |
- Связи:
  - → Entity-002 sessions (many-to-one, FK session_id)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — SQLite NO ACTION
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: [NOT SPECIFIED — в коде не найдено INSERT INTO consolidated_results; таблица определена в схеме, но активная запись результатов консолидации происходит в памяти через LogicService.consolidate → get_consolidated_data (JOIN staging_data + source_files)]
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-006: template_errors
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 62–72); репозиторий APP/core/infra/session_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | id | INTEGER | да | — | PRIMARY KEY AUTOINCREMENT | да (PK) |
  | session_id | TEXT | да | — | NOT NULL, FOREIGN KEY → sessions(session_id) | нет |
  | file_path | TEXT | нет | NULL | — | нет |
  | sheet_name | TEXT | нет | NULL | — | нет |
  | row_index | INTEGER | нет | NULL | — | нет |
  | error_type | TEXT | нет | NULL | — | нет |
  | details | TEXT | нет | NULL | — | нет |
  | raw_data | TEXT | нет | NULL | JSON исходных данных | нет |
- Связи:
  - → Entity-002 sessions (many-to-one, FK session_id)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — SQLite NO ACTION
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `SessionRepository.save_template_error` (session_repo.py:71) и `save_template_errors_batch` (session_repo.py:103) — INSERT/executemany в BEGIN IMMEDIATE
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-007: file_cache
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 75–81); репозиторий APP/core/infra/source_file_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | file_path | TEXT | да | — | PRIMARY KEY | да (PK) |
  | mtime | REAL | нет | NULL | modification time | нет |
  | size | INTEGER | нет | NULL | размер файла | нет |
  | dates_json | TEXT | нет | NULL | JSON array of strings (формат v4: {cache_version, dates, fingerprint}) | нет |
  | last_updated | TIMESTAMP | нет | CURRENT_TIMESTAMP | — | нет |
- Связи:
  - нет (автономный кэш)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — нет зависимых сущностей
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `SourceFileRepository.save_file_cache` (source_file_repo.py:131) — INSERT OR REPLACE через writer thread
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: INSERT OR REPLACE (upsert-семантика)
  - beforeDelete: `_cleanup_old_cache_entries` (db_connection.py:145) — DELETE WHERE last_updated < datetime('now','-7 days')
  - afterDelete: [NOT SPECIFIED]

### Entity-008: row_cache
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 84–93); репозиторий APP/core/infra/source_file_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | file_path | TEXT | да | — | NOT NULL, часть составного PK | да (PK составной + idx_row_cache_lookup) |
  | mtime | REAL | да | — | NOT NULL | да (idx_row_cache_lookup) |
  | size | INTEGER | да | — | NOT NULL | да (idx_row_cache_lookup) |
  | date_key | TEXT | да | — | NOT NULL, target_date или "all"; часть составного PK | да (PK составной) |
  | rows_json | TEXT | да | — | NOT NULL, JSON array of row dicts | нет |
  | row_count | INTEGER | нет | 0 | — | нет |
  | created_at | TIMESTAMP | нет | CURRENT_TIMESTAMP | — | нет |
  | — (составной PK) | — | — | — | PRIMARY KEY (file_path, date_key) | да |
- Связи:
  - нет (автономный кэш)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — нет зависимых сущностей
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `SourceFileRepository.save_row_cache` (source_file_repo.py:183) — INSERT OR REPLACE через writer thread
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: INSERT OR REPLACE (upsert-семантика)
  - beforeDelete: `_cleanup_old_cache_entries` (db_connection.py:154) — DELETE WHERE created_at < datetime('now','-7 days')
  - afterDelete: [NOT SPECIFIED]

### Entity-009: discovery_cache
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 96–100); репозиторий APP/core/infra/source_file_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | roots_key | TEXT | да | — | PRIMARY KEY (hash от scanned root paths) | да (PK) |
  | scanned_at | REAL | да | — | NOT NULL, timestamp сканирования | нет |
  | files_json | TEXT | да | — | NOT NULL, JSON array of file metadata | нет |
- Связи:
  - нет (автономный кэш)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — нет зависимых сущностей
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `SourceFileRepository.save_discovery_cache` (source_file_repo.py) — INSERT OR REPLACE
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: INSERT OR REPLACE (upsert-семантика)
  - beforeDelete: `_cleanup_old_cache_entries` (db_connection.py:156) — DELETE WHERE scanned_at < now - 43200 (12 часов); TTL 12ч в `get_discovery_cache`
  - afterDelete: [NOT SPECIFIED]

### Entity-010: customer_aliases
- Тип: database table
- Местоположение: APP/db_schema.sql (строки 103–111); миграция APP/migrations/002_customer_aliases.sql; репозиторий APP/core/infra/customer_alias_repo.py
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | id | INTEGER | да | — | PRIMARY KEY AUTOINCREMENT | да (PK) |
  | master_customer | TEXT | да | — | NOT NULL, часть UNIQUE(master_customer, rsch_customer) | да (idx_aliases_master) |
  | rsch_customer | TEXT | да | — | NOT NULL, часть UNIQUE(master_customer, rsch_customer) | да (idx_aliases_rsch) |
  | notes | TEXT | нет | '' | DEFAULT '' | нет |
  | created_at | TIMESTAMP | нет | CURRENT_TIMESTAMP | — | нет |
  | updated_at | TIMESTAMP | нет | CURRENT_TIMESTAMP | обновляется в update_alias | нет |
- Связи:
  - нет (справочник; используется сверкой в памяти через CustomerAliasRepository)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — нет зависимых сущностей
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: `CustomerAliasRepository.add_alias` (customer_alias_repo.py:121) — валидация: непустые значения, master ≠ rsch (case-insensitive); проверка UNIQUE → ValueError при дубликате; инвалидация in-memory кэша
  - afterCreate: логирование, возврат lastrowid, инвалидация `_cache`
  - beforeUpdate: `CustomerAliasRepository.update_alias` (customer_alias_repo.py:151) — валидация непустых значений; проверка UNIQUE
  - afterUpdate: UPDATE updated_at = CURRENT_TIMESTAMP; инвалидация `_cache`
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: `CustomerAliasRepository.delete_alias` (customer_alias_repo.py:183) — инвалидация `_cache`

### Entity-011: FinancialRowSchema
- Тип: model class (Pydantic BaseModel, in-memory)
- Местоположение: APP/core/domain/data_schemas.py (строки 7–91)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | date | Optional[str] | нет | None | валидатор: попытка parse DD.MM.YYYY, иначе str(v) | нет |
  | customer | Optional[str] | нет | None | alias="customer" | нет |
  | contractor | Optional[str] | нет | None | alias="contractor" | нет |
  | amount | Decimal | нет | Decimal("0.00") | валидатор to_decimal: очистка от пробелов/запятых | нет |
  | income | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | expense | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | total | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | transit_obligation | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | commission | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | percent_broker | Any | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | broker1 | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | broker2 | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | percent_broker2 | Any | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | exchange_rate | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | currency_amount | Decimal | нет | Decimal("0.00") | валидатор to_decimal | нет |
  | currency | Optional[str] | нет | "" | — | нет |
  | filters | Optional[str] | нет | "" | — | нет |
  | _sheet_name | Optional[str] | нет | None | private attribute | нет |
  | _row_index | Optional[int] | нет | None | private attribute | нет |
  | _file_path | Optional[str] | нет | None | private attribute | нет |
  | is_template_warning | bool | нет | False | — | нет |
- Конфиг модели: `coerce_numbers_to_str=True`, `extra="allow"` (доп. колонки сохраняются)
- Связи:
  - нет (in-memory DTO; экземпляры создаются из строк staging_data/raw_content_json в LogicService)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory, GC
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: field_validator `validate_date` (date), `to_decimal` (числовые поля) — нормализация до Decimal/str
  - afterCreate: [NOT SPECIFIED]
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-012: PathsConfig
- Тип: model class (Pydantic BaseModel, in-memory)
- Местоположение: APP/core/bootstrap.py (строки 23–28)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | master_file | str | нет | "Master_Report.xlsx" | — | нет |
  | source_root | str | нет | "REPORTS" | — | нет |
  | source_roots | Optional[List[str]] | нет | None | — | нет |
- Связи:
  - → Entity-016 AppConfig (many-to-one, как поле paths)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: [NOT SPECIFIED]
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-013: DatabaseConfig
- Тип: model class (Pydantic BaseModel, in-memory)
- Местоположение: APP/core/bootstrap.py (строки 31–37)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | path | str | нет | "cache.db" | — | нет |
  | schema_path | str | нет | "db_schema.sql" | — | нет |
  | timeout | float | нет | 30.0 | — | нет |
  | allow_local_fallback | bool | нет | False | — | нет |
- Связи:
  - → Entity-016 AppConfig (many-to-one, как поле database)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks: [NOT SPECIFIED] для всех

### Entity-014: LockingConfig
- Тип: model class (Pydantic BaseModel, in-memory)
- Местоположение: APP/core/bootstrap.py (строки 40–44)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | retry_count | int | нет | 3 | — | нет |
  | retry_backoff | float | нет | 1.0 | — | нет |
- Связи:
  - → Entity-016 AppConfig (many-to-one, как поле locking)
- Каскады: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory
- Триггеры/Hooks: [NOT SPECIFIED] для всех

### Entity-015: NetworkConfig
- Тип: model class (Pydantic BaseModel, in-memory)
- Местоположение: APP/core/bootstrap.py (строки 47–50)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | drive_letters | List[str] | нет | ["Q", "Z"] | — | нет |
- Связи:
  - → Entity-016 AppConfig (many-to-one, как поле network)
- Каскады: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory
- Триггеры/Hooks: [NOT SPECIFIED] для всех

### Entity-016: AppConfig
- Тип: model class (Pydantic BaseModel, in-memory)
- Местоположение: APP/core/bootstrap.py (строки 53–65)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | paths | PathsConfig | нет | PathsConfig() | — | нет |
  | database | DatabaseConfig | нет | DatabaseConfig() | — | нет |
  | locking | LockingConfig | нет | LockingConfig() | — | нет |
  | network | NetworkConfig | нет | NetworkConfig() | — | нет |
  | sh1 | Dict[str, Any] | нет | {} | — | нет |
  | logic | Dict[str, Any] | нет | {} | — | нет |
  | curators | Dict[str, Any] | нет | {} | — | нет |
  | validation | Dict[str, Any] | нет | {} | — | нет |
- Конфиг модели: `extra="allow"` (доп. секции config.yaml сохраняются)
- Связи:
  - → Entity-012 PathsConfig (one-to-one, поле paths)
  - → Entity-013 DatabaseConfig (one-to-one, поле database)
  - → Entity-014 LockingConfig (one-to-one, поле locking)
  - → Entity-015 NetworkConfig (one-to-one, поле network)
- Каскады: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory
- Триггеры/Hooks:
  - beforeCreate: Pydantic-валидация секций при загрузке config.yaml (ConfigController); при невалидной секции — warning + safe defaults
  - afterCreate: [NOT SPECIFIED]
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-017: CustomerAlias
- Тип: model class (plain Python class with `__slots__`, in-memory)
- Местоположение: APP/core/infra/customer_alias_repo.py (строки 17–39)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | id | Optional[int] | нет | None | — | нет |
  | master_customer | str | да | — | strip() в __init__ | нет |
  | rsch_customer | str | да | — | strip() в __init__ | нет |
  | notes | str | нет | "" | — | нет |
  | created_at | Optional[str] | нет | None | — | нет |
  | updated_at | Optional[str] | нет | None | — | нет |
- Связи:
  - → Entity-010 customer_aliases (one-to-one, ORM-маппинг строки таблицы)
- Каскады: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory DTO
- Триггеры/Hooks:
  - beforeCreate: `__init__` нормализует master_customer/rsch_customer через strip()
  - afterCreate: [NOT SPECIFIED]
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-018: RuntimeResult
- Тип: model class (dataclass frozen=True, in-memory)
- Местоположение: APP/core/ui/dashboard_state.py (строки 28–35)
- Поля:
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | label | str | да | — | — | нет |
  | ok | bool | да | — | — | нет |
  | message | str | да | — | — | нет |
  | path | Path \| None | нет | None | — | нет |
  | rows | int \| None | нет | None | — | нет |
  | created_at | datetime \| None | нет | None | — | нет |
- Связи:
  - → Entity-019 runtime_state.json (коллекция, сериализуется в JSON-массив)
- Каскады: [NOT SPECIFIED, DEFAULT APPLIES] — in-memory, frozen
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: [NOT SPECIFIED]
  - beforeUpdate: [NOT SPECIFIED] (frozen — обновление через пересоздание)
  - afterUpdate: [NOT SPECIFIED]
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

### Entity-019: runtime_state.json
- Тип: in-memory (JSON-файл, сериализованная коллекция RuntimeResult)
- Местоположение: APP/runtime_state.json; логика APP/core/ui/dashboard_state.py (`load_runtime_results`, `save_runtime_results`)
- Поля (элемент массива):
  | Поле | Тип | Обязательное? | По умолчанию | Ограничения | Индекс |
  |------|-----|---------------|--------------|-------------|--------|
  | label | str | да | — | непустое после strip | нет |
  | ok | bool | да | — | — | нет |
  | message | str | да | — | непустое после strip | нет |
  | path | str | нет | "" | сериализуется как str(Path) | нет |
  | rows | int \| null | нет | null | — | нет |
  | created_at | str | нет | null | ISO-формат datetime | нет |
- Ограничение: хранится максимум 10 записей (срез `[:10]` при загрузке и сохранении)
- Связи:
  - → Entity-018 RuntimeResult (one-to-many, каждый элемент массива = один RuntimeResult)
- Каскады:
  - При удалении: [NOT SPECIFIED, DEFAULT APPLIES] — перезапись файла при сохранении
  - При обновлении: [NOT SPECIFIED, DEFAULT APPLIES]
- Триггеры/Hooks:
  - beforeCreate: [NOT SPECIFIED]
  - afterCreate: `save_runtime_results` (dashboard_state.py:154) — сериализация списка RuntimeResult в JSON, запись в файл
  - beforeUpdate: [NOT SPECIFIED]
  - afterUpdate: новая запись добавляется в начало списка, список обрезается до 10, файл перезаписывается (ui_dashboard.py:417–420)
  - beforeDelete: [NOT SPECIFIED]
  - afterDelete: [NOT SPECIFIED]

---

## 2. ER-диаграмма (текстовая)

```
sessions ──has many──→ source_files
sessions ──has many──→ consolidated_results
sessions ──has many──→ template_errors
source_files ──has many──→ staging_data

_migrations               [автономная — учёт миграций]
file_cache                [автономная — кэш дат файлов]
row_cache                 [автономная — кэш распарсенных строк]
discovery_cache           [автономная — кэш сканирования директорий]
customer_aliases          [автономная — справочник алиасов сверки]

AppConfig ──has one──→ PathsConfig
AppConfig ──has one──→ DatabaseConfig
AppConfig ──has one──→ LockingConfig
AppConfig ──has one──→ NetworkConfig

CustomerAlias ──maps to──→ customer_aliases (строка таблицы)
FinancialRowSchema        [in-memory DTO, источник: staging_data.raw_content_json]

runtime_state.json ──has many──→ RuntimeResult
```

---

## 3. Ограничения БД

| Таблица | Поле | Тип ограничения | Значение |
|---------|------|-----------------|----------|
| _migrations | filename | PRIMARY KEY | TEXT, уникальный идентификатор файла миграции |
| _migrations | applied_at | DEFAULT | CURRENT_TIMESTAMP |
| sessions | session_id | PRIMARY KEY | TEXT |
| sessions | created_at | DEFAULT | CURRENT_TIMESTAMP |
| sessions | status | DEFAULT | 'in_progress' |
| source_files | id | PRIMARY KEY | INTEGER AUTOINCREMENT |
| source_files | session_id | NOT NULL | — |
| source_files | session_id | FOREIGN KEY | REFERENCES sessions(session_id) |
| source_files | file_path | NOT NULL | — |
| source_files | status | DEFAULT | 'pending' |
| staging_data | id | PRIMARY KEY | INTEGER AUTOINCREMENT |
| staging_data | file_id | NOT NULL | — |
| staging_data | file_id | FOREIGN KEY | REFERENCES source_files(id) |
| staging_data | status | DEFAULT | 'raw' |
| consolidated_results | id | PRIMARY KEY | INTEGER AUTOINCREMENT |
| consolidated_results | session_id | NOT NULL | — |
| consolidated_results | session_id | FOREIGN KEY | REFERENCES sessions(session_id) |
| template_errors | id | PRIMARY KEY | INTEGER AUTOINCREMENT |
| template_errors | session_id | NOT NULL | — |
| template_errors | session_id | FOREIGN KEY | REFERENCES sessions(session_id) |
| file_cache | file_path | PRIMARY KEY | TEXT |
| file_cache | last_updated | DEFAULT | CURRENT_TIMESTAMP |
| row_cache | (file_path, date_key) | PRIMARY KEY | составной |
| row_cache | file_path | NOT NULL | — |
| row_cache | mtime | NOT NULL | — |
| row_cache | size | NOT NULL | — |
| row_cache | date_key | NOT NULL | — |
| row_cache | rows_json | NOT NULL | — |
| row_cache | row_count | DEFAULT | 0 |
| row_cache | created_at | DEFAULT | CURRENT_TIMESTAMP |
| discovery_cache | roots_key | PRIMARY KEY | TEXT |
| discovery_cache | scanned_at | NOT NULL | — |
| discovery_cache | files_json | NOT NULL | — |
| customer_aliases | id | PRIMARY KEY | INTEGER AUTOINCREMENT |
| customer_aliases | master_customer | NOT NULL | — |
| customer_aliases | rsch_customer | NOT NULL | — |
| customer_aliases | (master_customer, rsch_customer) | UNIQUE | составной |
| customer_aliases | notes | DEFAULT | '' |
| customer_aliases | created_at | DEFAULT | CURRENT_TIMESTAMP |
| customer_aliases | updated_at | DEFAULT | CURRENT_TIMESTAMP |

> Примечание: `PRAGMA foreign_keys = ON` установлен в db_schema.sql и в db_connection.py (get_connection). Ни один FK не имеет явных ON DELETE / ON UPDATE — применяется SQLite default NO ACTION.

---

## 4. Индексы

| Таблица | Поля | Тип | Назначение |
|---------|------|-----|------------|
| _migrations | filename | PRIMARY KEY (неявный) | быстрый lookup применённых миграций |
| sessions | session_id | PRIMARY KEY (неявный) | быстрый lookup сессии |
| source_files | id | PRIMARY KEY (неявный) | доступ к записи файла по id |
| source_files | session_id | INDEX (idx_files_session) | фильтрация файлов по сессии |
| staging_data | id | PRIMARY KEY (неявный) | доступ к строке staging |
| staging_data | file_id | INDEX (idx_staging_file) | выборка строк по файлу |
| staging_data | (employee_name, date_val) | INDEX (idx_staging_employee_date) | фильтрация/сортировка по сотруднику и дате |
| consolidated_results | id | PRIMARY KEY (неявный) | доступ к результату |
| consolidated_results | session_id | INDEX (idx_consolidated_session) | фильтрация результатов по сессии |
| template_errors | id | PRIMARY KEY (неявный) | доступ к ошибке |
| file_cache | file_path | PRIMARY KEY (неявный) | lookup кэша по пути |
| row_cache | (file_path, date_key) | PRIMARY KEY (составной) | уникальная запись кэша строк |
| row_cache | (file_path, mtime, size) | INDEX (idx_row_cache_lookup) | быстрый lookup по fingerprint файла |
| discovery_cache | roots_key | PRIMARY KEY (неявный) | lookup кэша сканирования |
| customer_aliases | id | PRIMARY KEY (неявный) | доступ к алиасу |
| customer_aliases | master_customer | INDEX (idx_aliases_master) | поиск алиасов по master-заказчику |
| customer_aliases | rsch_customer | INDEX (idx_aliases_rsch) | поиск алиасов по РСЧ-заказчику |
| customer_aliases | (master_customer, rsch_customer) | UNIQUE (неявный) | запрет дубликатов пар |

---

## 5. Миграции

| Версия | Описание | Дата | Breaking? |
|--------|----------|------|-----------|
| 001_numeric_to_text.sql | Изменение типа финансовых колонок (amount, total_amount, commission, net_amount) с NUMERIC на TEXT для сохранения точности Decimal. Table-rebuild pattern: создание `_new` таблицы, копирование с CAST(... AS TEXT), DROP старой, RENAME. Пересоздание индексов idx_staging_file, idx_staging_employee_date, idx_consolidated_session. | 2026-06-18 | да (DROP TABLE staging_data, consolidated_results) |
| 002_customer_aliases.sql | Создание таблицы customer_aliases для сверки (master_customer ↔ rsch_customer) с UNIQUE-ограничением и индексами idx_aliases_master, idx_aliases_rsch. | 2026-06-18 | нет (CREATE TABLE IF NOT EXISTS, аддитивная) |

> Механика применения: `SQLiteConnectionManager._run_migrations` (db_connection.py:177) — сортировка файлов по имени, проверка применённых в `_migrations`, backup БД перед миграцией (`_backup_db`), построчное выполнение в BEGIN IMMEDIATE, запись в `_migrations` в той же транзакции. Очистка устаревших кэшей (`_cleanup_old_cache_entries`) после миграций: row_cache/file_cache > 7 дней, discovery_cache > 12 часов.
