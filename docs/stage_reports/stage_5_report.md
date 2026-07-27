# Stage 5 Report — Technical debt reduction (mypy strict + ruff + boundaries)

```text
Этап: 5 (Снижение технического долга без изменения поведения)
Цель: Сделать код предсказуемым для дальнейшего сопровождения.
Исходная проблема:
  - mypy baseline: 312 нормализованных (684 сырых) находок.
  - Самые большие концентрации: app_controller (44), gui_master (62),
    ui_sidebar (36), rsch (74), session_repo (37), export_formatting (32).
  - Архитектурные границы негарантированы: формально domain не зависел
    от tkinter/openpyxl, но не было теста, ловящего regression.
  - ruff только E/F; не использовался I (импорты), B (bugbear), SIM.
Сделано на этом этапе (частично — TЗ закладывает 7-10 дней, в сессии
выполнена первая волна по приоритету риска):
Изменённые файлы:
  - APP/core/domain/data_loss_log.py: record_loss(original_value) и
    _safe_str(v) получили аннотации. original_value → object, v → object.
  - APP/core/domain/data_schemas.py: validate_date(v) → Optional[str],
    to_decimal(v) → Decimal.
  - APP/core/domain/logic_service.py:
      * CuratorStrategy.apply, BorisCuratorStrategy.apply,
        IvanCuratorStrategy.apply — явные аннотации аргументов и
        возврат tuple[Any, Decimal, Decimal];
      * Validator._is_header_like — header_words: tuple[str, ...];
      * LogicService.apply_financial_rules, consolidate — curator и
        curator_config как Optional.
  - APP/core/services/reconciliation_service.py: 3 явные аннотации
    (start_thread_fn, get_drive_letters_fn, alias_repo, selected_date).
  - APP/core/services/rsch_service.py: 4 метода получили явные
    аннотации (Any для date-параметров, Optional для callback'ов).
  - APP/core/ui/gui_master.py, APP/core/ui/ui_settings.py: восстановлены
    Stage 0-фиксы (fallback RuntimeError вместо "5.6") — были случайно
    откачены во время эксперимента с ruff I001.
  - .mypy_baseline.txt: перегенерирован 312 → 303 (684 → 667 сырых).
  - tests/test_single_version_source.py: allowlist обновлён под
    сдвинутые номера строк updater_model.py.
Новые модули:
  - tests/test_architecture_boundaries.py (MR-0503): 47 параметризованных
    тестов:
      * domain не импортирует tkinter/openpyxl/core.ui/core.infra;
      * domain pathlib-использование явно allowlisted;
      * ui не делает финансовую математику (Decimal/to_decimal/
        ROUND_HALF_UP/apply_financial_rules);
      * инвентарь domain модулей стабилен (новый файл требует update
        EXPECTED_DOMAIN_MODULES).
Ruff:
  - Применены безопасные F401 fixes (неиспользуемые импорты в
    date_warnings.py, employees_schema.py, тестах).
  - I001 (unsorted-imports) — ОТОДВИНУТ. Попытка применения вскрыла
    скрытый circular import в core/infra/export_writer.py ↔ core/infra/
    __init__.py; ruff's reorder сделал его явным. Восстановление порядка
    устранило симптомы, но сам cycle — долг для будущей работы.
    Зафиксировано в карточке как R-5.4.
  - B/SIM/UP не применялись: их 1045 находок на full-suite требуют
    поэтапного внедрения (ТЗ явно говорит "без массового смешения
    с логикой"), и каждая требует review (например, UP045 меняет
    Optional[X] → X | None по 322 местам — слишком рискованно в одной
    правке).
Команды проверки (фактический gate):
  pytest tests/test_architecture_boundaries.py              # 47 passed
  pytest tests/ (full regression)                           # 911 passed
  pytest tests/golden/ (invariant regression)               # 55 passed
  ruff check APP tests                                      # All checks passed
  ci_mypy_check.py                                          # PASS 0 new
Результат:
  - mypy strict baseline: 312 → 303 (-9 нормализованных, -17 сырых).
    domain полностью clean, кроме 2 "Any-subclass" ошибок
    (требуют конфигурации mypy_path, не аннотаций).
  - services полностью clean (0 ошибок).
  - 47 новых архитектурных тестов закрепляют границы.
  - ruff E/F чист.
  - Все 911 тестов проходят; golden unchanged (55 passed).
Оставшиеся риски:
  - R-5.1 [средний]: mypy baseline всё ещё 303. Это сознательный
    частичный прогресс в рамках одной сессии. ТЗ закладывает 7-10 дней;
    эта сессия покрыла самую чистую и приоритетную часть (domain +
    services). Полная зачистка app_controller, ui, infra/{export,
    reconciliation, rsch} требует нескольких сессий.
  - R-5.2 [низкий]: 2 mypy-ошибки вида "Class cannot subclass X
    (has type Any)" в logic_service.py — это следствие layout'а
    (APP на sys.path, но не в mypy_path). Убираются конфигом mypy, но
    попытка добавить [tool.mypy] в pyproject вскрыла "Source file
    found twice under different module names" — нужен explicit_package_
    bases или mypy_path. Оставлено на отдельную задачу.
  - R-5.3 [низкий]: скрытый circular import в core.infra.__init__ ↔
    core.infra.export_writer. Сегодня маскируется порядком импортов
    (сработало после revert'а ruff I001). Это долг для отдельной
    сессии — рефакторинг export_writer, чтобы вынести is_file_writable
    из core.infra в core.infra.utils (или наоборот).
  - R-5.4 [низкий]: ruff I001 не применён. Любой будущий запуск
    `ruff check --fix --select I001` повторно вскрыл бы cycle.
    Зафиксировать предупреждением в CODEOWNERS / CONTRIBUTING.
  - R-5.5 [информационно]: core.domain.data_loss_log использует
    pathlib.Path (allowlisted в архитектурном тесте). Чистое разделение
    требовало бы путь лога прокидывать через параметр. Сознательно
    оставлено — текущий дизайн минимизирует поверхность API.
Решение gate: PASS (частичное завершение этапа; mypy baseline снижен,
                   границы закреплены тестами, regression- suite зеленый)
```

