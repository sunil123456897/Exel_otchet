# Version5 Stability, Performance, And Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Исправить найденные баги, красные проверки, риски запуска, узкие места производительности и мусорные артефакты без потери рабочих данных и без изменения бизнес-логики сверки.

**Architecture:** Идем малыми обратимыми итерациями: сначала восстанавливаем quality gates, затем стабилизируем запуск и конфиг, потом оптимизируем горячие пути Excel/сети, затем чистим артефакты и обновляем документацию. Сверка остается консервативной: точные совпадения становятся `СВЕРЕНО`, неоднозначные частичные совпадения остаются `ПРОВЕРИТЬ`.

**Tech Stack:** Python 3.12, Tkinter, openpyxl, python-calamine, SQLite, ruamel.yaml, pytest, ruff, mypy, GitNexus CLI.

---

## Execution Rules

- Не удалять Excel-файлы, если они не временные lock-файлы `~$*.xlsx`.
- Перед любой серией правок фиксировать `git status --short` и не смешивать исправления с чужими/пользовательскими изменениями.
- Перед правкой функции/класса запускать GitNexus impact, если MCP доступен; если MCP недоступен, использовать `gitnexus status` и локальный поиск вызывающих мест.
- После каждого успешного изменения запускать минимальные целевые проверки.
- После успешной серии изменений запускать `C:\Users\vanya\AppData\Roaming\npm\gitnexus.cmd analyze E:\Dlia Dashi\Version5`.
- Не трогать бизнес-правила fuzzy matching без отдельного решения заказчика.
- Любая уборка файлов сначала идет через dry-run inventory. Деструктивное удаление выполняется только после отдельного явного разрешения пользователя.

## Strategy Audit

### Strategy

Базовая стратегия: сначала восстановить доверие к проверкам, затем стабилизировать запуск, затем ускорять сетевые/Excel-операции, затем чистить мусор и обновлять документацию.

### Attack

Главные способы, которыми план может провалиться:

- Исправление теста `employees.yaml` может скрыть реальную ошибку конфигурации, если просто подогнать тест под текущий файл.
- Изменение `ЗАПУСК.bat` может улучшить Codex/локальный ПК, но сломать рабочий ПК без установленного `.venv`.
- Очистка кеша сетевых файлов может удалить файл, который параллельно читает другой поток.
- Оптимизация matching-алгоритма может незаметно изменить порядок one-to-one сопоставления и уменьшить точность.
- Ускорение Excel autosize/style может изменить визуальный формат отчета, хотя тесты по данным останутся зелеными.
- Formula-injection sanitizer может случайно примениться к числовым ячейкам или hyperlink-ячейкам и испортить формат.
- Уборка папки может затронуть tracked Excel или пользовательские артефакты.
- Документация может снова заявить зеленый baseline без фактической полной проверки.

### Fix

Защиты добавлены в план:

- Новый Task 0 фиксирует dirty worktree, текущие проверки и запрет смешивать чужие изменения.
- Task 1 теперь должен проверять контракт `employees.yaml`, а не просто менять expected values.
- Task 3 должен создавать/использовать локальный `.venv` безопасно и не зависеть от первого `python` в PATH.
- Task 5 требует ленивую и безопасную cache cleanup политику с защитой от удаления свежих/используемых файлов.
- Task 6 требует slow-reference/golden equivalence перед оптимизацией matching.
- Task 7 требует проверки форматирования, не только данных.
- Task 10 требует dry-run и отдельное разрешение перед удалением.

### Compare

Альтернатива "сразу чинить все найденное" быстрее, но рискованна из-за грязного worktree и Excel-артефактов. Альтернатива "только quality gates" безопаснее, но не решает сетевую медлительность и запуск на рабочем ПК. Выбранный подход лучше: сначала восстанавливает проверяемость, затем оптимизирует только после эталонов поведения.

### Improve

Оптимизации сверки и Excel-вывода выполняются только после стабилизации тестов и эталонных файлов. Любое изменение бизнес-семантики сверки остается вне этого плана, пока заказчик не утвердит правило.

