from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.auth import require_admin_session
from app.core.datetime_utils import normalize_date_range
from app.core.document_operations import (
    get_usable_cached_conversion,
    is_parse_cache_usable,
    success_response,
    stored_upload_from_document,
)
from app.core.file_utils import (
    FileValidationError,
    validate_filename_and_format,
    validate_task_id,
)
from app.core.id_generator import generate_file_id
from app.core.storage import storage_manager
from app.core.task_queue import task_queue
from app.core.uploads import save_upload_to_temp
from app.db.database import get_connection
from app.db.repository import (
    beijing_now,
    get_document_by_md5_and_format,
    get_latest_success_parse,
    list_document_assets,
    upsert_document,
)
from app.db.task_repository import get_conversion_task, insert_conversion_task
from app.db.task_repository import (
    cancel_queued_task,
    count_conversion_tasks,
    delete_conversion_task,
    list_conversion_tasks,
    update_conversion_task,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


def raise_api_error(status_code: int, error_code: str, message: str) -> None:
    response_status = "unsupported" if error_code == "unsupported_file_format" else "failed"
    raise HTTPException(
        status_code=status_code,
        detail={
            "status": response_status,
            "error_code": error_code,
            "message": message,
        },
    )


def handle_validation_error(exc: FileValidationError) -> None:
    raise_api_error(status.HTTP_400_BAD_REQUEST, exc.error_code, exc.message)


def task_url(task_id: str) -> str:
    return f"{settings.api_prefix}/tasks/{task_id}"


def get_success_result(file_id: str | None, cached: bool | None = None) -> dict[str, Any] | None:
    if not file_id:
        return None

    with get_connection() as conn:
        parse_record = get_latest_success_parse(conn, file_id)
        if parse_record is None:
            return None
        assets = list_document_assets(conn, file_id)
        if not is_parse_cache_usable(parse_record, assets):
            return None
        return success_response(
            file_id,
            parse_record["file_format"],
            parse_record,
            assets,
            cached=cached,
        )


def task_response(task: dict[str, Any]) -> dict[str, Any]:
    file_id = task.get("file_id")
    response: dict[str, Any] = {
        "task_id": task["task_id"],
        "status": task["status"],
        "progress": task["progress"],
        "stage": task["stage"],
        "message": task["message"],
        "file_id": file_id,
        "original_filename": task["original_filename"],
        "file_format": task["file_format"],
        "cached": bool(task.get("cached")),
        "status_url": task_url(task["task_id"]),
        "document_url": f"{settings.api_prefix}/documents/{file_id}" if file_id else None,
        "markdown_url": f"{settings.api_prefix}/documents/{file_id}/markdown" if file_id else None,
        "download_url": f"{settings.api_prefix}/documents/{file_id}/download" if file_id else None,
        "error_code": task.get("error_code"),
        "error_message": task.get("error_message"),
        "created_at": task.get("created_at"),
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "updated_at": task.get("updated_at"),
        "result": None,
    }

    if task["status"] == "success":
        response["result"] = get_success_result(file_id, cached=bool(task.get("cached")))

    return response


def create_success_task(
    original_filename: str,
    file_format: str,
    document_id: str,
    cached: bool,
) -> dict[str, Any]:
    task_id = generate_file_id()
    now = beijing_now()
    with get_connection() as conn:
        insert_conversion_task(
            conn,
            {
                "task_id": task_id,
                "file_id": document_id,
                "original_filename": original_filename,
                "file_format": file_format,
                "status": "success",
                "progress": 100,
                "stage": "completed",
                "message": "document conversion completed from cache",
                "cached": cached,
                "started_at": now,
                "finished_at": now,
            },
        )
        conn.commit()
        task = get_conversion_task(conn, task_id)
    return task


def create_queued_task_for_document(
    file_id: str,
    original_filename: str,
    file_format: str,
    message: str = "task is waiting for conversion",
) -> dict[str, Any]:
    task_id = generate_file_id()
    with get_connection() as conn:
        insert_conversion_task(
            conn,
            {
                "task_id": task_id,
                "file_id": file_id,
                "original_filename": original_filename,
                "file_format": file_format,
                "status": "queued",
                "progress": 10,
                "stage": "queued",
                "message": message,
                "cached": False,
            },
        )
        conn.commit()
        task = get_conversion_task(conn, task_id)
    return task


@router.post("/convert")
async def create_conversion_task(file: UploadFile | None = File(default=None)) -> JSONResponse:
    if file is None:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "empty_file", "file is required")

    temp_path: Path | None = None
    try:
        original_filename, _, file_format = validate_filename_and_format(file.filename)
        temp_path, md5_value, file_size = await save_upload_to_temp(file)
    except FileValidationError as exc:
        handle_validation_error(exc)

    cached = get_usable_cached_conversion(md5_value, file_format)
    if cached is not None:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        task = create_success_task(
            original_filename,
            cached.file_format,
            cached.document_id,
            cached=True,
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=task_response(task))

    with get_connection() as conn:
        existing_document = get_document_by_md5_and_format(conn, md5_value, file_format)

    try:
        document_id = existing_document["id"] if existing_document is not None else generate_file_id()
        stored = storage_manager.promote_upload_file(
            temp_path,
            original_filename,
            md5_value,
            document_id,
            file_size,
        )
        temp_path = None
    except FileValidationError as exc:
        handle_validation_error(exc)
    except OSError:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "upload_save_failed",
            "failed to save uploaded file",
        )

    task_id = generate_file_id()
    with get_connection() as conn:
        upsert_document(
            conn,
            {
                "id": stored.file_id,
                "md5": stored.md5,
                "original_filename": stored.original_filename,
                "file_format": stored.file_format,
                "mime_type": file.content_type,
                "file_size": stored.file_size,
                "storage_date": stored.storage_date,
                "upload_path": storage_manager.relative_to_data_dir(stored.upload_path),
            },
        )
        insert_conversion_task(
            conn,
            {
                "task_id": task_id,
                "file_id": stored.file_id,
                "original_filename": stored.original_filename,
                "file_format": stored.file_format,
                "status": "queued",
                "progress": 10,
                "stage": "queued",
                "message": "task is waiting for conversion",
                "cached": False,
            },
        )
        conn.commit()
        task = get_conversion_task(conn, task_id)

    await task_queue.enqueue(task_id)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=task_response(task))


