-- Migration 001: Change financial columns from NUMERIC to TEXT
--
-- SQLite NUMERIC affinity can coerce Decimal strings to REAL (float),
-- losing precision for large amounts. TEXT preserves the exact Decimal
-- representation stored by the Python sqlite3 Decimal adapter.
--
-- The migration runner checks table existence before executing each
-- statement group, so this file is safe on fresh DBs where the schema
-- has already created the tables with TEXT columns.
--
-- SQLite does not support ALTER COLUMN, so we use the table-rebuild
-- pattern: create new table, copy data, drop old, rename.

CREATE TABLE _staging_data_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    row_index INTEGER,
    raw_content_json TEXT,
    date_val TEXT,
    amount TEXT,
    employee_name TEXT,
    source_type TEXT,
    status TEXT DEFAULT 'raw',
    validation_error TEXT,
    FOREIGN KEY(file_id) REFERENCES source_files(id)
);

INSERT INTO _staging_data_new (id, file_id, row_index, raw_content_json, date_val, amount, employee_name, source_type, status, validation_error)
SELECT id, file_id, row_index, raw_content_json, date_val, CAST(amount AS TEXT), employee_name, source_type, status, validation_error
FROM staging_data;

DROP TABLE staging_data;
ALTER TABLE _staging_data_new RENAME TO staging_data;

CREATE TABLE _consolidated_results_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    date_val TEXT,
    employee_name TEXT,
    total_amount TEXT,
    commission TEXT,
    net_amount TEXT,
    logic_applied TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

INSERT INTO _consolidated_results_new (id, session_id, date_val, employee_name, total_amount, commission, net_amount, logic_applied)
SELECT id, session_id, date_val, employee_name, CAST(total_amount AS TEXT), CAST(commission AS TEXT), CAST(net_amount AS TEXT), logic_applied
FROM consolidated_results;

DROP TABLE consolidated_results;
ALTER TABLE _consolidated_results_new RENAME TO consolidated_results;

CREATE INDEX IF NOT EXISTS idx_staging_file ON staging_data(file_id);
CREATE INDEX IF NOT EXISTS idx_staging_employee_date ON staging_data(employee_name, date_val);
CREATE INDEX IF NOT EXISTS idx_consolidated_session ON consolidated_results(session_id);

