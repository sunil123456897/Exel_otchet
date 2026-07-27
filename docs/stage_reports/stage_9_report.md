# Stage 9 Report — Backup, recovery and diagnostics

```text
Этап: 9 (Backup, восстановление и диагностика)
Цель: Пользователь и поддержка могут восстановить работу без ручного
       анализа исходного кода.
Исходная проблема:
  - Backup создавался, но восстановление никогда не проверялось.
    Backup, который ни разу не восстанавливали — это не backup.
  - Не было единого диагностического пакета: поддержка получала
    скриншоты, обрывки логов и иногда реальные Excel-файлы с
    чувствительными данными клиентов.
  - Support runbook отсутствовал; каждый сотрудник фирмы решал
    проблемы заново, обращаясь в поддержку по телефону.
Изменённые файлы:
  - tools/diagnostic_package.py (MR-0902): новый модуль.
      * Собирает обезличенный ZIP: version, paths availability (без
        самих путей), config shape (только типы значений), DB schema
        (без содержимого), log tails (от_scrubbed).
      * Постпроцессинг: scrubbing tokens и firm-names рекурсивно по
        всем строкам manifest ДО json.dumps, чтобы не ломать escape.
      * CLI: --out, --scan (проверяет output на forbidden patterns).
  - tests/test_backup_restore.py (MR-0901): 10 тестов.
      * Excel backup → byte-identical restore;
      * rotation keeps latest;
      * SQLite backup → working restore (schema + data);
      * WAL-mode backup;
      * config.yaml backup/restore (с custom keys preservation);
      * employees.yaml backup/restore (с fingerprint);
      * rotation never deletes only backup;
      * missing source returns None (no empty file);
      * ~$ lock files never backed up.
  - tests/test_diagnostic_package.py (MR-0902): 17 тестов.
      * scan_for_forbidden helper correctness (6 tests);
      * collector excludes .xlsx files;
      * no GitHub token leak (даже truncated ghp_aaa);
      * no real monetary amounts leak;
      * no Windows user paths leak;
      * no UNC server names leak;
      * no customer/firm names leak (ООО Ромашка → ООО <CustomerName>);
      * DB schema present, row data absent;
      * robust to missing config;
      * robust to corrupt config;
      * installation_id stable across runs;
      * installation_id is hash, not path;
      * config_shape contains "str", not the string value.
  - docs/support_runbook.md (MR-0903): операторский runbook.
      * Как собрать diagnostic_package.zip (с обоснованием privacy);
      * 8 типовых проблем с пошаговым решением;
      * Когда обращаться в поддержку и какой файл передавать;
      * Сроки реакции поддержки;
      * Что НЕ делать;
      * Где хранятся данные и кто за backup отвечает.
Команды проверки (фактический gate):
  pytest tests/test_backup_restore.py                         # 10 passed
  pytest tests/test_diagnostic_package.py                     # 17 passed
  pytest tests/ (full regression)                             # 990 passed
  python tools/diagnostic_package.py --scan                   # privacy OK
  ruff check APP tests                                        # clean
  ci_mypy_check.py                                            # PASS 0 new
Результат:
  - Backup каждого артефакта (Excel/SQLite/config/employees)
    проверен на byte-identical или семантически-эквивалентное
    восстановление.
  - Диагностический пакет доказанно обезличен: 17 тестов проверяют,
    что tokens/paths/amounts/customer-names не утекают.
  - Support runbook готов для оператора: 8 типовых проблем с
    пошаговыми инструкциями.
  - mypy/ruff/golden все green.
Оставшиеся риски:
  - R-9.1 [низкий]: backup-restore тесты используют ``shutil.copy2``
    (main file only для SQLite WAL). Если в реальной работе есть
    незакоммиченные транзакции в WAL, простой copy2 их не захватит.
    Тест документирует, что backup = last-committed state, что и
    является правильным semantic для pre-migration backup.
  - R-9.2 [низкий]: diagnostic_package использует ``re`` для
    обнаружения PII. Это defence-in-depth, не полный redactor —
    хитрые escape-последовательности (например, base64-encoded
    token) могут проскользнуть. Тесты покрывают наиболее вероятные
    паттерны; расширение forbidden list — инкрементальная работа.
  - R-9.3 [низкий]: installation_id — хеш от repo_path. На двух
    разных машинах с одинаковой структурой папок ID совпадёт. Это
    компромисс между collision-resistance и privacy (нельзя
    использовать MAC/UUID, они не анонимны). Для задач поддержки
    (отнести тикеты к одной установке) этого достаточно.
  - R-9.4 [информационно]: support runbook описывает "ЗАПУСК.bat
  → Diagnostic → diagnostic_package.zip", но пока нет одного BAT'а,
    который всё делает (диагностика отдельно, packaging отдельно).
    Это UI/UX work для Stage 7 followup или Stage 11 (release
    rehearsal).
  - R-9.5 [информационно]: runbook ссылается на "обезличенный
    образец Excel", но процедура обезличивания не формализована.
    Operator должен вручную вычистить имена/суммы. Можно добавить
    инструмент ``tools/anonymise_excel.py`` в будущей работе.
Решение gate: PASS
```