### Verify

Стратегия считается достаточно проверенной только если:

- есть список dirty files до правок;
- первый исправленный slice дает зеленый targeted test;
- full pytest либо зеленый, либо каждый красный тест классифицирован;
- generated Excel после оптимизации сравнен на headers/status/counts/reasons и ключевые форматы;
- GitNexus обновлен после успешных изменений.

### Execute

Исполнять строго по порядку `Recommended Execution Order`. Не переходить к performance refactor, пока Task 1-5 не закрыты.

## Files Map

- `APP/employees.yaml` - текущая конфигурация сотрудников и привязанных файлов.
- `tests/test_employee_config_sync.py` - тест синхронизации текущего набора сотрудников.
- `APP/core/infra/reconciliation_report.py` - сборка сверки, сопоставление строк, Excel-вывод.
- `APP/core/ui/gui_commands.py` - GUI-команды РСЧ/сверки.
- `APP/core/app_controller.py` - фоновые операции и orchestration.
- `APP/core/infra/utils.py` - открытие путей и локальный кеш сетевых файлов.
- `APP/core/infra/rsch_report.py` - сборка РСЧ и Excel-вывод.
- `APP/core/bootstrap.py` - нормализация путей БД/схемы.
- `APP/config.yaml` - локальная рабочая конфигурация.
- `APP/config.example.yaml` - переносимый пример конфигурации.
- `ЗАПУСК.bat` - рабочий запускатор на ПК пользователя.
- `README.md`, `docs/DEVELOPMENT.md`, `docs/OPERATIONS.md`, `docs/PERFORMANCE_GUIDE.md`, `docs/PROJECT_AI_GUIDE.md` - документация и baseline.
- `.gitignore` - правила мусорных/локальных артефактов.

---

### Task 0: Establish Safety Baseline And Worktree Boundaries

**Problem:** Worktree already contains many modified/generated files. Without a baseline, fixes can accidentally absorb unrelated changes or overwrite user data.

**Files:**
- No modifications in this task.

- [ ] **Step 1: Capture current dirty worktree**

Run:

```powershell
git status --short
git diff --stat
```

Expected: record output in the implementation notes/final report. Do not revert anything.

- [ ] **Step 2: Capture current quality baseline**

Run:

```powershell
python -m pytest tests/test_employee_config_sync.py -q -p no:cacheprovider
python -m mypy APP\core\infra\reconciliation_report.py --no-error-summary
python -m ruff check APP tests -q
python -m compileall -q APP
```

Expected baseline:
- employee sync test currently fails;
- reconciliation mypy currently fails;
- ruff and compileall currently pass.

- [ ] **Step 3: Freeze Excel deletion policy**

Before any cleanup task, confirm this rule in the implementation notes:

```text
Do not delete or move *.xlsx, *.xlsm, *.xlsb, REPORTS/, РСЧ/, рсч всех/, or Master_Report.xlsx.
```

---

### Task 1: Restore Employee Config Sync Test

**Problem:** `tests/test_employee_config_sync.py` ожидает старый формат `employees.yaml`, а реальный YAML уже содержит смешанные строки и записи `{path,id,fp}`.

**Files:**
- Modify: `tests/test_employee_config_sync.py`
- Inspect only if needed: `APP/employees.yaml`

- [ ] **Step 1: Define the current contract before changing assertions**

The test must prove all of these:

- `employees.yaml` can contain either string path entries or dict entries with `path`;
- every dict entry must have a non-empty string `path`;
- optional `id` and `fp` metadata may exist but must not be required for old string entries;
- expected active employees are present;
- removed employees are absent;
- critical known file bindings are present by normalized path suffix, not by machine-specific absolute prefix.

- [ ] **Step 2: Add a local path normalizer in the test**

Use a helper that accepts both old string entries and new dict entries:

```python
def _entry_path(entry: object) -> str:
    if isinstance(entry, str):
        return entry.replace("\\", "/")
    if isinstance(entry, dict):
        raw_path = entry.get("path")
        assert isinstance(raw_path, str)
        return raw_path.replace("\\", "/")
    raise AssertionError(f"Unsupported employee entry: {entry!r}")
```

