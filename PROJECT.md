# Project: QA Testing

## Architecture
- **Ingestion**: `APP/core/infra/ingestion_reader.py`, `APP/core/infra/ingestion_engine.py`
- **Reconciliation**: `APP/core/domain/reconciliation.py` (or similar)
- **Export**: `APP/core/infra/export_writer.py`

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Ingestion Testing | Find bugs/edge cases in Ingestion module (CalamineReader, etc.) | none | DONE |
| 2 | Reconciliation Testing | Find bugs in core reconciliation rules, commissions, debts, etc. | none | IN_PROGRESS |
| 3 | Export Testing | Find bugs in Excel generation, file locking, network error handling | none | DONE |

## Code Layout
- Source files: `APP/core/`
- Existing Tests: `tests/`
