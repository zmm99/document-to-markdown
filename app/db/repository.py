from datetime import datetime, timezone
from sqlite3 import Connection, Row
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row: Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_document(conn: Connection, document_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ?",
        (document_id,),
    ).fetchone()
    return row_to_dict(row)


def get_success_parse_by_md5_and_format(
    conn: Connection,
    md5: str,
    file_format: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            d.*,
            p.id AS parse_record_id,
            p.engine,
            p.engine_version,
            p.status,
            p.output_dir,
            p.markdown_path,
            p.metadata_path
        FROM documents d
        JOIN parse_records p ON p.document_id = d.id
        WHERE d.md5 = ?
          AND d.file_format = ?
          AND p.status = 'success'
        ORDER BY p.id DESC
        LIMIT 1
        """,
        (md5, file_format),
    ).fetchone()
    return row_to_dict(row)


def upsert_document(conn: Connection, document: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO documents (
            id,
            md5,
            original_filename,
            file_format,
            mime_type,
            file_size,
            storage_date,
            upload_path,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            original_filename = excluded.original_filename,
            file_format = excluded.file_format,
            mime_type = excluded.mime_type,
            file_size = excluded.file_size,
            storage_date = excluded.storage_date,
            upload_path = excluded.upload_path,
            updated_at = excluded.updated_at
        """,
        (
            document["id"],
            document["md5"],
            document["original_filename"],
            document["file_format"],
            document.get("mime_type"),
            document["file_size"],
            document["storage_date"],
            document["upload_path"],
            document.get("created_at", now),
            document.get("updated_at", now),
        ),
    )


def insert_parse_record(conn: Connection, record: dict[str, Any]) -> int:
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO parse_records (
            document_id,
            file_format,
            engine,
            engine_version,
            status,
            output_dir,
            markdown_path,
            metadata_path,
            error_code,
            error_message,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["document_id"],
            record["file_format"],
            record["engine"],
            record.get("engine_version"),
            record["status"],
            record.get("output_dir"),
            record.get("markdown_path"),
            record.get("metadata_path"),
            record.get("error_code"),
            record.get("error_message"),
            record.get("created_at", now),
            record.get("updated_at", now),
        ),
    )
    return int(cursor.lastrowid)


def replace_document_assets(
    conn: Connection,
    document_id: str,
    assets: list[dict[str, Any]],
) -> None:
    conn.execute("DELETE FROM document_assets WHERE document_id = ?", (document_id,))
    now = utc_now()
    conn.executemany(
        """
        INSERT INTO document_assets (
            document_id,
            asset_name,
            content_type,
            asset_path,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                document_id,
                asset["asset_name"],
                asset.get("content_type"),
                asset["asset_path"],
                asset.get("created_at", now),
            )
            for asset in assets
        ],
    )


def list_document_assets(conn: Connection, document_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM document_assets WHERE document_id = ? ORDER BY id",
        (document_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_parse_output_dirs(conn: Connection, document_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT output_dir
        FROM parse_records
        WHERE document_id = ?
          AND output_dir IS NOT NULL
          AND output_dir != ''
        """,
        (document_id,),
    ).fetchall()
    return [str(row["output_dir"]) for row in rows]


def delete_parse_cache_records(conn: Connection, document_id: str) -> dict[str, int]:
    assets_deleted = conn.execute(
        "DELETE FROM document_assets WHERE document_id = ?",
        (document_id,),
    ).rowcount
    parse_records_deleted = conn.execute(
        "DELETE FROM parse_records WHERE document_id = ?",
        (document_id,),
    ).rowcount

    return {
        "assets": int(assets_deleted),
        "parse_records": int(parse_records_deleted),
    }
