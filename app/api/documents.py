from io import BytesIO
import hashlib
import json
import mimetypes
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse

from app.config import settings
from app.converters.base import ConversionError, write_convert_result
from app.converters.registry import get_converter
from app.core.auth import require_admin_session
from app.core.conversion_runner import run_converter_with_timeout
from app.core.datetime_utils import normalize_date_range
from app.core.document_operations import stored_upload_from_document
from app.core.file_utils import (
    FileValidationError,
    validate_asset_name,
    validate_file_id,
    validate_file_size,
    validate_filename_and_format,
)
from app.core.id_generator import generate_file_id
from app.core.storage import storage_manager
from app.core.task_queue import task_queue
from app.db.database import get_connection
from app.db.repository import (
    count_documents,
    delete_document_records,
    delete_parse_cache_records,
    get_document_asset,
    get_document,
    get_document_by_md5_and_format,
    get_latest_parse_record,
    get_latest_success_parse,
    get_success_parse_by_md5_and_format,
    insert_parse_record,
    list_document_assets,
    list_documents,
    list_parse_output_dirs,
    replace_document_assets,
    upsert_document,
)
from app.db.task_repository import (
    get_active_task_for_document,
    get_conversion_task,
    insert_conversion_task,
)


router = APIRouter(prefix="/documents", tags=["documents"])
UPLOAD_CHUNK_SIZE = 1024 * 1024


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


def document_url(document_id: str, suffix: str) -> str:
    return f"{settings.api_prefix}/documents/{document_id}/{suffix}"


def handle_validation_error(exc: FileValidationError) -> None:
    raise_api_error(status.HTTP_400_BAD_REQUEST, exc.error_code, exc.message)


async def save_upload_to_temp(file: UploadFile) -> tuple[Path, str, int]:
    temp_path = storage_manager.create_temp_upload_path()
    digest = hashlib.md5()
    file_size = 0

    try:
        with temp_path.open("wb") as output:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > settings.max_upload_size_bytes:
                    raise FileValidationError("file_too_large", "file is too large")
                digest.update(chunk)
                output.write(chunk)

        validate_file_size(file_size, settings.max_upload_size_bytes)
        return temp_path, digest.hexdigest(), file_size
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def safe_resolve_data_path(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    try:
        return storage_manager.resolve_data_path(relative_path)
    except (TypeError, ValueError):
        return None


def read_metadata(metadata_path: str | None) -> tuple[dict[str, Any], list[str]]:
    path = safe_resolve_data_path(metadata_path)
    if path is None or not path.exists() or not path.is_file():
        return {}, ["metadata is unavailable"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}, ["metadata is unavailable"]

    warnings = data.pop("warnings", [])
    data.pop("assets", None)
    return data, warnings


def is_parse_cache_usable(
    parse_record: dict[str, Any],
    assets: list[dict[str, Any]],
) -> bool:
    markdown_path = safe_resolve_data_path(parse_record.get("markdown_path"))
    if markdown_path is None or not markdown_path.exists() or not markdown_path.is_file():
        return False

    metadata_path = safe_resolve_data_path(parse_record.get("metadata_path"))
    if metadata_path is None or not metadata_path.exists() or not metadata_path.is_file():
        return False
    try:
        json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False

    for asset in assets:
        asset_path = safe_resolve_data_path(asset.get("asset_path"))
        if asset_path is None or not asset_path.exists() or not asset_path.is_file():
            return False

    return True


def asset_response(document_id: str, asset: dict[str, Any]) -> dict[str, str | None]:
    asset_name = asset["asset_name"]
    return {
        "name": asset_name,
        "content_type": asset.get("content_type"),
        "url": document_url(document_id, f"assets/{asset_name}"),
    }


def success_response(
    document_id: str,
    file_format: str,
    parse_record: dict[str, Any],
    assets: list[dict[str, Any]],
    cached: bool | None = None,
) -> dict[str, Any]:
    metadata, warnings = read_metadata(parse_record.get("metadata_path"))
    response: dict[str, Any] = {
        "file_id": document_id,
        "status": "success",
        "file_format": file_format,
        "markdown_url": document_url(document_id, "markdown"),
        "download_url": document_url(document_id, "download"),
        "assets": [asset_response(document_id, asset) for asset in assets],
        "metadata": metadata,
        "warnings": warnings,
    }
    if cached is not None:
        response["cached"] = cached
    return response


def record_failed_parse(
    document_id: str,
    file_format: str,
    engine: str,
    output_dir: Path,
    error_code: str,
    message: str,
) -> None:
    with get_connection() as conn:
        insert_parse_record(
            conn,
            {
                "document_id": document_id,
                "file_format": file_format,
                "engine": engine,
                "status": "failed",
                "output_dir": storage_manager.relative_to_data_dir(output_dir),
                "error_code": error_code,
                "error_message": message,
            },
        )
        conn.commit()


def resolve_markdown_path(parse_record: dict[str, Any]) -> Path:
    markdown_path = parse_record.get("markdown_path")
    if not markdown_path:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "markdown_not_found",
            "markdown not found",
        )

    path = safe_resolve_data_path(markdown_path)
    if path is None or not path.exists() or not path.is_file():
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "markdown_not_found",
            "markdown not found",
        )
    return path


