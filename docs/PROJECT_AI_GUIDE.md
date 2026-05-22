# Version5 Project Guide for Humans and AI Agents

## Purpose

Version5 is a Windows-first financial report consolidator. It reads many employee Excel reports, validates and normalizes the rows, applies financial business rules, and writes consolidated Excel outputs.

The project currently supports four major reporting flows:

- Master report consolidation for all employees.
- Dedicated curator reports for Boris and Ivan.
- RSCH bank-account report generation.
- Reconciliation report generation between existing master/curator reports and an existing RSCH report.

This document is the main operating guide for future maintainers and AI agents. Read it before changing code.

For a faster first pass, start with:

- `README.md` for the project overview.
- `docs/AI_CONTEXT.md` for a compact code map.
- `docs/OPERATIONS.md` for Windows/workstation setup.
- `docs/DEVELOPMENT.md` for safe change and verification rules.

## Quick Start

Install runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

Install development and verification tools:

```bash
python -m pip install -r requirements-dev.txt
```

Run the application on Windows:

```bash
ЗАПУСК.bat
```

Run from Python directly:

```bash
python APP/main.py
```

Run the full verification suite:

```bash
pytest tests
python -m ruff check APP tests
python -m mypy APP tests
pytest --cov=APP/core --cov-report=term-missing tests
```

Expected verification baseline must be refreshed from the current workspace before claiming success:

- `python -m pytest -q -p no:cacheprovider`
- `python -m ruff check APP tests -q`
- `python -m mypy APP tests --no-error-summary`
- `python -m compileall -q APP`

Do not rely on old `passed` counts. Sentrux is a valid gate only when its scan/health tools are available and have been run in the current session.

## Repository Layout

```text
APP/
  main.py                         GUI entrypoint.
  config.yaml                     Runtime configuration.
  employees.yaml                  Employee-to-file mapping.
  core/
    app/                          Application service functions and file processor.
    domain/                       Schemas, validation, financial business rules.
    infra/                        Excel ingestion/export, persistence, discovery, RSCH.
    ui/                           Tkinter GUI widgets and commands.
    view_models/                  GUI-facing state and orchestration view models.
  templates/                      Excel templates for master/curator outputs.
REPORTS/                          Local real input reports used in this workspace.
РСЧ/                              RSCH generated outputs and inspected files.
рсч всех/                         RSCH real input workbooks.
tests/                            Unit, integration, property, GUI, and regression tests.
docs/                             Project and architecture documentation.
tools/                            Utility scripts.
```

## Documentation Map

```text
README.md                         Primary entrypoint for people and AI agents.
docs/AI_CONTEXT.md                Compact context map for low-token orientation.
docs/OPERATIONS.md                Windows setup, config, logs, workstation issues.
docs/DEVELOPMENT.md               Safe development workflow and test selection.
docs/knowledge_base/              Deeper architecture and domain notes.
```

## Main Runtime Flow

The GUI starts in `APP/main.py`:

1. `preflight_gui_imports()` imports `GuiMaster`.
2. `Bootstrap.setup(app_root, config_path)` builds core dependencies.
3. `tk.Tk()` creates the GUI root.
4. `GuiMaster` wires UI panels, view models, and `GuiCommands`.
5. GUI actions call view models and then `AppController`.

The main consolidation flow is:

1. UI command calls `ConsolidationViewModel`.
2. `ConsolidationViewModel` calls `AppController.run_consolidation(...)`.
3. `AppController` resolves employees, report paths, date scope, and curator settings.
4. `core.app.file_processor.process_file_task(...)` reads relevant employee files.
5. `IngestionEngine` delegates workbook parsing to `CalamineReader`.
6. `LogicService` validates rows and applies financial rules.
7. `MasterWriter` writes the output workbook.

## Important Domain Rules

### Dates

Only sheet dates with an explicit year are valid. Examples:

- Valid: `13.04.2026`, `13.04.26`.
- Invalid: `13.04`.

