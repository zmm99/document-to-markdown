from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from app.converters.base import ConversionError, ConvertResult
from app.converters.registry import get_converter
from app.core.conversion_options import conversion_options_from_json


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


def run(
    file_format: str,
    input_path: Path,
    output_dir: Path,
    result_path: Path,
    options_json: str | None = None,
    layout_engine: str | None = None,
) -> int:
    try:
        options = conversion_options_from_json(options_json)
        target_layout_engine = layout_engine or (
            "ppstructure" if options.layout_engine == "ppstructure" else None
        )
        converter = get_converter(file_format, target_layout_engine)
        result = converter.convert(input_path, output_dir, options)
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
                "message": "文档转换失败",
            },
        )
        return 0


def main(argv: list[str]) -> int:
    if len(argv) not in {5, 6, 7}:
        return 2
    _, file_format, input_path, output_dir, result_path, *rest = argv
    options_json = rest[0] if rest else None
    layout_engine = rest[1] if len(rest) > 1 else None
    return run(
        file_format,
        Path(input_path),
        Path(output_dir),
        Path(result_path),
        options_json or None,
        layout_engine or None,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
