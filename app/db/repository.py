from datetime import datetime, timedelta, timezone
from sqlite3 import Connection, Row
from typing import Any


BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


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


def get_document_by_md5_and_format(
    conn: Connection,
    md5: str,
    file_format: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE md5 = ?
          AND file_format = ?
        """,
        (md5, file_format),
    ).fetchone()
    return row_to_dict(row)


def list_documents(
    conn: Connection,
    limit: int = 50,
    offset: int = 0,
    keyword: str | None = None,
    file_format: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []

    if keyword:
        filters.append("d.original_filename LIKE ?")
        params.append(f"%{keyword}%")
    if file_format:
        filters.append("d.file_format = ?")
        params.append(file_format)
    if start_time:
        filters.append("d.created_at >= ?")
        params.append(start_time)
    if end_time:
        filters.append("d.created_at <= ?")
        params.append(end_time)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = conn.execute(
        f"""
        SELECT
            d.*,
            p.status AS latest_parse_status,
            p.error_code AS latest_error_code,
            p.error_message AS latest_error_message,
            p.created_at AS latest_parse_created_at,
            COUNT(a.id) AS asset_count
        FROM documents d
        LEFT JOIN parse_records p
          ON p.id = (
              SELECT id
              FROM parse_records
              WHERE document_id = d.id
              ORDER BY id DESC
              LIMIT 1
          )
        LEFT JOIN document_assets a ON a.document_id = d.id
        {where}
        GROUP BY d.id
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT ?
        OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]


def count_documents(
    conn: Connection,
    keyword: str | None = None,
    file_format: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> int:
    filters: list[str] = []
    params: list[Any] = []

    if keyword:
        filters.append("original_filename LIKE ?")
        params.append(f"%{keyword}%")
    if file_format:
        filters.append("file_format = ?")
        params.append(file_format)
    if start_time:
        filters.append("created_at >= ?")
        params.append(start_time)
    if end_time:
        filters.append("created_at <= ?")
        params.append(end_time)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    row = conn.execute(
        f"SELECT COUNT(*) AS total FROM documents {where}",
        params,
    ).fetchone()
    return int(row["total"])


def get_latest_parse_record(
    conn: Connection,
    document_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM parse_records
        WHERE document_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (document_id,),
    ).fetchone()
    return row_to_dict(row)


def get_latest_success_parse(
    conn: Connection,
    document_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM parse_records
        WHERE document_id = ?
          AND status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """,
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
    now = beijing_now()
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
        ON CONFLICT(md5, file_format) DO UPDATE SET
            original_filename = excluded.original_filename,
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
    now = beijing_now()
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
    now = beijing_now()
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


def get_document_asset(
    conn: Connection,
    document_id: str,
    asset_name: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM document_assets
        WHERE document_id = ?
          AND asset_name = ?
        """,
        (document_id, asset_name),
    ).fetchone()
    return row_to_dict(row)


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


def delete_document_records(conn: Connection, document_id: str) -> dict[str, int]:
    detached_tasks = conn.execute(
        "UPDATE conversion_tasks SET file_id = NULL WHERE file_id = ?",
        (document_id,),
    ).rowcount
    cache_counts = delete_parse_cache_records(conn, document_id)
    documents_deleted = conn.execute(
        "DELETE FROM documents WHERE id = ?",
        (document_id,),
    ).rowcount

    return {
        "documents": int(documents_deleted),
        "parse_records": cache_counts["parse_records"],
        "assets": cache_counts["assets"],
        "detached_tasks": int(detached_tasks),
    }