Invalid yearless sheet names must not be silently interpreted as the current year. In employee status, they appear as `НЕТ ДАТЫ`.

Daily consolidation reads only sheets matching the selected date. Monthly/range consolidation reads only sheets in the selected date range.

### General Master Report

The general master report writes to `Master_Report.xlsx` by default.

Standard output columns:

```text
Источник, ЗАКАЗЧИК, ИСПОЛНИТЕЛЬ, Приход, Расход, Комиссия, ИТОГ,
% посредника, посредник 1(кэш), посредник 2, Фильтры
```

Template warnings are intentionally visible in the first column for the general report. Many real input files have legacy or structurally inconsistent templates, so warnings in real data are expected and useful.

### Boris Curator Report

Boris has a dedicated output and no `Дата` column. The date is represented by the worksheet name.

Default output:

```text
APP/output/boris_report.xlsx
```

Columns:

```text
Источник, ЗАКАЗЧИК, ИСПОЛНИТЕЛЬ, Приход, Расход, Комиссия, ИТОГ,
% посредник 1, посредник 1(кэш), % посредник 2, посредник 2, Фильтры
```

Structural warnings from the old general template are suppressed in the first column for curator outputs. Numeric/template warnings on specific numeric cells still remain visible.

### Ivan Curator Report

Ivan has a dedicated output and no `Дата` column. The date is represented by the worksheet name.

Default output:

```text
APP/output/ivan_report.xlsx
```

Columns:

```text
Сотрудник, ЗАКАЗЧИК, ИСПОЛНИТЕЛЬ, Приход, Расход, Комиссия, ИТОГ,
ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ, % посредника 1, посредник 1(кэш),
посредник 2, курс, сумма, валюта, фильтры
```

Ivan-specific rows can be valid even when `amount` and `total` are zero if transit/FX fields are populated. Do not drop rows that contain:

- `transit_obligation`
- `exchange_rate`
- `currency_amount`
- `currency`

The known regression case is `Бекхем` on `13.04.2026`; the output should contain 9 rows.

### RSCH Report

RSCH report generation is implemented in `APP/core/infra/rsch_report.py` and formatting helpers in `APP/core/infra/rsch_report_formatting.py`.

The GUI exposes only combined RSCH output. The older separate-files mode is intentionally hidden because it is too slow for the current workflow and the same practical result is achieved by generating only the needed dates.

### Reconciliation Report

The reconciliation report is implemented in `APP/core/infra/reconciliation_report.py`.

It intentionally reads already-generated files:

- general master report sheet for the selected date;
- Boris curator report sheet for the selected date;
- Ivan curator report sheet for the selected date;
- RSCH report sheet for the selected date.

It writes one separate workbook and does not mutate any source workbook. The GUI and automatic flow use `build_combined_reconciliation_report(...)` to create exactly three sheets in stable order:

```text
Общий, Борис, Иван
```

`build_reconciliation_report(...)` remains as the single-master helper for focused tests and compatibility. If a date is explicitly selected, reconciliation must use that date only. If no date is provided, auto-selection is allowed only when the selected workbooks have one unambiguous common date.

Output layout:

```text
Источник, ЗАКАЗЧИК, ИСПОЛНИТЕЛЬ, Приход, Расход, Комиссия, ИТОГ,
% посредника, посредник 1(кэш), посредник 2,
ИТОГ,
ИСПОЛНИТЕЛЬ, ЗАКАЗЧИК, Контрагент, Комментарий, Приход, Расход
```

Status rules:

- `СВЕРЕНО` when project/customer, executor, and income/expense amount match.
- `ОШИБКА` when the row is matched by project/customer but executor or amount differs.
- `ОШИБКА НЕТУ У КУРАТОРОВ` at the top when an RSCH row has no customer/project and cannot be mapped to curator data.

Matching is normalized for case, extra whitespace, non-breaking spaces, and `ё`/`е`.

Sheet selection rule:

- Include sheets whose normalized title contains `рсч`.
- Exclude sheets whose normalized title contains `шаблон`.
- `динамика рсч` is valid.

