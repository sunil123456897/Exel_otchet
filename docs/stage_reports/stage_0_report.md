# Stage 0 Report — Baseline freeze and CI fix

```text
Этап: 0 (Заморозка baseline и исправление инфраструктуры проверки)
Цель: Получить воспроизводимую точку отсчёта и исключить ложные зелёные проверки.
Исходная проблема:
  - CI mypy читал только stderr, куда mypy не пишет diagnostic —
    фактически mypy gate всегда был зелёным независимо от реального числа ошибок.
  - CI pytest молча пропускался, если в ветке не было tests/, что позволяло
    публиковать непроверенный runtime-код.
  - Версия продукта расходилась: APP/__init__.py = "5.6", а ЗАПУСК.bat
    показывал "v5.5"; в UI были устаревшие fallback-литералы "5.6", которые
    могли бы молча вернуться к дрейфу.
  - В ТЗ-1.0 указан устаревший baseline (434 passed / 149 skipped), который
    не отражает актуальное состояние.
Изменённые файлы:
  - ЗАПУСК.bat (MR-0004): версия теперь читается из APP/__init__.py через findstr
    и используется как %APP_VERSION%; хардкоженный "v5.5" убран.
  - APP/core/ui/gui_master.py (MR-0004): убран fallback APP_VERSION = "5.6";
    при недоступности APP.__version__ теперь поднимается RuntimeError.
  - APP/core/ui/ui_settings.py (MR-0004): то же самое — fallback удалён.
  - .mypy_baseline.txt (MR-0003): перегенерирован с нормализацией
    (путь/backslash → forward slash; :NN: → :LINE:). 684 сырых строк →
    312 уникальных нормализованных находок.
  - .github/workflows/python-app.yml (MR-0003 + MR-0005):
      * шаг mypy использует tools/ci_mypy_check.py (читает stdout, нормализует,
        сравнивает с baseline, не пишет в baseline автоматически);
      * шаг pytest больше не skip'ается при отсутствии tests/ — падает с
        понятной ошибкой, кроме случая RUNTIME_ONLY_DIST=1 (ветка-дистрибутив);
      * зависимости ставятся из requirements-dev.txt (раньше ruff/mypy/pytest
        ставились по отдельности без версий).
Новые/изменённые тесты:
  - tests/test_single_version_source.py (MR-0004): 4 теста + параметризованный
    прогон по всем *.py под APP/ (всего 89 параметризаций).
    Ловит: drifting version literal в Python; захардкоженный vN.M в BAT;
    недоступность APP.__version__.
Новые инструменты:
  - tools/qa_baseline.py (MR-0002 + MR-0006): единый JSON-отчёт baseline.
    Быстрый режим (collect-only) и полный (с pytest). Никаких PII.
  - tools/qa_mypy_baseline.py (MR-0003): перегенерация mypy baseline
    осознанным действием (никогда не из CI).
  - tools/ci_mypy_check.py (MR-0003): CI mypy gate; сравнивает с baseline,
    требует явного refresh при изменениях.
Команды проверки (фактический прогон gate):
  .venv\Scripts\python.exe -m compileall -q APP tests                # rc=0, clean
  .venv\Scripts\python.exe -m ruff check APP tests                   # All checks passed!
  .venv\Scripts\python.exe -m pytest tests -q --tb=short ...         # 672 passed in 66.14s
  .venv\Scripts\python.exe tools\qa_baseline.py --full --pretty      # wrote baseline_report.json
  .venv\Scripts\python.exe tools\ci_mypy_check.py                    # PASS — 0 new
Результат:
  - compileall: clean
  - ruff: clean
  - pytest: 672 passed, 0 failed, 0 skipped, 0 errors
  - mypy --strict: 312 normalized findings (baseline), 0 новых — PASS
  - app_version: "5.6" во всех точках отображения
  - .github_token: присутствует локально, корректно gitignored,
    0 token-shaped строк в tests/ и tools/
  - baseline_report.json создан, всех полей достаточно для этапа 8
Оставшиеся риски:
  - R-0.1 [низкий]: pytest-cov не установлен в текущей .venv, поэтому
    coverage_total_pct=null в baseline. qa_baseline честно об этом сообщает.
    Действие: на этапе 1 при работе с golden-тестами убедиться, что
    requirements-dev.txt действительно ставится в CI (теперь он есть в
    workflow), и добавить coverage в baseline-отчёт.
  - R-0.2 [низкий]: CI не запускался после правок workflow — нельзя
    доказать энд-ту-енд, что GitHub Actions отработает. Действие:
    запушить ветку и убедиться, что джоба проходит; не делать этого без
    разрешения владельца.
  - R-0.3 [информационно]: фактический baseline сильно расходится с
    ТЗ-разделом-2 (434/149 → 672/0; 621 → 312 normalized; ~22955 строк →
    20075). Это нормальный дрейф, ТЗ писалось по более раннему состоянию.
    Рекомендую обновить раздел 2 ТЗ при приёмке этапа 0.
  - R-0.4 [средний]: в существующем коде есть скрытые падения в mypy
    baseline (312), включая finance-логику. Этап 5 это адресует; сейчас
    задача была — зафиксировать, а не чинить.
Решение gate: PASS
```

## Дополнительно: расхождения с ТЗ-разделом 2 (для обновления ТЗ)

| Показатель | ТЗ (исходное) | Фактически | Комментарий |
|---|---:|---:|---|
| Python-файлы приложения | 83 | 86 | +3 файла: `__init__.py`, `headless_run.py`, и др. |
| Строки в `APP/core` | ~22 955 | 20 075 | Часть кода, видимо, рефакторилась. |
| Файлы тестов | 46 | 43 | Несколько удалено/слито. |
| pytest | 434 passed, 149 skipped | 672 passed, 0 skipped | На Windows с дисплеем UI-тесты реально выполняются. |
| Mypy strict | ~621 | 312 normalized (684 raw) | С нормализацией числа уникальных проблем. |
| Сверка контрольной даты | 4 906 / 0 различий | не проверялось на этапе 0 | это этап 1. |

Эти расхождения не являются ошибкой этапа 0. Они означают, что раздел 2
ТЗ описывает более раннее состояние. Обновить раздел 2 ТЗ — на усмотрение
владельца при приёмке.

## Что НЕ сделано (и почему)

- **CI не запускался на GitHub Actions после правок.** ТЗ запрещает пуш
  без разрешения владельца. Локальная проверка `ci_mypy_check.py` и yaml
  syntax выполнена; первая реальная проверка — после merge.
- **`pytest-cov` не установлен в текущую `.venv`.** Ставить пакеты в
  чужое окружение без разрешения — нарушение принципа минимальных правок.
  qa_baseline обнаруживает отсутствие, корректно сообщает и продолжает
  без coverage. На этапе 1 coverage появится естественным образом.

## Коммиты (логические единицы)

После разрешения владельца будут оформлены как отдельные коммиты:
1. `fix(version): single source via APP.__version__; remove BAT/UI hardcodes`
   (ЗАПУСК.bat, gui_master.py, ui_settings.py, test_single_version_source.py)
2. `fix(ci): mypy reads stdout+normalized; pytest fails when tests/ absent`
   (.github/workflows/python-app.yml, ci_mypy_check.py, qa_mypy_baseline.py,
    .mypy_baseline.txt)
3. `feat(qa): baseline_report.json with PII-free metrics + token audit`
   (qa_baseline.py, baseline_report.json)