@router.post("/convert")
async def convert_document(file: UploadFile | None = File(default=None)) -> dict[str, Any]:
    if file is None:
        raise_api_error(status.HTTP_400_BAD_REQUEST, "empty_file", "file is required")

    temp_path: Path | None = None
    try:
        original_filename, _, file_format = validate_filename_and_format(file.filename)
        temp_path, md5_value, file_size = await save_upload_to_temp(file)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        existing_document = get_document_by_md5_and_format(conn, md5_value, file_format)
        cached_parse = get_success_parse_by_md5_and_format(conn, md5_value, file_format)
        if cached_parse is not None:
            cached_document_id = cached_parse["id"]
            assets = list_document_assets(conn, cached_document_id)
            if is_parse_cache_usable(cached_parse, assets):
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
                return success_response(
                    cached_document_id,
                    cached_parse["file_format"],
                    cached_parse,
                    assets,
                    cached=True,
                )

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
        conn.commit()

    converter = None
    try:
        converter = get_converter(stored.file_format)
        result = await run_converter_with_timeout(
            stored.file_format,
            stored.upload_path,
            stored.output_dir,
        )
        markdown_path, metadata_path = write_convert_result(result, stored.output_dir)

        asset_records = [
            {
                "asset_name": asset.name,
                "content_type": asset.content_type,
                "asset_path": storage_manager.relative_to_data_dir(
                    resolve_convert_asset_path(asset.path, stored.output_dir)
                ),
            }
            for asset in result.assets
        ]
    except ConversionError as exc:
        engine = converter.engine if converter is not None else "unknown"
        record_failed_parse(
            stored.file_id,
            stored.file_format,
            engine,
            stored.output_dir,
            exc.error_code,
            exc.message,
        )
        raise_api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, exc.error_code, exc.message)
    except Exception:
        engine = converter.engine if converter is not None else "unknown"
        record_failed_parse(
            stored.file_id,
            stored.file_format,
            engine,
            stored.output_dir,
            "convert_failed",
            "document conversion failed",
        )
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "convert_failed",
            "document conversion failed",
        )

    with get_connection() as conn:
        parse_record_id = insert_parse_record(
            conn,
            {
                "document_id": stored.file_id,
                "file_format": stored.file_format,
                "engine": converter.engine,
                "status": "success",
                "output_dir": storage_manager.relative_to_data_dir(stored.output_dir),
                "markdown_path": storage_manager.relative_to_data_dir(markdown_path),
                "metadata_path": storage_manager.relative_to_data_dir(metadata_path),
            },
        )
        replace_document_assets(conn, stored.file_id, asset_records)
        conn.commit()

    parse_record = {
        "id": parse_record_id,
        "document_id": stored.file_id,
        "file_format": stored.file_format,
        "status": "success",
        "markdown_path": storage_manager.relative_to_data_dir(markdown_path),
        "metadata_path": storage_manager.relative_to_data_dir(metadata_path),
    }
    return success_response(
        stored.file_id,
        stored.file_format,
        parse_record,
        asset_records,
        cached=False,
    )


def resolve_convert_asset_path(asset_path: Path, output_dir: Path) -> Path:
    if asset_path.is_absolute():
        return asset_path
    if asset_path.exists():
        return asset_path.resolve()
    return (output_dir / asset_path).resolve()


def document_summary_response(document: dict[str, Any]) -> dict[str, Any]:
    document_id = document["id"]
    parse_status = document.get("latest_parse_status") or "uploaded"
    has_success = parse_status == "success"
    return {
        "file_id": document_id,
        "original_filename": document["original_filename"],
        "file_format": document["file_format"],
        "mime_type": document.get("mime_type"),
        "file_size": document["file_size"],
        "storage_date": document["storage_date"],
        "status": parse_status,
        "asset_count": int(document.get("asset_count") or 0),
        "original_url": document_url(document_id, "original"),
        "markdown_url": document_url(document_id, "markdown") if has_success else None,
        "download_url": document_url(document_id, "download") if has_success else None,
        "error_code": document.get("latest_error_code"),
        "error_message": document.get("latest_error_message"),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
        "latest_parse_created_at": document.get("latest_parse_created_at"),
    }