- [ ] **Step 3: Compare by normalized suffix instead of exact absolute local path**

Use this assertion helper:

```python
def _assert_has_path(data: dict[str, object], employee: str, suffix: str) -> None:
    entries = data[employee]
    assert isinstance(entries, list)
    normalized = [_entry_path(entry) for entry in entries]
    assert any(path.endswith(suffix.replace("\\", "/")) for path in normalized)
```

- [ ] **Step 4: Update fragile exact assertions**

Replace exact list equality for employees such as `Амалия`, `Марго`, `Алиса Ю` with `_assert_has_path(...)`. Preserve checks that deleted employees are absent and expected employees are present.

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest tests/test_employee_config_sync.py -q -p no:cacheprovider
```

Expected: `1 passed`.

---

### Task 2: Fix Current Mypy Error In Reconciliation Output

**Problem:** `mypy` fails at `APP/core/infra/reconciliation_report.py:808` because `values` is inferred as `list[None]`, then assigned `str`.

**Files:**
- Modify: `APP/core/infra/reconciliation_report.py`

- [ ] **Step 1: Run impact check**

Run:

```powershell
& 'C:\Users\vanya\AppData\Roaming\npm\gitnexus.cmd' status
rg -n "_master_values\(" APP tests
```

- [ ] **Step 2: Make the list type explicit**

Change `_master_values` fallback:

```python
def _master_values(row: ReconciliationRow, master_headers: list[str]) -> list[Any]:
    if row.master is not None:
        return row.master.values
    values: list[Any] = [None for _ in master_headers]
    if values:
        values[0] = row.reason
    return values
```

- [ ] **Step 3: Verify**

Run:

```powershell
python -m mypy APP\core\infra\reconciliation_report.py --no-error-summary
python -m pytest tests/test_reconciliation_report.py -q -p no:cacheprovider
python -m ruff check APP\core\infra\reconciliation_report.py tests\test_reconciliation_report.py -q
```

Expected: mypy passes for this file; reconciliation tests pass.

---

### Task 3: Stabilize Python Runtime Used By Launcher

**Problem:** `ЗАПУСК.bat` uses first `python` in PATH and mutates global/user packages with `pip install --user`, causing different behavior on different PCs.

**Files:**
- Modify: `ЗАПУСК.bat`
- Modify: `docs/OPERATIONS.md`
- Optional create: `.venv/` at runtime only; do not commit it.

- [ ] **Step 1: Prefer existing local venv**

Before `where python`, check `%~dp0.venv\Scripts\python.exe` and `%~dp0.venv\Scripts\pythonw.exe`.

Batch logic:

```bat
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    set "PYTHONW_CMD=%~dp0.venv\Scripts\pythonw.exe"
)
if defined PYTHON_CMD goto python_launcher_done
```

- [ ] **Step 2: Create local venv if missing and Python 3.12 launcher exists**

Use `py -3.12 -m venv "%~dp0.venv"` when `.venv` is missing. If `py -3.12` is unavailable, fall back to current Python detection but do not silently claim the environment is reproducible.

Batch shape:

```bat
if not exist "%~dp0.venv\Scripts\python.exe" (
    py -3.12 -m venv "%~dp0.venv" >> "%LOGFILE%" 2>&1
)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
    if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYTHONW_CMD=%~dp0.venv\Scripts\pythonw.exe"
    goto python_launcher_done
)
```

- [ ] **Step 3: Stop upgrading global/user tooling on every launch**

Replace unconditional tool upgrade with a version/log check. Do not run `pip install --user --upgrade pip setuptools wheel` during normal startup.

Safer behavior:

```bat
call :step "Step 3/5. Checking packaging tools"
"%PYTHON_CMD%" -m pip --version >> "%LOGFILE%" 2>&1
if errorlevel 1 goto pip_repair_failed
```

- [ ] **Step 4: Install missing requirements into local venv when available**

If `%PYTHON_CMD%` points to `.venv`, use:

```bat
"%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" >> "%LOGFILE%" 2>&1
```

Only fall back to `--user` if no venv exists and log a warning that the runtime is not isolated.

- [ ] **Step 5: Document recommended setup**

Add to `docs/OPERATIONS.md`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- [ ] **Step 6: Verify**

Run:

```powershell
cmd /c ЗАПУСК.bat
```

Expected: launcher finds local venv when present and does not upgrade global packages during normal launch.

---

### Task 4: Move Manual Reconciliation Off The GUI Thread

**Problem:** `GuiCommands.run_reconciliation_report` calls `build_combined_reconciliation_report(...)` synchronously and can freeze the window.

**Files:**
- Modify: `APP/core/ui/gui_commands.py`
- Test: `tests/test_gui_commands_rsch.py`

- [ ] **Step 1: Study existing background pattern**

Inspect `run_auto_reconciliation_day` and `AppController` background callbacks. Reuse the existing project pattern; do not invent a second threading model.

- [ ] **Step 2: Add/adjust a GUI test**

Create a test that verifies manual reconciliation delegates work asynchronously and disables/re-enables the reconciliation button through callbacks.

Expected shape:

```python
def test_run_reconciliation_report_runs_in_background(...):
    ...
    commands.run_reconciliation_report()
    mock_app_controller.run_in_background.assert_called_once()
