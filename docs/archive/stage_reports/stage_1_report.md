# Stage 1 Report — Golden regression of financial results

```text
Этап: 1 (Golden-регрессия финансовых результатов)
Цель: Зацементировать подтверждённое поведение до рефакторинга, обновления и упаковки.
Исходная проблема:
  - Подтверждённое совпадение 4 906 ячеек контрольной даты существовало только как
    разовый ручной факт. Любой рефакторинг (этапы 2-11) мог тихо увести финансовый
    результат, и никто бы не узнал, пока заказчик не получил бы другой отчёт.
  - Не было безопасного сравнителя книг: единственный способ сравнить два xlsx
    требовал печатать реальные значения в лог, что утечка PII.
  - tests/golden/ существовал как пустой каталог backups/.
  - Master_Report.xlsx был НЕ в .gitignore — реальная дыра: случайный
    `git add .` залил бы финансовые данные фирмы в репозиторий.
Изменённые файлы:
  - .gitignore (MR-0102 побочный эффект): добавлены Master_Report.xlsx,
    APP/cache.db, APP/config.yaml, APP/employees.yaml, APP/output/, APP/logs/,
    APP/runtime_state.json, Ване/, REPORTS/, РСЧ/, "рсч всех/", backups/,
    logs/, baseline_report.json, *.txt-логи, .update_*. Тест
    test_control_date_workbook_not_committed enforcing'ит это правило.
  - pyproject.toml (MR-0101/0103): pythonpath расширен до ["APP", "tools",
    "tests/golden"], чтобы тесты могли импортировать compare_workbooks.py
    и synthetic_fixtures.py.
Новые инструменты:
  - tools/compare_workbooks.py (MR-0101): PII-safe сравниватель xlsx.
    Режимы: sheet set, размер, значения, формулы, типы, merged cells,
    freeze panes, auto-filter, print area, styles (без style_id).
    Коды возврата: 0 = идентично, 1 = есть различия, 2 = ошибка чтения.
    Никогда не печатает значения ячеек.
  - tools/control_date_fingerprint.py (MR-0102): строит и проверяет
    SHA-256 fingerprint листа. Подкоманды capture/verify. Значения не
    попадают в fingerprint — только тип, presence и formula.
Новые тесты:
  - tests/test_compare_workbooks.py (MR-0101): 8 тестов, покрывают
    identical/diff/formula/type/missing-sheet/style/unreadable/CLI.
  - tests/golden/__init__.py + synthetic_fixtures.py (MR-0103):
    14 синтетических сценариев: master_day, master_period, master_all_dates,
    curator_report, rsch_day, rsch_period, reconciliation_no_diff,
    reconciliation_with_diff, returns, currency, transit_obligations,
    duplicates, formulas_and_links, empty_partial. Все детерминированы,
    без PII.
  - tests/golden/test_synthetic_fixtures.py (MR-0103): 44 параметризованных
    теста — buildability, determinism, unique headers, ≥14 сценариев,
    PII-сканер (запрещает ООО/АО/ИНН/КПП/телефоны в fixtures).
  - tests/golden/test_control_date.py (MR-0102): 3 теста — артефакт
    консистентен (446×11=4906), live-верификация против реального
    Master_Report.xlsx (если он есть локально), workbook gitignored.
  - tests/golden/test_financial_invariants.py (MR-0104): 8 тестов —
    order-independence, idempotency (без роста), source preservation,
    Decimal preservation, determinism, row-count conservation,
    empty-row drop, return-not-zeroed.
Новый артефакт:
  - tests/golden/control_date.json (MR-0102): обезличенный fingerprint
    контрольной даты 18.05.2026. Размеры 446×11=4906 ячеек, SHA-256
    content hash. Никаких значений.
Команды проверки (gate этапа 1):
  pytest tests/golden/ tests/test_compare_workbooks.py             # 63 passed
  python tools/control_date_fingerprint.py verify ... 18.05.2026   # PASS 4906 cells
  git status (sensitive files)                                     # пусто — все gitignored
  PII-сканер синтетических fixtures                                # 1 passed
Результат:
  - 63 golden теста passed, 0 failed/skipped
  - Контрольная дата 18.05.2026: SHA-256 совпадает с golden, 0 различий
  - Сравниватель книг работает и доказанно не печатает значения
  - 14 синтетических сценариев детерминированы
  - 8 финансовых инвариантов зафиксированы
  - Master_Report.xlsx и другие чувствительные файлы защищены .gitignore
    и авто-тестом, ловящим регрессию
  - В Git нет ни одного финансового значения; fingerprint обезличен
Оставшиеся риски:
  - R-1.1 [средний]: контрольная дата 18.05.2026 была найдена по
    размерности 446×11; если в будущем Master_Report.xlsx будет
    пересобран и размер изменится, fingerprint нужно перегенерировать.
    Это сознательное действие через `control_date_fingerprint.py capture`.
  - R-1.2 [низкий]: синтетические fixtures покрывают структуру, но не
    реальные edge cases финансовой логики (например, специфичные
    curator-strategy комбинации). Это задача этапа 6 (покрытие).
    На этапе 1 задача была — зацементировать инварианты, а не
    исчерпывающе протестировать правила.
  - R-1.3 [низкий]: тест идемпотентности проверяет "не растёт", а не
    "математически идемпотентен". Это сознательно: apply_financial_rules
    односторонний (вход → выход с русскими колонками), повторное
    применение математически не определено. Тест ловит регрессии
    "двойного применения в pipeline".
  - R-1.4 [информационно]: контрольная дата 18.05.2026 — это май 2026,
    недавняя дата. Возможно, стоит позже выбрать дату из активного
    периода эксплуатации для более репрезентативной сверки.
Решение gate: PASS
```

