from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4

from app.config import settings
from app.converters.base import ConversionError, ConvertAsset, ConvertResult
from app.core.conversion_options import ConversionOptions


_conversion_semaphore: asyncio.Semaphore | None = None
_conversion_semaphore_size: int | None = None


def _deserialize_result(data: dict[str, Any]) -> ConvertResult:
    return ConvertResult(
        markdown=data["markdown"],
        metadata=data["metadata"],
        warnings=data.get("warnings", []),
        assets=[
            ConvertAsset(
                name=asset["name"],
                content_type=asset.get("content_type"),
                path=Path(asset["path"]),
            )
            for asset in data.get("assets", [])
        ],
    )


def _run_converter_in_subprocess(
    file_format: str,
    input_path: Path,
    output_dir: Path,
    options: ConversionOptions | None,
    layout_engine: str | None,
    timeout_seconds: int,
) -> ConvertResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f".conversion-result-{uuid4().hex}.json"
    command = [
        sys.executable,
        "-m",
        "app.core.conversion_worker",
        file_format,
        str(input_path),
        str(output_dir),
        str(result_path),
    ]
    if options is not None or layout_engine is not None:
        command.append(options.to_json() if options is not None else "")
    if layout_engine is not None:
        command.append(layout_engine)

    try:
        subprocess.run(
            command,
            cwd=Path.cwd(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result_path.unlink(missing_ok=True)
        raise ConversionError("convert_timeout", "文档转换超时") from exc

    if not result_path.exists():
        raise ConversionError("convert_failed", "文档转换失败")

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConversionError("convert_failed", "文档转换失败") from exc
    finally:
        result_path.unlink(missing_ok=True)

    if payload["status"] == "success":
        return _deserialize_result(payload["result"])

    raise ConversionError(payload["error_code"], payload["message"])


def _get_conversion_semaphore() -> asyncio.Semaphore:
    global _conversion_semaphore, _conversion_semaphore_size
    size = settings.max_concurrent_conversions
    if _conversion_semaphore is None or _conversion_semaphore_size != size:
        _conversion_semaphore = asyncio.Semaphore(size)
        _conversion_semaphore_size = size
    return _conversion_semaphore


async def run_converter_with_timeout(
    file_format: str,
    input_path: Path,
    output_dir: Path,
    options: ConversionOptions | None = None,
    layout_engine: str | None = None,
) -> ConvertResult:
    semaphore = _get_conversion_semaphore()
    async with semaphore:
        return await asyncio.to_thread(
            _run_converter_in_subprocess,
            file_format,
            input_path,
            output_dir,
            options,
            layout_engine,
            settings.convert_timeout_seconds,
        )
