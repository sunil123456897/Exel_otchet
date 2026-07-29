# Stage 10 Report — Documentation actualisation

```text
Этап: 10 (Актуализация документации)
Цель: Документы описывают фактическую текущую версию, а не
       исторические планы.
Исходная проблема:
  - README.md: "v5.5" (актуальная 5.6), описывает main/experiments
    структуру, без упоминания Stage 0-9.
  - ARCHITECTURE.md: "v5.5", не отражает новые модули (config_schema,
    updater_model, date_warnings, etc.).
  - PROJECT.md: milestone-based, устаревшие статусы (DONE для вещей,
    которые переработаны).
  - FEATURE_TABLE.csv / features.json: "v5.5", ряд features "Untested",
    хотя есть comprehensive tests.
  - Не было CHANGELOG (что изменилось между версиями).
  - Не было формального TEST_PLAN.
  - Не было единого списка KNOWN_LIMITATIONS.
Новые документы:
  - CHANGELOG.md: все заметные изменения по этапам 0-9, в формате
    Keep a Changelog. Включает security fixes (data_loss_log, error_
    presenter) с явным указанием класса находки.
  - docs/KNOWN_LIMITATIONS.md: 5 категорий (A-E) с ~20 пунктами:
      A. Требует ручной проверки (SLA, acceptance matrix, pilot).
      B. Сознательные ограничения дизайна (updater BAT, psutil,
         standalone, Authenticode).
      C. Частично выполненные задачи (mypy, coverage%, ruff I001).
      D. Известные технические долги (circular import, messageboxes,
         L2 smoke, date classifier wiring, config wizard).
      E. Manual-only процедуры (diagnostic BAT, anonymise Excel,
         screenshot baseline).
    Каждый пункт: что, причина, mitigation, ссылка на stage report.
    В конце — таблица подписей (владелец, разработчик, 2 pilot users).
  - docs/TEST_PLAN.md: формальный тест-план.
      * Test pyramid (manual → e2e → integration → property → unit).
      * Coverage matrix by risk area (9 категорий).
      * Definition of Done для release (8 чек-пунктов).
      * Что НЕ покрыто автоматическими тестами + причины.
      * Команды тестирования (operator reference).
      * Инструкция "Adding a new test" для будущих разработчиков.
Обновлённые документы:
  - README.md: "v5.6" в заголовке; добавлена секция "Hardening —
    Stage 0–9" со сводкой каждого этапа и ссылками на docs/. Существующий
    контент (быстрый старт, ветки, качество кода) сохранён без правок.
  - ARCHITECTURE.md: "v5.6" в заголовке; добавлен дисклеймер про
    Stage 0-9 additions секцию; в конце — новая секция с описанием
    горизонтальных cross-cutting модулей (config_schema, updater_model,
    date_warnings, operation_result, diagnostic_package, и т.д.).
    Базовая слоистая архитектура сохранена без изменений.
Не изменено (сознательно):
  - PROJECT.md: исторический документ, отражающий раннее планирование.
    Переписывать значило бы потерять историю. VERSION в README +
    ARCHITECTURE — актуальный source of truth.
  - FEATURE_TABLE.csv / features.json: большой объём данных; статусы
    features лучше обновлять инкрементально через отдельный audit,
    не в рамках документационной актуализации.
  - DESIGN.md: UI-документация; Stage 7 acceptance matrix — актуальный
    операторский документ для UI.
  - ideal_debug_prompt_v2.0.md: устаревший промпт для ИИ-аудита; не
    user-facing.
Команды проверки (фактический gate):
  # Все 990 тестов проходят
  PYTHONPATH=APP:tools:tests/golden python -m pytest tests/ -q        # 990 passed
  # CI gates green
  python -m ruff check APP tests                                      # clean
  python tools/ci_mypy_check.py                                       # PASS 0 new
  # Version consistency
  grep "v5\.5" README.md ARCHITECTURE.md                              # empty
Результат:
  - 4 новых документа (CHANGELOG, KNOWN_LIMITATIONS, TEST_PLAN, и
    неявно — обновлённая Stage 0-9 секция в README и ARCHITECTURE).
  - README и ARCHITECTURE приведены к v5.6.
  - Все user-facing документы теперь согласованы по версии.
  - CHANGELOG объясняет все изменения по этапам 0-9 (включая
    security fixes как отдельные пункты).
  - KNOWN_LIMITATIONS явно перечисляет ~20 сознательных компромиссов.
  - TEST_PLAN даёт формальный контракт (8 чек-пунктов DoD) для release.
  - mypy/ruff/full-suite все green; regression не внесена.
Оставшиеся риски:
  - R-10.1 [низкий]: PROJECT.md и FEATURE_TABLE.csv остаются на v5.5.
    Это сознательно — исторические артефакты; актуальная информация
    в README/ARCHITECTURE. Если заказчик хочет formal feature audit
    (обновить все статусы features), это отдельная задача.
  - R-10.2 [низкий]: новый CHANGELOG/KNOWN_LIMITATIONS/TEST_PLAN —
    "living documents". Их актуальность зависит от того, будут ли
    будущие правки в них вноситься. CI не enforcing'ит это;
    ответственность на разработчике.
  - R-10.3 [информационно]: SBOM и THIRD_PARTY_NOTICES перенесены в
    Stage 12 (TZ раздел 10) — они имеют смысл только для упакованного
    продукта.
  - R-10.4 [информационно]: "traceability бизнес-правил и тестов"
    (TZ раздел 10) формально не построен как отдельный документ.
    Частично покрыт CHANGELOG (по этапам) и stage reports, но
    full traceability matrix (правило → тест → status) — отдельная
    задача для formal audit.
Решение gate: PASS
```