def document_detail_fields(document: dict[str, Any]) -> dict[str, Any]:
    document_id = document["id"]
    return {
        "file_id": document_id,
        "original_filename": document["original_filename"],
        "file_format": document["file_format"],
        "mime_type": document.get("mime_type"),
        "file_size": document["file_size"],
        "storage_date": document["storage_date"],
        "original_url": document_url(document_id, "original"),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def parse_record_response(parse_record: dict[str, Any] | None) -> dict[str, Any] | None:
    if parse_record is None:
        return None
    return {
        "id": parse_record.get("id"),
        "file_format": parse_record.get("file_format"),
        "engine": parse_record.get("engine"),
        "engine_version": parse_record.get("engine_version"),
        "status": parse_record.get("status"),
        "error_code": parse_record.get("error_code"),
        "error_message": parse_record.get("error_message"),
        "created_at": parse_record.get("created_at"),
        "updated_at": parse_record.get("updated_at"),
    }


def create_queued_task_for_document(
    document: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    task_id = generate_file_id()
    with get_connection() as conn:
        insert_conversion_task(
            conn,
            {
                "task_id": task_id,
                "file_id": document["id"],
                "original_filename": document["original_filename"],
                "file_format": document["file_format"],
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


def queued_task_response(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "progress": task["progress"],
        "stage": task["stage"],
        "message": task["message"],
        "file_id": task.get("file_id"),
        "file_format": task["file_format"],
        "original_filename": task["original_filename"],
        "status_url": f"{settings.api_prefix}/tasks/{task['task_id']}",
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


def ensure_no_active_document_task(document_id: str) -> None:
    with get_connection() as conn:
        active_task = get_active_task_for_document(conn, document_id)

    if active_task is not None:
        raise_api_error(
            status.HTTP_409_CONFLICT,
            "document_has_active_task",
            "document has an active conversion task",
        )


def delete_document_cache_by_id(document_id: str) -> dict[str, Any]:
    ensure_no_active_document_task(document_id)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

        output_dirs = list_parse_output_dirs(conn, document_id)
        deleted_counts = delete_parse_cache_records(conn, document_id)
        conn.commit()

    deleted_output_dirs = 0
    warnings: list[str] = []
    for output_dir in output_dirs:
        try:
            if storage_manager.delete_output_dir(output_dir):
                deleted_output_dirs += 1
        except (OSError, ValueError):
            warnings.append("failed to delete one output directory")

    return {
        "file_id": document_id,
        "status": "success",
        "deleted_parse_records": deleted_counts["parse_records"],
        "deleted_assets": deleted_counts["assets"],
        "deleted_output_dirs": deleted_output_dirs,
        "warnings": warnings,
    }


@router.get("")
def list_document_files(
    q: str | None = Query(default=None),
    file_format: str | None = Query(default=None),
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
        total = count_documents(
            conn,
            keyword=q,
            file_format=file_format,
            start_time=start_time,
            end_time=end_time,
        )
        documents = list_documents(
            conn,
            limit=limit,
            offset=offset,
            keyword=q,
            file_format=file_format,
            start_time=start_time,
            end_time=end_time,
        )

    return {
        "items": [document_summary_response(document) for document in documents],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{file_id}")
def get_document_info(file_id: str) -> dict[str, Any]:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

        parse_record = get_latest_parse_record(conn, document_id)
        if parse_record is None:
            return {
                **document_detail_fields(document),
                "status": "uploaded",
                "markdown_url": None,
                "download_url": None,
                "assets": [],
                "metadata": {},
                "warnings": [],
                "parse_record": None,
            }

        if parse_record["status"] == "success":
            assets = list_document_assets(conn, document_id)
            if not is_parse_cache_usable(parse_record, assets):
                return {
                    **document_detail_fields(document),
                    "status": "failed",
                    "markdown_url": None,
                    "download_url": None,
                    "assets": [],
                    "metadata": {},
                    "warnings": [],
                    "error_code": "cache_invalid",
                    "message": "cached conversion result is invalid",
                    "parse_record": parse_record_response(parse_record),
                }
            response = success_response(document_id, document["file_format"], parse_record, assets)
            response.update(document_detail_fields(document))
            response["parse_record"] = parse_record_response(parse_record)
            return response

        return {
            **document_detail_fields(document),
            "status": "failed",
            "markdown_url": None,
            "download_url": None,
            "assets": [],
            "metadata": {},
            "warnings": [],
            "error_code": parse_record.get("error_code"),
            "message": parse_record.get("error_message"),
            "parse_record": parse_record_response(parse_record),
        }


@router.get("/{file_id}/markdown")
def get_document_markdown(file_id: str) -> Response:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )
        parse_record = get_latest_success_parse(conn, document_id)
        if parse_record is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "markdown_not_found",
                "markdown not found",
            )

    path = resolve_markdown_path(parse_record)
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/{file_id}/original")
def download_original_document(file_id: str) -> FileResponse:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

    path = safe_resolve_data_path(document.get("upload_path"))
    if path is None or not path.exists() or not path.is_file():
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "upload_not_found",
            "uploaded file not found",
        )

    media_type = document.get("mime_type") or mimetypes.guess_type(document["original_filename"])[0]
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=document["original_filename"],
    )


@router.get("/{file_id}/assets/{asset_name}")
def get_document_asset_file(file_id: str, asset_name: str) -> FileResponse:
    try:
        document_id = validate_file_id(file_id)
        safe_asset_name = validate_asset_name(asset_name)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

        asset = get_document_asset(conn, document_id, safe_asset_name)
        if asset is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "asset_not_found",
                "asset not found",
            )

    path = safe_resolve_data_path(asset.get("asset_path"))
    if path is None or not path.exists() or not path.is_file():
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "asset_not_found",
            "asset not found",
        )

    media_type = asset.get("content_type") or mimetypes.guess_type(path.name)[0]
    return FileResponse(path, media_type=media_type)


@router.get("/{file_id}/download")
def download_document(file_id: str) -> Response:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

        parse_record = get_latest_success_parse(conn, document_id)
        if parse_record is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "markdown_not_found",
                "markdown not found",
            )
        assets = list_document_assets(conn, document_id)

    markdown_path = resolve_markdown_path(parse_record)
    metadata_path = safe_resolve_data_path(parse_record.get("metadata_path"))
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(markdown_path, "result.md")
        if metadata_path is not None and metadata_path.exists() and metadata_path.is_file():
            zip_file.write(metadata_path, "metadata.json")
        for asset in assets:
            asset_path = safe_resolve_data_path(asset.get("asset_path"))
            if asset_path is not None and asset_path.exists() and asset_path.is_file():
                zip_file.write(asset_path, f"assets/{asset['asset_name']}")

    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{document_id}.zip"'},
    )


