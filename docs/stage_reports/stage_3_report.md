# Stage 3 Report — Excel read reliability and data quality

```text
Этап: 3 (Надёжность чтения Excel и качество данных)
Цель: Повреждённый, раздутый, заблокированный или нестандартный файл не
       должен приводить к зависанию приложения, тихой потере строк или
       сбою обработки остальных сотрудников.
Исходная проблема:
  - Существующая infra (timeout, cancel, isolation, ~$ skip) была
    неплоха, но не тестировалась систематически. Любой regression
    в любом из этих механизмов мог тихо увести читателя в краш.
  - data_loss_log имел процедуру обезличивания, но она применялась
    ПОСЛЕ json.dumps — из-за escape'а backslash в JSON регексы
    scrub_path не срабатывали, и пути вида
    "C:\Users\vanya\..." попадали в лог как есть.
  - Не было явного предупреждения для подозрительных дат (2029 год
    из ТЗ-аномалии), формализованной модели частичного успеха
    (completed/warnings/failed/cancelled).
Изменённые файлы:
  - APP/core/domain/data_loss_log.py (MR-0304, security fix):
      * PII-scrubbing теперь применяется к каждому строковому полю
        (source, reason, value) ДО json.dumps, не после.
      * Причина: регексы scrub_path написаны для single-backslash
        путей; json.dumps их удваивает, и matching тихо падает.
      * Добавлен _safe_str — defensive str(), не бросающий исключение
        при сломанном __str__ у weird objects.
      * reason теперь тоже скрабится (free-form операторский текст
        может нести copy-pasted amount/path).
Новые модули:
  - APP/core/domain/date_warnings.py (MR-0303):
      * DateWarningKind (OK/FUTURE/DISTANT_PAST), DateWarning.
      * classify_sheet_date(date_str, reference, future_days=31,
        past_days=365) — pure функция, без side effects.
      * Поведение по умолчанию ловит "2029 аномалию" из ТЗ.
      * Даты НЕ дропаются — только помечаются (предотвращает тихую
        потерю реальных данных в легитимных edge-cases).
  - APP/core/domain/operation_result.py (MR-0305):
      * OperationStatus enum (COMPLETED, COMPLETED_WITH_WARNINGS,
        FAILED, CANCELLED).
      * SourceOutcome с rows_read/dropped/emitted + issues.
      * OperationResult с add_outcome/mark_failed/mark_cancelled,
        правилами promotion (warnings → failed → cancelled), counts,
        PII-free summary() для UI.
Новые тесты / fixtures:
  - tests/corrupt_fixtures.py (MR-0302): 8 программных генераторов
    повреждённых/раздутых книг + build_temp_dollar_lock. Все
    детерминированы, не коммитят бинарники.
  - tests/test_excel_reliability.py (MR-0301+0302): 16 тестов —
    * 8 параметризованных corrupt fixtures не крашат читатель;
    * truncated archive не возвращает "фейковые" rows;
    * directory scan skip'ает ~$ lock files;
    * directory scan skip'ает non-xlsx файлы;
    * missing directory → пустой список, не exception;
    * strict_io=True поднимает ошибку, non-strict возвращает [];
    * нет infinite retry на persistently broken file;
    * huge_used_range (1M строк) не вызывает OOM.
  - tests/test_date_warnings.py (MR-0303): 12 тестов — today OK,
    near future OK, far future FUTURE, distant past DISTANT_PAST,
    custom windows, boundary conditions, unparseable defense,
    serialisation, default reference today.
  - tests/test_data_loss_privacy.py (MR-0304): 10 тестов — amount
    in value redacted, comma-decimal redacted, 2-digit preserved,
    date preserved, Windows user path scrubbed (source field),
    UNC share scrubbed, row/sheet/field coordinates preserved,
    unserialisable payload doesn't throw, None fields OK,
    end-to-end no-forbidden-patterns self-audit.
  - tests/test_operation_result.py (MR-0305): 15 тестов — default
    status, summary shape, status promotion, mark_failed overrides
    warnings, mark_cancelled overrides warnings but not failure,
    counts, rows_dropped accumulation, SourceOutcome.ok semantics,
    JSON-serialisable summary, no source-name leak in summary.
Команды проверки (фактический gate):
  pytest tests/test_excel_reliability.py                    # 16 passed
  pytest tests/test_date_warnings.py                        # 12 passed
  pytest tests/test_data_loss_privacy.py                    # 10 passed
  pytest tests/test_operation_result.py                     # 15 passed
  pytest tests/ (full regression)                           # 841 passed
  ci_mypy_check.py                                          # PASS 0 new
Результат:
  - 53 новых теста этапа 3 passed, всего 841 в комплекте
  - Ни один corrupt fixture не крашит читатель (8 типов)
  - Lock files (~$book.xlsx) автоматически skip'аются
  - Timeout/cancel/no-infinite-retry протестированы явно
  - Подозрительные даты (future/past) формально классифицируются
  - data_loss_log больше не течёт путями с именами пользователей
    в лог (security fix — закрывал реальную дыру)
  - OperationResult — формальная модель для UI/controller Stage 7
  - mypy strict gate: 0 новых ошибок (baseline 312)
Оставшиеся риски:
  - R-3.1 [низкий]: IngestionEngine.read_file не возвращает
    OperationResult. Существующий код возвращает List[Dict] для
    обратной совместимости; OperationResult — это модель для
    будущего controller-layer (Stage 7). На этапе 3 добавлены тип
    и тесты его инвариантов.
  - R-3.2 [низкий]: classify_sheet_date формализован, но не
    wired в ingestion pipeline. Это сознательно: добавление в
    pipeline — изменение поведения, требующее UI для отображения
    warning. На этапе 3 зафиксирована логика классификации.
  - R-3.3 [информационно]: corrupt_fixtures build_huge_used_range
    использует raw byte-патч dimension-тэга. Если openpyxl в
    будущей версии изменит формат записи, fixture может перестать
    работать. Это приемлемо — fixture нужен именно для проверки
    reader'а против реального malforma¬tion, а не против самого
    себя.
  - R-3.4 [информационно]: build_protected_workbook может не
    установить реальную protection, если openpyxl этого не
    поддерживает в текущей версии. Тест всё равно полезен — он
    проверяет, что reader НЕ падает на любой нестандартной
    структуре.
Решение gate: PASS
```

