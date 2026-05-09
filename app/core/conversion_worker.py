from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from app.converters.base import ConversionError, ConvertResult
from app.converters.registry import get_converter


def serialize_result(result: ConvertResult) -> dict[str, Any]:
    return {
        "markdown": result.markdown,
        "metadata": result.metadata,
        "warnings": result.warnings,
        "assets": [
            {
                "name": asset.name,
                "content_type": asset.content_type,
                "path": str(asset.path),
            }
            for asset in result.assets
        ],
    }


def write_payload(result_path: Path, payload: dict[str, Any]) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run(file_format: str, input_path: Path, output_dir: Path, result_path: Path) -> int:
    try:
        converter = get_converter(file_format)
        result = converter.convert(input_path, output_dir)
        write_payload(result_path, {"status": "success", "result": serialize_result(result)})
        return 0
    except ConversionError as exc:
        write_payload(
            result_path,
            {
                "status": "conversion_error",
                "error_code": exc.error_code,
                "message": exc.message,
            },
        )
        return 0
    except BaseException:
        write_payload(
            result_path,
            {
                "status": "conversion_error",
                "error_code": "convert_failed",
                "message": "document conversion failed",
            },
        )
        return 0


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        return 2
    _, file_format, input_path, output_dir, result_path = argv
    return run(file_format, Path(input_path), Path(output_dir), Path(result_path))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