@router.post("/{file_id}/reconvert")
async def reconvert_document(
    file_id: str,
    _session: dict[str, Any] = Depends(require_admin_session),
) -> JSONResponse:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

    stored = stored_upload_from_document(document_id)
    if stored is None or not stored.upload_path.exists():
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "upload_not_found",
            "uploaded file not found",
        )

    cache_result = delete_document_cache_by_id(document_id)
    task = create_queued_task_for_document(
        document,
        message="reconvert task is waiting for conversion",
    )
    await task_queue.enqueue(task["task_id"])
    response = queued_task_response(task)
    response["cache"] = cache_result
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response)


@router.delete("/{file_id}/cache")
def delete_document_cache(
    file_id: str,
    _session: dict[str, Any] = Depends(require_admin_session),
) -> dict[str, Any]:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    return delete_document_cache_by_id(document_id)


@router.delete("/{file_id}")
def delete_document_file(
    file_id: str,
    _session: dict[str, Any] = Depends(require_admin_session),
) -> dict[str, Any]:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        handle_validation_error(exc)

    ensure_no_active_document_task(document_id)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

        upload_path = document.get("upload_path")
        output_dirs = list_parse_output_dirs(conn, document_id)
        deleted_counts = delete_document_records(conn, document_id)
        conn.commit()

    deleted_uploads = 0
    if upload_path:
        try:
            if storage_manager.delete_upload_file(upload_path):
                deleted_uploads = 1
        except (OSError, ValueError):
            deleted_uploads = 0

    deleted_output_dirs = 0
    warnings: list[str] = []
    for output_dir in output_dirs:
        try:
            if storage_manager.delete_output_dir(output_dir):
                deleted_output_dirs += 1
        except (OSError, ValueError):
            warnings.append("failed to delete one output directory")

    return {
        "file_id": document_id,
        "status": "success",
        "deleted_documents": deleted_counts["documents"],
        "deleted_parse_records": deleted_counts["parse_records"],
        "deleted_assets": deleted_counts["assets"],
        "detached_tasks": deleted_counts["detached_tasks"],
        "deleted_uploads": deleted_uploads,
        "deleted_output_dirs": deleted_output_dirs,
        "warnings": warnings,
    }