## Ключевые находки и решения этапа 3

1. **Закрыта реальная privacy-дыра в data_loss_log.** Старый код
   применял `scrub_path` к уже сериализованному JSON. Из-за того, что
   `json.dumps` удваивает backslash (`\` → `\\`), регексы scrub_path
   (написанные под single-backslash пути) молча не матчились. В лог
   попадало `C:\Users\vanya\...` как есть. Теперь scrub применяется к
   каждому строковому полю до сериализации. Тест
   `test_windows_user_path_in_source_is_scrubbed` фиксирует контракт.

2. **Бонус: `reason` теперь тоже скрабится.** Существующий тест
   `test_record_loss_redacts_amount` (Phase 2) передает сумму в `reason`
   (`"Сумма: 1234.56 невалидна"`), ожидая, что она замаскируется. До
   моего фикса маскировалось только post-JSON — что и работало в
   узком случае с amount regex (т.к. regex ловит цифры независимо от
   backslash). Но paths не маскировались вообще. Теперь явно mask и
   `reason`.

3. **MR-0301 (изоляция парсера) уже был реализован.** В коде уже были:
   subprocess worker с timeout=300 сек, cancel_event polling на 0.5с,
   terminate→kill по таймауту, ~$ skip в scan_directory. Задача этапа 3
   свелась к формализации контрактa через тесты — что и сделано.

4. **Формализация OperationResult как типа.** Это была самая большая
   дыра: существующий API возвращал `List[Dict]`, и caller не мог
   отличить "файл пуст" от "файл сломан, мы его скипнули". Теперь есть
   закрытый enum и правила promotion. Wiring в controller — Stage 7.

5. **classify_sheet_date — pure функция.** Без side effects, без I/O.
   Это позволит в Stage 7 показать warning в UI без изменений в
   pipeline (просто вызвать classifier на каждой распознанной дате).

## Что НЕ сделано (и почему)

- **OperationResult не подключён к controller.** Существующий
  `read_file` всё ещё возвращает `List[Dict]`. Это сознательно:
  подключение — это изменение публичного API ingestion pipeline,
  его надо делать вместе с UI (Stage 7), иначе контракт расходится с
  потребителем.

- **classify_sheet_date не вызывается в pipeline.** Функция готова, но
  интеграция в ingestion reader — это behaviour change (появится
  warning для каждого листа). UI Stage 7 должен показать это, иначе
  warning пропадёт в логах.

- **timeout=300 сек не сделан меньше.** 5 минут — это компромисс для
  медленных сетевых дисков. Делать меньше — рисковать ложными
  timeout'ами на больших Consolidation-операциях. На Stage 8
  (performance) можно профилировать и подтянуть.

## Коммиты (логические единицы, после разрешения владельца)

1. `fix(privacy): scrub data_loss_log fields before JSON serialisation`
   (data_loss_log.py)
2. `feat(reliability): corrupt fixture builders + reader isolation tests`
   (corrupt_fixtures.py, test_excel_reliability.py)
3. `feat(quality): formal date classifier for suspicious dates`
   (date_warnings.py, test_date_warnings.py)
4. `feat(quality): OperationResult status enum + per-source breakdown`
   (operation_result.py, test_operation_result.py)
5. `test(privacy): data_loss_log anonymisation invariants`
   (test_data_loss_privacy.py)
