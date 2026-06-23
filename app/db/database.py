import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import settings


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if not _column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def _table_sql(conn: sqlite3.Connection, table_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return str(row["sql"] if row is not None and row["sql"] is not None else "")


def _migrate_document_assets_schema(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "document_assets").lower().replace(" ", "")
    has_parse_record_id = _column_exists(conn, "document_assets", "parse_record_id")
    has_legacy_unique = "unique(document_id,asset_name)" in sql
    if has_parse_record_id and not has_legacy_unique:
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_assets_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            parse_record_id INTEGER,
            asset_name TEXT NOT NULL,
            content_type TEXT,
            asset_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id),
            FOREIGN KEY(parse_record_id) REFERENCES parse_records(id)
        )
        """
    )
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(document_assets)")}
    parse_record_select = "parse_record_id" if "parse_record_id" in existing_columns else "NULL"
    conn.execute(
        f"""
        INSERT INTO document_assets_new (
            id,
            document_id,
            parse_record_id,
            asset_name,
            content_type,
            asset_path,
            created_at
        )
        SELECT
            id,
            document_id,
            {parse_record_select},
            asset_name,
            content_type,
            asset_path,
            created_at
        FROM document_assets
        """
    )
    conn.execute("DROP TABLE document_assets")
    conn.execute("ALTER TABLE document_assets_new RENAME TO document_assets")


def run_schema_migrations(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(conn, "parse_records", "option_hash", "TEXT")
    _add_column_if_missing(conn, "parse_records", "options_json", "TEXT")
    _add_column_if_missing(conn, "conversion_tasks", "option_hash", "TEXT")
    _add_column_if_missing(conn, "conversion_tasks", "options_json", "TEXT")
    _migrate_document_assets_schema(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_parse_records_option_hash ON parse_records(option_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversion_tasks_option_hash ON conversion_tasks(option_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_assets_document_id ON document_assets(document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_assets_parse_record_id ON document_assets(parse_record_id)"
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_document_assets_parse_asset_name
        ON document_assets(parse_record_id, asset_name)
        WHERE parse_record_id IS NOT NULL
        """
    )


def init_db(db_path: Path | None = None) -> None:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        run_schema_migrations(conn)
        conn.commit()


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