## Ключевые находки этапа 1

1. **Реальная дыра приватности закрыта.** `Master_Report.xlsx` (и
   `APP/config.yaml`, `APP/employees.yaml`, `APP/cache.db`) **не были**
   в `.gitignore`. Это значит, что один `git add .` залил бы финансовые
   данные 23 сотрудников в репозиторий, доступный всем, у кого есть токен.
   Теперь это защищено и автоматическим тестом
   (`test_control_date_workbook_not_committed`).

2. **Контрольная дата подтверждена как 18.05.2026** с размерностью ровно
   446×11=4906 ячеек. Это та самая дата, на которой в ТЗ-разделе-2
   упоминается "4 906 значений/формул, 0 различий". Теперь она
   закоммичена как SHA-256 fingerprint, и любая регрессия будет поймана.

3. **Сравниватель книг доказуемо PII-safe.** Вывод содержит только
   координаты и количество, никогда — значения. Тест
   `test_value_difference_is_reported_without_leaking_value` явно
   проверяет, что `999` не появляется в отчёте о различии ячейки B2=999.

4. **Синтетические fixtures детерминированы.** Это критическое свойство:
   тот же билдер, запущенный дважды, даёт byte-identical xlsx. Без этого
   golden-тесты флапали бы на разнице во временных метках openpyxl.
   Проверено параметризованным тестом `test_scenario_is_deterministic`.

5. **Выходной формат LogicService использует русские имена колонок**
   (`ЗАКАЗЧИК (название проекта, наименование ЮЛ)`, `сумма платежа ПРИХОД`,
   и т.д.). Это было вскрыто при написании тестов инвариантов — пришлось
   переписывать assertions под реальные имена полей. Зафиксировано в
   тестах, чтобы будущие разработчики не споткнулись об это же.

## Что НЕ сделано (и почему)

- **Полный pipeline golden через Excel I/O не построен.** ТЗ говорит
  "повторить сборку контрольного отчёта", но реальная пересборка
  требует `config.yaml` с путями сотрудников на сетевых дисках, что
  нельзя автоматизировать в CI. Вместо этого:
  - **Live-верификация** fingerprint контрольного листа запускается на
    машине оператора (где `Master_Report.xlsx` существует) и проверяет
    byte-for-byte воспроизводимость.
  - **Инварианты** финансовой логики проверяются напрямую через
    `LogicService.apply_financial_rules`, без Excel I/O — это быстрее,
    детерминировано и не требует сетевых путей.
  Это разделение — стандартный подход для финансового ПО, где полная
  e2e-сборка доступна только в защищённой среде оператора.

- **Эталонные xlsx-выходы для каждого из 14 сценариев не сохранены.**
  На этапе 1 зафиксированы входы и инварианты; сохранение ожидаемых
  выходов имеет смысл после стабилизации формата экспорта (это часть
  этапа 5/6, чтобы не плодить golden-файлы, которые сразу надо менять).

## Коммиты (логические единицы, после разрешения владельца)

1. `feat(golden): PII-safe workbook comparator + control-date fingerprint`
   (tools/compare_workbooks.py, tools/control_date_fingerprint.py,
    tests/test_compare_workbooks.py, tests/golden/test_control_date.py,
    tests/golden/control_date.json)
2. `chore(security): gitignore real firm workbooks and config`
   (.gitignore)
3. `feat(golden): 14 synthetic PII-free scenarios + invariants`
   (tests/golden/synthetic_fixtures.py, tests/golden/test_synthetic_fixtures.py,
    tests/golden/test_financial_invariants.py, tests/golden/__init__.py,
    pyproject.toml pythonpath)
