# Master-Report v5.6

Windows-приложение для сборки финансовых Excel-отчетов сотрудников в итоговые файлы:

- общий мастер-отчет `Master_Report.xlsx`;
- отдельные отчеты кураторов Бориса и Ивана;
- общий РСЧ-отчет по банковским счетам.
- отчет расхождений между готовыми мастер-отчетами и готовым РСЧ.

Проект рассчитан на работу с локальными и сетевыми папками Windows, включая рабочие места, где отчеты лежат на диске `Q:\Отчет кураторов ...`.

## Состав Ветки `main`

`main` намеренно является runtime-only веткой для рабочих ПК и безопасного обновления программы. В ней отслеживается только минимальный набор, нужный для запуска и обновления:

```text
APP/core/                   код приложения
APP/main.py                 точка входа GUI
APP/headless_run.py         headless-точка входа для служебных запусков
APP/db_schema.sql           схема SQLite
APP/config.example.yaml     переносимый пример конфигурации
requirements.txt            runtime-зависимости
tools/update_from_github.ps1 безопасный updater
ЗАПУСК.bat
ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat
README.md
```

Реальные рабочие данные и локальные настройки не должны храниться в Git: `APP/config.yaml`, `APP/employees.yaml`, `APP/cache.db`, `Master_Report.xlsx`, `REPORTS/`, `РСЧ/`, `рсч всех/`, `APP/output/`.

Разработка, тесты, CI и подробная документация живут в ветке `experiments`. Если нужен аудит, правка кода с тестами или CI-проверка, переключайтесь на нее:

```bash
git fetch origin
git switch experiments
```

## Быстрый Старт

### Требование к рабочему месту

