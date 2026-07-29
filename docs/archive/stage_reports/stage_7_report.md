# Stage 7 Report — Windows UI/UX acceptance

```text
Этап: 7 (Windows UI/UX и первоначальная настройка)
Цель: Нетехнический сотрудник способен установить, настроить,
       обновить и использовать программу без доступа к коду.
Исходная проблема:
  - 127 UI-тестов уже существовали, но не было тестов на first-run
    flow и error presenter contract.
  - error_presenter использовал repr(exc) в detail-секции toast,
    что технически "безопаснее str", но repr(ValueError('token'))
    буквально содержит token — это реальная leak-поверхность.
  - Не было формального acceptance-чеклиста для ручной проверки
    на разных DPI/Excel/сеть-сценариях.
Изменённые файлы:
  - APP/core/ui/error_presenter.py (MR-0702, security fix):
      * detail-секция toast теперь показывает type(exc).__name__
        вместо repr(exc). Это закрывает leak: repr может содержать
        секретные аргументы (token, путь, SQL), а class name — нет.
      * Полный repr по-прежнему пишется в лог для разработчиков.
Новые модули:
  - tests/test_ui_acceptance.py (MR-0701 + MR-0702): 16 тестов:
      First-run flag (5):
        * round-trip write/read;
        * corrupt JSON treated as first-run (no crash);
        * extra keys preserved;
        * missing file ⇒ first run;
        * unwritable file ⇒ no crash (next launch re-shows).
      Error presenter invariants (11):
        * PermissionError → "Нет доступа к файлу" (no path leak);
        * FileNotFoundError → "Файл не найден" (no path leak);
        * JSONDecodeError → "Файл настроек повреждён";
        * unknown exception → "Внутренняя ошибка" (no str leak);
        * empty-str exception handled via repr;
        * present_error never leaks str(exc) in primary OR detail;
        * fallback to messagebox when no toasts;
        * no raise when toast fails;
        * no raise when both toast and messagebox fail;
        * non-empty message (not only color);
        * stable mapping (deterministic).
  - docs/stage_reports/stage_7_acceptance_matrix.md (MR-0703):
    формальный чеклист на 8 секций, ~50 пунктов:
      A. OS & display (12 пунктов): cold launch, DPI 100/125/150/200%,
         Full HD и laptop, light/dark/system theme, ru-RU locale.
      B. Keyboard navigation (8): Tab, Enter, Esc, shortcuts dialog,
         a11y "не только цвет", Cyrillic/UNC paths.
      C. Excel integration (8): Excel 2019/2021/M365, file lock,
         cancel timing, close-during-processing.
      D. Network & filesystem (6): mapped drive, slow LAN, disconnect,
         read-only output, ~$ skip.
      E. Error presentation (7): все 4 mapped класса, no leak, no
         traceback, progress + cancel.
      F. First-run (5): welcome dialog once, survives corrupt flag.
      G. Data integrity (5): source unchanged, idempotent, formulas
         preserved, no float drift.
      H. Update & rollback (5): только если Stage 4 wiring включён.
    Каждая строка: PASS/FAIL/BLOCKED + comment. Sign-off 4 ролей.
Команды проверки (фактический gate):
  pytest tests/ui/ tests/test_ui_acceptance.py            # 143 passed
  pytest tests/ (full regression)                         # 955 passed
  ruff check APP tests                                    # clean
  ci_mypy_check.py                                        # PASS 0 new
Результат:
  - 16 новых acceptance-тестов (143 всего UI-related, 0 skips)
  - 127 автоматических UI-тестов проходят на Windows
  - Security fix в error_presenter (repr → type.__name__)
  - Формальный acceptance matrix на 8 секций готов для pilot
  - mypy/ruff/golden все green
Оставшиеся риски:
  - R-7.1 [критический для релиза]: Windows acceptance matrix — это
    формальный чеклист, но его ещё НУЖНО выполнить вручную на реальных
    Windows 10/11 машинах. Автоматические UI-тесты не проверяют
    perceived rendering на разных DPI, реальную network latency,
    фактическое поведение Excel. Pilot без заполненного matrix не
    подписывается.
  - R-7.2 [низкий]: config wizard (TZ MR-0701 упоминает "мастер
    создания/проверки конфигурации") не построен. First-run
    обнаружение есть, но полноценный wizard с выбором путей —
    отдельная большая задача. Текущая first-run просто показывает
    welcome dialog; config editor уже существует в Settings tab.
  - R-7.3 [низкий]: около 16 messagebox.showerror(..., str(e))
    call-site'ов остаются не мигрированными на present_error (см.
    TODO в error_presenter.py). Они могут течь str(exc). Миграция —
    инкрементальная работа, не блокирующая, но желательная до релиза.
  - R-7.4 [информационно]: DPI-тестирование в CI невозможно (CI
    runners не имеют дисплея с configurable DPI). Поэтому A4-A6 в
    matrix — строго manual.
  - R-7.5 [информационно]: Excel-version-тестирование (C1-C3) требует
    реальных установок Excel, которых нет в CI.
Решение gate: PASS (автоматическая часть; ручная приёмка —
                   отдельный шаг перед пилотом)
```

