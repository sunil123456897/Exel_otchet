# Stage 7 — Windows UI/UX acceptance matrix

**Version:** 1.0
**Date:** 2026-07-21
**Purpose:** formal checklist for **manual** acceptance testing on real
Windows machines. Automated UI tests (127 in `tests/ui/`) cover widget
construction, event handling, theme switching and invariants — but
cannot verify the things only a human on the target OS can perceive:
DPI rendering, font hinting, real-network latency, actual Excel
behaviour.

The operator/QA engineer runs this checklist on each pilot machine and
records PASS/FAIL/BLOCKED per row, with a comment if not PASS.

## How to use

1. Boot a clean Windows 10 or 11 machine matching one of the columns
   below.
2. Install the app via `ЗАПУСК.bat` (which builds `.venv`).
3. Walk every row of every table. Do NOT skip rows; mark BLOCKED if a
   prerequisite isn't available (e.g. no network drive in the test
   lab).
4. Capture a screenshot of any FAIL or BLOCKED row.
5. File one issue per FAIL with the screenshot, OS version, app
   version (`about` dialog), and the row ID.

---

## A. Operating system & display

| ID | Check | Win10 | Win11 | Notes |
|----|-------|-------|-------|-------|
| A1 | Cold launch via `ЗАПУСК.bat` finishes < 5 s |   |   |   |
| A2 | App opens on a standard user (no admin) |   |   |   |
| A3 | Window appears at 100% DPI |   |   |   |
| A4 | Window appears at 125% DPI — no clipped buttons |   |   |   |
| A5 | Window appears at 150% DPI — no clipped buttons |   |   |   |
| A6 | Window appears at 200% DPI — no clipped buttons |   |   |   |
| A7 | Full HD (1920×1080): all 7 notebook tabs visible |   |   |   |
| A8 | Laptop 1366×768: all 7 tabs visible (scroll allowed) |   |   |   |
| A9 | Light theme renders correctly |   |   |   |
| A10 | Dark theme renders correctly |   |   |   |
| A11 | System theme follows OS dark/light switch |   |   |   |
| A12 | Russian locale (`ru-RU`) — all UI text Russian, no mojibake |   |   |   |

## B. Keyboard navigation & accessibility

| ID | Check | Result | Notes |
|----|-------|--------|-------|
| B1 | Tab moves focus through sidebar buttons predictably |   |   |
| B2 | Enter activates focused button |   |   |
| B3 | Esc closes any open dialog |   |   |
| B4 | Shortcuts dialog lists all bindings |   |   |
| B5 | Status is communicated by text, not only by colour (a11y) |   |   |
| B6 | Long paths in employees list wrap or scroll — no truncation silently |   |   |
| B7 | Cyrillic in paths works (e.g. `Q:\Отчет кураторов`) |   |   |
| B8 | UNC paths work (e.g. `\\server\share\book.xlsx`) |   |   |

## C. Excel integration

| ID | Check | Result | Notes |
|----|-------|--------|-------|
| C1 | Excel 2019 — input files read correctly |   |   |
| C2 | Excel 2021 — input files read correctly |   |   |
| C3 | Microsoft 365 — input files read correctly |   |   |
| C4 | Input file open in Excel — read still succeeds (file lock handling) |   |   |
| C5 | Output file open in Excel — write is rejected with clear message |   |   |
| C6 | Cancel during consolidation leaves inputs unchanged |   |   |
| C7 | Cancel responds within 2 s |   |   |
| C8 | Close window during processing — no orphan threads, no corruption |   |   |

## D. Network & filesystem resilience

| ID | Check | Result | Notes |
|----|-------|--------|-------|
| D1 | Network drive mapped (`Q:`) — refresh 23 employees < 2 s on LAN |   |   |
| D2 | Network drive slow (~5 s response) — UI shows progress, not freeze |   |   |
| D3 | Network drive disconnected mid-operation — clear error, no crash |   |   |
| D4 | Network drive completely absent — app launches, paths flagged |   |   |
| D5 | Read-only output dir — write attempt rejected with clear message |   |   |
| D6 | `~$book.xlsx` Excel lock file present — scanner skips it |   |   |

## E. Error presentation

| ID | Check | Result | Notes |
|----|-------|--------|-------|
| E1 | Permission error on a file → user sees Russian "Нет доступа к файлу", not a traceback |   |   |
| E2 | Missing file → user sees "Файл не найден", not a traceback |   |   |
| E3 | Corrupt config → user sees "Файл настроек повреждён", not a traceback |   |   |
| E4 | Generic error → user sees "Внутренняя ошибка. Подробнее в логе." |   |   |
| E5 | No `str(exc)` is ever visible to the user (no paths, tokens, SQL fragments) |   |   |
| E6 | Long-running operation has progress indicator and Cancel button |   |   |
| E7 | Cancel returns UI to a working state — no disabled buttons stuck |   |   |

## F. First-run experience

| ID | Check | Result | Notes |
|----|-------|--------|-------|
| F1 | Fresh install shows Welcome dialog once |   |   |
| F2 | Welcome dialog disappears after marking done |   |   |
| F3 | Second launch does NOT show Welcome |   |   |
| F4 | Corrupt `first_run.json` → app still launches, dialog re-shows |   |   |
| F5 | Unwritable `first_run.json` → app still launches |   |   |

## G. Data integrity (the most critical section)

| ID | Check | Result | Notes |
|----|-------|--------|-------|
| G1 | Source workbooks are unchanged after consolidation (size, mtime) |   |   |
| G2 | Two consecutive runs of the same date produce byte-identical output |   |   |
| G3 | Cancel does not leave a partially-written output file |   |   |
| G4 | Re-opening a previously-built report preserves formulas (no value-substitution) |   |   |
| G5 | Decimal values in the report have no float-precision drift |   |   |

## H. Update & rollback (only if Stage 4 wiring is enabled)

| ID | Check | Result | Notes |
|----|-------|--------|-------|
| H1 | `ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat` completes without admin rights |   |   |
| H2 | Update with app running is blocked with a clear message |   |   |
| H3 | Corrupt archive → rollback to previous version automatically |   |   |
| H4 | Successful update → next launch reports the new version |   |   |
| H5 | `ОБНОВИТЬ_ИЗ_ФАЙЛА.bat` works without internet |   |   |

---

## Sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| Pilot user 1 |   |   |   |
| Pilot user 2 |   |   |   |
| Developer |   |   |   |
| Owner |   |   |   |

**Definition of Done for Stage 7:** every row in sections A–G is PASS
or has an accepted known-limitation entry in CHANGELOG. Section H only
applies if Stage 4 wiring has been enabled by the owner.

## Known limitations (accept with documented reasoning)

_Populated during the pilot. Each entry must reference a row ID and
include the reason it cannot be fixed before the release._

- (none yet)