Перед первым запуском на ПК должен быть установлен **Python 3.12 или новее** (скачать: [python.org](https://www.python.org/downloads/)). При установке отметьте галочку «Add Python to PATH». `ЗАПУСК.bat` сам создаст изолированное виртуальное окружение `.venv` рядом с программой и установит туда зависимости из `requirements.txt` — ручная установка библиотек не нужна.

### Запуск

Обычный запуск на рабочем ПК:

```bat
ЗАПУСК.bat
```

При первом запуске, если `APP/config.yaml` еще нет, приложение создает его из `APP/config.example.yaml`. Уже существующий `APP/config.yaml` не перезаписывается.

Обновить программу с GitHub и сразу запустить:

```bat
ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat
```

Запуск напрямую через Python:

```bash
python APP/main.py
```

Установка зависимостей:

```bash
python -m pip install -r requirements.txt
```

Минимальная проверка чистой runtime-ветки:

```bash
python -m compileall -q APP
```

Полные проверки разработки находятся в ветке `experiments` вместе с `tests/`, `requirements-dev.txt`, `pyproject.toml` и `.github/workflows/quality-gate.yml`.

`ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat` использует `tools/update_from_github.ps1`: проверяет `sunil123456897/Exel_otchet`, сохраняет локальные `APP/config.yaml`, `APP/employees.yaml`, `APP/cache.db`, WAL/SHM-файлы БД и `APP/runtime_state.json`, обновляет только минимальный runtime-набор программы (`APP/core`, точки входа, `APP/db_schema.sql`, `requirements.txt`, батники запуска/обновления и сам updater), возвращает локальные данные и запускает обычный `ЗАПУСК.bat`. Пользовательские Excel-файлы, `REPORTS`, `РСЧ`, `APP/output`, документация и тесты не обновляются на рабочем ПК.

## EXE-дистрибуция (без Python)

Программу можно собрать в самодостаточный EXE (Nuitka, ~120 МБ), которому
**не нужен Python** на рабочем ПК. Код компилируется в нативный машинный код
(внутри нет `.pyc`, которые можно декомпилировать).

### Сборка (сторона разработчика)

```bat
tools\build_exe.bat                :: build_exe\main.dist\ (release, без консоли)
tools\build_exe.bat --console      :: с консолью — для отладки запуска
tools\build_exe.bat --zip          :: + Master-Report_<ver>_win64.zip для раздачи
```

Сборка кладёт в `main.dist` саму программу, иконки, `config.example.yaml`,
`db_schema.sql`, `migrations/`, а также компилирует автономный `updater.exe`
и батники `ЗАПУСК.bat` / `ОБНОВИТЬ_EXE.bat`. Быстрая проверка сборки:
`python tools\test_exe.py` (структура + реальный запуск).

### Новый ПК (первый запуск)

Достаточно скопировать папку `main.dist` (или установить через setup) и
запустить `ЗАПУСК.bat` / `main.exe` / ярлык. При первом запуске программа:

- сама создаёт `config.yaml` из встроенного примера (корни отчётов по
  умолчанию `Q:\Отчет кураторов 1|2|3`, кураторы, названия колонок);
- сама создаёт `cache.db` с полной схемой и применяет миграции;
- открывает интерфейс. Папку с отчётами можно потом поменять в
  **Настройках → «Пути и файлы»**.

### Обновление на рабочем ПК (данные сохраняются)

```bat
ОБНОВИТЬ_EXE.bat                   :: проверить GitHub-релиз и обновиться
ОБНОВИТЬ_EXE.bat <путь\файл.zip>   :: оффлайн-обновление из файла (перетащить zip на bat)
```

`updater.exe` скачивает новый релиз, сверяет его с опубликованным
`SHA256SUMS`, делает резервную копию данных и программы, заменяет только
программные файлы (данные — `config.yaml`, `employees.yaml`, `cache.db`,
состояние — не трогаются), проверяет запуск и пишет `version.json`. При сбое
предыдущая версия автоматически восстанавливается. Опциональный pin тега
релиза — в `updater_exe_pin.txt` рядом с `main.exe`.

### Публикация релиза (сторона разработчика)

```bat
tools\build_exe.bat --zip
python tools\publish_release.py --zip build_exe\Master-Report_<ver>_win64.zip
```

`publish_release.py` считает SHA-256, пишет `SHA256SUMS` и создаёт
GitHub-релиз с обоими файлами (нужен `gh auth login`). Именно опубликованный
`SHA256SUMS` — настоящая проверка целостности при обновлении.

### Установщик (Inno Setup)

```bat
tools\build_installer.bat          :: нужен Inno Setup 6 (ISCC.exe)
```

Создаёт `installer_output\Master-Report_<ver>_Setup.exe`: ставит программу в
пользовательскую папку (`%LocalAppData%`, без прав админа — программа пишет
данные рядом с `main.exe`), создаёт ярлыки (запуск + обновление), при
апгрейде **не затирает** существующие данные пользователя.

## Главные Файлы

```text
APP/main.py              точка входа GUI
APP/config.yaml          настройки путей, БД, кураторов и РСЧ
APP/employees.yaml       соответствие сотрудников и файлов отчетов
APP/core/bootstrap.py    сборка зависимостей приложения
APP/core/app_controller.py
                         основной координатор пользовательских действий
APP/core/domain/         бизнес-правила и схемы данных
APP/core/infra/          чтение Excel, запись Excel, SQLite, поиск файлов
APP/core/shared/         общие утилиты (path_scrub) — без зависимостей от infra
APP/core/ui/             Tkinter-интерфейс
```

## Что Читать Первым

Для людей и ИИ-агентов:

1. На рабочем ПК и в чистом `main` достаточно этого `README.md` и `APP/config.example.yaml`.
2. Для разработки переключайтесь на `experiments`: там находятся `docs/PROJECT_AI_GUIDE.md`, `docs/AI_CONTEXT.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT.md` и архитектурная база знаний.
3. Если документация из `experiments` расходится с текущим runtime-кодом `main`, источником факта считать текущий код, а противоречие исправлять отдельной документационной правкой.

## Основные Пользовательские Сценарии

- Выбрать дату и собрать отчет за день.
- Собрать общий отчет за все найденные даты.
- Собрать отчет за период.
- Собрать отчет куратора Бориса.
- Собрать отчет куратора Ивана.
- Собрать общий РСЧ-файл.
- Сверить готовые отчеты `Master_Report.xlsx`, Бориса и Ивана с готовым РСЧ и получить один отчет расхождений с листами `Общий`, `Борис`, `Иван`.
- Проверить статус готовности файлов сотрудников.
- Открыть папку с мастер-файлом или скопировать список должников.
- Переключить тему интерфейса (светлая/тёмная/системная) — сохраняется между запусками.
- Открыть историю последних операций (вкладка «📜 История»).
- Массовое удаление сотрудников (Ctrl+клик для выбора нескольких).
- Горячие клавиши: Ctrl+D (день), Ctrl+M (месяц), Ctrl+R (РСЧ), Ctrl+E (сверка), F5 (обновить статус), Esc (отмена).

## Важные Правила Поведения

- Листы с датой без года, например `13.04`, не считаются валидной датой для обычных отчетов.
- Для РСЧ листы с названием `рсч` используются, а шаблонные листы исключаются.
- Ивановские строки с транзитными обязательствами или валютными полями нельзя отбрасывать только из-за нулевых `Приход`/`ИТОГ`.
- У кураторских отчетов дата хранится в имени листа, а не в отдельной колонке.
- РСЧ сейчас собирается через общий файл; режим отдельных файлов убран из интерфейса как слишком медленный и ненужный.
- Сверка с РСЧ пишет отдельный файл и не меняет `Master_Report.xlsx`, отчеты кураторов или РСЧ-отчет.
- Excel-формулы нельзя сохранять через режим чтения `data_only=True`, иначе формулы будут уничтожены.

## Конфигурация

Главный файл: `APP/config.yaml`.

Ключевые секции:

- `database` - путь к SQLite-кэшу и режим WAL;
- `paths` - мастер-файл и корни отчетов;
- `curators` - настройки Бориса и Ивана;
- `rsch` - последние источники и папка вывода РСЧ;
- `sh1.markers` - названия колонок, которые ищет парсер.

Портативная настройка по умолчанию использует относительные пути:

```yaml
database:
  path: cache.db
  schema_path: db_schema.sql
paths:
  master_file: ../Master_Report.xlsx
  source_roots:
    - Q:\Отчет кураторов 1
    - Q:\Отчет кураторов 2
    - Q:\Отчет кураторов 3
rsch:
  mode: combined
  last_output_dir: ../РСЧ
```

## Технологии

- Python 3.12+
- Tkinter и tkcalendar для интерфейса
- tkinterdnd2 (опционально) для drag-and-drop файлов
- openpyxl для записи Excel
- python-calamine и pyxlsb для чтения Excel
- SQLite для кэша
- Pydantic для схем данных
- PyYAML / ruamel.yaml для конфигурации
- pytest, ruff, mypy для качества

## Разработка

### mypy baseline — строгая типизация без страха

**Текущий статус:** `mypy APP --strict --ignore-missing-imports` проходит
**полностью чисто — 0 ошибок в 93 файлах**. Файл `.mypy_baseline.txt` пуст
(исторически baseline-подход зафиксировал растущий список предупреждений; к
настоящему моменту он сведён к нулю). Baseline-механизм остаётся как
страховка: если новая правка внесёт mypy-ошибку, pre-commit и CI её поймают.

Проект использует **baseline-подход** к `mypy --strict`:

1. Файл `.mypy_baseline.txt` содержит все **существующие** предупреждения mypy
   (сгенерирован один раз командой `mypy APP --strict --ignore-missing-imports > .mypy_baseline.txt`)
2. Pre-commit хук (`.git/hooks/pre-commit`) и GitHub Actions **блокируют только НОВЫЕ ошибки**
3. Разработчик может спокойно добавлять код — если mypy находит ошибку,
   которой нет в baseline, коммит блокируется
4. Каждый спринт: типизируем 1 модуль → baseline уменьшается → прогресс виден по `wc -l .mypy_baseline.txt`

**Почему не `# type: ignore`:** комментарии загрязняют код. Baseline — внешний артефакт, не трогает исходники.

**Как обновить baseline после уменьшения ошибок:**
```bash
mypy APP --strict --ignore-missing-imports --no-error-summary > .mypy_baseline.txt 2>&1
```

### Структура пакетов

```
APP/core/infra/
├── reconciliation/    # сверка (6 модулей, ~1500 строк)
│   ├── __init__.py    # build_reconciliation_report, build_combined
│   ├── _types.py      # MasterReconciliationRow, ...
│   ├── _utils.py      # _to_decimal, константы
│   ├── _resolve.py    # поиск дат, executor/customer matching
│   ├── _collect.py    # чтение из Excel
│   └── _build.py      # запись в Excel
├── rsch/              # РСЧ-отчёт (5 модулей, ~1300 строк)
│   ├── __init__.py    # build_rsch_report
│   ├── _format.py     # константы, утилиты
│   ├── _collect.py    # чтение Calamine/openpyxl
│   ├── _template.py   # шаблоны, стили
│   └── _build.py      # запись, build_rsch_report
├── excel_safety.py    # _excel_safe_text — защита от formula injection
└── ...                 # ingestion, config, discovery, session_repo, etc.

APP/core/shared/
├── __init__.py         # реэкспорт scrub_path
└── path_scrub.py       # scrub_path — очистка путей (без зависимостей от infra)
```

Подробнее — см. документацию в ветке `experiments`.

## Качество кода

`main` — это чистая runtime-ветка: только код программы, схема БД, конфиг-пример, батники запуска и документация. Тесты, dev-зависимости и CI-конфиги живут в отдельной dev-среде разработчика и не входят в поставку.

Что гарантируется в этой ветке:

- `ruff check APP`: **0 ошибок** (линтер чистый).
- `mypy --strict`: существующие предупреждения зафиксированы в `.mypy_baseline.txt`; pre-commit хук (`.git/hooks/pre-commit` + `tools/precommit_check.py`) блокирует только **новые** ошибки — регрессий типов не будет.
- `python -m compileall -q APP`: OK — весь код компилируется без синтаксических ошибок.

Pre-commit хук запускается автоматически перед каждым коммитом и делает три проверки подряд: авто-фикс неиспользуемых импортов (ruff F401), полный ruff, и mypy baseline-diff с нормализацией номеров строк (чистый сдвиг строк от редактирования соседнего кода не считается новой ошибкой).

## Hardening — Stage 0–9

Отдельная серия работ по доведению до коммерческого качества «10/10 без
защиты». Этапы 0–9 выполнены; полная документация каждого этапа — в
`docs/stage_reports/<N>_report.md`. Сводка:

- **Stage 0 (baseline + CI fix):** единый JSON-отчёт `baseline_report.json`;
  CI mypy gate, читающий **stdout** (раньше был silent no-op); единый
  источник версии (BAT читает `APP/__init__.py`).
- **Stage 1 (golden regression):** PII-safe сравниватель xlsx
  (`tools/compare_workbooks.py`); fingerprint контрольной даты
  `18.05.2026` (446×11=4906 ячеек, 0 различий); 14 синтетических
  golden-сценариев; 8 инвариантов LogicService.
- **Stage 2 (config versioning):** Pydantic-схема с 4-way error
  taxonomy (UNREACHABLE_PATH отделён от WRONG_TYPE); idempotent
  migration runner; employees.yaml типизирован.
- **Stage 3 (Excel reliability):** классификатор подозрительных дат
  (ловит "2029 anomaly"); OperationResult enum; 8 corrupt-fixture
  генераторов; **security fix** в data_loss_log (paths/amounts
  скрабятся до JSON serialisation).
- **Stage 4 (atomic updater):** `APP/core/infra/updater_model.py` —
  полная Python-реализация (lock → staging → L0/L1 self-check →
  atomic switch → startup-ok → auto rollback).
- **Stage 5 (mypy + boundaries):** 47 архитектурных тестов (domain
  purity, UI no-fin-math); mypy baseline 312→303; domain+services
  полностью clean.
- **Stage 6 (test coverage):** Hypothesis property-тесты (нашли edge
  case с Decimal rounding modes); fault injection (SQLite, file
  handles, cancel_event latency); 28 новых тестов.
- **Stage 7 (Windows UI):** 16 UI acceptance тестов; **security fix**
  в error_presenter (`type.__name__` вместо `repr(exc)`); формальный
  Windows acceptance matrix (`docs/stage_reports/stage_7_acceptance_matrix.md`).
- **Stage 8 (performance):** `tools/timing_report.py`; 8 SLA + leak
  тестов; floor-оценки в 100-1000× ниже ТЗ-SLA → CPU не bottleneck.
- **Stage 9 (backup + diagnostics):** `tools/diagnostic_package.py`
  (обезличенный ZIP для поддержки); 10 backup-restore тестов; 17
  privacy-тестов; `docs/support_runbook.md`.

Полный список известных ограничений: [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).
Что изменилось по этапам: [`CHANGELOG.md`](CHANGELOG.md).

Тестов в комплекте (Stage 0–9 + hardening-цикл): **~1280 passed** на Windows
(1278 passed + 4 skipped: 3 платформенных UI-screenshot + 1 opt-in e2e).
Актуальное число — см. вывод `pytest tests/`.

## История стабилизации

Программа пережила четыре волны стабилизации без изменения финансовой семантики:

- **Phase 0 (стабильность):** Tk-колбэки прогресса маршалируются в GUI-поток; все openpyxl workbook'и закрываются в `try/finally` (нет «файл занят в Excel» при повторе); грязная ячейка суммы в сверке логируется и пропускается, не роняя лист.
- **Phase 1 (финансы):** `Decimal` из `LogicService` идёт в Excel напрямую (без `float`-приведения); валидатор `FinancialRowSchema` больше не течёт сырыми строками в Decimal-поля.
- **Phase 3 (надёжность):** миграции применяются атомарно (DDL + запись в `_migrations` в одной транзакции); `SourceFileRepository` surfaced writer-thread ошибки через `write_error`; `sqlite3` adapter'ы регистрируются один раз на уровне модуля.
- **Phase 5 (перфоманс):** прекомпиляция trash-row regex дала ~×3.5 ускорение чтения Excel (7.0s → 2.0s на пакете из 10 файлов / 11680 строк).
- **QA Audit (UX + dark mode):** 23 UX-улучшения (горячие клавиши, история операций, batch-удаление, сортировка колонок, фильтр статусов, drag-and-drop, тёмная тема); Master-report: per-curator headers (BORIS/IVAN) — убрана лишняя колонка; `scrub_path` вынесен в `core/shared/` (исправлен domain→infra violation); `_excel_safe_text` унифицирован в `excel_safety.py`; `purge_old_sessions(30d)` — автоочистка cache.db; удалён мёртвый код (`event_bus.py`, `metrics.py`); тесты ускорены ~×4 (92s → 22s). FIX-000 (блокировка single-token executor matching) откатан — оказался слишком агрессивным и ломал legitimate matches исполнителей, увеличивая количество строк в статусе «Проверить».