```

Use the actual helper name if the project already has one; otherwise add the smallest local helper in `GuiCommands`.

- [ ] **Step 3: Implement minimal background wrapper**

The worker should return `row_counts`; the completion callback should show success/open dialog; the error callback should show messagebox error.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests/test_gui_commands_rsch.py -q -p no:cacheprovider
python -m ruff check APP\core\ui\gui_commands.py tests\test_gui_commands_rsch.py -q
python -m compileall -q APP\core\ui\gui_commands.py
```

---

### Task 5: Make Network Local-Copy Cache Bounded And Config-Aware

**Problem:** `master_report_cache` has no cleanup policy, and RСЧ/sverka calls do not pass configured drive letters.

**Files:**
- Modify: `APP/core/infra/utils.py`
- Modify: `APP/core/infra/rsch_report.py`
- Modify: `APP/core/infra/reconciliation_report.py`
- Optional Modify: call sites in `APP/core/ui/gui_commands.py` / `APP/core/app_controller.py` if config must be threaded through.
- Test: `tests/test_utils.py`, `tests/test_rsch_report_edge_cases.py`, `tests/test_reconciliation_report.py`

- [ ] **Step 1: Add tests for configured drive letters**

Cover a non-default mapped drive such as `R:\file.xlsx`:

```python
def test_get_local_copy_uses_custom_drive_letters(...):
    ...
```

- [ ] **Step 2: Add tests for cache cleanup**

Add tests:

```python
def test_get_local_copy_removes_old_cache_files(tmp_path, monkeypatch):
    ...
```

Use monkeypatch to redirect `_CACHE_DIR` to `tmp_path`.

- [ ] **Step 3: Add cleanup helper**

Implement conservative cleanup:

```python
def cleanup_local_copy_cache(max_age_days: int = 14, max_total_mb: int = 512) -> None:
    ...
```

Rules:
- delete only files inside `_CACHE_DIR`;
- never follow symlinks;
- skip files modified in the last 30 minutes to reduce risk of deleting files another thread is reading;
- remove oldest remaining files first if total exceeds limit;
- swallow cleanup errors but log them.

- [ ] **Step 4: Call cleanup lazily**

Call cleanup at most once per process in `get_local_copy` before creating/copying a new cache file. Guard this with a module-level lock so concurrent workers cannot run cleanup at the same time.

- [ ] **Step 5: Pass configured drive letters into RСЧ and reconciliation**

Thread `drive_letters` through report builders without breaking current public calls:

```python
def build_rsch_report(..., drive_letters: tuple[str, ...] = ("Q", "Z")) -> Path:
    ...
```

```python
def build_combined_reconciliation_report(..., drive_letters: tuple[str, ...] = ("Q", "Z")) -> dict[str, int]:
    ...
```