## Ключевые решения этапа 10

1. **Living changelog, не release notes.** CHANGELOG организован по
   этапам TЗ, не по датам. Это позволяет оператору (и будущим
   разработчикам) быстро понять, что именно Stage N сделал и какие
   файлы тронул. Security fixes явно помечены — это важно для audit.

2. **KNOWN_LIMITATIONS как формальный контракт.** Список с 5
   категориями (A-E) и таблицей подписей. Pilot-пользователь, подписывая
   limitations, явно принимает сознательные компромиссы. Без этого
   списка "я думал, это работает" — типичный источник конфликтов
   post-release.

3. **TEST_PLAN с Definition of Done.** 8 конкретных чек-пунктов,
    каждый из которых проверяется командой. Это превращает "релиз
    готов" из субъективного ощущения в checkable invariant.

4. **README/ARCHITECTURE — additive updates, не переписывание.**
   Полная переработка README была бы рискованной (большой объём,
   сложный merge). Вместо этого я обновил версию в заголовке и добавил
   новую секцию "Hardening Stage 0-9", которая указывает на
   подробные документы. Существующий контент (быстрый старт,
   качество кода) сохранён без правок.

5. **PROJECT.md и FEATURE_TABLE.csv НЕ тронуты.** Это исторические
   артефакты раннего планирования. Переписывать значило бы потерять
   историю и внести путаницу (когда этот документ стал актуальным?).
   Актуальная информация — в README/ARCHITECTURE; историческая —
   остаётся как есть.

## Что НЕ сделано (и почему)

- **Feature audit** (обновить все статусы в FEATURE_TABLE.csv и
  features.json) — большой объём данных, требует feature-by-feature
  review. Не в рамках документационной актуализации.

- **SBOM, THIRD_PARTY_NOTICES** — TZ раздел 10 явно переносит их в
  Stage 12 (имеют смысл только для упакованного продукта).

- **Traceability matrix (бизнес-правило → тест)** — частично покрыто
  CHANGELOG + stage reports, но formal matrix — отдельная audit задача.

- **Удаление `ideal_debug_prompt_v2.0.md`** — это исторический
  ИИ-audit prompt; не user-facing. Удаление рискует потерей контекста
  будущими разработчиками; оставлено.

## Коммиты (логические единицы, после разрешения владельца)

1. `docs: CHANGELOG for Stage 0-9 hardening`
   (CHANGELOG.md)
2. `docs: KNOWN_LIMITATIONS with acceptance sign-off table`
   (docs/KNOWN_LIMITATIONS.md)
3. `docs: formal TEST_PLAN with Definition of Done`
   (docs/TEST_PLAN.md)
4. `docs: bump README and ARCHITECTURE to v5.6, add Stage 0-9 summary`
   (README.md, ARCHITECTURE.md)