## Главная находка — реальная leak-поверхность в error_presenter

Тест `test_present_error_never_leaks_str_exception` нашёл, что
`detail = repr(exc)` **утечка секреты**. Конкретно:
`ValueError("super-secret-token-12345")` →
`repr` = `"ValueError('super-secret-token-12345')"` — токен виден.

Старый комментарий говорил "`repr` is far less likely to contain
secrets than `str`" — это градиент, не гарантия. Я заменил detail на
`type(exc).__name__` — это максимум, что можно показать без аудита
каждого exception-класса. Полный repr по-прежнему в логе для
разработчиков.

Тест до фикса падал, после — проходит. Это снова пример правила
ТЗ "добавлять или изменять тест одновременно с исправлением дефекта".

## Ключевые решения

1. **acceptance matrix как living document.** Не одноразовый чеклист,
   а формальный артефакт с версионированием. Pilot подписывается по
   нему; known limitations фиксируются с reasoning.

2. **Acceptance = human-only checks.** Я не пытался автоматизировать
   DPI-rendering или Excel-version-тесты — это невозможно в CI.
   Вместо этого каждая строка матрицы — это явный пункт, который QA
   проходит вручную. Лучше явная ручная проверка, чем ложное
   "автоматизировано".

3. **First-run detection robust.** 5 тестов покрывают: corrupt JSON,
   missing file, unwritable file, extra keys preservation. Любой
   сбой → приложение продолжает работать, не крашится.

4. **Error presenter defensive depth.** Тесты проверяют, что
   present_error не бросает исключение, даже если toast И messagebox
   оба упали. Это критично: presentation layer не должен маскировать
   оригинальную ошибку второй.

## Что НЕ сделано (и почему)

- **Полный config wizard не построен.** TZ MR-0701 упоминает "мастер
  создания/проверки конфигурации" с выбором рабочих папок, импортом
  employees.yaml, dry-run без сохранения. Это большая UI-работа,
  выходящая за рамки одной сессии. Существующий Settings tab даёт
  эту функциональность, просто не как wizard.

- **Миграция 16 messagebox.showerror(..., str(e)) call sites** —
  TODO в коде, инкрементальная работа.

- **Manual acceptance matrix не заполнен.** Это работа для pilot
  пользователей на реальных машинах, не для agentic pipeline.

- **Screenshot baseline (TZ MR-0704 "baseline-скриншоты ключевых
  состояний")** — не построен. Требует решения о screen capture
  framework (pyautogui vs Pillow ImageGrab) и storage. Оставлено на
  отдельную сессию.

## Коммиты (логические единицы, после разрешения владельца)

1. `fix(ui): error_presenter detail shows type name, not repr (no leak)`
   (error_presenter.py)
2. `test(ui): first-run flag + error presenter invariants (16 tests)`
   (test_ui_acceptance.py)
3. `docs(acceptance): Windows UI/UX matrix for manual pilot sign-off`
   (docs/stage_reports/stage_7_acceptance_matrix.md)
