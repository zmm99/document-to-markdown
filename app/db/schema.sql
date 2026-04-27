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
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS document_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    asset_name TEXT NOT NULL,
    content_type TEXT,
    asset_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, asset_name),
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