- [ ] **Step 6: Verify**

Run:

```powershell
python -m pytest tests/test_utils.py tests/test_rsch_report_edge_cases.py tests/test_reconciliation_report.py -q -p no:cacheprovider
python -m ruff check APP\core\infra\utils.py APP\core\infra\rsch_report.py APP\core\infra\reconciliation_report.py tests -q
```

---

### Task 6: Optimize Reconciliation Matching Without Changing Semantics

**Problem:** `_build_reconciliation_rows` repeatedly scans `rsch_rows`; this is O(master * rsch) across several passes.

**Files:**
- Modify: `APP/core/infra/reconciliation_report.py`
- Test: `tests/test_reconciliation_report.py`

- [ ] **Step 1: Create a slow-reference guard before optimizing**

Before changing matching internals, preserve current semantics in a test helper or golden fixture. The guard must cover:

- exact match;
- amount mismatch -> `ПРОВЕРИТЬ`;
- executor mismatch -> `ПРОВЕРИТЬ`;
- weak customer unique candidate -> `ПРОВЕРИТЬ`;
- weak customer ambiguous candidates -> no auto-pair;
- duplicate equal amounts preserve stable first-unused row order.

- [ ] **Step 2: Add a benchmark-style regression test on matching counts**

Create a deterministic test with hundreds of rows and assert output statuses are identical before/after by snapshotting counts.

Use existing builders in `tests/test_reconciliation_report.py`; do not add pandas.

- [ ] **Step 3: Introduce internal indexes**

Add private indexes:

```python
@dataclass(frozen=True)
class _RschIndexes:
    by_customer: dict[str, list[tuple[int, RschReconciliationRow]]]
    by_amount_executor: dict[tuple[Decimal, str], list[tuple[int, RschReconciliationRow]]]
```

Keep exact business behavior:
- exact customer + amount + executor still wins;
- ambiguous weak customer candidates remain unpaired;
- used indexes are still honored.

- [ ] **Step 4: Refactor find helpers to use indexes**

Keep function names if possible; pass `_RschIndexes` into helpers.

- [ ] **Step 5: Verify business tests**

Run:

```powershell
python -m pytest tests/test_reconciliation_report.py -q -p no:cacheprovider
python -m mypy APP\core\infra\reconciliation_report.py --no-error-summary
python -m ruff check APP\core\infra\reconciliation_report.py tests\test_reconciliation_report.py -q
```

---

### Task 7: Reduce Excel Autosize And Style-Copy Cost

**Problem:** Autosize loops scan every cell after writing; RСЧ style copy copies cell styles row-by-row.

**Files:**
- Modify: `APP/core/infra/reconciliation_report.py`
- Modify: `APP/core/infra/rsch_report.py`
- Test: `tests/test_reconciliation_report.py`, `tests/test_rsch_report.py`

- [ ] **Step 1: Capture format expectations before changing code**

Add or inspect tests that assert:

- numeric columns keep numeric formats;
- percent columns keep percent formats;
- status colors remain the same;
- source hyperlinks still exist;
- important columns have width within expected min/max.

- [ ] **Step 2: Track widths while appending rows**

Replace post-write full scan with incremental width tracking:

```python
def _update_widths(widths: dict[int, int], values: list[Any]) -> None:
    for idx, value in enumerate(values, start=1):
        widths[idx] = max(widths.get(idx, 0), len(str(value)) if value is not None else 0)
```

- [ ] **Step 3: Apply final widths once**

```python
def _apply_widths(ws: Worksheet, widths: dict[int, int], min_width: int, max_width: int) -> None:
    for col_idx, max_len in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = max(
            min_width,
            min(max_width, max_len + 2),
        )
```

- [ ] **Step 4: Cache copied style objects per template column**

In RСЧ writer, resolve template styles once per column and reuse copies, instead of reading template cells repeatedly inside each row.

- [ ] **Step 5: Verify no format regression**

Run:

```powershell
python -m pytest tests/test_rsch_report.py tests/test_reconciliation_report.py -q -p no:cacheprovider
python -m compileall -q APP\core\infra\rsch_report.py APP\core\infra\reconciliation_report.py
```

