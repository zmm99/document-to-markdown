PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    md5 TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_format TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER NOT NULL,
    storage_date TEXT NOT NULL,
    upload_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(md5, file_format)
);

CREATE TABLE IF NOT EXISTS parse_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    file_format TEXT NOT NULL,
    engine TEXT NOT NULL,
    engine_version TEXT,
    status TEXT NOT NULL,
    output_dir TEXT,
    markdown_path TEXT,
    metadata_path TEXT,
    option_hash TEXT,
    options_json TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS document_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    parse_record_id INTEGER,
    asset_name TEXT NOT NULL,
    content_type TEXT,
    asset_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(parse_record_id) REFERENCES parse_records(id)
);

CREATE TABLE IF NOT EXISTS conversion_tasks (
    task_id TEXT PRIMARY KEY,
    file_id TEXT,
    original_filename TEXT NOT NULL,
    file_format TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT 'created',
    message TEXT NOT NULL DEFAULT '',
    error_code TEXT,
    error_message TEXT,
    cached INTEGER NOT NULL DEFAULT 0,
    option_hash TEXT,
    options_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_conversion_tasks_status
ON conversion_tasks(status);

CREATE INDEX IF NOT EXISTS idx_conversion_tasks_file_id
ON conversion_tasks(file_id);

CREATE INDEX IF NOT EXISTS idx_conversion_tasks_created_at
ON conversion_tasks(created_at);

CREATE INDEX IF NOT EXISTS idx_parse_records_option_hash
ON parse_records(option_hash);

CREATE INDEX IF NOT EXISTS idx_conversion_tasks_option_hash
ON conversion_tasks(option_hash);

CREATE INDEX IF NOT EXISTS idx_document_assets_document_id
ON document_assets(document_id);

CREATE INDEX IF NOT EXISTS idx_document_assets_parse_record_id
ON document_assets(parse_record_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_assets_parse_asset_name
ON document_assets(parse_record_id, asset_name)
WHERE parse_record_id IS NOT NULL;
