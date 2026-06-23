from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.converters.base import ConversionError, ConvertResult, write_convert_result
from app.converters.registry import get_converter
from app.core.conversion_options import (
    ConversionOptions,
    legacy_option_hash,
    metadata_with_options,
    parse_conversion_options,
    stored_upload_for_options,
)
from app.core.conversion_runner import run_converter_with_timeout
from app.core.layout_router import LayoutDecision, decide_layout
from app.core.response_text import status_text, translate_warnings
from app.core.storage import StoredUpload, storage_manager
from app.db.database import get_connection
from app.db.repository import (
    get_document,
    get_success_parse_by_md5_format_and_option_hash,
    insert_parse_record,
    list_assets_for_parse_record,
    replace_parse_assets,
)


@dataclass(frozen=True)
class DocumentConversionResult:
    document_id: str
    file_format: str
    parse_record: dict[str, Any]
    assets: list[dict[str, Any]]
    cached: bool


def document_url(document_id: str, suffix: str) -> str:
    return f"{settings.api_prefix}/documents/{document_id}/{suffix}"


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
        return {}, ["元数据不可用"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}, ["元数据不可用"]

    warnings = data.pop("warnings", [])
    data.pop("assets", None)
    return data, translate_warnings(warnings)


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


def parse_record_option_hash(parse_record: dict[str, Any] | None) -> str | None:
    if not parse_record:
        return None
    return parse_record.get("option_hash")


def asset_url(document_id: str, asset_name: str, option_hash: str | None = None) -> str:
    url = document_url(document_id, f"assets/{asset_name}")
    if option_hash:
        return f"{url}?option_hash={option_hash}"
    return url


def asset_response(
    document_id: str,
    asset: dict[str, Any],
    option_hash: str | None = None,
) -> dict[str, str | None]:
    asset_name = asset["asset_name"]
    scoped_option_hash = option_hash if asset.get("parse_record_id") is not None else None
    return {
        "name": asset_name,
        "content_type": asset.get("content_type"),
        "url": asset_url(document_id, asset_name, scoped_option_hash),
    }


def success_response(
    document_id: str,
    file_format: str,
    parse_record: dict[str, Any],
    assets: list[dict[str, Any]],
    cached: bool | None = None,
) -> dict[str, Any]:
    metadata, warnings = read_metadata(parse_record.get("metadata_path"))
    option_hash = parse_record_option_hash(parse_record)
    response: dict[str, Any] = {
        "file_id": document_id,
        "status": "success",
        "status_text": status_text("success"),
        "file_format": file_format,
        "markdown_url": document_url(document_id, "markdown"),
        "download_url": document_url(document_id, "download"),
        "assets": [asset_response(document_id, asset, option_hash) for asset in assets],
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
    options: ConversionOptions | None = None,
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
                "option_hash": options.option_hash if options is not None else None,
                "options_json": options.to_json() if options is not None else None,
            },
        )
        conn.commit()


def resolve_convert_asset_path(asset_path: Path, output_dir: Path) -> Path:
    if asset_path.is_absolute():
        return asset_path
    if asset_path.exists():
        return asset_path.resolve()
    return (output_dir / asset_path).resolve()


def get_usable_cached_conversion(
    md5_value: str,
    file_format: str,
    options: ConversionOptions | None = None,
) -> DocumentConversionResult | None:
    resolved_options = options or parse_conversion_options()
    with get_connection() as conn:
        cached_parse = get_success_parse_by_md5_format_and_option_hash(
            conn,
            md5_value,
            file_format,
            resolved_options.option_hash,
            legacy_option_hash(),
        )
        if cached_parse is None:
            return None

        document_id = cached_parse["id"]
        assets = list_assets_for_parse_record(conn, document_id, cached_parse)
        if not is_parse_cache_usable(cached_parse, assets):
            return None

        return DocumentConversionResult(
            document_id=document_id,
            file_format=cached_parse["file_format"],
            parse_record=cached_parse,
            assets=assets,
            cached=True,
        )


def failed_engine_for_options(options: ConversionOptions) -> str:
    if options.layout_engine == "ppstructure":
        return "ppstructure"
    return "unknown"


def _merge_warnings(*warning_lists: list[str]) -> list[str]:
    warnings: list[str] = []
    for warning_list in warning_lists:
        for warning in warning_list:
            if warning not in warnings:
                warnings.append(warning)
    return warnings


def result_with_options(
    result: ConvertResult,
    options: ConversionOptions,
    decision: LayoutDecision | None = None,
) -> ConvertResult:
    actual_layout_engine = result.metadata.get("layout_engine", "docling")
    ocr_applied = bool(result.metadata.get("ocr_applied", False))
    reason = result.metadata.get("layout_reason")
    decision_warnings: list[str] = []
    if decision is not None:
        actual_layout_engine = decision.actual_layout_engine
        ocr_applied = decision.ocr_applied
        reason = decision.reason
        decision_warnings = decision.warnings

    return ConvertResult(
        markdown=result.markdown,
        metadata=metadata_with_options(
            result.metadata,
            options,
            actual_layout_engine=actual_layout_engine,
            ocr_applied=ocr_applied,
            reason=reason,
        ),
        assets=result.assets,
        warnings=_merge_warnings(result.warnings, decision_warnings),
    )