---

### Task 8: Verify And Fix Formula-Injection Risk In Generated Excel

**Problem:** Main export sanitizes text, but RСЧ/sverka output may write raw source text beginning with `=`, `+`, `-`, `@`.

**Files:**
- Modify: `APP/core/infra/reconciliation_report.py`
- Modify: `APP/core/infra/rsch_report.py`
- Test: `tests/test_reconciliation_report.py`, `tests/test_rsch_report.py`

- [ ] **Step 1: Write failing tests**

Add rows with customer/comment values:

```python
"=HYPERLINK(\"http://bad\", \"click\")"
"+79000000000"
"@cmd"
```

Assert generated text cells start with apostrophe and are not formulas.

- [ ] **Step 2: Add a small local sanitizer**

Do not import domain `LogicService`. Add infra-local helper:

```python
def _excel_safe_text(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value
```

Apply only to text/business fields, not numeric amount cells and not hyperlink cells.

- [ ] **Step 3: Verify sanitizer does not touch numeric cells or hyperlinks**

Assert:

```python
assert isinstance(ws.cell(row, amount_col).value, (int, float, Decimal))
assert ws.cell(row, source_col).hyperlink is not None
```

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests/test_reconciliation_report.py tests/test_rsch_report.py -q -p no:cacheprovider
python -m ruff check APP\core\infra\reconciliation_report.py APP\core\infra\rsch_report.py tests -q
```

---

### Task 9: Make Config Example Portable And Current

**Problem:** `APP/config.example.yaml` references stale `APP/src/db_schema.sql` and old `employee_paths`; README baseline is outdated.

**Files:**
- Modify: `APP/config.example.yaml`
- Modify: `README.md`
- Modify: `docs/DEVELOPMENT.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/PROJECT_AI_GUIDE.md`

- [ ] **Step 1: Replace stale example with minimal current config**

Use current structure:

```yaml
database:
  path: cache.db
  schema_path: db_schema.sql
  timeout: 30.0
  allow_local_fallback: false
  isolation_level: EXCLUSIVE
  use_wal: true
network:
  drive_letters:
    - Q
    - Z
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

- [ ] **Step 2: Update baseline after actual checks**

Only document commands that were just run. Do not claim Sentrux passed if its scan tool is unavailable.

- [ ] **Step 3: Verify docs references**

Run:

```powershell
rg -n "737 passed|Sentrux rules - passed|APP/src/db_schema|employee_paths" README.md docs APP/config.example.yaml
```

Expected: no stale baseline/path references except historical notes if clearly marked.

---

### Task 10: Clean Workspace Safely Without Removing Excel Data

**Problem:** repo folder is heavy and contains cache/generated artifacts; Excel files must not be deleted.

**Files:**
- Modify: `.gitignore`
- Do not delete Excel files in this task.

- [ ] **Step 1: Generate a cleanup inventory**

Run:

```powershell
Get-ChildItem -Force | ForEach-Object {
  if ($_.PSIsContainer) {
    $sum = (Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    [PSCustomObject]@{Name=$_.Name; MB=[math]::Round(($sum/1MB),2)}
  } else {
    [PSCustomObject]@{Name=$_.Name; MB=[math]::Round(($_.Length/1MB),2)}
  }
} | Sort-Object MB -Descending
```

- [ ] **Step 2: Extend `.gitignore` for local tool caches**

Add if not already present:

```gitignore
.mypy_cache/
.opencode/node_modules/
.sentrux/
Version5.rar
MagicMock/
tmp_mode700_probe/
tmp_pytest_baseline_codex/
```

- [ ] **Step 3: Move/delete only clearly generated non-Excel artifacts after explicit dry-run**

Allowed candidates:
- `.mypy_cache/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.hypothesis/`
- `MagicMock/`
- `tmp_mode700_probe/`
- `tmp_pytest_baseline_codex/`
- `Version5.rar`

