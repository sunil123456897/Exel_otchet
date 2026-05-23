# Changelog

## Unreleased

- Added a repeatable headless performance timing report with markdown/json output in `benchmarks/` and previous-run regression comparison.
- Added safe backups for existing Excel outputs before overwrite, with retention controlled by `backup.excel_keep`.
- Added optional `performance.max_workers`; empty value keeps the current adaptive default.
- Documented release, branch-protection, new-PC smoke, Q/Z network smoke, backup restore, and benchmark procedures.

## 5.5 Hardening Baseline

- CI Quality Gate runs `pytest`, `ruff`, `mypy`, and `compileall` on Windows.
- Manual RSC reports with zero rows are treated as errors instead of successful empty outputs.
- Reconciliation outputs exclude current customer-approved curator filters: `доп сф`, `касса`, `зачет`, `посредник`, `корректировка`.
- Math-warning fills in master reports are preserved over ordinary income/expense fills.
- The template-error Excel sheet remains disabled; technical template issues stay in logs/database metadata.