def result_with_asset_option_urls(
    result: ConvertResult,
    document_id: str,
    option_hash: str | None,
) -> ConvertResult:
    if not option_hash or not result.assets:
        return result

    markdown = result.markdown
    for asset in result.assets:
        markdown = markdown.replace(
            document_url(document_id, f"assets/{asset.name}"),
            asset_url(document_id, asset.name, option_hash),
        )

    return ConvertResult(
        markdown=markdown,
        metadata=result.metadata,
        assets=result.assets,
        warnings=result.warnings,
    )


async def convert_stored_document(
    stored: StoredUpload,
    options: ConversionOptions | None = None,
) -> DocumentConversionResult:
    resolved_options = options or parse_conversion_options()
    conversion_stored = stored_upload_for_options(stored, resolved_options)
    converter = None
    try:
        decision = decide_layout(
            conversion_stored.file_format,
            conversion_stored.upload_path,
            resolved_options,
        )
        converter = get_converter(conversion_stored.file_format, decision.actual_layout_engine)
        result = await run_converter_with_timeout(
            conversion_stored.file_format,
            conversion_stored.upload_path,
            conversion_stored.output_dir,
            resolved_options,
            decision.actual_layout_engine,
        )
        result = result_with_options(result, resolved_options, decision)
        result = result_with_asset_option_urls(
            result,
            conversion_stored.file_id,
            resolved_options.option_hash,
        )
        markdown_path, metadata_path = write_convert_result(result, conversion_stored.output_dir)
        asset_records = [
            {
                "asset_name": asset.name,
                "content_type": asset.content_type,
                "asset_path": storage_manager.relative_to_data_dir(
                    resolve_convert_asset_path(asset.path, conversion_stored.output_dir)
                ),
            }
            for asset in result.assets
        ]
    except ConversionError as exc:
        engine = converter.engine if converter is not None else failed_engine_for_options(resolved_options)
        record_failed_parse(
            conversion_stored.file_id,
            conversion_stored.file_format,
            engine,
            conversion_stored.output_dir,
            exc.error_code,
            exc.message,
            resolved_options,
        )
        raise
    except Exception as exc:
        engine = converter.engine if converter is not None else failed_engine_for_options(resolved_options)
        record_failed_parse(
            conversion_stored.file_id,
            conversion_stored.file_format,
            engine,
            conversion_stored.output_dir,
            "convert_failed",
            "文档转换失败",
            resolved_options,
        )
        raise ConversionError("convert_failed", "文档转换失败") from exc

    with get_connection() as conn:
        parse_record_id = insert_parse_record(
            conn,
            {
                "document_id": conversion_stored.file_id,
                "file_format": conversion_stored.file_format,
                "engine": converter.engine,
                "status": "success",
                "output_dir": storage_manager.relative_to_data_dir(conversion_stored.output_dir),
                "markdown_path": storage_manager.relative_to_data_dir(markdown_path),
                "metadata_path": storage_manager.relative_to_data_dir(metadata_path),
                "option_hash": resolved_options.option_hash,
                "options_json": resolved_options.to_json(),
            },
        )
        replace_parse_assets(conn, conversion_stored.file_id, parse_record_id, asset_records)
        conn.commit()

    for asset_record in asset_records:
        asset_record["parse_record_id"] = parse_record_id

    parse_record = {
        "id": parse_record_id,
        "document_id": conversion_stored.file_id,
        "file_format": conversion_stored.file_format,
        "status": "success",
        "markdown_path": storage_manager.relative_to_data_dir(markdown_path),
        "metadata_path": storage_manager.relative_to_data_dir(metadata_path),
        "option_hash": resolved_options.option_hash,
        "options_json": resolved_options.to_json(),
    }
    return DocumentConversionResult(
        document_id=conversion_stored.file_id,
        file_format=conversion_stored.file_format,
        parse_record=parse_record,
        assets=asset_records,
        cached=False,
    )


def stored_upload_from_document(document_id: str) -> StoredUpload | None:
    with get_connection() as conn:
        document = get_document(conn, document_id)

    if document is None:
        return None

    upload_path = safe_resolve_data_path(document.get("upload_path"))
    if upload_path is None:
        return None

    extension = Path(document["upload_path"]).suffix
    output_dir = storage_manager.outputs_dir / document["storage_date"] / document["id"]
    return StoredUpload(
        file_id=document["id"],
        md5=document["md5"],
        original_filename=document["original_filename"],
        extension=extension,
        file_format=document["file_format"],
        file_size=int(document["file_size"]),
        storage_date=document["storage_date"],
        upload_path=upload_path,
        output_dir=output_dir,
    )