Required output columns:

```text
Дата, ИСПОЛНИТЕЛЬ, ЗАКАЗЧИК, Контрагент, Комментарий, Приход, Расход, р/с, Источник
```

Yellow warning rows are expected when `_is_problem_row(...)` returns true. A row is a problem row when:

- income and expense are both non-zero;
- customer is empty;
- executor is empty;
- account is empty;
- income and expense are both zero;
- contractor is empty while customer exists and customer is not a special label.

Special customer labels are not treated as missing-contractor problems:

- `% по депозиту`
- `комиссия`
- `налог`

## Key Components

### `Bootstrap`

File: `APP/core/bootstrap.py`

Builds the runtime graph: configuration controller, persistence repositories, ingestion engine, logic service, writer, and app controller.

Use this for integration/manual checks instead of constructing dependencies by hand.

### `AppController`

File: `APP/core/app_controller.py`

Coordinates GUI-facing actions:

- refresh employee status;
- single-date consolidation;
- all-dates consolidation;
- monthly consolidation;
- RSCH combined report generation.

Important methods:

- `refresh_status(...)`
- `run_consolidation(...)`
- `run_consolidation_all_dates(...)`
- `run_consolidation_month(...)`
- `run_rsch_report(...)`

Most methods run work in background threads and report through callbacks.

### `CalamineReader`

File: `APP/core/infra/ingestion_reader.py`

Reads Excel files through `python-calamine`, detects sheet dates, maps headers to canonical fields, and emits raw normalized rows.

Important behavior:

- date-aware sheet filtering;
- exact header match is preferred over substring match;
- old templates can produce template warnings rather than hard failures;
- junk/header/total rows are filtered.

### `LogicService`

File: `APP/core/domain/logic_service.py`

Validates and transforms raw rows into output rows. It owns most business rules:

- numeric parsing;
- income/expense resolution;
- commission calculation;
- curator-specific layouts;
- warning propagation.

### `MasterWriter`

File: `APP/core/infra/export_writer.py`

Writes Excel workbooks for general and curator outputs. It is responsible for:

- sheet creation by date;
- header styling;
- warning cell coloring;
- total formulas;
- preserving existing workbooks where needed.

### `Path Resolver`

File: `APP/core/infra/path_resolver.py`

Resolves employee file paths from configuration and discovery data. It supports local `REPORTS` fallback when configured network roots like `Q:\...` are unavailable.

## Configuration

Main config file:

```text
APP/config.yaml
```

Important sections:

- source roots and local aliases;
- database path and SQLite settings;
- master report output path;
- curator outputs and employee filters;
- RSCH input/output defaults;
- markers and aliases used during ingestion.

Employee mapping file:

```text
APP/employees.yaml
```

## Testing Strategy

The test suite is intentionally broad:

- unit tests for parsing, validation, calculations, and formatting;
- integration tests for full pipeline behavior;
- GUI component tests;
- threading smoke tests;
- property tests for date/discovery logic;
- regression tests for real-world bugs;
- RSCH edge-case tests.

Always run at least the focused tests for files you touch. Before declaring completion, run the full gate:

```bash
pytest tests
python -m ruff check APP tests
python -m mypy APP tests
pytest --cov=APP/core --cov-report=term-missing tests
```

For Excel-output changes, also run manual workbook inspection with `openpyxl` and check:

- sheet names;
- headers;
- data row counts;
- no repeated header rows inside data;
- no Excel error values such as `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`;
- warning colors only where expected.

## Manual E2E Smoke Script Pattern

Use this pattern for manual controller-level checks:

```python
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"E:\Dlia Dashi\Version5\APP")
from core.bootstrap import Bootstrap

app_root = Path(r"E:\Dlia Dashi\Version5\APP")
cfg_ctl, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))

try:
    done = threading.Event()
    payload = {}

    def complete(ok, msg, path):
        payload.update(ok=ok, msg=msg, path=str(path) if path else None)
        done.set()

    app_ctl.run_consolidation(
        datetime(2026, 4, 13),
        lambda progress: None,
        complete,
        curator="ivan",
    )
    if not done.wait(180):
        raise TimeoutError("consolidation timed out")
    print(payload)
finally:
    app_ctl.shutdown()
```

