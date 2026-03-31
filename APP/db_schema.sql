-- SQLite Schema for Master Report Hybrid Cache
-- Financial fields are stored as TEXT to maintain Decimal precision in Python.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Session tracking
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'in_progress', -- in_progress, completed, failed
    metadata TEXT -- JSON with run parameters
);

-- File metadata and tracking
CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT, -- MD5 fingerprint
    inode INTEGER, -- NTFS/Unix filesystem ID for rename detection
    status TEXT DEFAULT 'pending', -- pending, indexed, processed, error
    error_message TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

-- Staging area for raw rows before consolidation
CREATE TABLE IF NOT EXISTS staging_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    row_index INTEGER,
    raw_content_json TEXT, -- All columns from original Excel
    -- Mandatory extraction fields for filtering/sorting
    date_val TEXT,
    amount NUMERIC, -- Stored as string-compatible numeric
    employee_name TEXT,
    source_type TEXT, -- e.g. "Staff", "OPT"
    status TEXT DEFAULT 'raw', -- raw, validated, rejected
    validation_error TEXT,
    FOREIGN KEY(file_id) REFERENCES source_files(id)
);

-- Consolidated results (Final calculation cache)
CREATE TABLE IF NOT EXISTS consolidated_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    date_val TEXT,
    employee_name TEXT,
    total_amount NUMERIC,
    commission NUMERIC,
    net_amount NUMERIC,
    logic_applied TEXT, -- Rationale for the transformation
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

-- Template violations and warnings for curators
CREATE TABLE IF NOT EXISTS template_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    file_path TEXT,
    sheet_name TEXT,
    row_index INTEGER,
    error_type TEXT,
    details TEXT,
    raw_data TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_files_session ON source_files(session_id);
CREATE INDEX IF NOT EXISTS idx_staging_file ON staging_data(file_id);
CREATE INDEX IF NOT EXISTS idx_consolidated_session ON consolidated_results(session_id);