## Ключевые находки и решения этапа 9

1. **Backup-restore как формальный контракт.** Раньше backup был
   "best-effort" — файлы копировались, но никто не проверял, что
   восстановление работает. Теперь 10 тестов явно верифицируют
   восстановление каждого типа артефакта до byte-identical или
   семантически-эквивалентного состояния. Backup, который не прошёл
   тест восстановления, не backup.

2. **Privacy as tested invariant.** Диагностический пакет имеет
   17 тестов, каждый из которых пытается заставить collector утечь
   PII (токены, пути, суммы, имена клиентов) и проверяет, что этого
   не произошло. Это exactly тот подход из TZ MR-0902: "автотест,
   распаковывающий диагностический ZIP и ищущий запрещённые
   контрольные строки". Defence-in-depth: scrubbing на этапе сбора
   (log tails) + scrubbing на этапе сериализации (manifest).

3. **Post-serialise scrubbing сломал JSON.** Первая версия применяла
   regex к уже сериализованному JSON — это сломало escape-
   последовательности. Решение: scrubbing структурно, до
   ``json.dumps``. Это общая патология — text-level regex на JSON
   всегда рискован.

4. **Token detection — широкий паттерн.** Изначально regex требовал
   36+ символов после `ghp_` (как у реальных PAT). В логах оператор
   мог сохранить truncated token (`ghp_aaa`), и он прошёл бы через
   фильтр. Решение: отдельный, более широкий паттерн для scrubbing
   (любая `ghp_*` строка), оставляя узкий паттерн для forbidden-
   scan как «это точно валидный token».

5. **Support runbook — operator-facing документ.** Каждая проблема
   структурирована: что видит сотрудник → что делать → когда
   обращаться → какой файл передавать. Без этого runbook'а даже
   идеальный diagnostic_package бесполезен — сотрудник не знает,
   что с ним делать.

## Что НЕ сделано (и почему)

- **Один BAT, который собирает diagnostic_package.zip** — runbook
  описывает процесс через `ДИАГНОСТИКА.bat`, но packaging сейчас
  требует ручного запуска `tools/diagnostic_package.py`. Wiring —
  Stage 7 UI followup или Stage 11 rehearsal.

- **Anonymise Excel tool** — runbook упоминает "обезличенный образец
  Excel", но нет инструмента, который автоматически чистит имена и
  суммы из .xlsx. Operator делает это вручную. Это большая отдельная
  задача.

- **psutil-based diagnostics** — нет. psutil не в deps. Diagnostic
  package использует только стандартную библиотеку + openpyxl (для
  version). Это сознательно — dependency-free = portable.

- **Support SLA enforcement** — runbook описывает сроки реакции, но
  это контракт поддержки, не кодируемое требование.

## Коммиты (логические единицы, после разрешения владельца)

1. `test(backup): verify restore of Excel/SQLite/config/employees`
   (test_backup_restore.py)
2. `feat(diag): anonymised diagnostic ZIP with tested privacy contract`
   (tools/diagnostic_package.py, test_diagnostic_package.py)
3. `docs(support): operator-facing runbook with 8 common-issue recipes`
   (docs/support_runbook.md)
