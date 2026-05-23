# Release Procedure

Use this procedure for calm updates on multiple Windows PCs.

## Pre-Release Gate

Run locally from the repository root:

```powershell
python -m pytest -q -p no:cacheprovider
python -m ruff check APP tests -q
python -m mypy APP tests --no-error-summary
python -m compileall -q APP
python tools/timing_report.py --date 12.05.2026 --period-start 01.05.2026 --period-end 22.05.2026
```

The timing report writes local artifacts to `benchmarks/`. Commit code and docs only; do not commit benchmark outputs or real Excel files.

## Release Steps

1. Check `git status --short`; only intended code/docs/test changes should be staged.
2. Update `CHANGELOG.md`.
3. Commit to `main` or merge through a PR.
4. Wait for the GitHub Actions `Quality Gate` to pass on the final `main` commit.
5. On each work PC run `ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat`.
6. After update, run the new-PC smoke checklist from `docs/OPERATIONS.md`.
7. Keep `update_log.txt`, `startup_log.txt`, and the latest `benchmarks/*.md` if a PC behaves differently.

## Branch Protection

In GitHub repository settings:

1. Open `Settings -> Branches`.
2. Add or edit protection for `main`.
3. Enable `Require status checks to pass before merging`.
4. Select the required check `Quality Gate / Windows quality gate`.
5. Enable `Require branches to be up to date before merging` if PRs are used.
6. Keep direct pushes limited to trusted maintainers.

If the repository is private and a runner label stops starting, change only `.github/workflows/quality-gate.yml` from `windows-2025-vs2026` to `windows-2025`, then wait for a green Quality Gate.

## Rollback

Program files:

```powershell
git log --oneline -5
git revert <bad_commit_sha>
git push origin main
```

Excel output:

1. Open the configured backup folder, default `backups/excel_outputs/<report-name>/`.
2. Pick the latest known-good timestamped `.xlsx`.
3. Close Excel.
4. Copy it back over the broken report file.
5. Re-run only the failed scenario.

Do not delete source reports or RSC input files during rollback.