## Ключевые решения этапа 5

1. **Прогресс, а не полное завершение.** ТЗ закладывает 7-10 дней на
   mypy; в одной сессии выполнена первая волна по приоритету риска:
   domain (чистая бизнес-логика) и services (финансовая логика). Это
   устранило самые опасные "untyped" функции. Полная зачистка app/
   controller/ui/infra требует отдельных сессий и не меняет контракт.

2. **Архитектурные границы — в виде тестов.** Вместо описания в
   docstring теперь 47 параметризованных тестов, которые падают при
   любой утечке (tkinter в domain, Decimal в UI, новый domain-модуль).
   Это делает регрессию видимой в PR-review.

3. **Ruff I001 не трогать.** Попытка применить "безопасный" autofix
   вскрыла скрытый circular import в `core.infra.__init__`. Auto-реордер
   импортов его обострил. Восстановил порядок; сам cycle — отдельный
   технический долг.

4. **Per-layer isolation.** Все mypy-фиксы сделаны без изменения
   поведения. После каждого модуля — golden run. Доказательство:
   55 golden-тестов прошли до и после.

5. **mypy baseline перегенерирован** на 303 (с 312). Это легитимная
   операция после confirmed fixes — правила CI (MR-0003) говорят
   "обновление baseline допускается отдельным reviewable commit с
   объяснением". Карточка этапа — это объяснение.

## Что НЕ сделано (и почему)

- **app_controller.py (44 ошибки), gui_master.py (62), ui/* , infra/
  {export_writer, rsch, session_repo}** — не аннотированы. Объём
  слишком большой для одной сессии, и большая часть — UI-tkinter код,
  где типизация требует особого подхода (tk.Widget не всегда корректно
  типизирован в stubs).

- **ruff I001/B/SIM/UP** — не применены массово. I001 откатан и
  отложен (см. R-5.4). UP045 (Optional → X | None) — 322 находки,
  требует поэтапного review. B (bugbear) — 12 находок, но каждая
  требует проверки на false-positive.

- **L2 functional smoke в updater** (R-4.2) — по-прежнему skipped.
  Требует golden-test infra, готовой после Stage 5, но wiring —
  отдельная задача.

- **mypy_path конфигурация** — попытка добавить в pyproject.toml не
  удалась из-за "Source file found twice" (layout с APP как пакет
  + на sys.path). Нужен отдельный design.

## Коммиты (логические единицы, после разрешения владельца)

1. `refactor(types): annotate domain + services for mypy strict`
   (5 файлов в core/domain и core/services)
2. `test(arch): 47 boundary tests — domain purity + UI no-fin-math`
   (tests/test_architecture_boundaries.py)
3. `chore(ruff): clean unused imports (F401 autofix)`
   (10 файлов)
4. `chore(mypy): refresh baseline 312→303 after domain+services cleanup`
   (.mypy_baseline.txt)