Do not touch:
- `REPORTS/`
- `РСЧ/`
- `рсч всех/`
- `Master_Report.xlsx`
- any `*.xlsx`, `*.xlsm`, `*.xlsb`

- [ ] **Step 4: Prefer quarantine before permanent delete**

If the user approves cleanup, first move removable non-Excel artifacts into:

```text
.cleanup_quarantine/YYYYMMDD-HHMMSS/
```

Run checks. Permanently delete quarantine only after a separate explicit approval.

- [ ] **Step 5: Verify after cleanup/quarantine**

Run:

```powershell
python -m pytest tests/test_reconciliation_report.py tests/test_rsch_report.py -q -p no:cacheprovider
python -m ruff check APP tests -q
```

---

### Task 11: Resolve Global Dependency Drift

**Problem:** `python -m pip check` fails due global/user environment conflicts unrelated to the app but dangerous for launches.

**Files:**
- Modify: `docs/OPERATIONS.md`
- Optional Modify: `ЗАПУСК.bat`

- [ ] **Step 1: Do not try to fix global Python packages from app startup**

The app should run from `.venv` or a known Python. Avoid mutating user site-packages.

- [ ] **Step 2: Add documented health command**

Document:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

This should replace using global:

```powershell
python -m pip check
```

- [ ] **Step 3: Verify local environment**

Run only after `.venv` exists:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Expected: no conflicts inside project venv.

---

### Task 12: Refresh GitNexus And Final Quality Gates

**Problem:** After successful fixes, index/docs must match current code.

**Files:**
- No direct code files unless docs generated by GitNexus change.

- [ ] **Step 1: Run targeted checks**

```powershell
python -m pytest tests/test_employee_config_sync.py tests/test_reconciliation_report.py tests/test_rsch_report.py tests/test_gui_commands_rsch.py tests/test_utils.py -q -p no:cacheprovider
python -m ruff check APP tests -q
python -m mypy APP tests --no-error-summary
python -m compileall -q APP
```

- [ ] **Step 2: Run full test suite if targeted checks are green**

```powershell
python -m pytest -q -p no:cacheprovider
```

- [ ] **Step 3: Refresh GitNexus**

```powershell
& 'C:\Users\vanya\AppData\Roaming\npm\gitnexus.cmd' analyze 'E:\Dlia Dashi\Version5'
& 'C:\Users\vanya\AppData\Roaming\npm\gitnexus.cmd' status
```

- [ ] **Step 4: Produce final report**

Report:
- files changed;
- what was fixed;
- exact commands and results;
- remaining risks;
- whether any Excel files were intentionally left untouched.

---

## Recommended Execution Order

0. Task 0 - establish safety baseline and worktree boundaries.
1. Task 1 - restore pytest baseline.
2. Task 2 - restore mypy baseline.
3. Task 3 - stabilize launcher/runtime.
4. Task 4 - remove GUI freeze risk.
5. Task 5 - bound network cache and use configured drives.
6. Task 8 - confirm/close Excel formula-injection risk.
7. Task 6 - optimize matching algorithm only after semantic guard is in place.
8. Task 7 - optimize Excel formatting/autosize only after format guard is in place.
9. Task 9 - update docs/config example.
10. Task 10 - safe cleanup/quarantine.
11. Task 11 - isolate dependency health.
12. Task 12 - final gates and GitNexus refresh.

## Completion Criteria

- `tests/test_employee_config_sync.py` passes.
- `python -m mypy APP tests --no-error-summary` passes or any remaining errors are explicitly documented as pre-existing and accepted.
- `python -m ruff check APP tests -q` passes.
- `python -m compileall -q APP` passes.
- Targeted RСЧ/sverka tests pass.
- Full pytest passes with `-p no:cacheprovider`, or every failure is classified as unrelated environment/tool cache issue.
- Launcher no longer mutates global Python by default.
- Network cache cannot grow without bound.
- Current docs no longer claim stale green baselines.
- Cleanup does not remove Excel business data.
- No matching optimization changes `СВЕРЕНО` / `ПРОВЕРИТЬ` / `ОШИБКА` semantics without a separate business-rule decision.
