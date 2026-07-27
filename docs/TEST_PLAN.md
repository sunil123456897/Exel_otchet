# Test Plan — Master-Report v5.6

**Version:** 1.0
**Date:** 2026-07-21
**Status:** Stage 0–9 automated tests complete; Stage 11 (rehearsal +
pilot) pending.

## 1. Test pyramid

```
                  ┌─────────────────┐
                  │ Manual / Pilot  │  Stage 7 acceptance matrix
                  │   (~50 checks)  │  (~50 manual items, Win10/11)
                  └─────────────────┘
                ┌───────────────────────┐
                │  End-to-end / Stage 11│  Release rehearsal (12 steps)
                │   (~12 procedures)    │  Not yet executed
                └───────────────────────┘
              ┌─────────────────────────────┐
              │  Integration / Fault inject │  18 tests
              │  SQLite, Excel I/O, threads │  tests/test_fault_injection.py
              └─────────────────────────────┘
            ┌───────────────────────────────────┐
            │  Property-based (Hypothesis)      │  10 tests
            │  + UI acceptance (mocked ctrl)    │  + 16 UI acceptance
            │  + backup-restore + diagnostic    │  + 10 + 17
            └───────────────────────────────────┘
          ┌─────────────────────────────────────────┐
          │  Unit / Behaviour                       │  ~880 tests
          │  LogicService, ingestion, config, etc.  │  tests/test_*.py
          └─────────────────────────────────────────┘
```

**Total automated: 990 tests, 0 skipped on Windows.**

## 2. Coverage by risk area

| Area | Tests | Strategy |
|------|-------|----------|
| **Financial correctness** | 55 golden + 10 property + 8 invariant | Synthetic fixtures + Hypothesis + control-date fingerprint (4906 cells, 0 drift) |
| **Data integrity** | 18 fault-injection + 10 backup-restore | Atomic writes, SQLite rollback, source-file immutability |
| **Config & employees** | 48 (schema + matrix + employees) | 4-way error taxonomy, migration idempotency, legacy upgrade |
| **Excel reliability** | 16 corrupt-fixture + 8 SLA | 8 malformation types, parser isolation, no OOM |
| **Updater** | 22 matrix | Atomic switch, rollback, offline ZIP, path safety |
| **Privacy** | 17 diagnostic + 10 data_loss | Tokens/paths/amounts/names never leak |
| **UI** | 127 + 16 acceptance | Widget rendering, theme switching, error presenter |
| **Performance** | 8 SLA + timing harness | Floor-estimates + leak detection (0 threads growth) |
| **Architecture** | 47 boundary | domain purity, UI no-fin-math |

## 3. Definition of Done for a release

Before any release tag:

- [ ] All 990 automated tests pass on Windows 10 AND Windows 11.
- [ ] `ruff check APP tests` is clean.
- [ ] `mypy --strict` baseline is unchanged OR explicitly refreshed
      with a documented reason.
- [ ] `python tools/timing_report.py --runs 5` produces medians within
      20% of `tests/golden/timing_baseline.json`.
- [ ] Stage 7 acceptance matrix (`docs/stage_reports/stage_7_acceptance_matrix.md`)
      is filled, every row is PASS or has an accepted known-limitation.
- [ ] `python tools/diagnostic_package.py --scan` reports "privacy OK".
- [ ] Control-date fingerprint (`tests/golden/control_date.json`)
      reproduces on operator's real `Master_Report.xlsx`.
- [ ] KNOWN_LIMITATIONS is signed by owner.

## 4. What is NOT covered by automated tests

These are the limits of the automated suite. They are accepted as
known limitations (see `docs/KNOWN_LIMITATIONS.md`):

- **Real network drive latency.** CI has no SMB share.
- **DPI rendering perception.** CI has no configurable-DPI display.
- **Excel version compatibility.** CI has no real Excel 2019/2021/M365.
- **1-hour memory soak.** Leak tests run ~100 iterations (minutes).
- **Real SLA certification.** Harness gives floor; pilot measures ceiling.
- **Standalone packaging.** PyInstaller is Stage 12 (not in this TZ).
- **Authenticode signing.** Stage 12.

## 5. Test commands (operator reference)

```bat
:: Full automated suite (≈80 s on a typical dev machine)
.venv\Scripts\python.exe -m pytest tests -q --tb=short

:: CI gates (run from repo root)
.venv\Scripts\python.exe -m compileall -q APP tests
.venv\Scripts\python.exe -m ruff check APP tests
.venv\Scripts\python.exe tools\ci_mypy_check.py

:: Golden regression (control date + synthetic scenarios)
.venv\Scripts\python.exe -m pytest tests/golden/ -v

:: Performance + leak detection
.venv\Scripts\python.exe tools\timing_report.py --runs 5

:: Privacy self-audit
.venv\Scripts\python.exe tools\diagnostic_package.py --scan

:: Baseline report (machine-readable snapshot)
.venv\Scripts\python.exe tools\qa_baseline.py --full --pretty
```

## 6. Adding a new test

When adding a feature or fixing a bug:

1. **Decide the test level.**
   - Pure business rule? → unit test under `tests/test_<area>.py`.
   - Involves Excel/SQLite/filesystem? → integration under
     `tests/test_<area>.py` or `tests/test_fault_injection.py`.
   - Pure invariant over many inputs? → Hypothesis under
     `tests/test_property_based.py`.
   - UI behaviour? → `tests/ui/test_<feature>.py` (uses the `gui`
     fixture from `tests/ui/conftest.py`).

2. **Match the existing style.** Each test file starts with a module
   docstring explaining what it pins and why. Use Russian comments
   where the surrounding code does.

3. **Privacy by default.** Test fixtures must never contain real
   names, amounts, or paths. Use `tests/golden/synthetic_fixtures.py`
   patterns. The PII scanner (`test_synthetic_fixtures.py::
   test_no_real_pii_in_any_fixture`) enforces this.

4. **Run the full suite before commit.** A new test that breaks
   existing ones is a regression.
