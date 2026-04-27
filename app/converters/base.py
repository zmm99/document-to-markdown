from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Protocol


class ConversionError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass(frozen=True)
class ConvertAsset:
    name: str
    content_type: str | None
    path: Path


@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    metadata: dict
    assets: list[ConvertAsset] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Converter(Protocol):
    engine: str

    def convert(self, input_path: Path, output_dir: Path) -> ConvertResult:
        ...


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ConversionError("text_decode_failed", "failed to decode text file")


def escape_markdown_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def rows_to_markdown_table(rows: list[list[object]]) -> str:
    rows = [row for row in rows if any(cell is not None and str(cell) != "" for cell in row)]
    if not rows:
        return ""

    max_columns = max(len(row) for row in rows)
    padded_rows = [row + [""] * (max_columns - len(row)) for row in rows]

    header = [escape_markdown_cell(cell) for cell in padded_rows[0]]
    body = [[escape_markdown_cell(cell) for cell in row] for row in padded_rows[1:]]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * max_columns) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def write_convert_result(result: ConvertResult, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "result.md"
    metadata_path = output_dir / "metadata.json"

    markdown_path.write_text(result.markdown, encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                **result.metadata,
                "assets": [
                    {
                        "name": asset.name,
                        "content_type": asset.content_type,
                        "path": asset.path.as_posix(),
                    }
                    for asset in result.assets
                ],
                "warnings": result.warnings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return markdown_path, metadata_path
