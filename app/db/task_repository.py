from sqlite3 import Connection
from typing import Any

from app.db.repository import beijing_now, row_to_dict


TASK_STATUSES = {"queued", "running", "success", "failed", "timeout", "cancelled"}


def normalize_task(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    normalized = dict(row)
    normalized["cached"] = bool(normalized.get("cached"))
    return normalized


def insert_conversion_task(conn: Connection, task: dict[str, Any]) -> None:
    now = beijing_now()
    conn.execute(
        """
        INSERT INTO conversion_tasks (
            task_id,
            file_id,
            original_filename,
            file_format,
            status,
            progress,
            stage,
            message,
            error_code,
            error_message,
            cached,
            created_at,
            started_at,
            finished_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task["task_id"],
            task.get("file_id"),
            task["original_filename"],
            task["file_format"],
            task.get("status", "queued"),
            task.get("progress", 0),
            task.get("stage", "created"),
            task.get("message", ""),
            task.get("error_code"),
            task.get("error_message"),
            1 if task.get("cached") else 0,
            task.get("created_at", now),
            task.get("started_at"),
            task.get("finished_at"),
            task.get("updated_at", now),
        ),
    )


def get_conversion_task(conn: Connection, task_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM conversion_tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    return normalize_task(row_to_dict(row))


def update_conversion_task(
    conn: Connection,
    task_id: str,
    updates: dict[str, Any],
) -> int:
    allowed_fields = {
        "file_id",
        "status",
        "progress",
        "stage",
        "message",
        "error_code",
        "error_message",
        "cached",
        "started_at",
        "finished_at",
    }
    filtered = {key: value for key, value in updates.items() if key in allowed_fields}
    if not filtered:
        return 0

    if "cached" in filtered:
        filtered["cached"] = 1 if filtered["cached"] else 0

    filtered["updated_at"] = beijing_now()
    assignments = ", ".join(f"{key} = ?" for key in filtered)
    cursor = conn.execute(
        f"UPDATE conversion_tasks SET {assignments} WHERE task_id = ?",
        (*filtered.values(), task_id),
    )
    return int(cursor.rowcount)


def count_conversion_tasks(
    conn: Connection,
    status: str | None = None,
    keyword: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> int:
    filters: list[str] = []
    params: list[Any] = []

    if status is not None:
        filters.append("status = ?")
        params.append(status)
    if keyword:
        filters.append("(original_filename LIKE ? OR task_id LIKE ? OR file_id LIKE ?)")
        like_value = f"%{keyword}%"
        params.extend([like_value, like_value, like_value])
    if start_time:
        filters.append("created_at >= ?")
        params.append(start_time)
    if end_time:
        filters.append("created_at <= ?")
        params.append(end_time)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    row = conn.execute(
        f"SELECT COUNT(*) AS total FROM conversion_tasks {where}",
        params,
    ).fetchone()
    return int(row["total"])


def mark_task_running(conn: Connection, task_id: str) -> bool:
    now = beijing_now()
    cursor = conn.execute(
        """
        UPDATE conversion_tasks
        SET status = 'running',
            progress = 20,
            stage = 'validating',
            message = 'file validation completed',
            started_at = COALESCE(started_at, ?),
            updated_at = ?
        WHERE task_id = ?
          AND status = 'queued'
        """,
        (now, now, task_id),
    )
    return int(cursor.rowcount) == 1


def cancel_queued_task(conn: Connection, task_id: str) -> bool:
    now = beijing_now()
    cursor = conn.execute(
        """
        UPDATE conversion_tasks
        SET status = 'cancelled',
            progress = 100,
            stage = 'cancelled',
            message = 'task was cancelled',
            finished_at = COALESCE(finished_at, ?),
            updated_at = ?
        WHERE task_id = ?
          AND status = 'queued'
        """,
        (now, now, task_id),
    )
    return int(cursor.rowcount) == 1


def mark_unfinished_tasks_failed(
    conn: Connection,
    message: str = "task was interrupted by service restart",
) -> int:
    now = beijing_now()
    cursor = conn.execute(
        """
        UPDATE conversion_tasks
        SET status = 'failed',
            progress = 100,
            stage = 'interrupted',
            message = ?,
            error_code = 'service_restarted',
            error_message = ?,
            finished_at = COALESCE(finished_at, ?),
            updated_at = ?
        WHERE status IN ('queued', 'running')
        """,
        (message, message, now, now),
    )
    return int(cursor.rowcount)


def list_conversion_tasks(
    conn: Connection,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    keyword: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    filters: list[str] = []
    if status is not None:
        filters.append("status = ?")
        params.append(status)
    if keyword:
        filters.append("(original_filename LIKE ? OR task_id LIKE ? OR file_id LIKE ?)")
        like_value = f"%{keyword}%"
        params.extend([like_value, like_value, like_value])
    if start_time:
        filters.append("created_at >= ?")
        params.append(start_time)
    if end_time:
        filters.append("created_at <= ?")
        params.append(end_time)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM conversion_tasks
        {where}
        ORDER BY created_at DESC, task_id DESC
        LIMIT ?
        OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    return [normalize_task(dict(row)) for row in rows]


def delete_conversion_task(conn: Connection, task_id: str) -> int:
    cursor = conn.execute(
        "DELETE FROM conversion_tasks WHERE task_id = ?",
        (task_id,),
    )
    return int(cursor.rowcount)


def get_active_task_for_document(conn: Connection, document_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM conversion_tasks
        WHERE file_id = ?
          AND status IN ('queued', 'running')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id,),
    ).fetchone()
    return normalize_task(row_to_dict(row))