Use `curator=None` for the general master report, `curator="boris"` for Boris, and `curator="ivan"` for Ivan.

## Quality Gates

### Ruff

Configured in `pyproject.toml`.

The current Ruff baseline checks correctness-oriented `E`/`F` rules while ignoring legacy formatting noise:

- line length;
- import position caused by runtime `sys.path` setup;
- compact one-line statements in older code.

Do not widen ignores without a specific reason.

### Mypy

Configured in `pyproject.toml`.

The current mypy baseline is pragmatic rather than strict. It catches broad type problems while suppressing known legacy/noisy categories from third-party Excel stubs and old dynamic code.

When editing new code, prefer explicit types and do not rely on the baseline suppressions as a style guide.

### Coverage

Configured in `.coveragerc` with `fail_under = 90`.

The GUI package is omitted from coverage because Tkinter behavior is covered through targeted component and smoke tests.

## GitNexus and Sentrux Workflow

Before editing functions/classes/methods, run GitNexus impact analysis:

```text
gitnexus_impact(target="symbol", direction="upstream")
```

Before finishing or committing, run:

```text
gitnexus_detect_changes(scope="all")
```

For architecture checks:

```text
sentrux_scan(path="E:\\Dlia Dashi\\Version5")
sentrux_check_rules()
sentrux_health()
sentrux_dsm(format="stats")
```

Current architecture expectation:

- Sentrux rules pass.
- DSM should show clean layering with no above-diagonal dependency inversions.
- The known bottleneck is modularity, not cyclicity.

## Known Good Manual Results

Latest manual smoke at `13.04.2026` verified:

- `Master_Report.xlsx`: sheet `13.04.2026`, 541 data rows, no header-like rows, no Excel errors.
- `APP/output/boris_report.xlsx`: sheet `13.04.2026`, 41 data rows, no header-like rows, no first-column red structural warning noise.
- `APP/output/ivan_report.xlsx`: sheet `13.04.2026`, 46 data rows, 9 `Бекхем` rows, no header-like rows, no Excel errors.
- `output/manual_testing/rsch_manual_monica.xlsx`: sheet `13.04`, 552 data rows, yellow warning rows expected from RSCH problem-row logic.

## Common Pitfalls

- Do not interpret `DD.MM` sheet names as dates with the current year.
- Do not remove compatibility re-exports from `session_repo.py`; tests and old callers import from there.
- Do not treat all template warnings as bugs. Many real files are legacy or structurally inconsistent.
- Do not suppress numeric warning colors in curator reports; only old structural source-column noise is suppressed.
- Do not drop Ivan transit/FX rows just because `amount` and `total` are zero.
- Do not use `data_only=True` and then save workbooks; it destroys formulas.
- Do not rely on only unit tests for Excel output changes. Inspect generated workbook cells.
- Do not re-enable full network discovery during startup/status refresh without measuring startup impact on a real network share.
- Do not reintroduce separate RSCH file mode into the GUI unless there is a concrete user workflow that requires it.

## AI Agent Checklist

Before changing code:

- Read this guide and the specific files you will touch.
- Run GitNexus impact for modified symbols.
- Check existing tests for the behavior.
- Add or update tests first for bug fixes and behavior changes.

During implementation:

- Keep changes surgical.
- Preserve existing Excel template conventions.
- Prefer fixing root causes over filtering symptoms downstream.
- Do not revert unrelated dirty worktree changes.

Before completion:

- Run focused tests for touched files.
- Run `pytest tests`.
- Run `python -m ruff check APP tests`.
- Run `python -m mypy APP tests`.
- Run coverage gate.
- Run Sentrux rules/health.
- Run GitNexus change detection.
- For Excel work, inspect outputs manually.