@router.get("")
def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _session: dict[str, Any] = Depends(require_admin_session),
) -> dict[str, Any]:
    try:
        start_time, end_time = normalize_date_range(start_date, end_date)
    except ValueError:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_date_range",
            "date range is invalid",
        )

    with get_connection() as conn:
        total = count_conversion_tasks(
            conn,
            status=status_filter,
            keyword=q,
            start_time=start_time,
            end_time=end_time,
        )
        tasks = list_conversion_tasks(
            conn,
            limit=limit,
            offset=offset,
            status=status_filter,
            keyword=q,
            start_time=start_time,
            end_time=end_time,
        )

    return {
        "items": [task_response(task) for task in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    try:
        safe_task_id = validate_task_id(task_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        task = get_conversion_task(conn, safe_task_id)

    if task is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "task_not_found", "task not found")

    return task_response(task)


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: str,
    _session: dict[str, Any] = Depends(require_admin_session),
) -> dict[str, Any]:
    try:
        safe_task_id = validate_task_id(task_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        task = get_conversion_task(conn, safe_task_id)
        if task is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "task_not_found", "task not found")
        if task["status"] != "queued":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "task_not_cancellable",
                "only queued tasks can be cancelled",
            )
        cancel_queued_task(conn, safe_task_id)
        conn.commit()
        cancelled = get_conversion_task(conn, safe_task_id)

    return task_response(cancelled)


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: str,
    _session: dict[str, Any] = Depends(require_admin_session),
) -> JSONResponse:
    try:
        safe_task_id = validate_task_id(task_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        task = get_conversion_task(conn, safe_task_id)
    if task is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "task_not_found", "task not found")
    if task["status"] in {"queued", "running"}:
        raise_api_error(
            status.HTTP_409_CONFLICT,
            "task_not_retryable",
            "queued or running tasks cannot be retried",
        )

    stored = stored_upload_from_document(task.get("file_id"))
    if stored is None or not stored.upload_path.exists():
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "upload_not_found",
            "uploaded file not found",
        )

    new_task = create_queued_task_for_document(
        stored.file_id,
        stored.original_filename,
        stored.file_format,
        message="retry task is waiting for conversion",
    )
    await task_queue.enqueue(new_task["task_id"])
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=task_response(new_task))


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    _session: dict[str, Any] = Depends(require_admin_session),
) -> dict[str, Any]:
    try:
        safe_task_id = validate_task_id(task_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        task = get_conversion_task(conn, safe_task_id)
        if task is None:
            raise_api_error(status.HTTP_404_NOT_FOUND, "task_not_found", "task not found")
        if task["status"] == "running":
            raise_api_error(
                status.HTTP_409_CONFLICT,
                "task_is_running",
                "running task cannot be deleted",
            )
        if task["status"] == "queued":
            update_conversion_task(
                conn,
                safe_task_id,
                {
                    "status": "cancelled",
                    "progress": 100,
                    "stage": "cancelled",
                    "message": "task was cancelled before deletion",
                    "finished_at": beijing_now(),
                },
            )
        deleted = delete_conversion_task(conn, safe_task_id)
        conn.commit()

    return {
        "status": "success",
        "deleted_task_id": safe_task_id,
        "deleted_tasks": deleted,
    }
